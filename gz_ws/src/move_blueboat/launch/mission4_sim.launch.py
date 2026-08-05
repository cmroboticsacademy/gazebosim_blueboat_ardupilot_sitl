from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    LogInfo,
    OpaqueFunction,
    TimerAction,
)
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from ament_index_python.packages import get_package_share_directory
from move_blueboat.mission4_world_generator import create_seeded_world
import os


def _launch_seeded_gazebo(context):
    generated_world = create_seeded_world(
        LaunchConfiguration('seed').perform(context),
        LaunchConfiguration('world_template').perform(context),
    )

    actions = [
        LogInfo(msg=f'Mission 4 source template: {generated_world.template_path}'),
        LogInfo(msg=f'Mission 4 hazard seed: {generated_world.seed}'),
        LogInfo(msg=f'Generated Mission 4 world: {generated_world.world_path}'),
    ]

    for zone_name in sorted({p.zone.name for p in generated_world.placements}):
        zone_hazards = [
            p.entity_name
            for p in generated_world.placements
            if p.zone.name == zone_name
        ]
        actions.append(LogInfo(
            msg=f'{zone_name}: {", ".join(zone_hazards)}'
        ))

    actions.append(ExecuteProcess(
        cmd=[
            'env',
            # 'LIBGL_ALWAYS_SOFTWARE=1',
            'gz',
            'sim',
            '--force-version',
            '7',
            '-r',
            # '-s',
            str(generated_world.world_path),
        ],
        output='screen',
    ))
    return actions


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
        DeclareLaunchArgument(
            'seed',
            default_value='',
            description=(
                'Integer seed for Mission 4 hazard placement. '
                'Leave empty to generate a random seed.'
            ),
        ),
        DeclareLaunchArgument(
            'world_template',
            default_value='',
            description=(
                'Absolute path to the editable level6.sdf. When empty, '
                'the launch searches the current gz_ws source tree first.'
            ),
        ),
        DeclareLaunchArgument(
            'camera_mode',
            default_value='four',
            choices=['four', 'single'],
            description='four: ports 5600/5602/5604/5606; single: movable pod on 5600',
        ),
        DeclareLaunchArgument('camera_start_delay', default_value='10.0'),
        DeclareLaunchArgument('camera_startup_retries', default_value='5'),
        DeclareLaunchArgument('camera_width', default_value='256'),
        DeclareLaunchArgument('camera_height', default_value='256'),
        DeclareLaunchArgument('camera_fps', default_value='16.0'),
        DeclareLaunchArgument('camera_bitrate_kbps', default_value='800'),
        DeclareLaunchArgument('camera_preserve_aspect', default_value='false'),
        DeclareLaunchArgument('camera_single_target', default_value='blueboat'),
        OpaqueFunction(function=_launch_seeded_gazebo),

        Node(
            package='ros_ign_bridge',
            executable='parameter_bridge',
            arguments=[
                # Runtime camera controls (ROS 2 -> Gazebo Transport)
                '/blueboat/camera/enable_streaming@std_msgs/msg/Bool@ignition.msgs.Boolean',
                '/blueboat/camera/stream_config@std_msgs/msg/String@ignition.msgs.StringMsg',
                '/blueboat2/camera/enable_streaming@std_msgs/msg/Bool@ignition.msgs.Boolean',
                '/blueboat2/camera/stream_config@std_msgs/msg/String@ignition.msgs.StringMsg',
                '/blueboat3/camera/enable_streaming@std_msgs/msg/Bool@ignition.msgs.Boolean',
                '/blueboat3/camera/stream_config@std_msgs/msg/String@ignition.msgs.StringMsg',
                '/blueboat4/camera/enable_streaming@std_msgs/msg/Bool@ignition.msgs.Boolean',
                '/blueboat4/camera/stream_config@std_msgs/msg/String@ignition.msgs.StringMsg',
                '/camera_pod/camera/enable_streaming@std_msgs/msg/Bool@ignition.msgs.Boolean',
                '/camera_pod/camera/stream_config@std_msgs/msg/String@ignition.msgs.StringMsg',
                '/camera_pod/target@std_msgs/msg/String@ignition.msgs.StringMsg',

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
                # '/blueboat3/camera_info@sensor_msenable_streaminggs/msg/CameraInfo@ignition.msgs.CameraInfo',

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
            package='blueboat_camera_manager',
            executable='camera_manager_node',
            name='blueboat_camera_manager',
            output='screen',
            parameters=[{
                'mode': LaunchConfiguration('camera_mode'),
                'startup_delay': ParameterValue(
                    LaunchConfiguration('camera_start_delay'), value_type=float),
                'startup_retries': ParameterValue(
                    LaunchConfiguration('camera_startup_retries'), value_type=int),
                'default_width': ParameterValue(
                    LaunchConfiguration('camera_width'), value_type=int),
                'default_height': ParameterValue(
                    LaunchConfiguration('camera_height'), value_type=int),
                'default_fps': ParameterValue(
                    LaunchConfiguration('camera_fps'), value_type=float),
                'default_bitrate_kbps': ParameterValue(
                    LaunchConfiguration('camera_bitrate_kbps'), value_type=int),
                'default_preserve_aspect': ParameterValue(
                    LaunchConfiguration('camera_preserve_aspect'), value_type=bool),
                'single_default_target': LaunchConfiguration('camera_single_target'),
            }],
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

        # TimerAction(
        #     period=10.0,
        #     actions=[
        #         ExecuteProcess(
        #             cmd=[
        #                 'gz',
        #                 'topic',
        #                 '-t',
        #                 '/blueboat/camera/enable_streaming',
        #                 '-m',
        #                 'gz.msgs.Boolean',
        #                 '-p',
        #                 'data: true',
        #             ],
        #             output='screen',
        #         ),
        #         ExecuteProcess(
        #             cmd=[
        #                 'gz',
        #                 'topic',
        #                 '-t',
        #                 '/blueboat2/camera/enable_streaming',
        #                 '-m',
        #                 'gz.msgs.Boolean',
        #                 '-p',
        #                 'data: true',
        #             ],
        #             output='screen',
        #         ),
        #         ExecuteProcess(
        #             cmd=[
        #                 'gz',
        #                 'topic',
        #                 '-t',
        #                 '/blueboat3/camera/enable_streaming',
        #                 '-m',
        #                 'gz.msgs.Boolean',
        #                 '-p',
        #                 'data: true',
        #             ],
        #             output='screen',
        #         ),
        #         ExecuteProcess(
        #             cmd=[
        #                 'gz',
        #                 'topic',
        #                 '-t',
        #                 '/blueboat4/camera/enable_streaming',
        #                 '-m',
        #                 'gz.msgs.Boolean',
        #                 '-p',
        #                 'data: true',
        #             ],
        #             output='screen',
        #         ),
        #      ],
        # ),
    ])
