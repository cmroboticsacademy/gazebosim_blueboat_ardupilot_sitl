from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    LogInfo,
    OpaqueFunction,
)
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from ament_index_python.packages import get_package_share_directory
from move_blueboat.mission4_world_generator import create_seeded_world
import os


def _launch_foxglove(context):
    enabled = LaunchConfiguration("camera_foxglove").perform(context).strip().lower()
    if enabled not in ("1", "true", "yes", "on"):
        return []
    address = LaunchConfiguration("camera_foxglove_address").perform(context)
    port = LaunchConfiguration("camera_foxglove_port").perform(context)
    return [
        ExecuteProcess(
            cmd=[
                "ros2",
                "launch",
                "foxglove_bridge",
                "foxglove_bridge_launch.xml",
                f"address:={address}",
                f"port:={port}",
            ],
            output="screen",
        )
    ]


def _launch_seeded_gazebo(context):
    generated_world = create_seeded_world(
        LaunchConfiguration("seed").perform(context),
        LaunchConfiguration("world_template").perform(context),
    )

    actions = [
        LogInfo(msg=f"Mission 4 source template: {generated_world.template_path}"),
        LogInfo(msg=f"Mission 4 hazard seed: {generated_world.seed}"),
        LogInfo(msg=f"Generated Mission 4 world: {generated_world.world_path}"),
    ]

    for zone_name in sorted({p.zone.name for p in generated_world.placements}):
        zone_hazards = [
            p.entity_name
            for p in generated_world.placements
            if p.zone.name == zone_name
        ]
        actions.append(
            LogInfo(msg=f"{zone_name}: {', '.join(zone_hazards)}")
        )

    actions.append(
        ExecuteProcess(
            cmd=[
                "env",
                "gz",
                "sim",
                "--force-version",
                "7",
                "-r",
                str(generated_world.world_path),
            ],
            output="screen",
        )
    )
    return actions


def _bridge_arguments():
    arguments = []
    for boat in ("blueboat", "blueboat2", "blueboat3", "blueboat4"):
        prefix = f"/{boat}/camera"
        arguments.extend(
            [
                f"{prefix}/enable_streaming@std_msgs/msg/Bool]ignition.msgs.Boolean",
                f"{prefix}/stream_config@std_msgs/msg/String]ignition.msgs.StringMsg",
                f"{prefix}/image_raw@sensor_msgs/msg/Image[ignition.msgs.Image",
            ]
        )

    arguments.extend(
        [
            "/model/blueboat/joint/motor_port_joint/cmd_thrust@std_msgs/msg/Float64@ignition.msgs.Double",
            "/model/blueboat/joint/motor_stbd_joint/cmd_thrust@std_msgs/msg/Float64@ignition.msgs.Double",
            "/model/blueboat/odometry@nav_msgs/msg/Odometry@ignition.msgs.Odometry",
            "/navsat@sensor_msgs/msg/NavSatFix@ignition.msgs.NavSat",
            "/bathymetry/scan@sensor_msgs/msg/LaserScan@ignition.msgs.LaserScan",
            "/model/blueboat2/joint/motor_port_joint/cmd_thrust@std_msgs/msg/Float64@ignition.msgs.Double",
            "/model/blueboat2/joint/motor_stbd_joint/cmd_thrust@std_msgs/msg/Float64@ignition.msgs.Double",
            "/model/blueboat2/odometry@nav_msgs/msg/Odometry@ignition.msgs.Odometry",
            "/blueboat2/navsat@sensor_msgs/msg/NavSatFix@ignition.msgs.NavSat",
            "/blueboat2/bathymetry/scan@sensor_msgs/msg/LaserScan@ignition.msgs.LaserScan",
            "/model/blueboat3/joint/motor_port_joint/cmd_thrust@std_msgs/msg/Float64@ignition.msgs.Double",
            "/model/blueboat3/joint/motor_stbd_joint/cmd_thrust@std_msgs/msg/Float64@ignition.msgs.Double",
            "/model/blueboat3/odometry@nav_msgs/msg/Odometry@ignition.msgs.Odometry",
            "/blueboat3/navsat@sensor_msgs/msg/NavSatFix@ignition.msgs.NavSat",
            "/blueboat3/bathymetry/scan@sensor_msgs/msg/LaserScan@ignition.msgs.LaserScan",
            "/model/blueboat4/joint/motor_port_joint/cmd_thrust@std_msgs/msg/Float64@ignition.msgs.Double",
            "/model/blueboat4/joint/motor_stbd_joint/cmd_thrust@std_msgs/msg/Float64@ignition.msgs.Double",
            "/model/blueboat4/odometry@nav_msgs/msg/Odometry@ignition.msgs.Odometry",
            "/blueboat4/navsat@sensor_msgs/msg/NavSatFix@ignition.msgs.NavSat",
            "/blueboat4/bathymetry/scan@sensor_msgs/msg/LaserScan@ignition.msgs.LaserScan",
        ]
    )
    return arguments


def generate_launch_description():
    pkg_share = get_package_share_directory("move_blueboat")
    rviz_config = os.path.join(
        pkg_share, "rviz", "mission4_two_blueboats_mapping.rviz"
    )

    mapper_common_params = {
        "map_frame": "odom",
        "sensor_offset_xyz": [0.20, 0.0, -0.35],
        "sensor_offset_rpy": [0.0, 1.57079632679, 0.0],
        "voxel_size": 0.05,
        "min_range": 0.20,
        "max_range": 30.0,
    }

    actions = [
        DeclareLaunchArgument(
            "seed",
            default_value="",
            description=(
                "Integer seed for Mission 4 hazard placement. "
                "Leave empty to generate a random seed."
            ),
        ),
        DeclareLaunchArgument(
            "world_template",
            default_value="",
            description=(
                "Absolute path to the editable level6.sdf. When empty, "
                "the launch searches the current gz_ws source tree first."
            ),
        ),
        DeclareLaunchArgument(
            "camera_mode",
            default_value="4",
            choices=["1", "2", "3", "4"],
            description=(
                "Number of boat cameras to activate: 1=[blueboat], "
                "2=[blueboat, blueboat2], and so on."
            ),
        ),
        DeclareLaunchArgument("camera_start_delay", default_value="5.0"),
        DeclareLaunchArgument("camera_startup_retries", default_value="5"),
        DeclareLaunchArgument("camera_width", default_value="256"),
        DeclareLaunchArgument("camera_height", default_value="256"),
        DeclareLaunchArgument("camera_fps", default_value="16.0"),
        DeclareLaunchArgument("camera_preserve_aspect", default_value="true"),
        DeclareLaunchArgument(
            "camera_lag",
            default_value="0.0",
            description="Default artificial lag in seconds for active cameras.",
        ),
        DeclareLaunchArgument("camera_max_lag", default_value="30.0"),
        DeclareLaunchArgument("camera_max_buffer_mb", default_value="256.0"),
        DeclareLaunchArgument("camera_web", default_value="true"),
        DeclareLaunchArgument("camera_web_address", default_value="127.0.0.1"),
        DeclareLaunchArgument("camera_web_port", default_value="8080"),
        DeclareLaunchArgument("camera_web_jpeg_quality", default_value="80"),
        DeclareLaunchArgument(
            "camera_foxglove",
            default_value="false",
            description="Launch one optional Foxglove WebSocket bridge.",
        ),
        DeclareLaunchArgument("camera_foxglove_address", default_value="127.0.0.1"),
        DeclareLaunchArgument("camera_foxglove_port", default_value="8765"),
        OpaqueFunction(function=_launch_seeded_gazebo),
        Node(
            package="ros_ign_bridge",
            executable="parameter_bridge",
            arguments=_bridge_arguments(),
            output="screen",
        ),
        Node(
            package="blueboat_camera_manager",
            executable="camera_manager_node",
            name="blueboat_camera_manager",
            output="screen",
            parameters=[
                {
                    "mode": ParameterValue(
                        LaunchConfiguration("camera_mode"), value_type=int
                    ),
                    "startup_delay": ParameterValue(
                        LaunchConfiguration("camera_start_delay"), value_type=float
                    ),
                    "startup_retries": ParameterValue(
                        LaunchConfiguration("camera_startup_retries"), value_type=int
                    ),
                    "default_width": ParameterValue(
                        LaunchConfiguration("camera_width"), value_type=int
                    ),
                    "default_height": ParameterValue(
                        LaunchConfiguration("camera_height"), value_type=int
                    ),
                    "default_fps": ParameterValue(
                        LaunchConfiguration("camera_fps"), value_type=float
                    ),
                    "default_preserve_aspect": ParameterValue(
                        LaunchConfiguration("camera_preserve_aspect"), value_type=bool
                    ),
                    "default_lag_seconds": ParameterValue(
                        LaunchConfiguration("camera_lag"), value_type=float
                    ),
                    "maximum_lag_seconds": ParameterValue(
                        LaunchConfiguration("camera_max_lag"), value_type=float
                    ),
                    "maximum_buffer_mb_per_camera": ParameterValue(
                        LaunchConfiguration("camera_max_buffer_mb"), value_type=float
                    ),
                }
            ],
        ),
        Node(
            package="blueboat_camera_manager",
            executable="camera_web_node",
            name="blueboat_camera_web",
            output="screen",
            condition=IfCondition(LaunchConfiguration("camera_web")),
            parameters=[
                {
                    "address": LaunchConfiguration("camera_web_address"),
                    "port": ParameterValue(
                        LaunchConfiguration("camera_web_port"), value_type=int
                    ),
                    "jpeg_quality": ParameterValue(
                        LaunchConfiguration("camera_web_jpeg_quality"), value_type=int
                    ),
                }
            ],
        ),
        OpaqueFunction(function=_launch_foxglove),
    ]

    mapper_topics = {
        "blueboat": (
            "/bathymetry/scan",
            "/model/blueboat/odometry",
            "/blueboat/ocean_floor/map_cloud",
        ),
        "blueboat2": (
            "/blueboat2/bathymetry/scan",
            "/model/blueboat2/odometry",
            "/blueboat2/ocean_floor/map_cloud",
        ),
        "blueboat3": (
            "/blueboat3/bathymetry/scan",
            "/model/blueboat3/odometry",
            "/blueboat3/ocean_floor/map_cloud",
        ),
        "blueboat4": (
            "/blueboat4/bathymetry/scan",
            "/model/blueboat4/odometry",
            "/blueboat4/ocean_floor/map_cloud",
        ),
    }
    for name, (scan_topic, odom_topic, cloud_topic) in mapper_topics.items():
        actions.append(
            Node(
                package="move_blueboat",
                executable="bathymetry_mapper",
                name=f"bathymetry_mapper_{name}",
                output="screen",
                parameters=[
                    {
                        **mapper_common_params,
                        "scan_topic": scan_topic,
                        "odom_topic": odom_topic,
                        "cloud_topic": cloud_topic,
                    }
                ],
            )
        )

    actions.append(
        Node(
            package="rviz2",
            executable="rviz2",
            arguments=["-d", rviz_config],
            output="screen",
        )
    )
    return LaunchDescription(actions)
