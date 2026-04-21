#!/usr/bin/env python3
import math
from typing import Dict, Tuple, List

import rclpy
from rclpy.node import Node

from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan, PointCloud2
from std_msgs.msg import Header
from sensor_msgs_py import point_cloud2


def quat_to_rot(qx, qy, qz, qw):
    xx = qx * qx
    yy = qy * qy
    zz = qz * qz
    xy = qx * qy
    xz = qx * qz
    yz = qy * qz
    wx = qw * qx
    wy = qw * qy
    wz = qw * qz

    return [
        [1.0 - 2.0 * (yy + zz), 2.0 * (xy - wz),       2.0 * (xz + wy)],
        [2.0 * (xy + wz),       1.0 - 2.0 * (xx + zz), 2.0 * (yz - wx)],
        [2.0 * (xz - wy),       2.0 * (yz + wx),       1.0 - 2.0 * (xx + yy)],
    ]


def rpy_to_rot(roll, pitch, yaw):
    cr = math.cos(roll)
    sr = math.sin(roll)
    cp = math.cos(pitch)
    sp = math.sin(pitch)
    cy = math.cos(yaw)
    sy = math.sin(yaw)

    return [
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
        [-sp,     cp * sr,                cp * cr],
    ]


def matmul3(a, b):
    return [
        [
            a[0][0] * b[0][j] + a[0][1] * b[1][j] + a[0][2] * b[2][j]
            for j in range(3)
        ],
        [
            a[1][0] * b[0][j] + a[1][1] * b[1][j] + a[1][2] * b[2][j]
            for j in range(3)
        ],
        [
            a[2][0] * b[0][j] + a[2][1] * b[1][j] + a[2][2] * b[2][j]
            for j in range(3)
        ],
    ]


def matvec3(m, v):
    return [
        m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
        m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
        m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2],
    ]


class BathymetryMapper(Node):
    def __init__(self):
        super().__init__('bathymetry_mapper')

        self.declare_parameter('scan_topic', '/bathymetry/scan')
        self.declare_parameter('odom_topic', '/model/blueboat/odometry')
        self.declare_parameter('map_frame', 'odom')
        self.declare_parameter('sensor_offset_xyz', [0.0, 0.0, -0.10])
        self.declare_parameter('sensor_offset_rpy', [0.0, -1.57079632679, 0.0])
        self.declare_parameter('voxel_size', 0.15)
        self.declare_parameter('min_range', 0.25)
        self.declare_parameter('max_range', 25.0)

        scan_topic = self.get_parameter('scan_topic').value
        odom_topic = self.get_parameter('odom_topic').value
        self.map_frame = self.get_parameter('map_frame').value
        self.sensor_offset_xyz = list(self.get_parameter('sensor_offset_xyz').value)
        self.sensor_offset_rpy = list(self.get_parameter('sensor_offset_rpy').value)
        self.voxel_size = float(self.get_parameter('voxel_size').value)
        self.min_range = float(self.get_parameter('min_range').value)
        self.max_range = float(self.get_parameter('max_range').value)

        self.latest_odom = None
        self.cloud_pub = self.create_publisher(PointCloud2, '/ocean_floor/map_cloud', 1)
        self.scan_sub = self.create_subscription(LaserScan, scan_topic, self.scan_cb, 10)
        self.odom_sub = self.create_subscription(Odometry, odom_topic, self.odom_cb, 20)

        self.points: Dict[Tuple[int, int, int], Tuple[float, float, float]] = {}
        self.publish_timer = self.create_timer(1.0, self.publish_cloud)

        self.get_logger().info('Bathymetry mapper started.')

    def odom_cb(self, msg: Odometry):
        self.latest_odom = msg

    def scan_cb(self, scan: LaserScan):
        if self.latest_odom is None:
            return

        pose = self.latest_odom.pose.pose
        px = pose.position.x
        py = pose.position.y
        pz = pose.position.z
        qx = pose.orientation.x
        qy = pose.orientation.y
        qz = pose.orientation.z
        qw = pose.orientation.w

        r_world_body = quat_to_rot(qx, qy, qz, qw)
        r_body_sensor = rpy_to_rot(
            self.sensor_offset_rpy[0],
            self.sensor_offset_rpy[1],
            self.sensor_offset_rpy[2]
        )
        r_world_sensor = matmul3(r_world_body, r_body_sensor)

        sensor_offset_world = matvec3(r_world_body, self.sensor_offset_xyz)
        sensor_origin_world = [
            px + sensor_offset_world[0],
            py + sensor_offset_world[1],
            pz + sensor_offset_world[2],
        ]

        angle = scan.angle_min
        for r in scan.ranges:
            if math.isinf(r) or math.isnan(r):
                angle += scan.angle_increment
                continue
            if r < max(scan.range_min, self.min_range) or r > min(scan.range_max, self.max_range):
                angle += scan.angle_increment
                continue

            p_sensor = [r * math.cos(angle), r * math.sin(angle), 0.0]
            p_world_rel = matvec3(r_world_sensor, p_sensor)
            p_world = [
                sensor_origin_world[0] + p_world_rel[0],
                sensor_origin_world[1] + p_world_rel[1],
                sensor_origin_world[2] + p_world_rel[2],
            ]

            key = (
                int(math.floor(p_world[0] / self.voxel_size)),
                int(math.floor(p_world[1] / self.voxel_size)),
                int(math.floor(p_world[2] / self.voxel_size)),
            )
            self.points[key] = (p_world[0], p_world[1], p_world[2])

            angle += scan.angle_increment

    def publish_cloud(self):
        pts: List[Tuple[float, float, float]] = list(self.points.values())
        header = Header()
        header.stamp = self.get_clock().now().to_msg()
        header.frame_id = self.map_frame
        msg = point_cloud2.create_cloud_xyz32(header, pts)
        self.cloud_pub.publish(msg)


def main():
    rclpy.init()
    node = BathymetryMapper()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()