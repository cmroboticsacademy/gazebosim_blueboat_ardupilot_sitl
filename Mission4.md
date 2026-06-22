# Mission 4: Two BlueBoats, QGroundControl, RViz seafloor mapping, and camera notes

Mission 4 runs two BlueBoat models in the same Gazebo scene. Each boat has physics enabled, its own ArduPilot SITL instance, its own MAVLink system ID, its own Gazebo/ArduPilot JSON FDM port, and its own bathymetry mapping output for RViz.

## Files added or changed

```text
gz_ws/src/move_blueboat/launch/mission4_sim.launch.py
gz_ws/src/move_blueboat/move_blueboat/bathymetry_mapper.py
gz_ws/src/move_blueboat/move_blueboat/joy_sim_controller.py
gz_ws/src/move_blueboat/rviz/mission4_two_blueboats_mapping.rviz
gz_ws/src/asv_wave_sim/gz-waves-models/worlds/level6.sdf
gz_ws/cmra_boat1_sysid.params
gz_ws/cmra_boat2_sysid.params
SITL_Models/Gazebo/models/blueboat2/model.config
SITL_Models/Gazebo/models/blueboat2/model.sdf
Mission4.md
```

## Build and source

Inside the Docker container:

```bash
cd ~/gz_ws
colcon build --packages-select move_blueboat
source install/setup.bash
source gazebo_exports.sh
```

## Start Gazebo, bridges, mappers, and RViz

```bash
ros2 launch move_blueboat mission4_sim.launch.py
```

This starts:

- Gazebo with `level6.sdf`
- Boat 1 model: `blueboat`
- Boat 2 model: `blueboat2`
- ROS/Gazebo bridges for both boats' thrust, odometry, navsat, bathymetry scan, and camera image topics
- Two bathymetry mapper nodes
- RViz with both boats' seafloor point clouds and odometry

Expected ROS topics include:

```bash
ros2 topic list | grep -E 'blueboat|bathymetry|ocean_floor|camera'
```

Important topics:

```text
/bathymetry/scan
/blueboat2/bathymetry/scan
/blueboat/ocean_floor/map_cloud
/blueboat2/ocean_floor/map_cloud
/model/blueboat/odometry
/model/blueboat2/odometry
/camera
/blueboat2/camera
```

## Start ArduPilot SITL for Boat 1

In a separate ArduPilot terminal:

```bash
cd ~/ardupilot
sim_vehicle.py -v Rover -f gazebo-rover --model JSON   --add-param-file=../gz_ws/cmra_boat.params   --add-param-file=../gz_ws/cmra_boat1_sysid.params   -w -I0 --no-extra-ports   -l 40.595009,-79.99974,0,0   --out=udp:127.0.0.1:14550
```

## Start ArduPilot SITL for Boat 2

In another ArduPilot terminal:

```bash
cd ~/ardupilot
sim_vehicle.py -v Rover -f gazebo-rover --model JSON   --add-param-file=../gz_ws/cmra_boat.params   --add-param-file=../gz_ws/cmra_boat2_sysid.params   -w -I1 --no-extra-ports   -l 40.595009,-79.99974,0,0   --out=udp:127.0.0.1:14550
```

Check the IDs in each MAVProxy console:

```bash
param show SYSID_THISMAV
```

Expected values:

```text
Boat 1: SYSID_THISMAV 1
Boat 2: SYSID_THISMAV 2
```

## QGroundControl joystick control

Use QGroundControl's vehicle selector to make the boat you want to drive the active vehicle. QGC joystick control is sent over MAVLink to the selected vehicle. You can control one active vehicle at a time from one QGC joystick.

For each boat, check:

1. QGC shows two vehicles, not one vehicle jumping between positions.
2. The selected vehicle is the boat you want to drive.
3. The selected vehicle is armed.
4. The selected vehicle is in Manual mode.
5. Joystick is calibrated and enabled in QGC.
6. Advanced joystick settings still use Center stick is zero throttle and Allow negative thrust.

Do not run the ROS `joy_sim_controller` at the same time as QGC joystick control unless you intentionally want to bypass ArduPilot. The ROS joystick node publishes directly to Gazebo thruster topics and can fight ArduPilot's thruster commands.

## Optional direct ROS joystick control

This is for Gazebo-only testing. It bypasses ArduPilot and QGC.

Start a ROS joystick driver:

```bash
ros2 run joy joy_node
```

Directly control Boat 1:

```bash
ros2 run move_blueboat joy_sim_controller --ros-args -p target_model:=blueboat
```

Directly control Boat 2:

```bash
ros2 run move_blueboat joy_sim_controller --ros-args -p target_model:=blueboat2
```

Optional deadman button example:

```bash
ros2 run move_blueboat joy_sim_controller --ros-args   -p target_model:=blueboat2   -p deadman_button:=4
```

## QGroundControl camera feed

Boat 1 uses the original QGC/GStreamer camera port:

```text
127.0.0.1:5600
```

Boat 2 uses a separate camera port:

```text
127.0.0.1:5601
```

In QGroundControl:

```text
Application Settings -> General -> Video
Video Source: UDP h.264 Video Stream
URL/Port: 5600 for Boat 1, or 5601 for Boat 2
```

QGC's normal video setting is application-level, so do not expect one QGC instance to automatically show two independent UDP camera feeds at the same time from this simple Gazebo/GStreamer setup. To view both at once, use a second viewer for the second port or run a separate QGC instance with separate settings.

Example external GStreamer viewer for Boat 2:

```bash
gst-launch-1.0 -v udpsrc port=5601   caps='application/x-rtp, media=(string)video, clock-rate=(int)90000, encoding-name=(string)H264'   ! rtph264depay ! avdec_h264 ! videoconvert ! autovideosink
```

If no QGC video appears, first set `Disabled When Disarmed` to off in QGC video settings, then confirm Gazebo is publishing the camera stream:

```bash
gz topic -l | grep camera
```

## RViz seafloor mapping checks

RViz should show two point cloud displays:

```text
BlueBoat 1 Ocean Floor Map -> /blueboat/ocean_floor/map_cloud
BlueBoat 2 Ocean Floor Map -> /blueboat2/ocean_floor/map_cloud
```

If one map is empty, check the corresponding scan and odometry topics:

```bash
ros2 topic hz /bathymetry/scan
ros2 topic hz /blueboat2/bathymetry/scan
ros2 topic hz /model/blueboat/odometry
ros2 topic hz /model/blueboat2/odometry
```

The map cloud grows as each boat moves and its downward bathymetry scan hits the seafloor.
