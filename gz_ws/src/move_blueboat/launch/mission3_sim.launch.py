from launch import LaunchDescription
from launch.actions import ExecuteProcess, TimerAction
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os

def generate_launch_description():
    pkg_share = get_package_share_directory('move_blueboat')
    rviz_config = os.path.join(pkg_share, 'rviz', 'ocean_floor_mapping.rviz')

    return LaunchDescription([
        ExecuteProcess(
            cmd=['env', 'gz', 'sim', '--force-version', '7','-r', 'level5.sdf'],
            output='screen'
        ),

        Node(
            package='ros_ign_bridge',
            executable='parameter_bridge',
            arguments=[
                '/model/blueboat/joint/motor_port_joint/cmd_thrust@std_msgs/msg/Float64@ignition.msgs.Double',
                '/model/blueboat/joint/motor_stbd_joint/cmd_thrust@std_msgs/msg/Float64@ignition.msgs.Double',
                '/model/blueboat/odometry@nav_msgs/msg/Odometry@ignition.msgs.Odometry',
                '/navsat@sensor_msgs/msg/NavSatFix@ignition.msgs.NavSat',
                '/bathymetry/scan@sensor_msgs/msg/LaserScan@ignition.msgs.LaserScan',
            ],
            output='screen'
        ),


        Node(
            package='move_blueboat',
            executable='bathymetry_mapper',
            name='bathymetry_mapper',
            output='screen',
            parameters=[{
            'scan_topic': '/bathymetry/scan',
            'odom_topic': '/model/blueboat/odometry',
            'map_frame': 'odom',
            'sensor_offset_xyz': [0.20, 0.0, -0.35],
            'sensor_offset_rpy': [0.0, 1.57079632679, 0.0],
            'voxel_size': 0.05,
            'min_range': 0.20,
            'max_range': 30.0,
            }]
        ),

        Node(
            package='rviz2',
            executable='rviz2',
            arguments=['-d', rviz_config],
            output='screen'
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
                )
            ],
        ),
    ])