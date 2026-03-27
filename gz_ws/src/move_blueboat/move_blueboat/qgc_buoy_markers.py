#!/usr/bin/env python3
import math
import time

import rclpy
from rclpy.node import Node
from pymavlink import mavutil


class QGCBuoyGeofenceUploader(Node):
    def __init__(self):
        super().__init__('qgc_buoy_markers')

        # Listen to the MAVProxy/ArduPilot forwarded stream from:
        # sim_vehicle.py ... --out=udp:127.0.0.1:14551
        self.declare_parameter('vehicle_connection', 'udpin:0.0.0.0:14551')

        # Must match sim_vehicle.py -l LAT,LON,ALT,HDG
        self.declare_parameter('origin_lat_deg', 55.99541530863445)
        self.declare_parameter('origin_lon_deg', -3.3010225004910683)

        # Fence radius for each buoy in meters
        self.declare_parameter('buoy_radius_m', 5.0)

        self.vehicle_connection = str(self.get_parameter('vehicle_connection').value)
        self.origin_lat = float(self.get_parameter('origin_lat_deg').value)
        self.origin_lon = float(self.get_parameter('origin_lon_deg').value)
        self.buoy_radius_m = float(self.get_parameter('buoy_radius_m').value)

        # Match these to your Gazebo buoy poses
        # Gazebo X -> East, Gazebo Y -> North
        self.buoys = [
            {'name': 'B1', 'east_m': 15.0,  'north_m': 10.0},
            {'name': 'B2', 'east_m': -20.0, 'north_m': 5.0},
            {'name': 'B3', 'east_m': 30.0,  'north_m': -12.0},
        ]

        # Use explicit numeric command IDs to avoid pymavlink enum/version issues
        self.MAV_MISSION_TYPE_FENCE = 1
        self.MAV_FRAME_GLOBAL_INT = 5
        self.MAV_CMD_NAV_FENCE_CIRCLE_EXCLUSION = 5004

        self.master = mavutil.mavlink_connection(self.vehicle_connection)
        self.get_logger().info(f'Connecting to vehicle at {self.vehicle_connection} ...')

        self._wait_for_vehicle()
        self.upload_buoy_fences()

        self.get_logger().info('Buoy geofences uploaded successfully.')
        time.sleep(2.0)
        rclpy.shutdown()

    def _wait_for_vehicle(self):
        deadline = time.time() + 30.0
        while time.time() < deadline:
            msg = self.master.recv_match(type='HEARTBEAT', blocking=True, timeout=5)
            if msg is None:
                self.get_logger().info('Waiting for HEARTBEAT...')
                continue

            sysid = msg.get_srcSystem()
            compid = msg.get_srcComponent()

            if sysid == 0:
                continue

            self.master.target_system = sysid
            self.master.target_component = compid
            self.get_logger().info(f'Connected to system={sysid} component={compid}')
            return

        raise RuntimeError('Timed out waiting for valid vehicle HEARTBEAT')

    @staticmethod
    def offset_to_latlon(lat_deg, lon_deg, east_m, north_m):
        dlat = north_m / 111111.0
        dlon = east_m / (111111.0 * math.cos(math.radians(lat_deg)))
        return lat_deg + dlat, lon_deg + dlon

    def upload_buoy_fences(self):
        fence_items = []

        for i, buoy in enumerate(self.buoys):
            lat_deg, lon_deg = self.offset_to_latlon(
                self.origin_lat,
                self.origin_lon,
                buoy['east_m'],
                buoy['north_m'],
            )

            self.get_logger().info(
                f"{buoy['name']} -> lat={lat_deg:.7f}, lon={lon_deg:.7f}, radius={self.buoy_radius_m:.1f}m"
            )

            fence_items.append({
                'seq': i,
                'frame': self.MAV_FRAME_GLOBAL_INT,
                'command': self.MAV_CMD_NAV_FENCE_CIRCLE_EXCLUSION,
                'x': int(lat_deg * 1e7),
                'y': int(lon_deg * 1e7),
                'z': 0.0,
                'radius': self.buoy_radius_m,   # param1
            })

        count = len(fence_items)

        self.get_logger().info('Clearing existing geofence...')
        self.master.mav.mission_clear_all_send(
            self.master.target_system,
            self.master.target_component,
            self.MAV_MISSION_TYPE_FENCE,
        )

        time.sleep(1.0)

        # Drain stale messages so old ACKs don't confuse the upload
        while self.master.recv_match(blocking=False):
            pass

        self.get_logger().info(f'Uploading {count} geofence items...')

        self.master.mav.mission_count_send(
            self.master.target_system,
            self.master.target_component,
            count,
            self.MAV_MISSION_TYPE_FENCE,
        )

        sent = set()
        deadline = time.time() + 30.0

        while time.time() < deadline:
            msg = self.master.recv_match(
                type=['MISSION_REQUEST_INT', 'MISSION_REQUEST', 'MISSION_ACK'],
                blocking=True,
                timeout=5,
            )

            if msg is None:
                self.get_logger().warning('Retrying fence MISSION_COUNT...')
                self.master.mav.mission_count_send(
                    self.master.target_system,
                    self.master.target_component,
                    count,
                    self.MAV_MISSION_TYPE_FENCE,
                )
                continue

            mtype = msg.get_type()

            if mtype in ('MISSION_REQUEST_INT', 'MISSION_REQUEST'):
                seq = int(msg.seq)

                # Only answer requests for the fence mission type
                req_type = getattr(msg, 'mission_type', self.MAV_MISSION_TYPE_FENCE)
                if req_type != self.MAV_MISSION_TYPE_FENCE:
                    self.get_logger().warning(
                        f'Ignoring request for mission_type={req_type}, expected fence type'
                    )
                    continue

                if seq < 0 or seq >= count:
                    self.get_logger().warning(f'Ignoring invalid requested seq {seq}')
                    continue

                item = fence_items[seq]

                self.master.mav.mission_item_int_send(
                    self.master.target_system,
                    self.master.target_component,
                    item['seq'],
                    item['frame'],
                    item['command'],
                    0,              # current
                    1,              # autocontinue
                    item['radius'], # param1: radius meters
                    0.0,            # param2
                    0.0,            # param3
                    0.0,            # param4
                    item['x'],      # lat * 1e7
                    item['y'],      # lon * 1e7
                    item['z'],      # altitude (unused here)
                    self.MAV_MISSION_TYPE_FENCE,
                )

                sent.add(seq)
                self.get_logger().info(f"Sent fence item seq={seq} ({len(sent)}/{count})")
                continue

            if mtype == 'MISSION_ACK':
                ack_type = getattr(msg, 'type', None)
                ack_mission_type = getattr(msg, 'mission_type', self.MAV_MISSION_TYPE_FENCE)

                if ack_mission_type != self.MAV_MISSION_TYPE_FENCE:
                    self.get_logger().warning(
                        f'Ignoring ACK for mission_type={ack_mission_type}'
                    )
                    continue

                if ack_type == mavutil.mavlink.MAV_MISSION_ACCEPTED and len(sent) == count:
                    self.get_logger().info('Fence mission accepted.')
                    return

                self.get_logger().warning(
                    f'Ignoring premature/failed ACK type={ack_type} with {len(sent)}/{count} items sent'
                )

        raise RuntimeError('Geofence upload timed out')


def main():
    rclpy.init()
    QGCBuoyGeofenceUploader()


if __name__ == '__main__':
    main()