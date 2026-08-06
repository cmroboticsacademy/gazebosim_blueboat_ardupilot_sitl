#!/usr/bin/env python3
"""Local HTTP control panel and on-demand MJPEG server for BlueBoat cameras."""

from __future__ import annotations

import json
import math
import mimetypes
import threading
import time
from collections import defaultdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import cv2
import numpy as np
from ament_index_python.packages import get_package_share_directory
import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
    qos_profile_sensor_data,
)
from sensor_msgs.msg import Image
from std_msgs.msg import String

from blueboat_camera_manager.srv import (
    SetCameraConfig,
    SetCameraEnabled,
    SetCameraLag,
)


class CameraWebNode(Node):
    """Serve camera state, batch controls, and low-overhead previews."""

    BOATS = ("blueboat", "blueboat2", "blueboat3", "blueboat4")

    def __init__(self) -> None:
        super().__init__("blueboat_camera_web")
        self.declare_parameter("address", "127.0.0.1")
        self.declare_parameter("port", 8080)
        self.declare_parameter("jpeg_quality", 72)
        self.declare_parameter("preview_max_fps", 0.0)
        self.declare_parameter("opencv_threads", 1)
        self.declare_parameter("service_timeout_seconds", 5.0)

        self.address = str(self.get_parameter("address").value)
        self.port = int(self.get_parameter("port").value)
        self.default_jpeg_quality = min(
            92, max(25, int(self.get_parameter("jpeg_quality").value))
        )
        self.preview_max_fps = max(
            0.0, min(60.0, float(self.get_parameter("preview_max_fps").value))
        )
        cv2.setNumThreads(
            max(1, int(self.get_parameter("opencv_threads").value))
        )
        self.service_timeout = max(
            0.5,
            float(self.get_parameter("service_timeout_seconds").value),
        )
        self.web_root = Path(
            get_package_share_directory("blueboat_camera_manager")
        ) / "web"

        self._state_lock = threading.Lock()
        self._state = {
            "mode": 0,
            "active_cameras": [],
            "cameras": {},
            "status": "Waiting for camera manager state",
        }

        self._frame_conditions = {
            name: threading.Condition() for name in self.BOATS
        }
        self._frames: dict[str, bytes | None] = {
            name: None for name in self.BOATS
        }
        self._frame_versions = {name: 0 for name in self.BOATS}

        self._web_stats_lock = threading.Lock()
        self._viewer_counts = {name: 0 for name in self.BOATS}
        self._jpeg_quality = {
            name: self.default_jpeg_quality for name in self.BOATS
        }
        self._last_encoded_at = {name: -1.0 for name in self.BOATS}
        self._encoded_frames = {name: 0 for name in self.BOATS}
        self._encoded_bytes = {name: 0 for name in self.BOATS}
        self._rate_previous_frames = {name: 0 for name in self.BOATS}
        self._rate_previous_bytes = {name: 0 for name in self.BOATS}
        self._encoded_fps = {name: 0.0 for name in self.BOATS}
        self._encoded_bitrate_kbps = {name: 0.0 for name in self.BOATS}
        self._rate_previous_time = time.monotonic()

        # Image subscriptions are created only while at least one browser is
        # viewing a boat. This prevents the web UI from forcing all four ROS
        # image pipelines to resize and JPEG-encode continuously.
        self._image_subscriptions = {name: None for name in self.BOATS}
        self._running = True

        state_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self.create_subscription(
            String,
            "/blueboat_camera_manager/state",
            self._on_state,
            state_qos,
        )
        self._subscription_timer = self.create_timer(
            0.25, self._reconcile_image_subscriptions
        )

        self._config_client = self.create_client(
            SetCameraConfig, "/blueboat_camera_manager/set_config"
        )
        self._enabled_client = self.create_client(
            SetCameraEnabled, "/blueboat_camera_manager/set_enabled"
        )
        self._lag_client = self.create_client(
            SetCameraLag, "/blueboat_camera_manager/set_lag"
        )

        handler_class = self._make_handler()
        self._http_server = ThreadingHTTPServer(
            (self.address, self.port), handler_class
        )
        self._http_server.daemon_threads = True
        self._http_thread = threading.Thread(
            target=self._http_server.serve_forever,
            name="blueboat-camera-http",
            daemon=True,
        )
        self._http_thread.start()
        preview_description = (
            "full processed ROS topic rate"
            if self.preview_max_fps <= 0.0
            else f"capped at {self.preview_max_fps:g} FPS"
        )
        self.get_logger().info(
            f"BlueBoat camera web UI: http://{self.address}:{self.port}; "
            f"previews are on-demand at {preview_description}"
        )

    def _on_state(self, message: String) -> None:
        try:
            state = json.loads(message.data)
        except json.JSONDecodeError as error:
            self.get_logger().error(f"Invalid camera state JSON: {error}")
            return
        with self._state_lock:
            self._state = state

    def _camera_web_config(self, name: str) -> tuple[float, int]:
        with self._state_lock:
            camera = self._state.get("cameras", {}).get(name, {})
            config = camera.get("config", {})
            camera_fps = float(config.get("fps", self.preview_max_fps))
            bitrate_kbps = int(config.get("bitrate_kbps", 800))
        camera_fps = max(0.1, min(60.0, camera_fps))
        preview_fps = (
            camera_fps
            if self.preview_max_fps <= 0.0
            else min(self.preview_max_fps, camera_fps)
        )
        return preview_fps, max(64, bitrate_kbps)

    @staticmethod
    def _image_to_bgr(message: Image) -> np.ndarray:
        """Return a BGR uint8 image without depending on cv_bridge."""
        width = int(message.width)
        height = int(message.height)
        encoding = str(message.encoding).lower()
        channels_by_encoding = {
            "bgr8": 3,
            "8uc3": 3,
            "rgb8": 3,
            "bgra8": 4,
            "rgba8": 4,
            "mono8": 1,
            "8uc1": 1,
        }
        channels = channels_by_encoding.get(encoding)
        if channels is None:
            raise ValueError(f"unsupported image encoding '{message.encoding}'")
        row_bytes = width * channels
        step = int(message.step) or row_bytes
        if width <= 0 or height <= 0 or step < row_bytes:
            raise ValueError("invalid image dimensions or row step")

        raw = np.frombuffer(message.data, dtype=np.uint8)
        required = step * height
        if raw.size < required:
            raise ValueError(
                f"image buffer has {raw.size} bytes; expected at least {required}"
            )
        pixels = raw[:required].reshape(height, step)[:, :row_bytes]
        pixels = pixels.reshape(height, width, channels)

        if encoding in ("bgr8", "8uc3"):
            return np.ascontiguousarray(pixels)
        if encoding == "rgb8":
            return cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR)
        if encoding == "bgra8":
            return cv2.cvtColor(pixels, cv2.COLOR_BGRA2BGR)
        if encoding == "rgba8":
            return cv2.cvtColor(pixels, cv2.COLOR_RGBA2BGR)
        return cv2.cvtColor(pixels, cv2.COLOR_GRAY2BGR)

    def _on_image(self, name: str, message: Image) -> None:
        preview_fps, bitrate_kbps = self._camera_web_config(name)
        now = time.monotonic()
        with self._web_stats_lock:
            if self._viewer_counts[name] <= 0:
                return
            last = self._last_encoded_at[name]
            if self.preview_max_fps > 0.0:
                period = 1.0 / preview_fps
                if last >= 0.0 and now - last + 1e-9 < period:
                    return
            self._last_encoded_at[name] = now
            quality = self._jpeg_quality[name]

        try:
            image = self._image_to_bgr(message)
            ok, encoded = cv2.imencode(
                ".jpg",
                image,
                [cv2.IMWRITE_JPEG_QUALITY, quality],
            )
        except (ValueError, cv2.error) as error:
            self.get_logger().error(f"Could not encode {name} frame: {error}")
            return
        if not ok:
            return

        frame = encoded.tobytes()
        target_bytes = max(
            512.0, (bitrate_kbps * 1000.0 / 8.0) / preview_fps
        )
        size_ratio = len(frame) / target_bytes
        with self._web_stats_lock:
            # One encode per frame: adjust the next frame's JPEG quality instead
            # of doing an expensive second encode to hit the target exactly.
            if size_ratio > 1.12:
                adjusted = int(round(quality / math.sqrt(size_ratio)))
                self._jpeg_quality[name] = max(25, min(92, adjusted))
            elif size_ratio < 0.72:
                self._jpeg_quality[name] = min(92, quality + 3)
            self._encoded_frames[name] += 1
            self._encoded_bytes[name] += len(frame)

        condition = self._frame_conditions[name]
        with condition:
            self._frames[name] = frame
            self._frame_versions[name] += 1
            condition.notify_all()

    def _add_viewer(self, name: str) -> None:
        with self._web_stats_lock:
            self._viewer_counts[name] += 1

    def _remove_viewer(self, name: str) -> None:
        with self._web_stats_lock:
            self._viewer_counts[name] = max(0, self._viewer_counts[name] - 1)

    def _reconcile_image_subscriptions(self) -> None:
        with self._web_stats_lock:
            desired = {
                name: self._viewer_counts[name] > 0 for name in self.BOATS
            }

        for name in self.BOATS:
            subscription = self._image_subscriptions[name]
            if desired[name] and subscription is None:
                self._image_subscriptions[name] = self.create_subscription(
                    Image,
                    f"/{name}/camera/image",
                    lambda message, camera=name: self._on_image(camera, message),
                    qos_profile_sensor_data,
                )
            elif not desired[name] and subscription is not None:
                self.destroy_subscription(subscription)
                self._image_subscriptions[name] = None
                condition = self._frame_conditions[name]
                with condition:
                    self._frames[name] = None
                    self._frame_versions[name] += 1
                    condition.notify_all()

    def _roll_web_rates(self) -> None:
        now = time.monotonic()
        with self._web_stats_lock:
            elapsed = now - self._rate_previous_time
            if elapsed < 0.5:
                return
            for name in self.BOATS:
                frames = self._encoded_frames[name]
                bytes_count = self._encoded_bytes[name]
                self._encoded_fps[name] = (
                    frames - self._rate_previous_frames[name]
                ) / elapsed
                self._encoded_bitrate_kbps[name] = (
                    (bytes_count - self._rate_previous_bytes[name])
                    * 8.0
                    / elapsed
                    / 1000.0
                )
                self._rate_previous_frames[name] = frames
                self._rate_previous_bytes[name] = bytes_count
            self._rate_previous_time = now

    def get_state(self) -> dict:
        with self._state_lock:
            state = json.loads(json.dumps(self._state))
        self._roll_web_rates()
        now = time.monotonic()
        with self._web_stats_lock:
            for name in self.BOATS:
                camera = state.setdefault("cameras", {}).setdefault(name, {})
                configured_fps = float(
                    camera.get("config", {}).get("fps", self.preview_max_fps)
                )
                last = self._last_encoded_at[name]
                camera["web"] = {
                    "viewers": self._viewer_counts[name],
                    "preview_active": self._viewer_counts[name] > 0,
                    "preview_fps_limit": (
                        max(0.1, configured_fps)
                        if self.preview_max_fps <= 0.0
                        else min(
                            self.preview_max_fps, max(0.1, configured_fps)
                        )
                    ),
                    "preview_unthrottled": self.preview_max_fps <= 0.0,
                    "encoded_fps": self._encoded_fps[name],
                    "actual_bitrate_kbps": self._encoded_bitrate_kbps[name],
                    "jpeg_quality": self._jpeg_quality[name],
                    "last_encoded_age_seconds": (
                        None if last < 0.0 else max(0.0, now - last)
                    ),
                }
        return state

    def get_frame(
        self, name: str, last_version: int, timeout: float = 2.0
    ) -> tuple[bytes | None, int]:
        condition = self._frame_conditions[name]
        with condition:
            if self._frame_versions[name] == last_version and self._running:
                condition.wait(timeout=timeout)
            return self._frames[name], self._frame_versions[name]

    def _call_service(self, client, request) -> dict:
        if not client.service_is_ready():
            return {
                "success": False,
                "message": "Camera manager service is not ready",
                "http_status": HTTPStatus.SERVICE_UNAVAILABLE,
            }

        event = threading.Event()
        result_holder = {}
        future = client.call_async(request)

        def completed(done_future) -> None:
            try:
                result_holder["result"] = done_future.result()
            except Exception as error:  # rclpy surfaces transport failures here.
                result_holder["error"] = str(error)
            finally:
                event.set()

        future.add_done_callback(completed)
        if not event.wait(timeout=self.service_timeout):
            return {
                "success": False,
                "message": "Timed out waiting for camera manager",
                "http_status": HTTPStatus.GATEWAY_TIMEOUT,
            }
        if "error" in result_holder:
            return {
                "success": False,
                "message": result_holder["error"],
                "http_status": HTTPStatus.BAD_GATEWAY,
            }
        result = result_holder["result"]
        return {
            "success": bool(result.success),
            "message": str(result.message),
            "http_status": (
                HTTPStatus.OK if result.success else HTTPStatus.BAD_REQUEST
            ),
        }

    def _call_config_groups(
        self, names: list[str], payload: dict, state: dict
    ) -> list[dict]:
        grouped: dict[tuple, list[str]] = defaultdict(list)
        for name in names:
            current = state["cameras"][name].get("config", {})
            config = (
                int(payload.get("width", current.get("width", 256))),
                int(payload.get("height", current.get("height", 256))),
                float(payload.get("fps", current.get("fps", 16.0))),
                int(
                    payload.get(
                        "bitrate_kbps", current.get("bitrate_kbps", 800)
                    )
                ),
                bool(
                    payload.get(
                        "preserve_aspect",
                        current.get("preserve_aspect", True),
                    )
                ),
            )
            grouped[config].append(name)

        responses = []
        for config, camera_names in grouped.items():
            request = SetCameraConfig.Request()
            request.cameras = camera_names
            request.width = config[0]
            request.height = config[1]
            request.fps = config[2]
            request.bitrate_kbps = config[3]
            request.preserve_aspect = config[4]
            result = self._call_service(self._config_client, request)
            responses.append(result)
            if not result["success"]:
                break
        return responses

    def _call_lag(self, names: list[str], lag_seconds: float) -> dict:
        request = SetCameraLag.Request()
        request.cameras = names
        request.lag_seconds = lag_seconds
        return self._call_service(self._lag_client, request)

    @staticmethod
    def _validate_final_settings(names: list[str], payload: dict, state: dict) -> None:
        maximum_lag = float(state.get("maximum_lag_seconds", 30.0))
        maximum_buffer_mb = float(
            state.get("maximum_buffer_mb_per_camera", 256.0)
        )
        maximum_buffer_bytes = maximum_buffer_mb * 1024.0 * 1024.0
        for name in names:
            camera = state["cameras"][name]
            current = camera.get("config", {})
            width = int(payload.get("width", current.get("width", 256)))
            height = int(payload.get("height", current.get("height", 256)))
            fps = float(payload.get("fps", current.get("fps", 16.0)))
            bitrate = int(
                payload.get("bitrate_kbps", current.get("bitrate_kbps", 800))
            )
            lag = float(payload.get("lag_seconds", camera.get("lag_seconds", 0.0)))
            if (
                width < 16
                or height < 16
                or width > 1920
                or height > 1080
                or width % 2
                or height % 2
            ):
                raise ValueError(
                    f"{name}: width and height must be even, at least 16, "
                    "and no more than 1920x1080"
                )
            if not math.isfinite(fps) or fps <= 0.0 or fps > 60.0:
                raise ValueError(f"{name}: FPS must be within (0, 60]")
            if bitrate < 64 or bitrate > 20000:
                raise ValueError(
                    f"{name}: preview bitrate must be between 64 and 20000 kbps"
                )
            if not math.isfinite(lag) or lag < 0.0 or lag > maximum_lag:
                raise ValueError(
                    f"{name}: lag must be between 0 and {maximum_lag:g} seconds"
                )
            estimated = width * height * 3.0 * fps * lag
            if estimated > maximum_buffer_bytes:
                raise ValueError(
                    f"{name}: final lag buffer is "
                    f"{estimated / (1024 * 1024):.1f} MiB; limit is "
                    f"{maximum_buffer_mb:.1f} MiB"
                )

    def update_cameras(self, requested_names, payload: dict) -> dict:
        state = self.get_state()
        names = list(
            dict.fromkeys(str(name).strip().lower() for name in requested_names)
        )
        names = [name for name in names if name]
        if not names:
            return {
                "success": False,
                "message": "Select at least one camera",
                "http_status": HTTPStatus.BAD_REQUEST,
            }

        for name in names:
            camera = state.get("cameras", {}).get(name)
            if name not in self.BOATS or not camera:
                return {
                    "success": False,
                    "message": f"Unknown camera '{name}'",
                    "http_status": HTTPStatus.NOT_FOUND,
                }
            if not camera.get("active", False):
                return {
                    "success": False,
                    "message": f"{name} is outside the selected camera mode",
                    "http_status": HTTPStatus.BAD_REQUEST,
                }

        config_fields = {
            "width",
            "height",
            "fps",
            "bitrate_kbps",
            "preserve_aspect",
        }
        self._validate_final_settings(names, payload, state)
        has_config = bool(config_fields.intersection(payload))
        has_lag = "lag_seconds" in payload
        has_enabled = "enabled" in payload
        if not (has_config or has_lag or has_enabled):
            return {
                "success": False,
                "message": "No supported camera settings were supplied",
                "http_status": HTTPStatus.BAD_REQUEST,
            }

        responses: list[dict] = []
        requested_lag = (
            float(payload["lag_seconds"]) if has_lag else None
        )

        # When lag and frame size change together, order each camera so the
        # intermediate lag buffer is never larger than both its old and final
        # configurations. This avoids transient memory-limit rejections.
        lag_before: list[str] = []
        lag_after: list[str] = []
        if has_lag:
            for name in names:
                current_lag = float(
                    state["cameras"][name].get("lag_seconds", 0.0)
                )
                if requested_lag <= current_lag:
                    lag_before.append(name)
                else:
                    lag_after.append(name)

        if lag_before:
            result = self._call_lag(lag_before, requested_lag)
            responses.append(result)
            if not result["success"]:
                return result

        if has_config:
            for result in self._call_config_groups(names, payload, state):
                responses.append(result)
                if not result["success"]:
                    return result

        if lag_after:
            result = self._call_lag(lag_after, requested_lag)
            responses.append(result)
            if not result["success"]:
                return result

        if has_lag and not has_config and not lag_before and not lag_after:
            result = self._call_lag(names, requested_lag)
            responses.append(result)
            if not result["success"]:
                return result

        if has_enabled:
            if not isinstance(payload["enabled"], bool):
                raise ValueError("enabled must be true or false")
            request = SetCameraEnabled.Request()
            request.cameras = names
            request.enabled = payload["enabled"]
            result = self._call_service(self._enabled_client, request)
            responses.append(result)
            if not result["success"]:
                return result

        return {
            "success": True,
            "message": "; ".join(item["message"] for item in responses),
            "http_status": HTTPStatus.OK,
        }

    def update_camera(self, name: str, payload: dict) -> dict:
        return self.update_cameras([name], payload)

    def _make_handler(self):
        node = self

        class CameraRequestHandler(BaseHTTPRequestHandler):
            server_version = "BlueBoatCameraWeb/2.0"

            def log_message(self, _format, *_args) -> None:
                return

            def _send_json(self, status: int, payload: dict) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(int(status))
                self.send_header(
                    "Content-Type", "application/json; charset=utf-8"
                )
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _read_json(self) -> dict:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 65536:
                    raise ValueError("invalid request length")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("JSON body must be an object")
                return payload

            def _send_static(self, relative_path: str) -> None:
                # Validate the URL path lexically. With --symlink-install the
                # installed asset can safely resolve back into the source tree.
                relative = Path(relative_path)
                if relative.is_absolute() or ".." in relative.parts:
                    self.send_error(HTTPStatus.FORBIDDEN)
                    return
                requested = node.web_root / relative
                if not requested.is_file():
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                body = requested.read_bytes()
                content_type = mimetypes.guess_type(requested.name)[0]
                self.send_response(HTTPStatus.OK)
                self.send_header(
                    "Content-Type", content_type or "application/octet-stream"
                )
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802 - HTTP handler API.
                path = unquote(urlparse(self.path).path)
                if path == "/api/state":
                    self._send_json(HTTPStatus.OK, node.get_state())
                    return
                if path.startswith("/stream/") and path.endswith(".mjpg"):
                    name = path[len("/stream/") : -len(".mjpg")]
                    if name not in node.BOATS:
                        self.send_error(HTTPStatus.NOT_FOUND)
                        return
                    self._serve_mjpeg(name)
                    return
                if path in ("/", "/index.html"):
                    self._send_static("index.html")
                    return
                self._send_static(path.lstrip("/"))

            def do_POST(self) -> None:  # noqa: N802 - HTTP handler API.
                path = unquote(urlparse(self.path).path).rstrip("/")
                try:
                    body = self._read_json()
                    if path == "/api/cameras":
                        cameras = body.get("cameras", [])
                        settings = body.get("settings", {})
                        if not isinstance(cameras, list):
                            raise ValueError("cameras must be an array")
                        if not isinstance(settings, dict):
                            raise ValueError("settings must be an object")
                        result = node.update_cameras(cameras, settings)
                    elif path.startswith("/api/cameras/"):
                        name = path[len("/api/cameras/") :].strip("/")
                        result = node.update_camera(name, body)
                    else:
                        self.send_error(HTTPStatus.NOT_FOUND)
                        return
                except (ValueError, TypeError, json.JSONDecodeError) as error:
                    self._send_json(
                        HTTPStatus.BAD_REQUEST,
                        {"success": False, "message": str(error)},
                    )
                    return
                except Exception as error:  # Keep the HTTP thread alive.
                    node.get_logger().error(
                        f"Camera web request failed for {path}: {error}"
                    )
                    self._send_json(
                        HTTPStatus.INTERNAL_SERVER_ERROR,
                        {"success": False, "message": "Internal server error"},
                    )
                    return
                status = result.pop("http_status", HTTPStatus.OK)
                self._send_json(status, result)

            def _serve_mjpeg(self, name: str) -> None:
                node._add_viewer(name)
                try:
                    self.send_response(HTTPStatus.OK)
                    self.send_header(
                        "Content-Type",
                        "multipart/x-mixed-replace; boundary=blueboatframe",
                    )
                    self.send_header("Cache-Control", "no-store, no-cache")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    version = -1
                    while node._running:
                        frame, next_version = node.get_frame(name, version)
                        if frame is None or next_version == version:
                            continue
                        version = next_version
                        self.wfile.write(b"--blueboatframe\r\n")
                        self.wfile.write(b"Content-Type: image/jpeg\r\n")
                        self.wfile.write(
                            f"Content-Length: {len(frame)}\r\n\r\n".encode(
                                "ascii"
                            )
                        )
                        self.wfile.write(frame)
                        self.wfile.write(b"\r\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, TimeoutError):
                    return
                finally:
                    node._remove_viewer(name)

        return CameraRequestHandler

    def shutdown(self) -> None:
        self._running = False
        for condition in self._frame_conditions.values():
            with condition:
                condition.notify_all()
        self._http_server.shutdown()
        self._http_server.server_close()
        if self._http_thread.is_alive():
            self._http_thread.join(timeout=2.0)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = CameraWebNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
