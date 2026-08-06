# BlueBoat camera lag ROS 2 API

The camera manager accepts artificial lag updates while the simulation is running.

## Primary camera topic

```bash
ros2 topic pub --once /blueboat/camera/lag \
  std_msgs/msg/Float64 "{data: 3}"
```

`0.0` disables the artificial delay. Values from `0.0` to `30.0` seconds are accepted.

## Service

```bash
ros2 service call /blueboat_camera_manager/set_lag \
  blueboat_camera_manager/srv/SetCameraLag \
  "{cameras: [blueboat], lag_seconds: 3}"
```

Camera selectors are `blueboat`, `blueboat2`, `blueboat3`, `blueboat4`, `camera_pod`, `all`, and `all_boats`. An empty camera list selects all cameras active in the current manager mode.

## Status

```bash
ros2 service call /blueboat_camera_manager/status std_srvs/srv/Trigger "{}"
ros2 topic echo /blueboat/camera/lag_status
```

The existing stream endpoints and camera controls are unchanged. Updating lag rebuilds that camera's GStreamer pipeline and discards the previous queue, preventing stale delayed frames from leaking into the new setting.
