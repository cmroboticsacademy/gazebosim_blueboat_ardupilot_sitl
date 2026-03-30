### Wrokstaion preperation
Perpare your work envirionment.
1. Open 4 terminal windows. Press `win_key` start typing `terminal`. Open the application when it appears. To open anoter terminal window, right click ther terminal app icon one the left toolbar. Select `New Window`.
2. Recommended: use the layout below
   ![Alt text](./cmra_images/TerminalLayout.png)
    <b>T1</b> Simulation terminal <br/>
    <b>T2</b> ArduPilot terminal <br />
    <b>T3</b> QGroundControl terminal <br />
    <b>T4</b> Misson Uploader terminal <br />



## Building
Follow these steps to build the project. First you will launch the docker container, and then build the project inside of it.

### Launching the docker container
Perform these steps in <b>T1</b>.
1. Navigate to <b>T1</b> to the projects docker folder. <br />
   ** Tripple click the command bellow to highlight it. `ctl + c` to copy. In <b>T1</b> use `ctl + shift + v to paste`. You must use `shift` key for copying and pasting inside of terminals. </br>
    ```bash
    cd cmra_sim/gazebosim_blueboat_ardupilot_sitl/blueboat_sitl/docker/
    ```
2. In <b>T1</b> start the docker container by executing the run script. <b>This command will promopt you for a password. Ask instructor for the password to continue.</b>
    ```bash
    sudo ./run.sh
    ```
    You should see the following output:
    ```
    cmra@cmra-LOQ-15IRX9:~/cmra_sim/gazebosim_blueboat_ardupilot_sitl/blueboat_sitl/docker$ sudo ./run.sh
    [sudo] password for cmra: 
    xauth:  file /tmp/.docker.xauth does not exist
    blueboat_sitl@cmra-LOQ-15IRX9:~/colcon_ws$
    ```
### Building the general ROS 2 / Gazebo integration dependencies
In this section you will use the colcon to build ROS 2 packages. <br/>

The build command will:<br/>
- compile and install the ROS 2 packages fetched from the .repos file
- create the install/setup.bash overlay that gets sourced
- make Gazebo/ROS bridge packages available to the rest of the system.

1. In <b>T1</b> run the build command.
   ```bash
    colcon build
    ```
2. In <b>T1</b> source the setup file
   ```bash
   source install/setup.bash
   ```
### Build BlueBoat simulation workspace
The build command will:<br/>
- install the local ROS 2 packages in gz_ws/src
- make launch files like ros2 launch move_blueboat launch_robot_simulation.launch.py work
- place built outputs into gz_ws/install, which is then sourced
- place libraries into locations referenced by gazebo_exports.sh, such as $HOME/gz_ws/install/lib
1. In <b>T1</b> navigate to the `gz_ws` folder
   ```bash
   cd ../gz_ws
   ```
   ** `../` is shorthand for 'go back one folder'
2. In <b>T1</b> run the build command
   ```bash
   colcon build --symlink-install --merge-install --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo -DBUILD_TESTING=ON -DCMAKE_CXX_STANDARD=17
   ```
3. In <b>T1</b> Source the setup file
   ```bash
   source install/setup.bash
   ```
4. In <b>T1</b> source the gazebo exports
   ```bash
   source gazebo_exports.sh
   ```
<b>T1</b> is now ready to start Gazebo.

### Prepare ArduPilot terminal
In this secion you will enter the docker container in <b>T2</b>

1. In <b>T2</b> enter the docker container.
   ```bash
   sudo docker exec -it blueboat_sitl /bin/bash
   ```
2. In <b>T2</b> navigate to the ArduPilot folder
   ```bash
   cd ../ardupilot
   ```
<b>T2</b> is now ready to start ArduPilot

## Running the simulation
When running the simulation you must follow these steps in order. If the these steps do not work, see the restarting the simulation section.

Follow this order exactly.
1. Launch the gazebo simulation
2. Start the simulation inside of gazebo
3. Launch Ardupilot

### Launch and run Gazebo Simulation
1. Launch Gazebo
   ```bash
   ros2 launch move_blueboat level1_sim.launch.py
   ```
   ** To change levels, change level1 to perfered level.
2. This will open the simulation window. Allow it to open and load
3. <b>IMPORTANT</b> - Press play and confirm simulation is running before moving on

### Launch ArduPilot
The launch command needs to match the level that you opened in the simulation. There is a folder that contains all of the levels launch commands. You can find them cmra_sim/Location ArduLaunchCommands. I have also provided a list of launch commands for each level at the bottom of this document. These insructions will load the first level.
1. In <b>T2</b> run the launch command
   ```
   sim_vehicle.py -v Rover -f gazebo-rover --model JSON --map --console \
   -l 21.286722,-157.963594,0,0 \
   --out=udp:127.0.0.1:14550 \
   --out=udp:127.0.0.1:14551

### Launch QGroundControl
In <b>T3</b> launch QGroundControl
1. Navigate to the application folder
   ```bash
   cd QGroundControl/
   ```
2. Start QGroundControl
```bash
   ./QGroundControl-x86_64.AppImage
```
You are now running the full simulation stack.

### Confirming your tech stack is running.
To confirm your tech stack is running you should see the following:
1. Gazebo sim is running
2. ArduPilot messages are streaming in <b>T2</b>
3. QGroundControl is connected and shows your robot on the map.

## Resetting the simulation
There are often times you may need to restart the simulation<. Most of the time you do not have to rebuild.

1. Click into <b>T1</b> and press `ctl + c`. This will stop the gazebo simulation. If the terminal does not stop processing, press `ctl + c` again until you get a terminal line that you can type into.
2. Do the same for <b>T2</b>
3. After both terminals are stopped, Re run the launch commands. Click into <b>T1</b>. Use the up arrow on your keyboard to load the last executed command. Check to make sure that it is the correct launch command and press enter.
4. Do the same for <b>T2</b>

Most of the time you will not have to reset QGroundControl in <b>T3</b>. Follow these steps if needed:
1. Close QGroundControl Application
2. Click into <b>T3</b>, and press `ctl + c`.
3. Press up to load the last executed command. Confirm its correct and press enter.

## Closing the simulation tech stack.
1. Close out of QGroundControl application
2. Click into <b>T1</b>, and press `ctl + c`.
3. Do this for all <b>T2</b> and <b>T3</b>.
4. In <b>T1</b> run the exit command
   ```bash
   exit
   ```

## Level 1
1. Follow the build instructions to get the tech stack started.
2. Complete Manual Drive in QGroundControl
3. Complete Simple Waypoint Mission in QGroundControl

### Manuel Drive in QGroundControl
Instruction
1. Arm your robot by clicking on the message icon (upper left). This will expand and you will see an Arm button.
2. Click the Arm button.
3. Confirm Arm command by holding space or sliding the actuator in the center of the screen.
4. Use the left virtual joystick to drive the boat forward and backward. Use the right virtual joystick to steer.
5. Drive the boat, monitor the battery, and take note of the expereince.

### Simple Waypoint mMssion in QGroundControl
QGroundControl can send a waypoint plan to ArduPilot. ArduPilot uses that plan to navigate the boat to each waypoint.
1. Click the top left icon in QGroundControl (looks like a Q)
2. Selct Plan Flight
3. Select Empty Plan
4. Click Waypoint button on the left menu bar
5. Add waypoints by clicking on the map.
6. When you add waypoints they will appear on the right menu bar next to the map. If you need to edit or delete waypoints, select them there by clicking on them.
7. Adjust the launch / RTL location by selcting the Mission Start node in the left menu above your waypoints.
8. Once selected click and drag the "lauch" pin on the map to the desiered launch / rtl position.
9. When ready to execute plan, click Upload or Upload Required in the top left of the application. 
10. After the plan is uploaded, click exit plan.
11. Hold space or slide the actuator to start the waypoint plan.