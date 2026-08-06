#!/usr/bin/env python3
"""ROS 2 service and topic front end for BlueBoat Gazebo camera streams."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from functools import partial
from typing import Iterable

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, Float64, String
from std_srvs.srv import Trigger

from blueboat_camera_manager.srv import (
    SelectCamera,
    SetCameraConfig,
    SetCameraEnabled,
    SetCameraLag,
)


@dataclass(frozen=True)
class CameraEndpoint:
    """Static metadata for one camera stream."""

    name: str
    prefix: str
    source_width: int
    source_height: int
    port: int


@dataclass(frozen=True)
class CameraConfig:
    """Current encoder settings retained by the ROS manager."""

    width: int
    height: int
    fps: float
    bitrate_kbps: int
    preserve_aspect: bool


class BlueBoatCameraManager(Node):
    """Expose stable ROS 2 controls and publish Gazebo transport commands."""

    ENDPOINTS = {
        "blueboat": CameraEndpoint("blueboat", "/blueboat/camera", 640, 480, 5600),
        "blueboat2": CameraEndpoint("blueboat2", "/blueboat2/camera", 640, 480, 5602),
        "blueboat3": CameraEndpoint("blueboat3", "/blueboat3/camera", 640, 480, 5604),
        "blueboat4": CameraEndpoint("blueboat4", "/blueboat4/camera", 640, 480, 5606),
        "camera_pod": CameraEndpoint("camera_pod", "/camera_pod/camera", 1280, 720, 5600),
    }
    BOATS = ("blueboat", "blueboat2", "blueboat3", "blueboat4")

    def __init__(self) -> None:
        super().__init__("blueboat_camera_manager")
        self.declare_parameter("mode", "four")
        self.declare_parameter("startup_delay", 0.0)
        self.declare_parameter("startup_retries", 60)
        self.declare_parameter("startup_retry_period", 1.0)
        self.declare_parameter("default_width", 256)
        self.declare_parameter("default_height", 256)
        self.declare_parameter("default_fps", 16.0)
        self.declare_parameter("default_bitrate_kbps", 800)
        self.declare_parameter("default_preserve_aspect", True)
        self.declare_parameter("default_lag_seconds", 0.0)
        self.declare_parameter("maximum_lag_seconds", 30.0)
        self.declare_parameter("single_default_target", "blueboat")

        self.mode = str(self.get_parameter("mode").value).strip().lower()
        if self.mode not in ("four", "single"):
            raise ValueError("camera manager mode must be 'four' or 'single'")

        self._maximum_lag = float(self.get_parameter("maximum_lag_seconds").value)
        if (
            not math.isfinite(self._maximum_lag)
            or self._maximum_lag <= 0.0
            or self._maximum_lag > 30.0
        ):
            raise ValueError(
                "maximum_lag_seconds must be finite, greater than zero, "
                "and no more than 30"
            )

        default_lag = float(self.get_parameter("default_lag_seconds").value)
        lag_error = self._validate_lag(default_lag)
        if lag_error:
            raise ValueError(f"invalid default_lag_seconds: {lag_error}")

        self._enable_publishers: dict[str, object] = {}
        self._config_publishers: dict[str, object] = {}
        self._lag_status_publishers: dict[str, object] = {}
        self._lag_subscriptions: list[object] = []
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
            self._lag_subscriptions.append(
                self.create_subscription(
                    Float64,
                    f"{endpoint.prefix}/lag",
                    partial(self._on_lag_topic, name),
                    10,
                )
            )

        self._target_publisher = self.create_publisher(
            String, "/camera_pod/target", 10
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
        self._select_camera_service = self.create_service(
            SelectCamera, "~/select_camera", self._on_select_camera
        )
        self._status_service = self.create_service(
            Trigger, "~/status", self._on_status
        )

        self._current_target = str(
            self.get_parameter("single_default_target").value
        ).strip()
        if self._current_target not in self.BOATS:
            self._current_target = "blueboat"

        self._enabled = {name: False for name in self.ENDPOINTS}
        self._configs: dict[str, CameraConfig] = {}
        self._lags = {name: default_lag for name in self.ENDPOINTS}
        self._startup_attempt = 0
        self._startup_retries = max(
            1, int(self.get_parameter("startup_retries").value)
        )
        self._startup_delay = max(
            0.0, float(self.get_parameter("startup_delay").value)
        )
        self._retry_period = max(
            0.1, float(self.get_parameter("startup_retry_period").value)
        )
        self._start_time = time.monotonic()
        self._startup_timer = self.create_timer(0.2, self._startup_tick)

        active = ", ".join(self._active_camera_names())
        self.get_logger().info(
            f"Camera manager mode={self.mode}; startup enables [{active}] "
            f"after {self._startup_delay:.1f} seconds; "
            f"default lag={default_lag:.3f} seconds"
        )

    def _active_camera_names(self) -> tuple[str, ...]:
        return self.BOATS if self.mode == "four" else ("camera_pod",)

    @staticmethod
    def _dedupe(values: Iterable[str]) -> list[str]:
        return list(dict.fromkeys(values))

    def _resolve_names(self, requested: Iterable[str]) -> tuple[list[str], str | None]:
        raw = [str(value).strip() for value in requested if str(value).strip()]
        if not raw:
            raw = ["all"]

        expanded: list[str] = []
        for name in raw:
            lowered = name.lower()
            if lowered == "all":
                expanded.extend(self._active_camera_names())
            elif lowered in ("all_boats", "boats"):
                expanded.extend(self.BOATS)
            elif lowered in self.ENDPOINTS:
                expanded.append(lowered)
            else:
                return [], f"unknown camera '{name}'"
        return self._dedupe(expanded), None

    @staticmethod
    def _validate_config(
        width: int,
        height: int,
        fps: float,
        bitrate_kbps: int,
    ) -> str | None:
        if width < 16 or height < 16 or width % 2 or height % 2:
            return "width and height must be even integers of at least 16"
        if width > 3840 or height > 2160:
            return "requested output exceeds 3840x2160"
        if not math.isfinite(fps) or fps <= 0.0 or fps > 60.0:
            return "fps must be finite, greater than 0, and no more than 60"
        if bitrate_kbps < 100 or bitrate_kbps > 50000:
            return "bitrate_kbps must be between 100 and 50000"
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

    @staticmethod
    def _config_payload(config: CameraConfig, lag_seconds: float) -> str:
        return (
            f"width={config.width};height={config.height};fps={config.fps:.6g};"
            f"bitrate_kbps={config.bitrate_kbps};"
            f"preserve_aspect={'true' if config.preserve_aspect else 'false'};"
            f"lag_seconds={lag_seconds:.9g}"
        )

    def _default_config(self) -> CameraConfig:
        return CameraConfig(
            width=int(self.get_parameter("default_width").value),
            height=int(self.get_parameter("default_height").value),
            fps=float(self.get_parameter("default_fps").value),
            bitrate_kbps=int(self.get_parameter("default_bitrate_kbps").value),
            preserve_aspect=bool(
                self.get_parameter("default_preserve_aspect").value
            ),
        )

    def _publish_config(
        self,
        names: Iterable[str],
        config: CameraConfig,
    ) -> list[str]:
        upscale_warnings: list[str] = []
        for name in names:
            endpoint = self.ENDPOINTS[name]
            message = String()
            message.data = self._config_payload(config, self._lags[name])
            self._config_publishers[name].publish(message)
            self._configs[name] = config
            if (
                config.width > endpoint.source_width
                or config.height > endpoint.source_height
            ):
                upscale_warnings.append(
                    f"{name} source is {endpoint.source_width}x{endpoint.source_height}"
                )
        return upscale_warnings

    def _publish_enabled(self, names: Iterable[str], enabled: bool) -> None:
        message = Bool()
        message.data = enabled
        for name in names:
            self._enable_publishers[name].publish(message)
            self._enabled[name] = enabled

    def _publish_lag(self, names: Iterable[str], lag_seconds: float) -> None:
        for name in names:
            self._lags[name] = lag_seconds
            config = self._configs.get(name, self._default_config())
            self._configs[name] = config
            message = String()
            message.data = self._config_payload(config, lag_seconds)
            self._config_publishers[name].publish(message)

            status = Float64()
            status.data = lag_seconds
            self._lag_status_publishers[name].publish(status)

    def _publish_target(self, target: str) -> None:
        message = String()
        message.data = target
        self._target_publisher.publish(message)
        self._current_target = target

    def _startup_tick(self) -> None:
        if time.monotonic() - self._start_time < self._startup_delay:
            return
        if self._startup_attempt >= self._startup_retries:
            self.destroy_timer(self._startup_timer)
            return

        active = self._active_camera_names()
        self._publish_config(active, self._default_config())
        for name in active:
            status = Float64()
            status.data = self._lags[name]
            self._lag_status_publishers[name].publish(status)
        if self.mode == "single":
            self._publish_target(self._current_target)
        self._publish_enabled(active, True)

        self._startup_attempt += 1
        if self._startup_attempt == 1:
            self.get_logger().info(
                "Published delayed initial camera configuration and enable command"
            )
        if self._startup_attempt < self._startup_retries:
            self.destroy_timer(self._startup_timer)
            self._startup_timer = self.create_timer(
                self._retry_period, self._startup_tick
            )
        else:
            self.destroy_timer(self._startup_timer)

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
            bitrate_kbps=int(request.bitrate_kbps),
            preserve_aspect=bool(request.preserve_aspect),
        )
        validation = self._validate_config(
            config.width,
            config.height,
            config.fps,
            config.bitrate_kbps,
        )
        if validation:
            response.success = False
            response.message = validation
            return response

        warnings = self._publish_config(names, config)
        response.success = True
        response.message = (
            f"configured {', '.join(names)} to {config.width}x{config.height} "
            f"at {config.fps:g} Hz"
        )
        if warnings:
            response.message += "; output will be upscaled: " + ", ".join(warnings)
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

    def _on_set_lag(self, request, response):
        names, error = self._resolve_names(request.cameras)
        if error:
            response.success = False
            response.message = error
            return response

        lag_seconds = float(request.lag_seconds)
        validation = self._validate_lag(lag_seconds)
        if validation:
            response.success = False
            response.message = validation
            return response

        self._publish_lag(names, lag_seconds)
        response.success = True
        response.message = (
            f"set lag for {', '.join(names)} to {lag_seconds:g} seconds"
        )
        return response

    def _on_lag_topic(self, camera_name: str, message: Float64) -> None:
        lag_seconds = float(message.data)
        validation = self._validate_lag(lag_seconds)
        if validation:
            self.get_logger().error(
                f"Rejected {camera_name} lag topic update: {validation}"
            )
            return
        self._publish_lag((camera_name,), lag_seconds)
        self.get_logger().info(
            f"Set {camera_name} camera lag to {lag_seconds:g} seconds"
        )

    def _on_select_camera(self, request, response):
        target = str(request.camera).strip().lower()
        if target not in self.BOATS:
            response.success = False
            response.message = "camera must be one of: " + ", ".join(self.BOATS)
            return response
        if self.mode != "single":
            response.success = False
            response.message = "select_camera is available only in camera_mode:=single"
            return response
        self._publish_target(target)
        self._publish_enabled(("camera_pod",), True)
        response.success = True
        response.message = f"camera pod now follows {target} on UDP port 5600"
        return response

    def _on_status(self, _request, response):
        enabled = [name for name, value in self._enabled.items() if value]
        lag_text = ",".join(
            f"{name}:{value:g}s" for name, value in self._lags.items()
        )
        response.success = True
        response.message = (
            f"mode={self.mode}; enabled={','.join(enabled) or 'none'}; "
            f"single_target={self._current_target}; lags={lag_text}; "
            f"configs={self._configs}"
        )
        return response

    def shutdown_streams(self) -> None:
        """Best-effort stop messages before ROS context and bridges disappear."""
        all_names = tuple(self.ENDPOINTS)
        for _ in range(3):
            self._publish_enabled(all_names, False)
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
