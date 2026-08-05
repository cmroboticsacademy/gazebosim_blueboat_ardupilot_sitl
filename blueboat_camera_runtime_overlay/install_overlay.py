#!/usr/bin/env python3
"""Install the BlueBoat camera runtime overlay into a repository checkout.

This script only edits source files once during installation. Runtime camera
changes are performed through ROS 2 services and never rewrite SDF files.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

OVERLAY_ROOT = Path(__file__).resolve().parent

CAMERAS = {
    "blueboat": ("SITL_Models/Gazebo/models/blueboat/model.sdf", "/blueboat/camera", 5600),
    "blueboat2": ("SITL_Models/Gazebo/models/blueboat2/model.sdf", "/blueboat2/camera", 5602),
    "blueboat3": ("SITL_Models/Gazebo/models/blueboat3/model.sdf", "/blueboat3/camera", 5604),
    "blueboat4": ("SITL_Models/Gazebo/models/blueboat4/model.sdf", "/blueboat4/camera", 5606),
}


def atomic_write(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".camera-runtime.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def copy_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def camera_sensor_block(prefix: str, port: int) -> str:
    return f'''      <sensor name="fpv_camera" type="camera">
        <always_on>true</always_on>
        <!-- The sensor stays at a fixed maximum source resolution. The custom
             stream plugin changes encoded output size and trigger rate live. -->
        <update_rate>30</update_rate>
        <topic>{prefix}/image</topic>
        <camera>
          <triggered>true</triggered>
          <trigger_topic>{prefix}/trigger</trigger_topic>
          <horizontal_fov>1.3962634</horizontal_fov>
          <image>
            <width>640</width>
            <height>480</height>
            <format>RGB_INT8</format>
            <anti_aliasing>1</anti_aliasing>
          </image>
          <clip>
            <near>0.05</near>
            <far>100</far>
          </clip>
        </camera>
        <plugin name="BlueBoatGstCameraPlugin"
                filename="libBlueBoatGstCameraPlugin.so">
          <image_topic>{prefix}/image</image_topic>
          <enable_topic>{prefix}/enable_streaming</enable_topic>
          <config_topic>{prefix}/stream_config</config_topic>
          <trigger_topic>{prefix}/trigger</trigger_topic>
          <udp_host>127.0.0.1</udp_host>
          <udp_port>{port}</udp_port>
          <output_width>256</output_width>
          <output_height>256</output_height>
          <output_fps>16</output_fps>
          <bitrate_kbps>800</bitrate_kbps>
          <preserve_aspect>false</preserve_aspect>
        </plugin>
      </sensor>'''


def patch_camera_models(repo: Path) -> None:
    sensor_pattern = re.compile(
        r'(?P<indent>^[ \t]*)<sensor name="fpv_camera" type="camera">.*?^[ \t]*</sensor>',
        re.MULTILINE | re.DOTALL,
    )
    for name, (relative_path, prefix, port) in CAMERAS.items():
        path = repo / relative_path
        text = path.read_text(encoding="utf-8")
        if "BlueBoatGstCameraPlugin" in text and f"<udp_port>{port}</udp_port>" in text:
            print(f"already patched: {relative_path}")
            continue
        updated, count = sensor_pattern.subn(camera_sensor_block(prefix, port), text, count=1)
        if count != 1:
            raise RuntimeError(f"could not identify exactly one FPV camera sensor in {relative_path}")
        atomic_write(path, updated)
        print(f"patched: {relative_path} ({name}, UDP {port})")


def patch_world(repo: Path) -> None:
    relative_path = Path("gz_ws/src/asv_wave_sim/gz-waves-models/worlds/level6.sdf")
    path = repo / relative_path
    text = path.read_text(encoding="utf-8")
    if "model://blueboat_camera_pod" in text:
        print(f"already patched: {relative_path}")
        return

    marker = '''     <include>
      <name>blueboat4</name>
      <pose>0 -11 0 0 0 -1.5708</pose>
      <uri>model://blueboat4</uri>
    </include>'''
    if marker not in text:
        # Tolerate harmless indentation changes while still anchoring to boat 4.
        match = re.search(
            r'(?P<block>[ \t]*<include>\s*<name>blueboat4</name>.*?<uri>model://blueboat4</uri>\s*</include>)',
            text,
            re.DOTALL,
        )
        if not match:
            raise RuntimeError("could not find the blueboat4 include in level6.sdf")
        marker = match.group("block")

    addition = marker + '''

    <!-- Disabled unless camera_mode:=single enables its stream. -->
    <include>
      <name>blueboat_camera_pod</name>
      <pose>0 -5 0.28 0 0 -1.5708</pose>
      <uri>model://blueboat_camera_pod</uri>
    </include>'''
    text = text.replace(marker, addition, 1)
    atomic_write(path, text)
    print(f"patched: {relative_path}")


def patch_package_xml(repo: Path) -> None:
    relative_path = Path("gz_ws/src/move_blueboat/package.xml")
    path = repo / relative_path
    text = path.read_text(encoding="utf-8")
    if "<exec_depend>blueboat_camera_manager</exec_depend>" in text:
        return
    pattern = re.compile(r"(?P<indent>^[ \t]*)<depend>rviz2</depend>", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        raise RuntimeError("could not find rviz2 dependency in move_blueboat/package.xml")
    anchor = match.group(0)
    indent = match.group("indent")
    text = text.replace(
        anchor,
        anchor + f"\n{indent}<exec_depend>blueboat_camera_manager</exec_depend>",
        1,
    )
    atomic_write(path, text)
    print(f"patched: {relative_path}")


def patch_launch(repo: Path) -> None:
    relative_path = Path("gz_ws/src/move_blueboat/launch/mission4_sim.launch.py")
    path = repo / relative_path
    text = path.read_text(encoding="utf-8")

    import_line = "from launch_ros.actions import Node\n"
    parameter_import = "from launch_ros.parameter_descriptions import ParameterValue\n"
    if parameter_import not in text:
        if import_line not in text:
            raise RuntimeError("could not find launch_ros Node import")
        text = text.replace(import_line, import_line + parameter_import, 1)

    args_marker = "        OpaqueFunction(function=_launch_seeded_gazebo),"
    if "'camera_mode'" not in text:
        if args_marker not in text:
            raise RuntimeError("could not find OpaqueFunction launch marker")
        camera_arguments = '''        DeclareLaunchArgument(
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
'''
        text = text.replace(args_marker, camera_arguments + args_marker, 1)

    bridge_anchor = "                # Boat 1 / ArduPilot instance -I0 / SYSID 1"
    if "/camera_pod/target@std_msgs/msg/String@ignition.msgs.StringMsg" not in text:
        if bridge_anchor not in text:
            raise RuntimeError("could not find parameter_bridge Boat 1 marker")
        controls = '''                # Runtime camera controls (ROS 2 -> Gazebo Transport)
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

'''
        text = text.replace(bridge_anchor, controls + bridge_anchor, 1)

    node_anchor = '''        Node(
            package='move_blueboat',
            executable='bathymetry_mapper',
            name='bathymetry_mapper_blueboat','''
    if "package='blueboat_camera_manager'" not in text:
        if node_anchor not in text:
            raise RuntimeError("could not find first bathymetry mapper node")
        manager_node = '''        Node(
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

'''
        text = text.replace(node_anchor, manager_node + node_anchor, 1)

    atomic_write(path, text)
    print(f"patched: {relative_path}")


def validate_repo(repo: Path) -> None:
    required = [
        "gz_ws/src/move_blueboat/launch/mission4_sim.launch.py",
        "gz_ws/src/asv_wave_sim/gz-waves-models/worlds/level6.sdf",
        *[value[0] for value in CAMERAS.values()],
    ]
    missing = [item for item in required if not (repo / item).is_file()]
    if missing:
        raise RuntimeError(
            "repository root is missing expected files:\n  " + "\n  ".join(missing)
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "repository",
        nargs="?",
        default=".",
        help="path to gazebosim_blueboat_ardupilot_sitl checkout",
    )
    args = parser.parse_args()
    repo = Path(args.repository).expanduser().resolve()

    try:
        validate_repo(repo)
        copy_tree(
            OVERLAY_ROOT / "gz_ws/src/blueboat_camera_manager",
            repo / "gz_ws/src/blueboat_camera_manager",
        )
        copy_tree(
            OVERLAY_ROOT / "SITL_Models/Gazebo/models/blueboat_camera_pod",
            repo / "SITL_Models/Gazebo/models/blueboat_camera_pod",
        )
        print("copied: gz_ws/src/blueboat_camera_manager")
        print("copied: SITL_Models/Gazebo/models/blueboat_camera_pod")
        patch_camera_models(repo)
        patch_world(repo)
        patch_package_xml(repo)
        patch_launch(repo)
    except Exception as exc:  # noqa: BLE001 - installer should report one clear error
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("\nInstallation complete. Review with: git status --short && git diff")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
