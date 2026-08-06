# BlueBoat camera lag

Set a launch default with `camera_lag:=SECONDS`, use the local website, publish a
`std_msgs/msg/Float64` value to `/<boat>/camera/lag`, or call
`/blueboat_camera_manager/set_lag`. See `BLUEBOAT_CAMERA_WEB.md` for examples and
buffer limits.
