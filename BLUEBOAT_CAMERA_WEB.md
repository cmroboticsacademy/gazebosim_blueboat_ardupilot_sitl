# BlueBoat ROS 2 camera manager and local website

## Camera activation and Gazebo RTF

The base parameter bridge no longer subscribes permanently to all four Gazebo
image topics. The camera manager starts a dedicated `ros_gz_bridge`
`parameter_bridge` process only for a camera that is both inside `camera_mode`
and enabled. Disabling a camera publishes the disable command and terminates its
image bridge. With no image subscriber, Gazebo can omit that rendering sensor
from its scheduled sensor set.

The manager also requests Gazebo's built-in `<image topic>/set_rate` service so
the sensor update schedule follows the configured FPS rather than remaining at
the SDF maximum of 60 Hz. The trigger plugin remains as an additional gate.

Four simultaneous feeds still require four Gazebo camera renders. Disabling
unused cameras, lowering FPS, and lowering the Gazebo source resolution are the
changes that affect Gazebo rendering cost. Output size changes occur after the
fixed 640x480 Gazebo render and therefore mostly affect ROS/web CPU and memory.

## Web UI

The interface contains:

1. a multi-camera selector with **Select all active BlueBoats**;
2. one status card per boat;
3. shared batch controls for activeness, FPS, size, bitrate, lag, and scaling;
4. an **Active camera feeds** grid containing every enabled camera.

The feeds open automatically and follow every processed ROS frame by default.
The browser does not intentionally drop frames when
`camera_web_preview_fps:=0.0`. The web node still creates image subscriptions
only while a browser is actually viewing the MJPEG endpoint.

The bitrate option controls JPEG compression for the browser feed. ROS
`sensor_msgs/Image` topics remain uncompressed.

## Dependencies

```bash
sudo apt update
sudo apt install -y python3-opencv python3-numpy
```

Optional Foxglove:

```bash
sudo apt install -y ros-$ROS_DISTRO-foxglove-bridge
```

## Rebuild inside Docker

```bash
cd ~/gz_ws
source /opt/ros/$ROS_DISTRO/setup.bash

colcon build \
  --symlink-install \
  --merge-install \
  --packages-select blueboat_camera_manager move_blueboat \
  --cmake-clean-cache

source install/setup.bash
```

## Launch

```bash
ros2 launch move_blueboat mission4_sim.launch.py \
  camera_mode:=4 \
  camera_start_delay:=5.0 \
  camera_width:=256 \
  camera_height:=256 \
  camera_fps:=16.0 \
  camera_bitrate_kbps:=800 \
  camera_preserve_aspect:=true \
  camera_lag:=0.0 \
  camera_opencv_threads:=1 \
  camera_process_without_subscribers:=false \
  camera_manage_image_bridges:=true \
  camera_image_bridge_package:=ros_gz_bridge \
  camera_set_gazebo_sensor_rate:=true \
  camera_web:=true \
  camera_web_address:=127.0.0.1 \
  camera_web_port:=8080 \
  camera_web_preview_fps:=0.0
```

Open `http://127.0.0.1:8080`.

If the installation exposes only the compatibility package, launch with:

```bash
camera_image_bridge_package:=ros_ign_bridge
```

## Verify true Gazebo deactivation

Check the manager state:

```bash
ros2 service call /blueboat_camera_manager/status \
  std_srvs/srv/Trigger "{}"
```

For an enabled camera, state should contain:

```json
"image_bridge_running": true
```

After disabling it through the UI, the value should become false. Confirm the
Gazebo image topic has no subscriber:

```bash
gz topic -i -t /blueboat/camera/image_raw
```

Confirm the child bridge disappears from the process list:

```bash
pgrep -af 'parameter_bridge.*blueboat/camera/image_raw'
```

The other non-camera bridge remains running normally.

## Compare RTF

Use a repeatable test and allow several seconds after each change:

```bash
gz topic -e -t /stats | grep -m 10 real_time_factor
```

Compare these states:

1. all four cameras enabled;
2. only `blueboat` enabled;
3. all cameras disabled.

If RTF remains unchanged after `image_bridge_running` becomes false, inspect
other rendering sensors. The world also contains GPU bathymetry lidars and wave
visual rendering, which may dominate the rendering cost on a particular GPU or
Docker configuration.
