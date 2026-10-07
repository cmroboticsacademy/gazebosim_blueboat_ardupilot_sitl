"""Launch the standalone Mission 4 findings map."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument("address", default_value="127.0.0.1"),
            DeclareLaunchArgument("port", default_value="8090"),
            DeclareLaunchArgument("latitude_deg", default_value="40.595009"),
            DeclareLaunchArgument("longitude_deg", default_value="-79.999740"),
            DeclareLaunchArgument("heading_deg", default_value="0.0"),
            DeclareLaunchArgument("path_min_distance_m", default_value="0.75"),
            Node(
                package="move_blueboat",
                executable="mission4_findings_web",
                name="mission4_findings_web",
                output="screen",
                parameters=[
                    {
                        "address": LaunchConfiguration("address"),
                        "port": ParameterValue(
                            LaunchConfiguration("port"), value_type=int
                        ),
                        "latitude_deg": ParameterValue(
                            LaunchConfiguration("latitude_deg"),
                            value_type=float,
                        ),
                        "longitude_deg": ParameterValue(
                            LaunchConfiguration("longitude_deg"),
                            value_type=float,
                        ),
                        "heading_deg": ParameterValue(
                            LaunchConfiguration("heading_deg"), value_type=float
                        ),
                        "path_min_distance_m": ParameterValue(
                            LaunchConfiguration("path_min_distance_m"),
                            value_type=float,
                        ),
                    }
                ],
            ),
        ]
    )
