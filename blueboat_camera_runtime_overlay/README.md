# BlueBoat runtime camera control overlay

This overlay is designed for the `main` branch of:

`cmroboticsacademy/gazebosim_blueboat_ardupilot_sitl`

It adds runtime ROS 2 services for the four existing FPV camera streams and an
optional single-camera mode that follows one selected boat and streams only on
UDP port 5600.

## What this changes

New source files:

- `gz_ws/src/blueboat_camera_manager/`
  - ROS 2 services and manager node
  - `BlueBoatGstCameraPlugin` Gazebo sensor plugin
  - `BlueBoatCameraFollowerPlugin` Gazebo model plugin
- `SITL_Models/Gazebo/models/blueboat_camera_pod/`

Existing source files modified by `apply.sh`:

- `SITL_Models/Gazebo/models/blueboat/model.sdf`
- `SITL_Models/Gazebo/models/blueboat2/model.sdf`
- `SITL_Models/Gazebo/models/blueboat3/model.sdf`
- `SITL_Models/Gazebo/models/blueboat4/model.sdf`
- `gz_ws/src/asv_wave_sim/gz-waves-models/worlds/level6.sdf`
- `gz_ws/src/move_blueboat/launch/mission4_sim.launch.py`
- `gz_ws/src/move_blueboat/package.xml`

The installer edits these source files once. During simulation, no Python code
rewrites an SDF file.

## Important resolution detail

Gazebo Garden does not expose a safe supported way for an external sensor
plugin to reallocate the active `CameraSensor` render buffer while it is
running. This overlay therefore uses fixed maximum source render sizes:

- Four boat cameras: `640x480`
- Single camera pod: `1280x720`

The ROS 2 service changes the dimensions of the live encoded UDP stream. A
request above the fixed source dimensions is allowed but is only an upscale and
cannot add detail. The frame rate is a true runtime camera trigger rate: when a
stream is disabled, its plugin removes the image subscription and stops sending
triggers, so that camera produces no image frames for the stream.

## Install into the repository

From the directory containing this extracted overlay:

```bash
cd ~/path/to/gazebosim_blueboat_ardupilot_sitl
/path/to/blueboat_camera_runtime_overlay/apply.sh .

git status --short
git diff --stat
git diff
```

The script is idempotent for the expected `main` branch layout. It copies the
new package and model, then makes narrow source edits around the existing FPV
camera blocks, level 6 boat includes, and Mission 4 launch description.

## System dependencies

On the Ubuntu machine that already builds this Gazebo Garden workspace:

```bash
sudo apt update
sudo apt install -y \
  libgz-sim7-dev \
  libopencv-dev \
  libgstreamer1.0-dev \
  libgstreamer-plugins-base1.0-dev \
  gstreamer1.0-plugins-base \
  gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad \
  gstreamer1.0-plugins-ugly
```

The `x264enc` element comes from the GStreamer ugly plugin package. Verify it:

```bash
gst-inspect-1.0 x264enc
gst-inspect-1.0 rtph264pay
```

## Build

Use the same ROS distribution and shell setup as the current project:

```bash
source /opt/ros/$ROS_DISTRO/setup.bash
cd ~/path/to/gazebosim_blueboat_ardupilot_sitl/gz_ws

rosdep install --from-paths src --ignore-src -r -y

colcon build \
  --symlink-install \
  --merge-install \
  --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo

source install/setup.bash
```

The package installs environment hooks that add `gz_ws/install/lib` to both
`GZ_SIM_SYSTEM_PLUGIN_PATH` and `IGN_GAZEBO_SYSTEM_PLUGIN_PATH`. Always source
`gz_ws/install/setup.bash` in the terminal that launches Mission 4.

Confirm the package and service interfaces:

```bash
ros2 pkg prefix blueboat_camera_manager
ros2 interface show blueboat_camera_manager/srv/SetCameraConfig
ros2 interface show blueboat_camera_manager/srv/SetCameraEnabled
ros2 interface show blueboat_camera_manager/srv/SelectCamera
```

## Launch: four-camera mode

This preserves the current port layout:

| Camera | UDP port |
|---|---:|
| `blueboat` | 5600 |
| `blueboat2` | 5602 |
| `blueboat3` | 5604 |
| `blueboat4` | 5606 |

```bash
cd ~/path/to/gazebosim_blueboat_ardupilot_sitl/gz_ws
source install/setup.bash

ros2 launch move_blueboat mission4_sim.launch.py \
  camera_mode:=four \
  camera_start_delay:=10.0 \
  camera_width:=256 \
  camera_height:=256 \
  camera_fps:=16.0 \
  camera_bitrate_kbps:=800
```

The manager repeats its initial configuration and enable publications five
times after the delay. This avoids the current startup race where the original
one-shot enable publication can occur before the Gazebo plugin subscribes.

## Launch: single movable camera mode

Only the camera pod subscribes, triggers, encodes, and streams. It sends to UDP
port 5600 and initially follows `blueboat` unless another target is supplied.

```bash
ros2 launch move_blueboat mission4_sim.launch.py \
  camera_mode:=single \
  camera_single_target:=blueboat \
  camera_start_delay:=10.0 \
  camera_width:=640 \
  camera_height:=360 \
  camera_fps:=16.0 \
  camera_bitrate_kbps:=1000 \
  camera_preserve_aspect:=true
```

Valid launch targets are `blueboat`, `blueboat2`, `blueboat3`, and `blueboat4`.

## Runtime ROS 2 service calls

Open a second terminal and source the workspace:

```bash
source /opt/ros/$ROS_DISTRO/setup.bash
source ~/path/to/gazebosim_blueboat_ardupilot_sitl/gz_ws/install/setup.bash
```

### Change all active streams

In four-camera mode, `all` means all four boats. In single mode, `all` means the
camera pod.

```bash
ros2 service call \
  /blueboat_camera_manager/set_config \
  blueboat_camera_manager/srv/SetCameraConfig \
  "{cameras: ['all'], width: 320, height: 240, fps: 10.0, bitrate_kbps: 600, preserve_aspect: true}"
```

The selected GStreamer pipeline restarts to apply dimensions, caps, and bitrate.
QGroundControl may briefly pause while it receives the next H.264 keyframe.

### Change one boat

```bash
ros2 service call \
  /blueboat_camera_manager/set_config \
  blueboat_camera_manager/srv/SetCameraConfig \
  "{cameras: ['blueboat3'], width: 640, height: 480, fps: 20.0, bitrate_kbps: 1400, preserve_aspect: false}"
```

### Change a group explicitly

```bash
ros2 service call \
  /blueboat_camera_manager/set_config \
  blueboat_camera_manager/srv/SetCameraConfig \
  "{cameras: ['blueboat', 'blueboat4'], width: 256, height: 256, fps: 8.0, bitrate_kbps: 450, preserve_aspect: false}"
```

Accepted camera selectors:

- `all` — active camera set for the selected launch mode
- `all_boats` or `boats` — all four physical boat cameras
- `blueboat`, `blueboat2`, `blueboat3`, `blueboat4`
- `camera_pod`

Configuration limits:

- Width and height: even values, minimum 16, maximum 3840x2160 output
- FPS: greater than 0 and no more than 30
- Bitrate: 100 through 50000 kbps
- `preserve_aspect: false` stretches to exactly the requested dimensions
- `preserve_aspect: true` letterboxes with black bars

### Disable or enable streams

Disable one camera and release its encoder, UDP sink, image subscription, and
camera triggers:

```bash
ros2 service call \
  /blueboat_camera_manager/set_enabled \
  blueboat_camera_manager/srv/SetCameraEnabled \
  "{cameras: ['blueboat2'], enabled: false}"
```

Enable it again:

```bash
ros2 service call \
  /blueboat_camera_manager/set_enabled \
  blueboat_camera_manager/srv/SetCameraEnabled \
  "{cameras: ['blueboat2'], enabled: true}"
```

Stop every physical boat stream:

```bash
ros2 service call \
  /blueboat_camera_manager/set_enabled \
  blueboat_camera_manager/srv/SetCameraEnabled \
  "{cameras: ['all_boats'], enabled: false}"
```

### Move the single camera to another boat

This service is intentionally rejected in four-camera mode.

```bash
ros2 service call \
  /blueboat_camera_manager/select_camera \
  blueboat_camera_manager/srv/SelectCamera \
  "{camera: 'blueboat3'}"
```

The camera pod immediately follows the selected boat with the same forward
mount offset used by the existing FPV cameras.

### Read manager status

```bash
ros2 service call \
  /blueboat_camera_manager/status \
  std_srvs/srv/Trigger \
  "{}"
```

## Direct ROS topics

Services are recommended because they validate names and values. The bridge also
exposes these ROS topics for diagnostics:

```text
/blueboat/camera/enable_streaming       std_msgs/msg/Bool
/blueboat/camera/stream_config          std_msgs/msg/String
/blueboat2/camera/enable_streaming      std_msgs/msg/Bool
/blueboat2/camera/stream_config         std_msgs/msg/String
/blueboat3/camera/enable_streaming      std_msgs/msg/Bool
/blueboat3/camera/stream_config         std_msgs/msg/String
/blueboat4/camera/enable_streaming      std_msgs/msg/Bool
/blueboat4/camera/stream_config         std_msgs/msg/String
/camera_pod/camera/enable_streaming     std_msgs/msg/Bool
/camera_pod/camera/stream_config        std_msgs/msg/String
/camera_pod/target                      std_msgs/msg/String
```

Example direct publication:

```bash
ros2 topic pub --once /blueboat/camera/stream_config std_msgs/msg/String \
  "{data: 'width=320;height=240;fps=12;bitrate_kbps=700;preserve_aspect=true'}"
```

## QGroundControl

Use the existing UDP H.264 settings:

- Four mode: use the corresponding port 5600, 5602, 5604, or 5606.
- Single mode: leave QGroundControl on 5600 and change boats with the
  `select_camera` service.

## Shutdown and cleanup

There are two cleanup layers:

1. The ROS 2 manager publishes `enabled: false` for every stream during normal
   ROS shutdown.
2. Each Gazebo stream plugin listens for render teardown and also runs cleanup
   in its destructor. It quits the GLib main loop, sets the GStreamer pipeline
   to `GST_STATE_NULL`, joins the worker thread, unsubscribes from the image
   topic, and releases the UDP socket.

After closing the launch, verify no process owns the ports:

```bash
ss -lunp | grep -E ':(5600|5602|5604|5606)\\b' || true
```

## Troubleshooting

### Gazebo cannot load `libBlueBoatGstCameraPlugin.so`

```bash
source ~/path/to/gazebosim_blueboat_ardupilot_sitl/gz_ws/install/setup.bash
echo "$GZ_SIM_SYSTEM_PLUGIN_PATH"
find ~/path/to/gazebosim_blueboat_ardupilot_sitl/gz_ws/install \
  -name 'libBlueBoat*Plugin.so' -print
```

### No stream after ten seconds

Check controls and plugin logs:

```bash
ros2 topic list | grep camera
ros2 service call /blueboat_camera_manager/status std_srvs/srv/Trigger "{}"
gz topic -l | grep -E 'camera|camera_pod'
```

Then re-enable the desired stream with the service. The launch retries startup
publications, so a permanent failure usually indicates that the bridge or custom
plugin did not load rather than the old one-shot timing race.

### GStreamer reports a missing element

```bash
gst-inspect-1.0 x264enc
gst-inspect-1.0 h264parse
gst-inspect-1.0 rtph264pay
```

Install the base/good/bad/ugly GStreamer plugin packages listed above.

### Revert the overlay before committing

Review first. To discard only these changes from a clean main checkout:

```bash
git restore -- \
  SITL_Models/Gazebo/models/blueboat/model.sdf \
  SITL_Models/Gazebo/models/blueboat2/model.sdf \
  SITL_Models/Gazebo/models/blueboat3/model.sdf \
  SITL_Models/Gazebo/models/blueboat4/model.sdf \
  gz_ws/src/asv_wave_sim/gz-waves-models/worlds/level6.sdf \
  gz_ws/src/move_blueboat/launch/mission4_sim.launch.py \
  gz_ws/src/move_blueboat/package.xml

rm -rf \
  SITL_Models/Gazebo/models/blueboat_camera_pod \
  gz_ws/src/blueboat_camera_manager
```
