# Mission 0 - Mission 0: Software Setup and Manual Un-docking
Learn and practice the steps to start up the simulation. Understand the relationship between the simulator setup and the real-world hardware and software configuration. Verify the vehicle responds by manually driving it away from the dock, then back.

## Setup
1. Complete steps in [System Overview -  Setup and Running](https://github.com/cmroboticsacademy/gazebosim_blueboat_ardupilot_sitl/blob/main/README.md)

### Opening a plan in QGroundControl.
Each mission has a default program that needs to be opened and uploaded to the robot. These steps will use mission0.plan as an example. Other missions will instruct you to open the plan, but will not go into detail.
1. In QGroundControl click on the Q menu button. <br /> ![q_menu](./cmra_images/qgc_menu.png)
2. Click <b>Plan Flight</b>
3. Select <b>File</b> to open the menu. ![q_menu](./cmra_images/qgc_file.png)
4. Click <b>Open</b> <br />
5. Open mission0.plan file. ![q_menu](./cmra_images/qgc_plan.png)
6. Upload your plan to ArduPilot by clicking Upload Required<br /> ![Alt text](./cmra_images/qgc_upload.png)
7. Exit plan.

### Mission 0 plan
The mission zero plan provides you with two GEO fences. The first fence is where the dock is located in the simulated world. The second is where a buoy is located in the world. These GEO fences are set up to work with your robot's pathfinding logic. The pathfinder will try to avoid these zones as best as possible. If your robot enters one of these zones, it will automatically change the flight mode to Hold. 

###  Manual Un-docking
All steps should be performed inside QGroundControl unless otherwise stated.
<b>Arming in manual mode</b>

1. In Gazebo, right-click the blueboat in the Entity Tree. Click Follow. This will make the camera follow the Blueboat while it moves. <br />![Alt text](./cmra_images/follow.png)
2.  QGroundControl will have a green banner and state "Ready to Fly" as its status.
    1.  In <b>T2 (ArduPilot Terminal)</b>, confirm your robot is ready to be armed. You should see output similar to this.
        ```bash
        AP: EKF3 IMU0 tilt alignment complete
        AP: EKF3 IMU1 tilt alignment complete
        AP: EKF3 IMU0 MAG0 initial yaw alignment complete
        AP: EKF3 IMU1 MAG0 initial yaw alignment complete
        AP: GPS 1: detected as u-blox at 230400 baud
        AP: EKF3 IMU0 origin set
        AP: EKF3 IMU1 origin set
        AP: Field Elevation Set: 0m
        AP: EKF3 IMU0 is using GPS
        AP: EKF3 IMU1 is using GPS
        AP: AHRS: EKF3 active
        ```
3. Arm your robot by pressing the <b>Arm Button</b> on your RC. <br />
    <details>

    <summary>Failed to arm?</summary>

    Before the robot arms, it goes through a series of checks. If one of the checks fails, the robot fails to arm. In the simulator, it is most likely due to three causes.
    1. Your RC is throttling the robot and not set in a netural postion. This will prevent EKF3 from activating. Try recalibrating your RC in vehicle configuration. If this fails, unplug the RC and manually arm through QGroundControl before plugging your RC back in. 
    2. You did not wait until EKF3 is active. You'll see errors stating you did not set the AHRS mode.
    3. The computer is running too slow to consistently send sensor data to ArduPilot, and will take a little longer to calibrate its position and satisfy all of the arming checks.
        
    If this happens to you, wait until your QGroundControl status states "Ready to Fly" and is green and rearm.

    </details>

4. Drive the boat, monitor the battery, and take note of the experience. There is a buoy marked on your map. Try to drive around it. What happens when you get too close? 