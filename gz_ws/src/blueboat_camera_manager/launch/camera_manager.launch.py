"""Standalone launch file for the BlueBoat camera manager."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument("mode", default_value="four", choices=["four", "single"]),
        DeclareLaunchArgument("startup_delay", default_value="0.0"),
        DeclareLaunchArgument("default_lag_seconds", default_value="0.0"),
        DeclareLaunchArgument("maximum_lag_seconds", default_value="30.0"),
        DeclareLaunchArgument("single_default_target", default_value="blueboat"),
        Node(
            package="blueboat_camera_manager",
            executable="camera_manager_node",
            name="blueboat_camera_manager",
            output="screen",
            parameters=[{
                "mode": LaunchConfiguration("mode"),
                "startup_delay": ParameterValue(
                    LaunchConfiguration("startup_delay"), value_type=float
                ),
                "default_lag_seconds": ParameterValue(
                    LaunchConfiguration("default_lag_seconds"), value_type=float
                ),
                "maximum_lag_seconds": ParameterValue(
                    LaunchConfiguration("maximum_lag_seconds"), value_type=float
                ),
                "single_default_target": LaunchConfiguration("single_default_target"),
            }],
        ),
    ])
