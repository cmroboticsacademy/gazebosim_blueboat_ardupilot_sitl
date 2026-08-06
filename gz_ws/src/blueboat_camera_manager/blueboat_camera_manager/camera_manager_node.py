#!/usr/bin/env python3
"""ROS 2 camera manager for BlueBoat Gazebo image streams."""

from __future__ import annotations

import json
import math
import time
from collections import deque
from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Deque, Iterable

import cv2
import numpy as np
from cv_bridge import CvBridge, CvBridgeError
from geometry_msgs.msg import TransformStamped
import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
    qos_profile_sensor_data,
)
from sensor_msgs.msg import CameraInfo, Image
from std_msgs.msg import Bool, Float64, String
from std_srvs.srv import Trigger
from tf2_ros import TransformBroadcaster

from blueboat_camera_manager.srv import (
    SetCameraConfig,
    SetCameraEnabled,
    SetCameraLag,
)


@dataclass(frozen=True)
class CameraEndpoint:
    name: str
    prefix: str
    source_width: int = 640
    source_height: int = 480
    horizontal_fov: float = 1.3962634

    @property
    def raw_topic(self) -> str:
        return f"{self.prefix}/image_raw"

    @property
    def image_topic(self) -> str:
        return f"{self.prefix}/image"

    @property
    def camera_info_topic(self) -> str:
        return f"{self.prefix}/camera_info"


@dataclass(frozen=True)
class CameraConfig:
    width: int
    height: int
    fps: float
    preserve_aspect: bool


@dataclass
class QueuedFrame:
    release_at: float
    image: Image
    camera_info: CameraInfo
    transform: TransformStamped | None


class BlueBoatCameraManager(Node):
    """Apply camera selection, resize, frame-rate, and lag in ROS 2."""

    BOATS = ("blueboat", "blueboat2", "blueboat3", "blueboat4")
    ENDPOINTS = {
        name: CameraEndpoint(name=name, prefix=f"/{name}/camera")
        for name in BOATS
    }
    ODOMETRY_TOPICS = {
        name: f"/model/{name}/odometry" for name in BOATS
    }
    CAMERA_OFFSET = (0.55, 0.0, 0.28)
    # SDF camera +X-forward frame to ROS optical +Z-forward, +X-right, +Y-down.
    CAMERA_OPTICAL_ROTATION = (-0.5, 0.5, -0.5, 0.5)

    def __init__(self) -> None:
        super().__init__("blueboat_camera_manager")

        self.declare_parameter("mode", 4)
        self.declare_parameter("startup_delay", 5.0)
        self.declare_parameter("startup_retries", 5)
        self.declare_parameter("startup_retry_period", 1.0)
        self.declare_parameter("default_width", 256)
        self.declare_parameter("default_height", 256)
        self.declare_parameter("default_fps", 16.0)
        self.declare_parameter("default_preserve_aspect", True)
        self.declare_parameter("default_lag_seconds", 0.0)
        self.declare_parameter("maximum_lag_seconds", 30.0)
        self.declare_parameter("maximum_buffer_mb_per_camera", 256.0)

        self.mode = int(self.get_parameter("mode").value)
        if self.mode not in (1, 2, 3, 4):
            raise ValueError("camera manager mode must be 1, 2, 3, or 4")

        self._maximum_lag = float(
            self.get_parameter("maximum_lag_seconds").value
        )
        if (
            not math.isfinite(self._maximum_lag)
            or self._maximum_lag <= 0.0
            or self._maximum_lag > 30.0
        ):
            raise ValueError(
                "maximum_lag_seconds must be finite, greater than zero, "
                "and no more than 30"
            )

        self._maximum_buffer_bytes = int(
            max(
                16.0,
                float(
                    self.get_parameter("maximum_buffer_mb_per_camera").value
                ),
            )
            * 1024
            * 1024
        )

        default_config = CameraConfig(
            width=int(self.get_parameter("default_width").value),
            height=int(self.get_parameter("default_height").value),
            fps=float(self.get_parameter("default_fps").value),
            preserve_aspect=bool(
                self.get_parameter("default_preserve_aspect").value
            ),
        )
        config_error = self._validate_config(default_config)
        if config_error:
            raise ValueError(f"invalid default camera config: {config_error}")

        default_lag = float(
            self.get_parameter("default_lag_seconds").value
        )
        lag_error = self._validate_lag(default_lag)
        if lag_error:
            raise ValueError(f"invalid default_lag_seconds: {lag_error}")
        memory_error = self._validate_buffer(default_config, default_lag)
        if memory_error:
            raise ValueError(f"invalid default camera buffer: {memory_error}")

        self._bridge = CvBridge()
        self._tf_broadcaster = TransformBroadcaster(self)
        self._configs = {name: default_config for name in self.BOATS}
        self._lags = {name: default_lag for name in self.BOATS}
        self._enabled = {name: False for name in self.BOATS}
        self._last_accepted = {name: -1.0 for name in self.BOATS}
        self._queues: dict[str, Deque[QueuedFrame]] = {
            name: deque() for name in self.BOATS
        }
        self._last_conversion_error = {name: 0.0 for name in self.BOATS}
        self._latest_transforms: dict[str, TransformStamped | None] = {
            name: None for name in self.BOATS
        }

        self._enable_publishers = {}
        self._config_publishers = {}
        self._lag_status_publishers = {}
        self._image_publishers = {}
        self._camera_info_publishers = {}
        self._raw_subscriptions = []
        self._lag_subscriptions = []
        self._odom_subscriptions = []

        for name, endpoint in self.ENDPOINTS.items():
            self._enable_publishers[name] = self.create_publisher(
                Bool, f"{endpoint.prefix}/enable_streaming", 10
            )
            self._config_publishers[name] = self.create_publisher(
                String, f"{endpoint.prefix}/stream_config", 10
            )
            self._lag_status_publishers[name] = self.create_publisher(
                Float64, f"{endpoint.prefix}/lag_status", 10
            )
            self._image_publishers[name] = self.create_publisher(
                Image, endpoint.image_topic, qos_profile_sensor_data
            )
            self._camera_info_publishers[name] = self.create_publisher(
                CameraInfo,
                endpoint.camera_info_topic,
                qos_profile_sensor_data,
            )
            self._raw_subscriptions.append(
                self.create_subscription(
                    Image,
                    endpoint.raw_topic,
                    lambda message, camera=name: self._on_raw_image(
                        camera, message
                    ),
                    qos_profile_sensor_data,
                )
            )
            self._lag_subscriptions.append(
                self.create_subscription(
                    Float64,
                    f"{endpoint.prefix}/lag",
                    lambda message, camera=name: self._on_lag_topic(
                        camera, message
                    ),
                    10,
                )
            )

            self._odom_subscriptions.append(
                self.create_subscription(
                    Odometry,
                    self.ODOMETRY_TOPICS[name],
                    lambda message, camera=name: self._on_odometry(
                        camera, message
                    ),
                    qos_profile_sensor_data,
                )
            )

        state_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self._state_publisher = self.create_publisher(
            String, "~/state", state_qos
        )

        self._set_config_service = self.create_service(
            SetCameraConfig, "~/set_config", self._on_set_config
        )
        self._set_enabled_service = self.create_service(
            SetCameraEnabled, "~/set_enabled", self._on_set_enabled
        )
        self._set_lag_service = self.create_service(
            SetCameraLag, "~/set_lag", self._on_set_lag
        )
        self._status_service = self.create_service(
            Trigger, "~/status", self._on_status
        )

        self._startup_delay = max(
            0.0, float(self.get_parameter("startup_delay").value)
        )
        self._startup_retries = max(
            1, int(self.get_parameter("startup_retries").value)
        )
        self._startup_retry_period = max(
            0.1,
            float(self.get_parameter("startup_retry_period").value),
        )
        self._startup_attempt = 0
        self._start_time = time.monotonic()
        self._startup_timer = self.create_timer(0.2, self._startup_tick)
        self._release_timer = self.create_timer(0.01, self._release_due_frames)
        self._state_timer = self.create_timer(1.0, self._publish_state)
        self._publish_state()

        self.get_logger().info(
            "Camera mode %d activates [%s]; default lag %.3f seconds"
            % (
                self.mode,
                ", ".join(self._active_camera_names()),
                default_lag,
            )
        )

    def _active_camera_names(self) -> tuple[str, ...]:
        return self.BOATS[: self.mode]

    @staticmethod
    def _dedupe(values: Iterable[str]) -> list[str]:
        return list(dict.fromkeys(values))

    def _resolve_names(
        self, requested: Iterable[str]
    ) -> tuple[list[str], str | None]:
        raw = [str(value).strip().lower() for value in requested]
        raw = [value for value in raw if value]
        if not raw:
            raw = ["all"]

        active = self._active_camera_names()
        expanded: list[str] = []
        for name in raw:
            if name in ("all", "boats", "all_boats"):
                expanded.extend(active)
            elif name not in self.ENDPOINTS:
                return [], f"unknown camera '{name}'"
            elif name not in active:
                return [], (
                    f"camera '{name}' is outside camera_mode:={self.mode}; "
                    f"active cameras are {', '.join(active)}"
                )
            else:
                expanded.append(name)
        return self._dedupe(expanded), None

    @staticmethod
    def _validate_config(config: CameraConfig) -> str | None:
        if (
            config.width < 16
            or config.height < 16
            or config.width % 2
            or config.height % 2
        ):
            return "width and height must be even integers of at least 16"
        if config.width > 1920 or config.height > 1080:
            return "requested output exceeds 1920x1080"
        if not math.isfinite(config.fps) or config.fps <= 0.0:
            return "fps must be finite and greater than zero"
        if config.fps > 60.0:
            return "fps must be no more than 60"
        return None

    def _validate_lag(self, lag_seconds: float) -> str | None:
        if not math.isfinite(lag_seconds):
            return "lag_seconds must be finite"
        if lag_seconds < 0.0:
            return "lag_seconds must be zero or greater"
        if lag_seconds > self._maximum_lag:
            return (
                f"lag_seconds must be no more than "
                f"{self._maximum_lag:g} seconds"
            )
        return None

    def _validate_buffer(
        self, config: CameraConfig, lag_seconds: float
    ) -> str | None:
        estimated = int(
            config.width
            * config.height
            * 3
            * config.fps
            * lag_seconds
        )
        if estimated > self._maximum_buffer_bytes:
            requested_mb = estimated / (1024 * 1024)
            maximum_mb = self._maximum_buffer_bytes / (1024 * 1024)
            return (
                f"estimated lag buffer is {requested_mb:.1f} MiB; "
                f"limit is {maximum_mb:.1f} MiB per camera. "
                "Reduce resolution, fps, or lag."
            )
        return None

    @staticmethod
    def _config_payload(config: CameraConfig) -> str:
        return (
            f"width={config.width};height={config.height};"
            f"fps={config.fps:.6g};"
            f"preserve_aspect="
            f"{'true' if config.preserve_aspect else 'false'}"
        )

    def _publish_control_config(self, name: str) -> None:
        message = String()
        message.data = self._config_payload(self._configs[name])
        self._config_publishers[name].publish(message)

    def _publish_enabled(self, names: Iterable[str], enabled: bool) -> None:
        message = Bool()
        message.data = enabled
        for name in names:
            self._enable_publishers[name].publish(message)
            self._enabled[name] = enabled
            self._last_accepted[name] = -1.0
            if not enabled:
                self._queues[name].clear()
        self._publish_state()

    def _publish_lag_status(self, name: str) -> None:
        status = Float64()
        status.data = self._lags[name]
        self._lag_status_publishers[name].publish(status)

    def _startup_tick(self) -> None:
        if time.monotonic() - self._start_time < self._startup_delay:
            return
        if self._startup_attempt >= self._startup_retries:
            self.destroy_timer(self._startup_timer)
            return

        active = self._active_camera_names()
        inactive = tuple(name for name in self.BOATS if name not in active)
        for name in self.BOATS:
            self._publish_control_config(name)
            self._publish_lag_status(name)
        self._publish_enabled(inactive, False)
        self._publish_enabled(active, True)

        self._startup_attempt += 1
        if self._startup_attempt == 1:
            self.get_logger().info(
                "Published initial camera configuration and enable commands"
            )
        if self._startup_attempt < self._startup_retries:
            self.destroy_timer(self._startup_timer)
            self._startup_timer = self.create_timer(
                self._startup_retry_period, self._startup_tick
            )
        else:
            self.destroy_timer(self._startup_timer)

    @staticmethod
    def _quaternion_multiply(left, right):
        lx, ly, lz, lw = left
        rx, ry, rz, rw = right
        return (
            lw * rx + lx * rw + ly * rz - lz * ry,
            lw * ry - lx * rz + ly * rw + lz * rx,
            lw * rz + lx * ry - ly * rx + lz * rw,
            lw * rw - lx * rx - ly * ry - lz * rz,
        )

    @staticmethod
    def _rotate_vector(quaternion, vector):
        qx, qy, qz, qw = quaternion
        vx, vy, vz = vector
        # Quaternion-vector rotation expanded to avoid another runtime package.
        tx = 2.0 * (qy * vz - qz * vy)
        ty = 2.0 * (qz * vx - qx * vz)
        tz = 2.0 * (qx * vy - qy * vx)
        return (
            vx + qw * tx + (qy * tz - qz * ty),
            vy + qw * ty + (qz * tx - qx * tz),
            vz + qw * tz + (qx * ty - qy * tx),
        )

    def _on_odometry(self, name: str, message: Odometry) -> None:
        if name not in self._active_camera_names():
            return
        orientation = message.pose.pose.orientation
        base_q = (
            float(orientation.x),
            float(orientation.y),
            float(orientation.z),
            float(orientation.w),
        )
        norm = math.sqrt(sum(value * value for value in base_q))
        if norm < 1e-9:
            return
        base_q = tuple(value / norm for value in base_q)
        offset = self._rotate_vector(base_q, self.CAMERA_OFFSET)
        optical_q = self._quaternion_multiply(
            base_q, self.CAMERA_OPTICAL_ROTATION
        )

        transform = TransformStamped()
        transform.header.stamp = message.header.stamp
        transform.header.frame_id = message.header.frame_id or "odom"
        transform.child_frame_id = f"{name}/camera_optical_frame"
        position = message.pose.pose.position
        transform.transform.translation.x = float(position.x) + offset[0]
        transform.transform.translation.y = float(position.y) + offset[1]
        transform.transform.translation.z = float(position.z) + offset[2]
        transform.transform.rotation.x = optical_q[0]
        transform.transform.rotation.y = optical_q[1]
        transform.transform.rotation.z = optical_q[2]
        transform.transform.rotation.w = optical_q[3]
        self._latest_transforms[name] = transform
        if self._lags[name] <= 0.0:
            self._tf_broadcaster.sendTransform(transform)

    @staticmethod
    def _shift_stamp(stamp, seconds: float):
        shifted = deepcopy(stamp)
        total_nanoseconds = (
            int(stamp.sec) * 1_000_000_000
            + int(stamp.nanosec)
            + int(round(seconds * 1_000_000_000))
        )
        shifted.sec, shifted.nanosec = divmod(total_nanoseconds, 1_000_000_000)
        return shifted

    def _on_raw_image(self, name: str, message: Image) -> None:
        if not self._enabled[name]:
            return

        now = time.monotonic()
        config = self._configs[name]
        period = 1.0 / config.fps
        last = self._last_accepted[name]
        if last >= 0.0 and now - last + 1e-9 < period:
            return
        self._last_accepted[name] = now

        try:
            source = self._bridge.imgmsg_to_cv2(
                message, desired_encoding="bgr8"
            )
            output = self._resize(source, config)
            processed = self._bridge.cv2_to_imgmsg(output, encoding="bgr8")
        except (CvBridgeError, cv2.error, ValueError) as error:
            if now - self._last_conversion_error[name] > 2.0:
                self.get_logger().error(
                    f"Failed to process {name} camera frame: {error}"
                )
                self._last_conversion_error[name] = now
            return

        processed.header.stamp = message.header.stamp
        processed.header.frame_id = f"{name}/camera_optical_frame"
        camera_info = self._make_camera_info(name, processed)
        lag = self._lags[name]
        if lag <= 0.0:
            self._image_publishers[name].publish(processed)
            self._camera_info_publishers[name].publish(camera_info)
            return

        delayed_stamp = self._shift_stamp(processed.header.stamp, lag)
        processed.header.stamp = delayed_stamp
        camera_info.header.stamp = delayed_stamp
        queued_transform = deepcopy(self._latest_transforms[name])
        if queued_transform is not None:
            queued_transform.header.stamp = delayed_stamp
        self._queues[name].append(
            QueuedFrame(
                release_at=now + lag,
                image=processed,
                camera_info=camera_info,
                transform=queued_transform,
            )
        )

    @staticmethod
    def _resize(source, config: CameraConfig):
        target = (config.width, config.height)
        if not config.preserve_aspect:
            return cv2.resize(source, target, interpolation=cv2.INTER_AREA)

        source_height, source_width = source.shape[:2]
        scale = min(
            config.width / source_width,
            config.height / source_height,
        )
        scaled_width = max(2, int(round(source_width * scale)))
        scaled_height = max(2, int(round(source_height * scale)))
        scaled = cv2.resize(
            source,
            (scaled_width, scaled_height),
            interpolation=cv2.INTER_AREA,
        )
        output = np.zeros((config.height, config.width, 3), dtype=source.dtype)
        x = (config.width - scaled_width) // 2
        y = (config.height - scaled_height) // 2
        output[y : y + scaled_height, x : x + scaled_width] = scaled
        return output

    def _make_camera_info(self, name: str, image: Image) -> CameraInfo:
        endpoint = self.ENDPOINTS[name]
        width = int(image.width)
        height = int(image.height)
        config = self._configs[name]
        source_fx = endpoint.source_width / (
            2.0 * math.tan(endpoint.horizontal_fov / 2.0)
        )
        if config.preserve_aspect:
            scale = min(
                width / endpoint.source_width,
                height / endpoint.source_height,
            )
            fx = source_fx * scale
            fy = source_fx * scale
        else:
            fx = source_fx * width / endpoint.source_width
            fy = source_fx * height / endpoint.source_height
        cx = (width - 1.0) / 2.0
        cy = (height - 1.0) / 2.0

        info = CameraInfo()
        info.header = image.header
        info.height = height
        info.width = width
        info.distortion_model = "plumb_bob"
        info.d = [0.0, 0.0, 0.0, 0.0, 0.0]
        info.k = [fx, 0.0, cx, 0.0, fy, cy, 0.0, 0.0, 1.0]
        info.r = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
        info.p = [fx, 0.0, cx, 0.0, 0.0, fy, cy, 0.0, 0.0, 0.0, 1.0, 0.0]
        return info

    def _release_due_frames(self) -> None:
        now = time.monotonic()
        for name in self._active_camera_names():
            queue = self._queues[name]
            while queue and queue[0].release_at <= now:
                frame = queue.popleft()
                if not self._enabled[name]:
                    continue

                # The queued transform retains the capture pose and is stamped
                # with capture time + configured lag. This keeps delayed Camera
                # messages transformable after the original TF cache entry ages out.
                if frame.transform is not None:
                    self._tf_broadcaster.sendTransform(frame.transform)

                self._image_publishers[name].publish(frame.image)
                self._camera_info_publishers[name].publish(frame.camera_info)

    def _on_set_config(self, request, response):
        names, error = self._resolve_names(request.cameras)
        if error:
            response.success = False
            response.message = error
            return response

        config = CameraConfig(
            width=int(request.width),
            height=int(request.height),
            fps=float(request.fps),
            preserve_aspect=bool(request.preserve_aspect),
        )
        validation = self._validate_config(config)
        if validation:
            response.success = False
            response.message = validation
            return response
        for name in names:
            memory_error = self._validate_buffer(config, self._lags[name])
            if memory_error:
                response.success = False
                response.message = f"{name}: {memory_error}"
                return response

        for name in names:
            self._configs[name] = config
            self._queues[name].clear()
            self._last_accepted[name] = -1.0
            self._publish_control_config(name)

        response.success = True
        response.message = (
            f"configured {', '.join(names)} to "
            f"{config.width}x{config.height} at {config.fps:g} Hz"
        )
        self._publish_state()
        return response

    def _on_set_enabled(self, request, response):
        names, error = self._resolve_names(request.cameras)
        if error:
            response.success = False
            response.message = error
            return response
        self._publish_enabled(names, bool(request.enabled))
        response.success = True
        response.message = (
            f"{'enabled' if request.enabled else 'disabled'} "
            + ", ".join(names)
        )
        return response

    def _set_lag(
        self, names: Iterable[str], lag_seconds: float
    ) -> str | None:
        validation = self._validate_lag(lag_seconds)
        if validation:
            return validation
        for name in names:
            memory_error = self._validate_buffer(
                self._configs[name], lag_seconds
            )
            if memory_error:
                return f"{name}: {memory_error}"
        for name in names:
            self._lags[name] = lag_seconds
            self._queues[name].clear()
            self._publish_lag_status(name)
        self._publish_state()
        return None

    def _on_set_lag(self, request, response):
        names, error = self._resolve_names(request.cameras)
        if error:
            response.success = False
            response.message = error
            return response
        lag_seconds = float(request.lag_seconds)
        validation = self._set_lag(names, lag_seconds)
        if validation:
            response.success = False
            response.message = validation
            return response
        response.success = True
        response.message = (
            f"set lag for {', '.join(names)} to {lag_seconds:g} seconds"
        )
        return response

    def _on_lag_topic(self, name: str, message: Float64) -> None:
        if name not in self._active_camera_names():
            return
        error = self._set_lag((name,), float(message.data))
        if error:
            self.get_logger().error(f"Rejected {name} lag update: {error}")

    def _state(self) -> dict:
        active = self._active_camera_names()
        cameras = {}
        for name, endpoint in self.ENDPOINTS.items():
            cameras[name] = {
                "active": name in active,
                "enabled": self._enabled[name],
                "lag_seconds": self._lags[name],
                "config": asdict(self._configs[name]),
                "raw_topic": endpoint.raw_topic,
                "image_topic": endpoint.image_topic,
                "camera_info_topic": endpoint.camera_info_topic,
                "queued_frames": len(self._queues[name]),
            }
        return {
            "mode": self.mode,
            "active_cameras": list(active),
            "maximum_lag_seconds": self._maximum_lag,
            "cameras": cameras,
        }

    def _publish_state(self) -> None:
        message = String()
        message.data = json.dumps(self._state(), separators=(",", ":"))
        self._state_publisher.publish(message)

    def _on_status(self, _request, response):
        response.success = True
        response.message = json.dumps(self._state(), sort_keys=True)
        return response

    def shutdown_streams(self) -> None:
        for _ in range(3):
            self._publish_enabled(self.BOATS, False)
            rclpy.spin_once(self, timeout_sec=0.05)
            time.sleep(0.05)
        self.get_logger().info("Published camera shutdown commands")


def main(args=None) -> None:
    rclpy.init(args=args)
    node = BlueBoatCameraManager()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if rclpy.ok():
            node.shutdown_streams()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
