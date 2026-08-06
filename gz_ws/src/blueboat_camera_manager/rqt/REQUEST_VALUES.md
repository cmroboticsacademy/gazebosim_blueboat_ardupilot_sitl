# BlueBoat camera-manager request values

In each RQt Service Caller panel, edit the **expression** column using Python-style values.

## Set lag

Service: `/blueboat_camera_manager/set_lag`

All four boat cameras, 3 seconds behind live:

- `cameras`: `['all_boats']`
- `lag_seconds`: `3.0`

Only the first boat:

- `cameras`: `['blueboat']`
- `lag_seconds`: `3.0`

Return all four cameras to near-live:

- `cameras`: `['all_boats']`
- `lag_seconds`: `0.0`

## Set stream configuration

Service: `/blueboat_camera_manager/set_config`

Recommended four-camera example:

- `cameras`: `['all_boats']`
- `width`: `256`
- `height`: `256`
- `fps`: `30.0`
- `bitrate_kbps`: `1000`
- `preserve_aspect`: `True`

The current plugin accepts no more than 30 FPS.

## Enable or disable streams

Service: `/blueboat_camera_manager/set_enabled`

Enable all boat cameras:

- `cameras`: `['all_boats']`
- `enabled`: `True`

Disable all boat cameras:

- `cameras`: `['all_boats']`
- `enabled`: `False`

## Select camera

Service: `/blueboat_camera_manager/select_camera`

This service works only when the simulator was launched with `camera_mode:=single`.

- `camera`: `'blueboat'`

Valid targets are `blueboat`, `blueboat2`, `blueboat3`, and `blueboat4`.

## Status

Service: `/blueboat_camera_manager/status`

The request has no fields. Press **Call** to refresh the manager status.
