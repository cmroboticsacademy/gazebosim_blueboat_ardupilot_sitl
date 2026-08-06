# BlueBoat camera ROS API

## Topics

For each active boat name:

- `/<boat>/camera/image_raw` — Gazebo-to-ROS raw image.
- `/<boat>/camera/image` — resized, FPS-limited, optionally delayed image.
- `/<boat>/camera/camera_info` — matching calibration metadata.
- `/<boat>/camera/lag` — optional `std_msgs/msg/Float64` lag command.
- `/<boat>/camera/lag_status` — current lag status.

The manager state is published as transient-local JSON on:

```text
/blueboat_camera_manager/state
```

The state includes configured values, input/processed/output rates, dropped and
subscriber-skipped frame counts, queue depth, last raw-frame age, and subscriber
counts. The web API augments it with viewer count, JPEG quality, encoded FPS, and
measured preview bitrate.

## SetCameraConfig

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

`bitrate_kbps` is the target for the local MJPEG preview. ROS `Image` messages
remain uncompressed.

## Other services

- `/blueboat_camera_manager/set_enabled`
- `/blueboat_camera_manager/set_lag`
- `/blueboat_camera_manager/status`

Use `all` in the `cameras` array to target every camera active in the numeric
mode.

## HTTP API

Batch update:

```http
POST /api/cameras
Content-Type: application/json

{
  "cameras": ["blueboat", "blueboat2"],
  "settings": {
    "enabled": true,
    "width": 320,
    "height": 240,
    "fps": 12,
    "bitrate_kbps": 800,
    "preserve_aspect": true,
    "lag_seconds": 0.5
  }
}
```

Every setting is optional. Omitted fields retain each boat's existing value.
The old single-camera endpoint `/api/cameras/<boat>` remains available.

## Gazebo activation status (v4)

Each camera entry in `/blueboat_camera_manager/state` and the `status` service
also reports:

- `image_bridge_running` and `image_bridge_pid`;
- `image_bridge_last_exit`;
- `gazebo_sensor_rate_requested` and `gazebo_sensor_rate_applied`;
- `gazebo_sensor_rate_error` and `gazebo_sensor_rate_in_flight`.

When `manage_image_bridges` is true, disabling a camera stops its dedicated
Gazebo-to-ROS image bridge rather than only stopping ROS-side processing.
