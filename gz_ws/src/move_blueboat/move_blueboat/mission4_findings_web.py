#!/usr/bin/env python3
"""Mission 4 findings map: RViz clicked points + replayed boat tracks."""

from __future__ import annotations

import csv
import io
import json
import math
import mimetypes
import threading
import time
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import PointStamped
from nav_msgs.msg import Odometry
import rclpy
from rclpy.node import Node

from move_blueboat.mission4_geo import local_to_wgs84


class Mission4FindingsWeb(Node):
    """Listen for RViz findings and expose them on a lightweight local map."""

    BOAT_TOPICS = {
        "blueboat": "/model/blueboat/odometry",
        "blueboat2": "/model/blueboat2/odometry",
        "blueboat3": "/model/blueboat3/odometry",
        "blueboat4": "/model/blueboat4/odometry",
    }
    CLASSIFICATIONS = {"unclassified", "hazard", "non-hazard"}

    def __init__(self) -> None:
        super().__init__("mission4_findings_web")

        self.declare_parameter("address", "127.0.0.1")
        self.declare_parameter("port", 8090)
        self.declare_parameter("latitude_deg", 40.595009)
        self.declare_parameter("longitude_deg", -79.999740)
        self.declare_parameter("heading_deg", 0.0)
        self.declare_parameter("elevation_m", 0.0)
        self.declare_parameter("path_min_distance_m", 0.75)
        self.declare_parameter("max_path_points_per_boat", 5000)

        self.address = str(self.get_parameter("address").value)
        self.port = int(self.get_parameter("port").value)
        self.latitude_deg = float(self.get_parameter("latitude_deg").value)
        self.longitude_deg = float(self.get_parameter("longitude_deg").value)
        self.heading_deg = float(self.get_parameter("heading_deg").value)
        self.elevation_m = float(self.get_parameter("elevation_m").value)
        self.path_min_distance_m = max(
            0.05, float(self.get_parameter("path_min_distance_m").value)
        )
        self.max_path_points = max(
            100, int(self.get_parameter("max_path_points_per_boat").value)
        )

        self.web_root = Path(
            get_package_share_directory("move_blueboat")
        ) / "findings_web"

        self._lock = threading.Lock()
        self._next_finding_id = 1
        self._findings: list[dict] = []
        self._paths = {
            boat: deque(maxlen=self.max_path_points)
            for boat in self.BOAT_TOPICS
        }
        self._last_path_xy: dict[str, tuple[float, float] | None] = {
            boat: None for boat in self.BOAT_TOPICS
        }

        self._clicked_subscription = self.create_subscription(
            PointStamped, "/clicked_point", self._on_clicked_point, 10
        )
        self._odom_subscriptions = []
        for boat, topic in self.BOAT_TOPICS.items():
            self._odom_subscriptions.append(
                self.create_subscription(
                    Odometry,
                    topic,
                    lambda message, name=boat: self._on_odometry(name, message),
                    20,
                )
            )

        handler = self._make_handler()
        self._http_server = ThreadingHTTPServer(
            (self.address, self.port), handler
        )
        self._http_server.daemon_threads = True
        self._http_thread = threading.Thread(
            target=self._http_server.serve_forever,
            name="mission4-findings-http",
            daemon=True,
        )
        self._http_thread.start()

        self.get_logger().info(
            "Mission 4 Findings Map listening for /clicked_point at "
            f"http://{self.address}:{self.port}"
        )
        self.get_logger().info(
            "Origin %.6f, %.6f; replay map heading %.1f deg"
            % (self.latitude_deg, self.longitude_deg, self.heading_deg)
        )

    def _local_to_wgs84(self, x: float, y: float) -> tuple[float, float]:
        return local_to_wgs84(
            x,
            y,
            self.latitude_deg,
            self.longitude_deg,
            self.heading_deg,
            self.elevation_m,
        )

    def _on_clicked_point(self, message: PointStamped) -> None:
        x = float(message.point.x)
        y = float(message.point.y)
        z = float(message.point.z)
        latitude, longitude = self._local_to_wgs84(x, y)
        stamp = (
            float(message.header.stamp.sec)
            + float(message.header.stamp.nanosec) / 1_000_000_000.0
        )
        with self._lock:
            finding = {
                "id": self._next_finding_id,
                "x": x,
                "y": y,
                "z": z,
                "latitude": latitude,
                "longitude": longitude,
                "frame_id": message.header.frame_id or "odom",
                "ros_time_sec": stamp,
                "classification": "unclassified",
                "object_guess": "",
                "confidence": 50,
                "notes": "",
                "created_at_unix": time.time(),
            }
            self._next_finding_id += 1
            self._findings.append(finding)

        self.get_logger().info(
            "Finding %d: local=(%.2f, %.2f, %.2f), gps=(%.7f, %.7f)"
            % (finding["id"], x, y, z, latitude, longitude)
        )

    def _on_odometry(self, boat: str, message: Odometry) -> None:
        x = float(message.pose.pose.position.x)
        y = float(message.pose.pose.position.y)

        with self._lock:
            previous = self._last_path_xy[boat]
            if previous is not None:
                if math.hypot(x - previous[0], y - previous[1]) < (
                    self.path_min_distance_m
                ):
                    return

        latitude, longitude = self._local_to_wgs84(x, y)
        with self._lock:
            self._paths[boat].append([latitude, longitude])
            self._last_path_xy[boat] = (x, y)

    def state(self) -> dict:
        with self._lock:
            findings = [dict(item) for item in self._findings]
            paths = {
                boat: list(points) for boat, points in self._paths.items()
            }
        return {
            "origin": {
                "latitude": self.latitude_deg,
                "longitude": self.longitude_deg,
                "heading_deg": self.heading_deg,
            },
            "findings": findings,
            "paths": paths,
        }

    def update_finding(self, finding_id: int, payload: dict) -> dict | None:
        with self._lock:
            finding = next(
                (item for item in self._findings if item["id"] == finding_id),
                None,
            )
            if finding is None:
                return None

            classification = str(
                payload.get("classification", finding["classification"])
            ).strip().lower()
            if classification not in self.CLASSIFICATIONS:
                raise ValueError("invalid classification")

            confidence = int(payload.get("confidence", finding["confidence"]))
            confidence = max(0, min(100, confidence))
            object_guess = str(
                payload.get("object_guess", finding["object_guess"])
            ).strip()[:80]
            notes = str(payload.get("notes", finding["notes"])).strip()[:500]

            finding.update(
                classification=classification,
                confidence=confidence,
                object_guess=object_guess,
                notes=notes,
            )
            return dict(finding)

    def delete_finding(self, finding_id: int) -> bool:
        with self._lock:
            before = len(self._findings)
            self._findings = [
                item for item in self._findings
                if item["id"] != finding_id
            ]
            return len(self._findings) != before

    def clear_findings(self) -> None:
        with self._lock:
            self._findings.clear()
            self._next_finding_id = 1

    def export_csv(self) -> bytes:
        fields = [
            "id", "classification", "object_guess", "confidence", "notes",
            "x", "y", "z", "latitude", "longitude", "frame_id",
            "ros_time_sec",
        ]
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        with self._lock:
            for finding in self._findings:
                writer.writerow(finding)
        return output.getvalue().encode("utf-8")

    def _make_handler(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "Mission4Findings/1.0"

            def log_message(self, format_string, *args):
                owner.get_logger().debug(format_string % args)

            def _send(
                self,
                status: int,
                body: bytes,
                content_type: str,
                filename: str | None = None,
            ) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                if filename:
                    self.send_header(
                        "Content-Disposition",
                        f'attachment; filename="{filename}"',
                    )
                self.end_headers()
                self.wfile.write(body)

            def _json(self, status: int, value: object) -> None:
                body = json.dumps(value, separators=(",", ":")).encode("utf-8")
                self._send(status, body, "application/json; charset=utf-8")

            def _read_json(self) -> dict:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0 or length > 65536:
                    raise ValueError("request body too large")
                raw = self.rfile.read(length) if length else b"{}"
                value = json.loads(raw.decode("utf-8"))
                if not isinstance(value, dict):
                    raise ValueError("JSON body must be an object")
                return value

            def do_GET(self):
                path = unquote(urlparse(self.path).path)

                if path == "/api/state":
                    self._json(HTTPStatus.OK, owner.state())
                    return

                if path == "/api/export.json":
                    body = json.dumps(
                        owner.state(), indent=2, sort_keys=True
                    ).encode("utf-8")
                    self._send(
                        HTTPStatus.OK,
                        body,
                        "application/json; charset=utf-8",
                        "mission4_findings.json",
                    )
                    return

                if path == "/api/export.csv":
                    self._send(
                        HTTPStatus.OK,
                        owner.export_csv(),
                        "text/csv; charset=utf-8",
                        "mission4_findings.csv",
                    )
                    return

                if path == "/":
                    path = "/index.html"
                candidate = (owner.web_root / path.lstrip("/")).resolve()
                try:
                    candidate.relative_to(owner.web_root.resolve())
                except ValueError:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                if not candidate.is_file():
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return

                body = candidate.read_bytes()
                content_type = (
                    mimetypes.guess_type(candidate.name)[0]
                    or "application/octet-stream"
                )
                if content_type.startswith("text/") or content_type in (
                    "application/javascript",
                    "application/json",
                ):
                    content_type += "; charset=utf-8"
                self._send(HTTPStatus.OK, body, content_type)

            def do_POST(self):
                path = unquote(urlparse(self.path).path)
                try:
                    if path == "/api/clear":
                        owner.clear_findings()
                        self._json(HTTPStatus.OK, {"ok": True})
                        return

                    parts = path.strip("/").split("/")
                    if len(parts) < 3 or parts[:2] != ["api", "findings"]:
                        self.send_error(HTTPStatus.NOT_FOUND)
                        return

                    finding_id = int(parts[2])
                    if len(parts) == 4 and parts[3] == "delete":
                        deleted = owner.delete_finding(finding_id)
                        self._json(
                            HTTPStatus.OK if deleted else HTTPStatus.NOT_FOUND,
                            {"ok": deleted},
                        )
                        return
                    if len(parts) != 3:
                        self.send_error(HTTPStatus.NOT_FOUND)
                        return

                    updated = owner.update_finding(
                        finding_id, self._read_json()
                    )
                    if updated is None:
                        self._json(
                            HTTPStatus.NOT_FOUND,
                            {"error": "finding not found"},
                        )
                        return
                    self._json(HTTPStatus.OK, updated)
                except (ValueError, json.JSONDecodeError) as error:
                    self._json(
                        HTTPStatus.BAD_REQUEST, {"error": str(error)}
                    )

        return Handler

    def destroy_node(self):
        self._http_server.shutdown()
        self._http_server.server_close()
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = Mission4FindingsWeb()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
