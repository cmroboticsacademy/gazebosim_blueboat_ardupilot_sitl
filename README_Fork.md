# BlueBoat simulation SITL with GazeboSim and QGC

The following repository offers the BlueBoat simulation SITL with GazeboSim. Users can plan complex missions using QGroundControl by defining waypoints and survey grids.

## BlueBoat follows waypoints

![image](https://github.com/oceansystemslab/blueboat_ardupilot_SITL/assets/30973337/46894659-2f5c-4a65-8e1d-d58383a94fc8)

## BlueBoat performs a survey

![image](https://github.com/oceansystemslab/blueboat_ardupilot_SITL/assets/30973337/85a8fe30-87c4-49d0-acbd-c38d9fff1fb7)



## Prerequisites

- Download and Install [QGroundControl](https://docs.qgroundcontrol.com/master/en/qgc-user-guide/getting_started/download_and_install.html) (optional).
- Install [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) to support Docker to access GPU (required).
- Repository has been tested on: Ubuntu 22.04, Ubuntu 24.04, ArchLinux (Kernel 6.8).
- Run these commands, so the system will use the NVIDIA GPU for rendering graphics, which is typically desired for more graphics-intensive tasks.

```bash
sudo apt install nvidia-prime
sudo prime-select nvidia
sudo reboot now
```
   

## Build

```bash
git clone https://github.com/markusbuchholz/gazebosim_blueboat_ardupilot_sitl.git

cd /gazebosim_blueboat_ardupilot_sitl/blueboat_sitl/docker

sudo ./build.sh

```

## Run

Note:

Adjust these lines in ```run.sh```

```bash
local_gz_ws="/home/markus/blueboat_ardupilot_SITL/gz_ws"
local_SITL_Models="/home/markus/blueboat_ardupilot_SITL/SITL_Models"
```


```bash
sudo ./run.sh

colcon build

source install/setup.bash

cd ../gz_ws

colcon build --symlink-install --merge-install --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo -DBUILD_TESTING=ON -DCMAKE_CXX_STANDARD=17

source install/setup.bash

source gazebo_exports.sh
 
```
## Start QGC (outside Docker)

```bash
./QGroundControl.AppImage
```

## Run GazeboSim inside Docker

```bash
sudo docker exec -it blueboat_sitl /bin/bash

ros2 launch move_blueboat launch_robot_simulation.launch.py
```

## Run SITL


Notes:

- IMPORTANT: Run GazbenSim first as it holds the ArduPilot plugin, which you can connect with the ArduPilot SITL (Rover) simulator!
  
- The flag ```-l``` is the localization (lat,lon,alt,heading). Check your favorite location with Google Maps.
- ```sim_vehicle.py --help ``` -prints all available commands and flags.
- in ```run.sh``` adjust these two lines for your host specific:

```bash
local_gz_ws="/home/markus/blueboat_ardupilot_SITL/gz_ws"
local_SITL_Models="/home/markus/blueboat_ardupilot_SITL/SITL_Models"
```
  
```bash

sudo docker exec -it blueboat_sitl /bin/bash

cd ../ardupilot

sim_vehicle.py -v Rover -f gazebo-rover --model JSON --map --console -l 55.99541530863445,-3.3010225004910683,0,0

# if you need to recompile 
Tools/environment_install/install-prereqs-ubuntu.sh -y

# after recompiling 
. ~/.profile
```

## Path Planner Interface 

The Mavlink protocol offers simple commands to the vehicle to navigate to waypoints so that the vehicle can perform its mission. The following can be considered an interface to the vehicle (simulator). It accepts waypoints from the path planner as arguments from the terminal and sends them to ArduRover for execution.

```bash
# Launch Gazebo and ArduRover before executing the mission.

cd extras_boat
python3 args_mission_planner_gps.py --positions "0,0;5,5;0,0;10,-10;-5,5;0,0;30,30;0,0"

```
You can launch the program with "hard-coded" waypoints.

```bash
cd extras_boat
python3 mission_planner_gps.py

```

Run the following program to feed ArduRover with waypoints one by one. Once the program activates, it will execute a constant flow of waypoints from the terminal.

```bash
cd extras_boat
python3 loop_mission_planner_gps.py

```

---

## Start BlueBoat simulation with ArduPilot and simple ROS 2 interface

ROS 2 interface provides two common topics (ROS 2 is a function wrapper for Mavlink protocol):

```bash
/bluerov2/odometry
/bluerov2/cmd_vel
/bluerov2/servo_outputs
/blueboat/send_port_motor_0_100_thrust
/blueboat/send_stbd_motor_0_100_thrust
```

All steps as follows:

```bash
#Termminal 1
ros2 launch move_blueboat launch_robot_simulation.launch.py

#Termminal 2
sim_vehicle.py -v Rover -f gazebo-rover --model JSON --map --console -l 55.99541530863445,-3.3010225004910683,0,0

#Termminal 3
cd /home/gz_ws/src/extras_interface
python3 ros2_blueboat_interface.py

```
Run the motors individually.

```bash
ros2 topic pub /blueboat/send_port_motor_0_100_thrust std_msgs/msg/Float32 "{data: 25.0}"
ros2 topic pub /blueboat/send_stbd_motor_0_100_thrust std_msgs/msg/Float32 "{data: 30.0}"
``

---

## Guided mode with Dynamic Position

Following the program accepts the X and Y coordinates of the desired waypoint through terminal input. The vehicle navigates to position and maintains its ```dynamic position```, ensuring stability between waypoints despite external disturbances.

```bash
cd extras_boat
python3 loop_mission_planner_gps_dynamic_position.py

```
The following program accepts the constant flow of waypoints from the terminal and performs the ```dynamic position``` in the last.

```bash
cd extras_boat
python3 mission_planner_gps_dynamic_position.py

```

## ROS 2 mission controller with Dynamic Position

The path planner can execute the mission by feeding the mission controller with waypoints. Each waypoint will be executed, and the boat will stay at the last waypoint in a dynamic position, waiting for the next command from the controller.

```bash
# Start Gazebo
ros2 launch move_blueboat launch_robot_simulation.launch.py

# Start Controller
ros2 run move_blueboat dp_beacon_dvl_run_boat_waypoint

# Publish waypoints
ros2 topic pub -1 /waypoints std_msgs/Float64MultiArray "{data: [5.0, 5.0]}" -1

```


## Control BlueBoat using joystick

Launching the interface allows control of BlueBoat using a joystick.

```bash
cd /home/gz_ws/src/extras_interface
python3 ros2_blueboat_interface.py
```
The joystick left/right handler is mapped to topics,

```bash
/blueboat/send_port_motor_0_100_thrust
/blueboat/send_stbd_motor_0_100_thrust
```
Launching the interface enables control of BlueBoat using a differential drive.<br>
The RIGHT axis of the joystick is responsible for moving forward and backward, while the other LEFT axis of the joystick controls movement to the left/right, 

```bash
cd /home/gz_ws/src/extras_interface
python3 ros2_blueboat_interface_diff.py
```

## ROS 2 topics

```bash
# BlueBoat
/model/blueboat/joint/motor_port_joint/cmd_thrust
/model/blueboat/joint/motor_stbd_joint/cmd_thrust
/model/blueboat/navsat
/model/blueboat/odometry
```

## Control BlueBoat directly using [pymavlink](https://mavlink.io/en/mavgen_python/)
Note:

- Find useful examples in folder ```èxtras_boat```.
 
```bash
sudo pip3 install pymavlink
```
### Run scripts
```bash
cd extras_boat

python3 run_boat.py
```

## PlotJuggler

```bash
ros2 run plotjuggler plotjuggler
```
![image](https://github.com/oceansystemslab/blueboat_ardupilot_SITL/assets/30973337/776bb3e9-4848-4f54-bc26-55da6d475fa1)



## Waves Control

Type ```Waves Control```in the GazeboSim menu (3 dots) to access the control panel of ocean disturbances.

![image](https://github.com/oceansystemslab/blueboat_ardupilot_SITL/assets/30973337/674ac7da-55fd-46bc-887a-36e1ba55016e)

## ASV Mission Planner

The mission planner provides the opportunity to define the start, goal, obstacles, and waypoints for the ASV to follow. Users can plan missions using the ```RRT*``` or ```A*``` algorithm. The ```Simple Path``` constructs the path based on the start, goal, and waypoints. After the path planner finds the path, the user can send the path to run ROS 2 program, which reads the path and moves the vehicle (default in ```Gazebo```).

```bash
#run Gazebo

ros2 launch move_blueboat launch_robot_simulation.launch.py

#start path planner GUI

cd gz_ws/src/move_blueboat/move_blueboat

python3 coralguide_asv_mission_planner.py
```

![image](https://github.com/oceansystemslab/blueboat_ardupilot_SITL/assets/30973337/96d934f4-e89d-41ea-9397-906ed8635f5b)


## MAVProxy Cheatsheet

For example:
```bash
arm throttle
mode
mode GUIDED
disarm

```

- [cheatsheet](https://ardupilot.org/mavproxy/docs/getting_started/cheatsheet.html)

## References

- [ROS-Gazebo Bridge](https://github.com/gazebosim/ros_gz/tree/ros2/ros_gz_bridge)
- [Ardupilot_gazebo](https://github.com/ArduPilot/ardupilot_gazebo)
- [Gazebo demos](https://github.com/gazebosim/ros_gz/tree/ros2/ros_gz_sim_demos)
- [BlueBoat operational manual](https://bluerobotics.com/learn/blueboat-operators-guide/)
- [QGroundControl User Guide](https://docs.qgroundcontrol.com/master/en/qgc-user-guide/)
- [BlueBoat SITL](https://github.com/ArduPilot/SITL_Models/blob/master/Gazebo/docs/BlueBoat.md)
- [ArduPilot and Gazebo](https://ardupilot.org/dev/docs/sitl-with-gazebo.html)
- [SITL](https://www.ardusub.com/developers/sitl.html)
- [Wave Sim](https://github.com/srmainwaring/asv_wave_sim)
- [icra2023_ros2_gz_tutorial](https://github.com/osrf/icra2023_ros2_gz_tutorial?tab=readme-ov-file#overview)
- [Gazebo Ocean Simulation](https://docs.google.com/presentation/d/1JXwWMPPVT7y03Vr6cWtrwAwyvdysmg3NW9ZmI276dMY/edit#slide=id.p)
- [Multi-LRAUV Simulation](https://docs.google.com/presentation/d/1RIuvOOTdQvoAKKRzGnNZW8Ikp_VGVaUOyAZc-BANXdo/edit#slide=id.g71c89e7412_2_52)
- [rover-sitl](https://ardupilot.org/dev/docs/rover-sitlmavproxy-tutorial.html)
- [cruise-throttle-and-cruise-speed](https://ardupilot.org/rover/docs/rover-tuning-throttle-and-speed.html#cruise-throttle-and-cruise-speed) - refer to the doc. for instructions on how to set global velocity and acc.
- [Rover: L1 navigation overview](https://ardupilot.org/dev/docs/rover-L1.html)
- [Extended Kalman Filter Navigation Overview and Tuning](https://ardupilot.org/dev/docs/extended-kalman-filter.html)
- [Rover Control Modes](https://ardupilot.org/rover/docs/rover-control-modes.html)
- [Dynamic position mode](https://ardupilot.org/rover/docs/loiter-mode.html)
- [flight-modes](https://ardupilot.org/copter/docs/flight-modes.html)
- [common-non-gps-navigation](https://ardupilot.org/copter/docs/common-non-gps-navigation-landing-page.html)
- [Guided Mode](https://ardupilot.org/copter/docs/ac2_guidedmode.html)
- [ArduPilot-ROVER](https://ardupilot.org/rover/index.html)
- [GPS / Non-GPS Transitions](https://ardupilot.org/copter/docs/common-non-gps-to-gps.html)
- [EKF Failsafe](https://ardupilot.org/copter/docs/ekf-inav-failsafe.html)
- [tuning-navigation](https://ardupilot.org/rover/docs/rover-tuning-navigation.html)
  
