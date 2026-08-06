#!/usr/bin/env python3
"""Local HTTP control panel and MJPEG server for BlueBoat cameras."""

from __future__ import annotations

import json
import mimetypes
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import cv2
from ament_index_python.packages import get_package_share_directory
from cv_bridge import CvBridge, CvBridgeError
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
    BOATS = ("blueboat", "blueboat2", "blueboat3", "blueboat4")

    def __init__(self) -> None:
        super().__init__("blueboat_camera_web")
        self.declare_parameter("address", "127.0.0.1")
        self.declare_parameter("port", 8080)
        self.declare_parameter("jpeg_quality", 80)
        self.declare_parameter("service_timeout_seconds", 5.0)

        self.address = str(self.get_parameter("address").value)
        self.port = int(self.get_parameter("port").value)
        self.jpeg_quality = min(
            100, max(20, int(self.get_parameter("jpeg_quality").value))
        )
        self.service_timeout = max(
            0.5,
            float(self.get_parameter("service_timeout_seconds").value),
        )
        self.web_root = Path(
            get_package_share_directory("blueboat_camera_manager")
        ) / "web"

        self._bridge = CvBridge()
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
        for name in self.BOATS:
            self.create_subscription(
                Image,
                f"/{name}/camera/image",
                lambda message, camera=name: self._on_image(camera, message),
                qos_profile_sensor_data,
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
        self.get_logger().info(
            f"BlueBoat camera web UI: http://{self.address}:{self.port}"
        )

    def _on_state(self, message: String) -> None:
        try:
            state = json.loads(message.data)
        except json.JSONDecodeError as error:
            self.get_logger().error(f"Invalid camera state JSON: {error}")
            return
        with self._state_lock:
            self._state = state

    def _on_image(self, name: str, message: Image) -> None:
        try:
            image = self._bridge.imgmsg_to_cv2(
                message, desired_encoding="bgr8"
            )
            ok, encoded = cv2.imencode(
                ".jpg",
                image,
                [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality],
            )
        except (CvBridgeError, cv2.error) as error:
            self.get_logger().error(f"Could not encode {name} frame: {error}")
            return
        if not ok:
            return
        condition = self._frame_conditions[name]
        with condition:
            self._frames[name] = encoded.tobytes()
            self._frame_versions[name] += 1
            condition.notify_all()

    def get_state(self) -> dict:
        with self._state_lock:
            return json.loads(json.dumps(self._state))

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

    def update_camera(self, name: str, payload: dict) -> dict:
        state = self.get_state()
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

        responses = []
        config_fields = {"width", "height", "fps", "preserve_aspect"}
        has_config = bool(config_fields.intersection(payload))
        has_lag = "lag_seconds" in payload
        current_lag = float(camera.get("lag_seconds", 0.0))
        requested_lag = (
            float(payload["lag_seconds"]) if has_lag else current_lag
        )

        def apply_config() -> dict:
            current = camera.get("config", {})
            request = SetCameraConfig.Request()
            request.cameras = [name]
            request.width = int(payload.get("width", current.get("width", 256)))
            request.height = int(
                payload.get("height", current.get("height", 256))
            )
            request.fps = float(payload.get("fps", current.get("fps", 16.0)))
            request.preserve_aspect = bool(
                payload.get(
                    "preserve_aspect",
                    current.get("preserve_aspect", True),
                )
            )
            return self._call_service(self._config_client, request)

        def apply_lag() -> dict:
            request = SetCameraLag.Request()
            request.cameras = [name]
            request.lag_seconds = requested_lag
            return self._call_service(self._lag_client, request)

        # Apply whichever change reduces memory pressure first. This avoids a
        # transient buffer rejection when resolution and lag change together.
        operations = []
        if has_lag and requested_lag <= current_lag:
            operations.append(apply_lag)
        if has_config:
            operations.append(apply_config)
        if has_lag and requested_lag > current_lag:
            operations.append(apply_lag)

        for operation in operations:
            result = operation()
            responses.append(result)
            if not result["success"]:
                return result

        if "enabled" in payload:
            request = SetCameraEnabled.Request()
            request.cameras = [name]
            request.enabled = bool(payload["enabled"])
            result = self._call_service(self._enabled_client, request)
            responses.append(result)
            if not result["success"]:
                return result

        if not responses:
            return {
                "success": False,
                "message": "No supported camera settings were supplied",
                "http_status": HTTPStatus.BAD_REQUEST,
            }
        return {
            "success": True,
            "message": "; ".join(item["message"] for item in responses),
            "http_status": HTTPStatus.OK,
        }

    def _make_handler(self):
        node = self

        class CameraRequestHandler(BaseHTTPRequestHandler):
            server_version = "BlueBoatCameraWeb/1.0"

            def log_message(self, _format, *_args) -> None:
                return

            def _send_json(self, status: int, payload: dict) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(int(status))
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _send_static(self, relative_path: str) -> None:
                # Validate the URL path lexically instead of comparing resolved
                # paths.  With ``colcon build --symlink-install``, installed web
                # assets may be symlinks back into the source tree; resolving the
                # file therefore leaves the package share directory even though
                # the requested URL is safe.
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
                path = unquote(urlparse(self.path).path)
                prefix = "/api/cameras/"
                if not path.startswith(prefix):
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                name = path[len(prefix) :].strip("/")
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if length <= 0 or length > 65536:
                        raise ValueError("invalid request length")
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    if not isinstance(payload, dict):
                        raise ValueError("JSON body must be an object")
                except (ValueError, json.JSONDecodeError) as error:
                    self._send_json(
                        HTTPStatus.BAD_REQUEST,
                        {"success": False, "message": str(error)},
                    )
                    return

                try:
                    result = node.update_camera(name, payload)
                except (TypeError, ValueError) as error:
                    self._send_json(
                        HTTPStatus.BAD_REQUEST,
                        {"success": False, "message": str(error)},
                    )
                    return
                except Exception as error:  # Keep the HTTP thread alive.
                    node.get_logger().error(
                        f"Camera web request failed for {name}: {error}"
                    )
                    self._send_json(
                        HTTPStatus.INTERNAL_SERVER_ERROR,
                        {"success": False, "message": "Internal server error"},
                    )
                    return
                status = result.pop("http_status", HTTPStatus.OK)
                self._send_json(status, result)

            def _serve_mjpeg(self, name: str) -> None:
                self.send_response(HTTPStatus.OK)
                self.send_header(
                    "Content-Type",
                    "multipart/x-mixed-replace; boundary=blueboatframe",
                )
                self.send_header("Cache-Control", "no-store, no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
                version = -1
                try:
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
