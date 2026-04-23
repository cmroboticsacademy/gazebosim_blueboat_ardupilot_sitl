#!/usr/bin/env python3
import math
import time

import rclpy
from rclpy.node import Node
from pymavlink import mavutil


class QGCFenceUploader(Node):
    def __init__(self):
        super().__init__('qgc_mixed_geofence')

        self.declare_parameter('vehicle_connection', 'udpin:0.0.0.0:14551')
        self.declare_parameter('origin_lat_deg', 40.594988)
        self.declare_parameter('origin_lon_deg', -79.999149)
        self.declare_parameter('buoy_radius_m', 5.0)

        self.vehicle_connection = str(self.get_parameter('vehicle_connection').value)
        self.origin_lat = float(self.get_parameter('origin_lat_deg').value)
        self.origin_lon = float(self.get_parameter('origin_lon_deg').value)
        self.buoy_radius_m = float(self.get_parameter('buoy_radius_m').value)

        # =========================
        # BUOYS (CIRCLES)
        # =========================
        self.buoys = [
            {'name': 'B1', 'east': 15,  'north': 90.0},
            {'name': 'B2', 'east': 12.5,  'north': 92.5},
            {'name': 'B3', 'east': 10,  'north': 95.0},

        ]

        # =========================
        # DOCKS (RECTANGLES)
        # =========================
        self.rectangles = [
            {
                'name': 'dock_1',
                'east': 0.0,
                'north': 1.8,
                'length': 6.0,
                'width': 2.0,
                'yaw': 0.0
            }
        ]

        # MAVLink constants
        self.MAV_MISSION_TYPE_FENCE = 1
        self.MAV_FRAME_GLOBAL_INT = 5
        self.MAV_CMD_NAV_FENCE_CIRCLE_EXCLUSION = 5004
        self.MAV_CMD_NAV_FENCE_POLYGON_VERTEX_EXCLUSION = 5002

        self.master = mavutil.mavlink_connection(self.vehicle_connection)

        self.get_logger().info(f'Connecting to {self.vehicle_connection}...')
        self._wait_for_vehicle()

        self.upload_fences()

        self.get_logger().info('✅ Fence upload complete')
        time.sleep(2)
        rclpy.shutdown()

    # =========================================
    # CONNECTION
    # =========================================
    def _wait_for_vehicle(self):
        deadline = time.time() + 30
        while time.time() < deadline:
            msg = self.master.recv_match(type='HEARTBEAT', blocking=True, timeout=5)
            if msg:
                self.master.target_system = msg.get_srcSystem()
                self.master.target_component = msg.get_srcComponent()
                self.get_logger().info(
                    f'Connected to system={self.master.target_system}'
                )
                return
        raise RuntimeError("No heartbeat received")

    # =========================================
    # GEO HELPERS
    # =========================================
    @staticmethod
    def offset_to_latlon(lat, lon, east, north):
        dlat = north / 111111.0
        dlon = east / (111111.0 * math.cos(math.radians(lat)))
        return lat + dlat, lon + dlon

    @staticmethod
    def rotate_point(x, y, yaw):
        return (
            x * math.cos(yaw) - y * math.sin(yaw),
            x * math.sin(yaw) + y * math.cos(yaw)
        )

    def rectangle_to_vertices(self, rect):
        hl = rect['length'] / 2.0
        hw = rect['width'] / 2.0

        local = [
            (-hl, -hw),
            ( hl, -hw),
            ( hl,  hw),
            (-hl,  hw),
        ]

        pts = []
        for x, y in local:
            rx, ry = self.rotate_point(x, y, rect['yaw'])
            pts.append((rect['east'] + rx, rect['north'] + ry))

        return pts

    # =========================================
    # BUILD FENCE ITEMS
    # =========================================
    def build_fence_items(self):
        items = []
        seq = 0

        # ---- CIRCLES ----
        for b in self.buoys:
            lat, lon = self.offset_to_latlon(
                self.origin_lat, self.origin_lon,
                b['east'], b['north']
            )

            self.get_logger().info(
                f"Circle {b['name']} @ ({lat:.7f}, {lon:.7f})"
            )

            items.append({
                'seq': seq,
                'cmd': self.MAV_CMD_NAV_FENCE_CIRCLE_EXCLUSION,
                'lat': lat,
                'lon': lon,
                'p1': self.buoy_radius_m
            })
            seq += 1

        # ---- RECTANGLES ----
        for rect in self.rectangles:
            vertices = self.rectangle_to_vertices(rect)
            vcount = len(vertices)

            self.get_logger().info(
                f"Rectangle {rect['name']} with {vcount} vertices"
            )

            for (east, north) in vertices:
                lat, lon = self.offset_to_latlon(
                    self.origin_lat, self.origin_lon,
                    east, north
                )

                items.append({
                    'seq': seq,
                    'cmd': self.MAV_CMD_NAV_FENCE_POLYGON_VERTEX_EXCLUSION,
                    'lat': lat,
                    'lon': lon,
                    'p1': vcount
                })
                seq += 1

        return items

    # =========================================
    # UPLOAD
    # =========================================
    def upload_fences(self):
        fence_items = self.build_fence_items()
        count = len(fence_items)

        self.get_logger().info(f'Uploading {count} fence items...')

        # Clear existing
        self.master.mav.mission_clear_all_send(
            self.master.target_system,
            self.master.target_component,
            self.MAV_MISSION_TYPE_FENCE,
        )

        time.sleep(1)

        # Drain old messages
        while self.master.recv_match(blocking=False):
            pass

        # Send count
        self.master.mav.mission_count_send(
            self.master.target_system,
            self.master.target_component,
            count,
            self.MAV_MISSION_TYPE_FENCE,
        )

        sent = set()
        deadline = time.time() + 30

        while time.time() < deadline:
            msg = self.master.recv_match(
                type=['MISSION_REQUEST_INT', 'MISSION_REQUEST', 'MISSION_ACK'],
                blocking=True,
                timeout=5
            )

            if msg is None:
                self.get_logger().warning("Retrying mission_count...")
                self.master.mav.mission_count_send(
                    self.master.target_system,
                    self.master.target_component,
                    count,
                    self.MAV_MISSION_TYPE_FENCE,
                )
                continue

            mtype = msg.get_type()

            # =========================
            # REQUEST HANDLER
            # =========================
            if mtype in ('MISSION_REQUEST_INT', 'MISSION_REQUEST'):
                seq = int(msg.seq)

                if seq < 0 or seq >= count:
                    continue

                item = fence_items[seq]

                self.master.mav.mission_item_int_send(
                    self.master.target_system,
                    self.master.target_component,
                    item['seq'],
                    self.MAV_FRAME_GLOBAL_INT,
                    item['cmd'],
                    0,
                    1,
                    item['p1'],  # radius OR vertex count
                    0, 0, 0,
                    int(item['lat'] * 1e7),
                    int(item['lon'] * 1e7),
                    0,
                    self.MAV_MISSION_TYPE_FENCE,
                )

                sent.add(seq)

                self.get_logger().info(
                    f"Sent item {seq} ({len(sent)}/{count})"
                )

            # =========================
            # ACK HANDLER
            # =========================
            elif mtype == 'MISSION_ACK':
                ack_type = getattr(msg, 'type', None)

                if (
                    ack_type == mavutil.mavlink.MAV_MISSION_ACCEPTED
                    and len(sent) == count
                ):
                    self.get_logger().info("✅ Fence upload accepted")
                    return

                self.get_logger().warning(
                    f"ACK received but incomplete ({len(sent)}/{count})"
                )

        raise RuntimeError("Upload timeout")


def main():
    rclpy.init()
    QGCFenceUploader()


if __name__ == '__main__':
    main()