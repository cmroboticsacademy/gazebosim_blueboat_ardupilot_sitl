"""Standalone BlueBoat camera manager and local web UI."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "mode", default_value="4", choices=["1", "2", "3", "4"]
            ),
            DeclareLaunchArgument("startup_delay", default_value="0.0"),
            DeclareLaunchArgument("default_width", default_value="256"),
            DeclareLaunchArgument("default_height", default_value="256"),
            DeclareLaunchArgument("default_fps", default_value="16.0"),
            DeclareLaunchArgument("default_bitrate_kbps", default_value="800"),
            DeclareLaunchArgument("default_preserve_aspect", default_value="true"),
            DeclareLaunchArgument("default_lag_seconds", default_value="0.0"),
            DeclareLaunchArgument("opencv_threads", default_value="1"),
            DeclareLaunchArgument(
                "process_without_subscribers", default_value="false"
            ),
            DeclareLaunchArgument("maximum_lag_seconds", default_value="30.0"),
            DeclareLaunchArgument("maximum_buffer_mb_per_camera", default_value="256.0"),
            DeclareLaunchArgument("web", default_value="true"),
            DeclareLaunchArgument("web_address", default_value="127.0.0.1"),
            DeclareLaunchArgument("web_port", default_value="8080"),
            DeclareLaunchArgument("web_jpeg_quality", default_value="72"),
            DeclareLaunchArgument("web_preview_fps", default_value="8.0"),
            Node(
                package="blueboat_camera_manager",
                executable="camera_manager_node",
                name="blueboat_camera_manager",
                output="screen",
                parameters=[
                    {
                        "mode": ParameterValue(
                            LaunchConfiguration("mode"), value_type=int
                        ),
                        "startup_delay": ParameterValue(
                            LaunchConfiguration("startup_delay"), value_type=float
                        ),
                        "default_width": ParameterValue(
                            LaunchConfiguration("default_width"), value_type=int
                        ),
                        "default_height": ParameterValue(
                            LaunchConfiguration("default_height"), value_type=int
                        ),
                        "default_fps": ParameterValue(
                            LaunchConfiguration("default_fps"), value_type=float
                        ),
                        "default_bitrate_kbps": ParameterValue(
                            LaunchConfiguration("default_bitrate_kbps"), value_type=int
                        ),
                        "default_preserve_aspect": ParameterValue(
                            LaunchConfiguration("default_preserve_aspect"),
                            value_type=bool,
                        ),
                        "default_lag_seconds": ParameterValue(
                            LaunchConfiguration("default_lag_seconds"),
                            value_type=float,
                        ),
                        "opencv_threads": ParameterValue(
                            LaunchConfiguration("opencv_threads"), value_type=int
                        ),
                        "process_without_subscribers": ParameterValue(
                            LaunchConfiguration("process_without_subscribers"),
                            value_type=bool,
                        ),
                        "maximum_lag_seconds": ParameterValue(
                            LaunchConfiguration("maximum_lag_seconds"),
                            value_type=float,
                        ),
                        "maximum_buffer_mb_per_camera": ParameterValue(
                            LaunchConfiguration("maximum_buffer_mb_per_camera"),
                            value_type=float,
                        ),
                    }
                ],
            ),
            Node(
                package="blueboat_camera_manager",
                executable="camera_web_node",
                name="blueboat_camera_web",
                output="screen",
                condition=IfCondition(LaunchConfiguration("web")),
                parameters=[
                    {
                        "address": LaunchConfiguration("web_address"),
                        "port": ParameterValue(
                            LaunchConfiguration("web_port"), value_type=int
                        ),
                        "jpeg_quality": ParameterValue(
                            LaunchConfiguration("web_jpeg_quality"), value_type=int
                        ),
                        "preview_max_fps": ParameterValue(
                            LaunchConfiguration("web_preview_fps"), value_type=float
                        ),
                        "opencv_threads": ParameterValue(
                            LaunchConfiguration("opencv_threads"), value_type=int
                        ),
                    }
                ],
            ),
        ]
    )
