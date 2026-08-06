# BlueBoat ROS 2 camera manager and local website

## What changed

- `camera_mode` is now numeric: `1`, `2`, `3`, or `4`.
  - `1`: `blueboat`
  - `2`: `blueboat`, `blueboat2`
  - `3`: adds `blueboat3`
  - `4`: adds `blueboat4`
- The single movable camera-pod mode is removed.
- RQT camera management and the UDP/SDP camera ports are removed.
- Each enabled camera publishes standard ROS 2 topics:
  - `/<boat>/camera/image`
  - `/<boat>/camera/camera_info`
- The raw Gazebo bridge topics are `/<boat>/camera/image_raw`.
- Boat camera sensors remain fixed at a `640x480` raw render size; larger ROS
  output sizes are upscaled and do not add source detail.
- A local website provides camera selection, enable/disable, resolution, FPS,
  aspect-ratio, and lag controls plus live MJPEG tiles.
- Foxglove Bridge is optional and uses one WebSocket port instead of one UDP
  port per camera.

## Dependencies

Use the same ROS distribution already configured for this project:

```bash
sudo apt update
sudo apt install -y \
  ros-$ROS_DISTRO-cv-bridge \
  python3-opencv \
  python3-numpy
```

Optional Foxglove bridge:

```bash
sudo apt install -y ros-$ROS_DISTRO-foxglove-bridge
```

The GStreamer packages that were required only for camera UDP streaming are no
longer required by `blueboat_camera_manager`.

## Build

```bash
cd gazebosim_blueboat_ardupilot_sitl/gz_ws
source /opt/ros/$ROS_DISTRO/setup.bash
rosdep install --from-paths src --ignore-src -r -y
colcon build \
  --symlink-install \
  --merge-install \
  --packages-select blueboat_camera_manager move_blueboat \
  --cmake-clean-cache
source install/setup.bash
```

If this workspace previously built the old camera interfaces and CMake reports
stale generated files, remove only the old package build directory and rebuild:

```bash
rm -rf build/blueboat_camera_manager
colcon build --symlink-install --merge-install \
  --packages-select blueboat_camera_manager move_blueboat
source install/setup.bash
```

## Launch Mission 4

Example with two cameras and a default 0.5 second lag:

```bash
ros2 launch move_blueboat mission4_sim.launch.py \
  camera_mode:=2 \
  camera_lag:=0.5
```

Full camera arguments:

```bash
ros2 launch move_blueboat mission4_sim.launch.py \
  camera_mode:=4 \
  camera_start_delay:=5.0 \
  camera_width:=256 \
  camera_height:=256 \
  camera_fps:=16.0 \
  camera_preserve_aspect:=true \
  camera_lag:=0.0 \
  camera_web:=true \
  camera_web_address:=127.0.0.1 \
  camera_web_port:=8080
```

Open:

```text
http://127.0.0.1:8080
```

The web server binds to localhost by default. To access it from another machine,
set `camera_web_address:=0.0.0.0` and use normal network/firewall precautions.

## RViz

Add an RViz **Camera** display and select:

```text
/blueboat/camera/image
```

Its matching camera-info topic is:

```text
/blueboat/camera/camera_info
```

Use the corresponding `blueboat2`, `blueboat3`, or `blueboat4` namespace for the
other boats. The image topic is enabled/disabled, resized, frame-limited, and
delayed by the same manager used by the website.
The manager also derives `odom` to `<boat>/camera_optical_frame` transforms from
each boat's odometry, so the RViz **Camera** display receives both calibrated
`CameraInfo` and a transformable optical frame.

## Optional Foxglove

Install the Foxglove bridge dependency, then launch with:

```bash
ros2 launch move_blueboat mission4_sim.launch.py \
  camera_mode:=4 \
  camera_foxglove:=true
```

Connect Foxglove to:

```text
ws://127.0.0.1:8765
```

## ROS 2 services

```bash
ros2 service call /blueboat_camera_manager/set_enabled \
  blueboat_camera_manager/srv/SetCameraEnabled \
  "{cameras: [blueboat], enabled: true}"

ros2 service call /blueboat_camera_manager/set_config \
  blueboat_camera_manager/srv/SetCameraConfig \
  "{cameras: [blueboat], width: 640, height: 480, fps: 30.0, preserve_aspect: true}"

ros2 service call /blueboat_camera_manager/set_lag \
  blueboat_camera_manager/srv/SetCameraLag \
  "{cameras: [blueboat], lag_seconds: 1.5}"

ros2 service call /blueboat_camera_manager/status std_srvs/srv/Trigger "{}"
```

`all` selects the cameras active in the chosen numeric mode. A request for a boat
outside that mode is rejected.

## Lag buffer guard

Lag is implemented after resize and frame-rate limiting. The manager estimates
the raw delayed-frame memory required per camera and rejects a combination over
`camera_max_buffer_mb` (256 MiB by default). Reduce resolution, FPS, or lag if a
request is rejected.

## Smoke test

After launch, verify the manager and first camera:

```bash
ros2 service call /blueboat_camera_manager/status std_srvs/srv/Trigger "{}"
ros2 topic hz /blueboat/camera/image
ros2 topic echo --once /blueboat/camera/camera_info
```

Then open the local web page and toggle `blueboat` off and on. The image topic
rate should stop and resume. In RViz, add a **Camera** display and choose
`/blueboat/camera/image`.

## Installer backup

`apply.sh` creates a timestamped backup directory beside the repository before
changing source files. It also writes `CAMERA_WEB_OVERLAY_APPLIED.txt` in the
repository with the exact backup path and installed path list.
