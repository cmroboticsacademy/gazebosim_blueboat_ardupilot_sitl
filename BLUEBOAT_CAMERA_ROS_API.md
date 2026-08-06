# BlueBoat Camera ROS 2 API Reference

This reference documents the camera-control API added to the `mission4_sim.launch.py` setup used with `level6.sdf` and the four BlueBoat models.

## 1. System overview

The ROS 2 node is:

```text
/blueboat_camera_manager
```

It controls five possible camera endpoints:

| API name | ROS topic prefix | Source render size | UDP port | Used by mode |
|---|---|---:|---:|---|
| `blueboat` | `/blueboat/camera` | 640x480 | 5600 | `four` |
| `blueboat2` | `/blueboat2/camera` | 640x480 | 5602 | `four` |
| `blueboat3` | `/blueboat3/camera` | 640x480 | 5604 | `four` |
| `blueboat4` | `/blueboat4/camera` | 640x480 | 5606 | `four` |
| `camera_pod` | `/camera_pod/camera` | 1280x720 | 5600 | `single` |

The requested width and height control the encoded UDP output. Requests larger than the source render size are upscaled and do not add detail.

---

## 2. Camera modes

### Mode: `four`

All four physical cameras are active.

| Boat | UDP port |
|---|---:|
| `blueboat` | 5600 |
| `blueboat2` | 5602 |
| `blueboat3` | 5604 |
| `blueboat4` | 5606 |

Launch:

```bash
source /opt/ros/humble/setup.bash
source ~/gz_ws/install/setup.bash

ros2 launch move_blueboat mission4_sim.launch.py \
  camera_mode:=four \
  camera_start_delay:=5.0 \
  camera_width:=1280 \
  camera_height:=720 \
  camera_fps:=60.0 \
  camera_bitrate_kbps:=50000 \
  camera_preserve_aspect:=true
```

ros2 launch move_blueboat mission4_sim.launch.py \
  camera_mode:=four \
  camera_start_delay:=5.0 \
  camera_width:=256 \
  camera_height:=256 \
  camera_fps:=30.0 \
  camera_bitrate_kbps:=1000 \
  camera_preserve_aspect:=true

In this mode, the `select_camera` service is rejected because each boat already has its own stream.

### Mode: `single`

Only the movable `camera_pod` is streamed. It always sends to UDP port 5600 and follows one selected boat.

Launch:

```bash
source /opt/ros/humble/setup.bash
source ~/gz_ws/install/setup.bash

ros2 launch move_blueboat mission4_sim.launch.py \
  camera_mode:=single \
  camera_single_target:=blueboat \
  camera_start_delay:=0.0 \
  camera_width:=640 \
  camera_height:=360 \
  camera_fps:=16.0 \
  camera_bitrate_kbps:=1000 \
  camera_preserve_aspect:=true
```

Valid single-camera targets:

```text
blueboat
blueboat2
blueboat3
blueboat4
```

---

## 3. Launch arguments

| Argument | Type | Default | Meaning |
|---|---|---:|---|
| `camera_mode` | string | `four` | `four` or `single` |
| `camera_start_delay` | float | `10.0` | Seconds before initial configuration and enable commands |
| `camera_width` | integer | `256` | Initial encoded output width |
| `camera_height` | integer | `256` | Initial encoded output height |
| `camera_fps` | float | `16.0` | Initial triggered camera rate |
| `camera_bitrate_kbps` | integer | `800` | Initial H.264 bitrate in kbps |
| `camera_preserve_aspect` | boolean | `false` | Letterbox instead of stretching when aspect ratios differ |
| `camera_single_target` | string | `blueboat` | Initial followed boat in `single` mode |

The manager waits for `camera_start_delay`, then repeats the initial configuration and enable command five times at one-second intervals. This avoids losing the enable command before the Gazebo camera plugin subscribes.

---

## 4. Recommended service API

List the services:

```bash
ros2 service list | grep blueboat_camera_manager
```

Expected services:

```text
/blueboat_camera_manager/set_config
/blueboat_camera_manager/set_enabled
/blueboat_camera_manager/select_camera
/blueboat_camera_manager/status
```

### 4.1 Configure resolution, FPS, bitrate, and aspect behavior

Service:

```text
/blueboat_camera_manager/set_config
```

Type:

```text
blueboat_camera_manager/srv/SetCameraConfig
```

Interface:

```text
string[] cameras
uint32 width
uint32 height
float32 fps
uint32 bitrate_kbps
bool preserve_aspect
---
bool success
string message
```

Show the installed interface:

```bash
ros2 interface show blueboat_camera_manager/srv/SetCameraConfig
```


```bash
ros2 service call \
  /blueboat_camera_manager/set_config \
  blueboat_camera_manager/srv/SetCameraConfig \
  "{cameras: ['all'], width: 256, height: 256, fps: 30.0, bitrate_kbps: 1400, preserve_aspect: true}"
```

Configure one physical camera:

```bash
ros2 service call \
  /blueboat_camera_manager/set_config \
  blueboat_camera_manager/srv/SetCameraConfig \
  "{cameras: ['blueboat3'], width: 640, height: 480, fps: 20.0, bitrate_kbps: 1400, preserve_aspect: false}"
```

Configure multiple cameras:

```bash
ros2 service call \
  /blueboat_camera_manager/set_config \
  blueboat_camera_manager/srv/SetCameraConfig \
  "{cameras: ['blueboat', 'blueboat4'], width: 256, height: 256, fps: 8.0, bitrate_kbps: 450, preserve_aspect: false}"
```

Configure the movable camera pod explicitly:

```bash
ros2 service call \
  /blueboat_camera_manager/set_config \
  blueboat_camera_manager/srv/SetCameraConfig \
  "{cameras: ['camera_pod'], width: 1280, height: 720, fps: 16.0, bitrate_kbps: 1800, preserve_aspect: true}"
```

Configuration limits:

| Field | Allowed value |
|---|---|
| `width` | Even integer from 16 through 3840 |
| `height` | Even integer from 16 through 2160 |
| `fps` | Greater than 0 and no more than 30 |
| `bitrate_kbps` | 100 through 50000 |
| `preserve_aspect=false` | Stretch exactly to the requested dimensions |
| `preserve_aspect=true` | Preserve aspect ratio and add black letterbox bars |

Changing dimensions, caps, or bitrate restarts the selected GStreamer pipeline. QGroundControl may pause briefly until the next H.264 keyframe.

### 4.2 Turn streams on or off

Service:

```text
/blueboat_camera_manager/set_enabled
```

Type:

```text
blueboat_camera_manager/srv/SetCameraEnabled
```

Interface:

```text
string[] cameras
bool enabled
---
bool success
string message
```

Show the installed interface:

```bash
ros2 interface show blueboat_camera_manager/srv/SetCameraEnabled
```

Turn on boat 1:

```bash
ros2 service call \
  /blueboat_camera_manager/set_enabled \
  blueboat_camera_manager/srv/SetCameraEnabled \
  "{cameras: ['blueboat'], enabled: true}"
```

Turn off boat 1:

```bash
ros2 service call \
  /blueboat_camera_manager/set_enabled \
  blueboat_camera_manager/srv/SetCameraEnabled \
  "{cameras: ['blueboat'], enabled: false}"
```

Turn on every camera active for the current mode:

```bash
ros2 service call \
  /blueboat_camera_manager/set_enabled \
  blueboat_camera_manager/srv/SetCameraEnabled \
  "{cameras: ['all'], enabled: true}"
```

Turn off every physical boat camera:

```bash
ros2 service call \
  /blueboat_camera_manager/set_enabled \
  blueboat_camera_manager/srv/SetCameraEnabled \
  "{cameras: ['all_boats'], enabled: false}"
```

Turn the single-mode camera pod on:

```bash
ros2 service call \
  /blueboat_camera_manager/set_enabled \
  blueboat_camera_manager/srv/SetCameraEnabled \
  "{cameras: ['camera_pod'], enabled: true}"
```

Turning a stream off releases its encoder, UDP sink, image subscription, and camera triggers.

### 4.3 Select the followed boat in single-camera mode

Service:

```text
/blueboat_camera_manager/select_camera
```

Type:

```text
blueboat_camera_manager/srv/SelectCamera
```

Interface:

```text
string camera
---
bool success
string message
```

Show the installed interface:

```bash
ros2 interface show blueboat_camera_manager/srv/SelectCamera
```

Move the camera pod to boat 3:

```bash
ros2 service call \
  /blueboat_camera_manager/select_camera \
  blueboat_camera_manager/srv/SelectCamera \
  "{camera: 'blueboat3'}"
```

Other examples:

```bash
ros2 service call /blueboat_camera_manager/select_camera \
  blueboat_camera_manager/srv/SelectCamera \
  "{camera: 'blueboat'}"

ros2 service call /blueboat_camera_manager/select_camera \
  blueboat_camera_manager/srv/SelectCamera \
  "{camera: 'blueboat2'}"

ros2 service call /blueboat_camera_manager/select_camera \
  blueboat_camera_manager/srv/SelectCamera \
  "{camera: 'blueboat4'}"
```

Behavior:

- Available only when launched with `camera_mode:=single`.
- The service automatically enables `camera_pod` after changing the target.
- The output remains on UDP port 5600.
- In `four` mode, the service returns `success: false`.

### 4.4 Read camera-manager status

Service:

```text
/blueboat_camera_manager/status
```

Type:

```text
std_srvs/srv/Trigger
```

Call:

```bash
ros2 service call \
  /blueboat_camera_manager/status \
  std_srvs/srv/Trigger \
  "{}"
```

The returned message contains:

- Current mode.
- Cameras the manager currently considers enabled.
- Current single-camera target.
- Last configuration published for each camera.

Example response message:

```text
mode=four; enabled=blueboat,blueboat2,blueboat3,blueboat4; single_target=blueboat; configs={...}
```

The status reports commands published by the manager. It is not a direct health check of QGroundControl or the receiving UDP socket.

---

## 5. Camera selectors

The `cameras` array used by `set_config` and `set_enabled` accepts:

| Selector | Meaning |
|---|---|
| `all` | Current mode's active set: all four boats in `four`, or `camera_pod` in `single` |
| `all_boats` | All four physical boat cameras |
| `boats` | Alias for `all_boats` |
| `blueboat` | Physical boat 1 camera |
| `blueboat2` | Physical boat 2 camera |
| `blueboat3` | Physical boat 3 camera |
| `blueboat4` | Physical boat 4 camera |
| `camera_pod` | Movable single-mode camera |

An empty camera array is treated as `['all']`.

Duplicate names are automatically removed.

---

## 6. Direct ROS topic API

The service API is recommended because it validates camera names and values. Direct topic publication bypasses those checks.

### 6.1 Enable topics

| Topic | Type | Purpose |
|---|---|---|
| `/blueboat/camera/enable_streaming` | `std_msgs/msg/Bool` | Enable or disable boat 1 stream |
| `/blueboat2/camera/enable_streaming` | `std_msgs/msg/Bool` | Enable or disable boat 2 stream |
| `/blueboat3/camera/enable_streaming` | `std_msgs/msg/Bool` | Enable or disable boat 3 stream |
| `/blueboat4/camera/enable_streaming` | `std_msgs/msg/Bool` | Enable or disable boat 4 stream |
| `/camera_pod/camera/enable_streaming` | `std_msgs/msg/Bool` | Enable or disable the movable camera stream |

Turn boat 1 on directly:

```bash
ros2 topic pub --once \
  /blueboat/camera/enable_streaming \
  std_msgs/msg/Bool \
  "{data: true}"
```

Turn boat 1 off directly:

```bash
ros2 topic pub --once \
  /blueboat/camera/enable_streaming \
  std_msgs/msg/Bool \
  "{data: false}"
```

Turn all four physical streams on directly:

```bash
for camera in blueboat blueboat2 blueboat3 blueboat4; do
  ros2 topic pub --once \
    "/${camera}/camera/enable_streaming" \
    std_msgs/msg/Bool \
    "{data: true}"
done
```

### 6.2 Stream configuration topics

| Topic | Type |
|---|---|
| `/blueboat/camera/stream_config` | `std_msgs/msg/String` |
| `/blueboat2/camera/stream_config` | `std_msgs/msg/String` |
| `/blueboat3/camera/stream_config` | `std_msgs/msg/String` |
| `/blueboat4/camera/stream_config` | `std_msgs/msg/String` |
| `/camera_pod/camera/stream_config` | `std_msgs/msg/String` |

Payload format:

```text
width=<integer>;height=<integer>;fps=<number>;bitrate_kbps=<integer>;preserve_aspect=<true|false>
```

Example:

```bash
ros2 topic pub --once \
  /blueboat/camera/stream_config \
  std_msgs/msg/String \
  "{data: 'width=320;height=240;fps=12;bitrate_kbps=700;preserve_aspect=true'}"
```

Apply the same raw configuration to all four boat cameras:

```bash
for camera in blueboat blueboat2 blueboat3 blueboat4; do
  ros2 topic pub --once \
    "/${camera}/camera/stream_config" \
    std_msgs/msg/String \
    "{data: 'width=256;height=256;fps=16;bitrate_kbps=800;preserve_aspect=false'}"
done
```

After publishing a raw configuration, enable the corresponding stream if it is currently off.

### 6.3 Single-camera target topic

Topic:

```text
/camera_pod/target
```

Type:

```text
std_msgs/msg/String
```

Move the pod directly to boat 4:

```bash
ros2 topic pub --once \
  /camera_pod/target \
  std_msgs/msg/String \
  "{data: 'blueboat4'}"
```

Then ensure the pod stream is enabled:

```bash
ros2 topic pub --once \
  /camera_pod/camera/enable_streaming \
  std_msgs/msg/Bool \
  "{data: true}"
```

The service is safer because it rejects invalid targets and rejects this operation outside `single` mode. The raw topic does neither.

---

## 7. Internal Gazebo trigger topics

Each SDF camera is configured as a triggered camera. The GStreamer plugin publishes trigger messages internally at the selected FPS.

Internal Gazebo Transport topics include:

```text
/blueboat/camera/trigger
/blueboat2/camera/trigger
/blueboat3/camera/trigger
/blueboat4/camera/trigger
/camera_pod/camera/trigger
```

These are not bridged as public ROS 2 control topics in the supplied launch file. Normally, do not publish them manually. Set FPS using `set_config`; the camera plugin then generates triggers at that rate while the stream is enabled.

---

## 8. ROS parameters

Node parameters:

| Parameter | Default | Purpose |
|---|---:|---|
| `mode` | `four` | `four` or `single` |
| `startup_delay` | `10.0` | Delay before startup publications |
| `startup_retries` | `5` | Number of startup publication attempts |
| `startup_retry_period` | `1.0` | Seconds between startup attempts |
| `default_width` | `256` | Startup width |
| `default_height` | `256` | Startup height |
| `default_fps` | `16.0` | Startup FPS |
| `default_bitrate_kbps` | `800` | Startup bitrate |
| `default_preserve_aspect` | `false` | Startup aspect behavior |
| `single_default_target` | `blueboat` | Startup target in single mode |

List current values:

```bash
ros2 param list /blueboat_camera_manager
ros2 param dump /blueboat_camera_manager
```

These parameters are primarily startup configuration. After startup, use the services to change stream state and configuration. Changing parameters with `ros2 param set` does not invoke a dynamic parameter callback and should not be treated as the runtime camera API.

---

## 9. Useful discovery commands

```bash
ros2 node list | grep blueboat_camera_manager
ros2 node info /blueboat_camera_manager
ros2 service list | grep blueboat_camera_manager
ros2 topic list | grep -E 'blueboat.*/camera|camera_pod'
ros2 topic info /blueboat/camera/enable_streaming
ros2 topic info /blueboat/camera/stream_config
ros2 interface show blueboat_camera_manager/srv/SetCameraConfig
ros2 interface show blueboat_camera_manager/srv/SetCameraEnabled
ros2 interface show blueboat_camera_manager/srv/SelectCamera
```

Gazebo Transport diagnostics:

```bash
gz topic -l | grep -E 'blueboat.*/camera|camera_pod'
```

Check for UDP output on boat 1's port:

```bash
sudo timeout 8 tcpdump -ni lo 'udp dst port 5600'
```

Check all four ports:

```bash
sudo timeout 8 tcpdump -ni lo \
  'udp dst port 5600 or udp dst port 5602 or udp dst port 5604 or udp dst port 5606'
```

---

## 10. QGroundControl settings

For a local simulation, QGroundControl should listen rather than bind to a specific sender address.

Use:

```text
Video Source: UDP h.264 Video Stream
UDP URL:      0.0.0.0:5600
```

Port by mode:

- `four`: choose 5600, 5602, 5604, or 5606 for the desired boat.
- `single`: keep QGroundControl on 5600 and use `select_camera` to switch boats.

For testing, disable any QGroundControl option that suppresses video while the vehicle is disarmed.

---

## 11. Common complete workflows

### Start four-camera mode and force boat 1 on

```bash
ros2 launch move_blueboat mission4_sim.launch.py \
  camera_mode:=four \
  camera_start_delay:=10.0 \
  camera_width:=256 \
  camera_height:=256 \
  camera_fps:=16.0 \
  camera_bitrate_kbps:=800
```

In another sourced terminal:

```bash
ros2 service call \
  /blueboat_camera_manager/set_config \
  blueboat_camera_manager/srv/SetCameraConfig \
  "{cameras: ['blueboat'], width: 256, height: 256, fps: 16.0, bitrate_kbps: 800, preserve_aspect: false}"

ros2 service call \
  /blueboat_camera_manager/set_enabled \
  blueboat_camera_manager/srv/SetCameraEnabled \
  "{cameras: ['blueboat'], enabled: true}"
```

### Start single mode and switch among boats

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

Switch to boat 2:

```bash
ros2 service call \
  /blueboat_camera_manager/select_camera \
  blueboat_camera_manager/srv/SelectCamera \
  "{camera: 'blueboat2'}"
```

Switch to boat 4:

```bash
ros2 service call \
  /blueboat_camera_manager/select_camera \
  blueboat_camera_manager/srv/SelectCamera \
  "{camera: 'blueboat4'}"
```

### Stop all camera streaming

```bash
ros2 service call \
  /blueboat_camera_manager/set_enabled \
  blueboat_camera_manager/srv/SetCameraEnabled \
  "{cameras: ['all_boats', 'camera_pod'], enabled: false}"
```

### Restore the default four-camera configuration

```bash
ros2 service call \
  /blueboat_camera_manager/set_config \
  blueboat_camera_manager/srv/SetCameraConfig \
  "{cameras: ['all_boats'], width: 256, height: 256, fps: 16.0, bitrate_kbps: 800, preserve_aspect: false}"

ros2 service call \
  /blueboat_camera_manager/set_enabled \
  blueboat_camera_manager/srv/SetCameraEnabled \
  "{cameras: ['all_boats'], enabled: true}"
```

---

## 12. Shutdown behavior

During normal ROS shutdown, the camera manager publishes `enabled: false` to every endpoint three times before exiting.

The Gazebo camera plugins also clean up on render teardown by:

- Stopping the GStreamer pipeline.
- Setting the pipeline to `GST_STATE_NULL`.
- Joining the worker thread.
- Unsubscribing from the image and control topics.
- Releasing the UDP socket.

After stopping the launch, check that no process owns the camera ports:

```bash
ss -lunp | grep -E ':5600|:5602|:5604|:5606'
```

No output is expected once Gazebo and QGroundControl are closed.
