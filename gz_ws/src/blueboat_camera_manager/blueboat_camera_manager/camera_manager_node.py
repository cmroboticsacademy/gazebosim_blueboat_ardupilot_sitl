#!/usr/bin/env python3
"""ROS 2 service front end for BlueBoat Gazebo camera stream plugins."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String
from std_srvs.srv import Trigger

from blueboat_camera_manager.srv import (
    SelectCamera,
    SetCameraConfig,
    SetCameraEnabled,
)


@dataclass(frozen=True)
class CameraEndpoint:
    name: str
    prefix: str
    source_width: int
    source_height: int
    port: int


class BlueBoatCameraManager(Node):
    """Expose stable ROS 2 services and publish Gazebo transport controls."""

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
        self.declare_parameter("startup_delay", 10.0)
        self.declare_parameter("startup_retries", 5)
        self.declare_parameter("startup_retry_period", 1.0)
        self.declare_parameter("default_width", 256)
        self.declare_parameter("default_height", 256)
        self.declare_parameter("default_fps", 16.0)
        self.declare_parameter("default_bitrate_kbps", 800)
        self.declare_parameter("default_preserve_aspect", False)
        self.declare_parameter("single_default_target", "blueboat")

        self.mode = str(self.get_parameter("mode").value).strip().lower()
        if self.mode not in ("four", "single"):
            raise ValueError("camera manager mode must be 'four' or 'single'")

        self._enable_publishers: dict[str, object] = {}
        self._config_publishers: dict[str, object] = {}
        for name, endpoint in self.ENDPOINTS.items():
            self._enable_publishers[name] = self.create_publisher(
                Bool, f"{endpoint.prefix}/enable_streaming", 10
            )
            self._config_publishers[name] = self.create_publisher(
                String, f"{endpoint.prefix}/stream_config", 10
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
        self._configs: dict[str, tuple[int, int, float, int, bool]] = {}
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
            f"after {self._startup_delay:.1f} seconds"
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
        if fps <= 0.0 or fps > 30.0:
            return "fps must be greater than 0 and no more than 30"
        if bitrate_kbps < 100 or bitrate_kbps > 50000:
            return "bitrate_kbps must be between 100 and 50000"
        return None

    @staticmethod
    def _config_payload(
        width: int,
        height: int,
        fps: float,
        bitrate_kbps: int,
        preserve_aspect: bool,
    ) -> str:
        return (
            f"width={width};height={height};fps={fps:.6g};"
            f"bitrate_kbps={bitrate_kbps};"
            f"preserve_aspect={'true' if preserve_aspect else 'false'}"
        )

    def _publish_config(
        self,
        names: Iterable[str],
        width: int,
        height: int,
        fps: float,
        bitrate_kbps: int,
        preserve_aspect: bool,
    ) -> list[str]:
        payload = self._config_payload(
            width, height, fps, bitrate_kbps, preserve_aspect
        )
        message = String()
        message.data = payload
        upscale_warnings: list[str] = []
        for name in names:
            endpoint = self.ENDPOINTS[name]
            self._config_publishers[name].publish(message)
            self._configs[name] = (
                width, height, fps, bitrate_kbps, preserve_aspect
            )
            if width > endpoint.source_width or height > endpoint.source_height:
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

        width = int(self.get_parameter("default_width").value)
        height = int(self.get_parameter("default_height").value)
        fps = float(self.get_parameter("default_fps").value)
        bitrate = int(self.get_parameter("default_bitrate_kbps").value)
        preserve = bool(self.get_parameter("default_preserve_aspect").value)
        active = self._active_camera_names()

        self._publish_config(active, width, height, fps, bitrate, preserve)
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
        validation = self._validate_config(
            int(request.width),
            int(request.height),
            float(request.fps),
            int(request.bitrate_kbps),
        )
        if validation:
            response.success = False
            response.message = validation
            return response

        warnings = self._publish_config(
            names,
            int(request.width),
            int(request.height),
            float(request.fps),
            int(request.bitrate_kbps),
            bool(request.preserve_aspect),
        )
        response.success = True
        response.message = (
            f"configured {', '.join(names)} to {request.width}x{request.height} "
            f"at {request.fps:g} Hz"
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

    def _on_select_camera(self, request, response):
        target = str(request.camera).strip().lower()
        if target not in self.BOATS:
            response.success = False
            response.message = (
                "camera must be one of: " + ", ".join(self.BOATS)
            )
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
        response.success = True
        response.message = (
            f"mode={self.mode}; enabled={','.join(enabled) or 'none'}; "
            f"single_target={self._current_target}; configs={self._configs}"
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
