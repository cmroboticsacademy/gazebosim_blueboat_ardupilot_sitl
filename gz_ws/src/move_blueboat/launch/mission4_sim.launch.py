from launch import LaunchDescription
from launch.actions import ExecuteProcess, TimerAction
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    pkg_share = get_package_share_directory('move_blueboat')
    rviz_config = os.path.join(pkg_share, 'rviz', 'mission4_two_blueboats_mapping.rviz')

    mapper_common_params = {
        'map_frame': 'odom',
        'sensor_offset_xyz': [0.20, 0.0, -0.35],
        'sensor_offset_rpy': [0.0, 1.57079632679, 0.0],
        'voxel_size': 0.05,
        'min_range': 0.20,
        'max_range': 30.0,
    }

    return LaunchDescription([
        ExecuteProcess(
            cmd=[
                'env',
                # 'LIBGL_ALWAYS_SOFTWARE=1',
                'gz',
                'sim',
                '--force-version',
                '7',
                '-r',
                'level6.sdf',
            ],
            output='screen',
        ),

        Node(
            package='ros_ign_bridge',
            executable='parameter_bridge',
            arguments=[
                # Boat 1 / ArduPilot instance -I0 / SYSID 1
                '/model/blueboat/joint/motor_port_joint/cmd_thrust@std_msgs/msg/Float64@ignition.msgs.Double',
                '/model/blueboat/joint/motor_stbd_joint/cmd_thrust@std_msgs/msg/Float64@ignition.msgs.Double',
                '/model/blueboat/odometry@nav_msgs/msg/Odometry@ignition.msgs.Odometry',
                '/navsat@sensor_msgs/msg/NavSatFix@ignition.msgs.NavSat',
                '/bathymetry/scan@sensor_msgs/msg/LaserScan@ignition.msgs.LaserScan',
                # '/camera@sensor_msgs/msg/Image@ignition.msgs.Image',
                # '/camera_info@sensor_msgs/msg/CameraInfo@ignition.msgs.CameraInfo',

                # Boat 2 / ArduPilot instance -I1 / SYSID 2
                '/model/blueboat2/joint/motor_port_joint/cmd_thrust@std_msgs/msg/Float64@ignition.msgs.Double',
                '/model/blueboat2/joint/motor_stbd_joint/cmd_thrust@std_msgs/msg/Float64@ignition.msgs.Double',
                '/model/blueboat2/odometry@nav_msgs/msg/Odometry@ignition.msgs.Odometry',
                '/blueboat2/navsat@sensor_msgs/msg/NavSatFix@ignition.msgs.NavSat',
                '/blueboat2/bathymetry/scan@sensor_msgs/msg/LaserScan@ignition.msgs.LaserScan',
                # '/blueboat2/camera@sensor_msgs/msg/Image@ignition.msgs.Image',
                # '/blueboat2/camera_info@sensor_msgs/msg/CameraInfo@ignition.msgs.CameraInfo',

                # Boat 3 / ArduPilot instance -I1 / SYSID 3
                '/model/blueboat3/joint/motor_port_joint/cmd_thrust@std_msgs/msg/Float64@ignition.msgs.Double',
                '/model/blueboat3/joint/motor_stbd_joint/cmd_thrust@std_msgs/msg/Float64@ignition.msgs.Double',
                '/model/blueboat3/odometry@nav_msgs/msg/Odometry@ignition.msgs.Odometry',
                '/blueboat3/navsat@sensor_msgs/msg/NavSatFix@ignition.msgs.NavSat',
                '/blueboat3/bathymetry/scan@sensor_msgs/msg/LaserScan@ignition.msgs.LaserScan',
                # '/blueboat3/camera@sensor_msgs/msg/Image@ignition.msgs.Image',
                # '/blueboat3/camera_info@sensor_msgs/msg/CameraInfo@ignition.msgs.CameraInfo',

                # Boat 4 / ArduPilot instance -I1 / SYSID 4
                '/model/blueboat4/joint/motor_port_joint/cmd_thrust@std_msgs/msg/Float64@ignition.msgs.Double',
                '/model/blueboat4/joint/motor_stbd_joint/cmd_thrust@std_msgs/msg/Float64@ignition.msgs.Double',
                '/model/blueboat4/odometry@nav_msgs/msg/Odometry@ignition.msgs.Odometry',
                '/blueboat4/navsat@sensor_msgs/msg/NavSatFix@ignition.msgs.NavSat',
                '/blueboat4/bathymetry/scan@sensor_msgs/msg/LaserScan@ignition.msgs.LaserScan',
                # '/blueboat4/camera@sensor_msgs/msg/Image@ignition.msgs.Image',
                # '/blueboat4/camera_info@sensor_msgs/msg/CameraInfo@ignition.msgs.CameraInfo',
            ],
            output='screen',
        ),

        Node(
            package='move_blueboat',
            executable='bathymetry_mapper',
            name='bathymetry_mapper_blueboat',
            output='screen',
            parameters=[{
                **mapper_common_params,
                'scan_topic': '/bathymetry/scan',
                'odom_topic': '/model/blueboat/odometry',
                'cloud_topic': '/blueboat/ocean_floor/map_cloud',
            }],
        ),

        Node(
            package='move_blueboat',
            executable='bathymetry_mapper',
            name='bathymetry_mapper_blueboat2',
            output='screen',
            parameters=[{
                **mapper_common_params,
                'scan_topic': '/blueboat2/bathymetry/scan',
                'odom_topic': '/model/blueboat2/odometry',
                'cloud_topic': '/blueboat2/ocean_floor/map_cloud',
            }],
        ),
        Node(
            package='move_blueboat',
            executable='bathymetry_mapper',
            name='bathymetry_mapper_blueboat3',
            output='screen',
            parameters=[{
                **mapper_common_params,
                'scan_topic': '/blueboat3/bathymetry/scan',
                'odom_topic': '/model/blueboat3/odometry',
                'cloud_topic': '/blueboat3/ocean_floor/map_cloud',
            }],
        ),
        Node(
            package='move_blueboat',
            executable='bathymetry_mapper',
            name='bathymetry_mapper_blueboat4',
            output='screen',
            parameters=[{
                **mapper_common_params,
                'scan_topic': '/blueboat4/bathymetry/scan',
                'odom_topic': '/model/blueboat4/odometry',
                'cloud_topic': '/blueboat4/ocean_floor/map_cloud',
            }],
        ),

        Node(
            package='rviz2',
            executable='rviz2',
            arguments=['-d', rviz_config],
            output='screen',
        ),

        TimerAction(
            period=10.0,
            actions=[
                ExecuteProcess(
                    cmd=[
                        'gz',
                        'topic',
                        '-t',
                        '/camera/enable_streaming',
                        '-m',
                        'gz.msgs.Boolean',
                        '-p',
                        'data: true',
                    ],
                    output='screen',
                ),
                ExecuteProcess(
                    cmd=[
                        'gz',
                        'topic',
                        '-t',
                        '/blueboat2/camera/enable_streaming',
                        '-m',
                        'gz.msgs.Boolean',
                        '-p',
                        'data: true',
                    ],
                    output='screen',
                ),
                ExecuteProcess(
                    cmd=[
                        'gz',
                        'topic',
                        '-t',
                        '/blueboat3/camera/enable_streaming',
                        '-m',
                        'gz.msgs.Boolean',
                        '-p',
                        'data: true',
                    ],
                    output='screen',
                ),
                ExecuteProcess(
                    cmd=[
                        'gz',
                        'topic',
                        '-t',
                        '/blueboat4/camera/enable_streaming',
                        '-m',
                        'gz.msgs.Boolean',
                        '-p',
                        'data: true',
                    ],
                    output='screen',
                ),
             ],
        ),
    ])
