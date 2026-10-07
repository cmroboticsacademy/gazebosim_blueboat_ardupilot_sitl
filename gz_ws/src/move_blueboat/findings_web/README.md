# Mission 4 Findings Map — ROS Bag Replay

The Mission 4 Findings Map is a post-mission analysis tool for ROS 2 bag recordings.

It is designed to be used with:

- A recorded Mission 4 ROS bag
- The four Mission 4 bathymetry mapper nodes
- RViz
- The Mission 4 Findings Map web app

Gazebo, ArduPilot, and QGroundControl do **not** need to be running during replay.

The workflow is:

```text
Mission 4 ROS bag
       |
       +--> Boat odometry ------------------------+
       |                                          |
       |                                          v
       |                                  Findings Map
       |                                  boat tracks
       |
       +--> Raw bathymetry scans --> Bathymetry mappers
                                           |
                                           v
                                      PointCloud2
                                           |
                                           v
                                          RViz
                                           |
                                  RViz Publish Point
                                           |
                                      /clicked_point
                                           |
                                           v
                                      Findings Map
                                      map marker
```

When a student sees a suspected submerged object in the reconstructed point
cloud, they pause the bag, click the object with RViz **Publish Point**, and the
finding automatically appears on the geographic map.

The finding can then be classified and exported as CSV or JSON.

---

## 1. Use the `mission4-findings-map` branch

From the repository:

```bash
git fetch origin
git checkout mission4-findings-map
git pull
```

The Findings Map branch is based on `mission4-rtf-optimization`, so it also
contains the Mission 4 runtime optimizations.

---

## 2. Build the ROS workspace

Enter the BlueBoat Docker container if needed:

```bash
sudo docker exec -it blueboat_sitl /bin/bash
```

Then build and source the workspace:

```bash
cd ~/gz_ws
colcon build --merge-install
source install/setup.bash
```

Run the build after initially pulling this branch because the Findings Map adds
a new ROS executable, launch file, and web assets.

---

## 3. Record the Mission 4 bag

If you already have a Mission 4 bag containing the required topics, skip to
[Inspect the bag](#4-inspect-the-bag).

During the live Mission 4 run, record the four boats' odometry and raw
bathymetry scans:

```bash
ros2 bag record -o mission4_run \
  /model/blueboat/odometry \
  /bathymetry/scan \
  /model/blueboat2/odometry \
  /blueboat2/bathymetry/scan \
  /model/blueboat3/odometry \
  /blueboat3/bathymetry/scan \
  /model/blueboat4/odometry \
  /blueboat4/bathymetry/scan
```

Leave the recorder running for the complete survey.

When the mission is finished, stop recording with:

```text
Ctrl+C
```

The bag will be stored in:

```text
mission4_run/
```

### Why the accumulated point clouds are not recorded

Do not normally record:

```text
/blueboat/ocean_floor/map_cloud
/blueboat2/ocean_floor/map_cloud
/blueboat3/ocean_floor/map_cloud
/blueboat4/ocean_floor/map_cloud
```

The mapper republishes the entire accumulated map. Recording those topics would
store increasingly large copies of the same map.

Instead, the replay regenerates the maps from the original bathymetry scans and
odometry.

---

## 4. Inspect the bag

Before replaying, verify the bag:

```bash
ros2 bag info mission4_run
```

The bag should contain these eight topics:

```text
/model/blueboat/odometry
/bathymetry/scan

/model/blueboat2/odometry
/blueboat2/bathymetry/scan

/model/blueboat3/odometry
/blueboat3/bathymetry/scan

/model/blueboat4/odometry
/blueboat4/bathymetry/scan
```

The Findings Map uses the odometry topics to draw each boat's route.

The bathymetry mappers use the odometry and scan topics together to reconstruct
the ocean floor.

---

# Replay Setup

Start the replay tools **before playing the bag**.

A useful terminal layout is:

```text
Terminal 1    Boat 1 mapper
Terminal 2    Boat 2 mapper
Terminal 3    Boat 3 mapper
Terminal 4    Boat 4 mapper
Terminal 5    Findings Map
Terminal 6    ROS bag playback
RViz          Point-cloud visualization
Browser       Findings Map
```

Each ROS terminal should have the workspace sourced:

```bash
cd ~/gz_ws
source install/setup.bash
```

---

## 5. Start the four bathymetry mappers

### Boat 1

```bash
ros2 run move_blueboat bathymetry_mapper --ros-args \
  -r __node:=bathymetry_mapper_blueboat \
  -p scan_topic:=/bathymetry/scan \
  -p odom_topic:=/model/blueboat/odometry \
  -p cloud_topic:=/blueboat/ocean_floor/map_cloud \
  -p map_frame:=odom \
  -p sensor_offset_xyz:="[0.20, 0.0, -0.35]" \
  -p sensor_offset_rpy:="[0.0, 1.57079632679, 0.0]" \
  -p voxel_size:=0.05 \
  -p min_range:=0.20 \
  -p max_range:=30.0
```

### Boat 2

```bash
ros2 run move_blueboat bathymetry_mapper --ros-args \
  -r __node:=bathymetry_mapper_blueboat2 \
  -p scan_topic:=/blueboat2/bathymetry/scan \
  -p odom_topic:=/model/blueboat2/odometry \
  -p cloud_topic:=/blueboat2/ocean_floor/map_cloud \
  -p map_frame:=odom \
  -p sensor_offset_xyz:="[0.20, 0.0, -0.35]" \
  -p sensor_offset_rpy:="[0.0, 1.57079632679, 0.0]" \
  -p voxel_size:=0.05 \
  -p min_range:=0.20 \
  -p max_range:=30.0
```

### Boat 3

```bash
ros2 run move_blueboat bathymetry_mapper --ros-args \
  -r __node:=bathymetry_mapper_blueboat3 \
  -p scan_topic:=/blueboat3/bathymetry/scan \
  -p odom_topic:=/model/blueboat3/odometry \
  -p cloud_topic:=/blueboat3/ocean_floor/map_cloud \
  -p map_frame:=odom \
  -p sensor_offset_xyz:="[0.20, 0.0, -0.35]" \
  -p sensor_offset_rpy:="[0.0, 1.57079632679, 0.0]" \
  -p voxel_size:=0.05 \
  -p min_range:=0.20 \
  -p max_range:=30.0
```

### Boat 4

```bash
ros2 run move_blueboat bathymetry_mapper --ros-args \
  -r __node:=bathymetry_mapper_blueboat4 \
  -p scan_topic:=/blueboat4/bathymetry/scan \
  -p odom_topic:=/model/blueboat4/odometry \
  -p cloud_topic:=/blueboat4/ocean_floor/map_cloud \
  -p map_frame:=odom \
  -p sensor_offset_xyz:="[0.20, 0.0, -0.35]" \
  -p sensor_offset_rpy:="[0.0, 1.57079632679, 0.0]" \
  -p voxel_size:=0.05 \
  -p min_range:=0.20 \
  -p max_range:=30.0
```

Leave all four mapper nodes running.

---

## 6. Open RViz

Open another sourced terminal and launch the existing Mission 4 RViz
configuration:

```bash
rviz2 -d "$(ros2 pkg prefix move_blueboat)/share/move_blueboat/rviz/mission4_two_blueboats_mapping.rviz"
```

The RViz configuration displays:

```text
BlueBoat 1 Ocean Floor Map
BlueBoat 2 Ocean Floor Map
BlueBoat 3 Ocean Floor Map
BlueBoat 4 Ocean Floor Map

BlueBoat 1 Odometry
BlueBoat 2 Odometry
BlueBoat 3 Odometry
BlueBoat 4 Odometry
```

The fixed frame should be:

```text
odom
```

RViz may initially appear mostly empty. That is expected because the bag has not
started playing yet.

---

## 7. Start the Findings Map

In another sourced terminal:

```bash
ros2 launch move_blueboat mission4_findings.launch.py
```

The terminal should report:

```text
Mission 4 Findings Map listening for /clicked_point at http://127.0.0.1:8090
```

Open a browser on the host computer:

```text
http://127.0.0.1:8090
```

The app is localhost-only by default.

The Findings Map automatically listens to:

```text
/clicked_point

/model/blueboat/odometry
/model/blueboat2/odometry
/model/blueboat3/odometry
/model/blueboat4/odometry
```

No additional ROS bridge is required.

### Map layers

The app provides:

- Satellite imagery
- Street-map imagery
- Mission 4 geographic origin
- BlueBoat 1 route
- BlueBoat 2 route
- BlueBoat 3 route
- BlueBoat 4 route
- Student findings

The satellite imagery comes from an online tile service, so the browser needs
internet access to display the satellite layer.

The custom Gazebo Mission 4 terrain is not a copy of the real-world terrain at
the WGS84 anchor. The satellite layer is therefore geographic context rather
than a visual representation of the simulated lake.

---

## 8. Start the ROS bag

Only after the mappers, RViz, and Findings Map are running, start the replay.

From the directory containing the bag:

```bash
ros2 bag play mission4_run
```

The point clouds should begin reconstructing in RViz.

The four BlueBoat routes should begin appearing in the Findings Map.

---

# Marking Findings

## 9. Pause when an object is found

Watch the reconstructed point cloud in RViz.

When a suspected submerged object appears, go to the terminal running the bag
and press:

```text
Space
```

The bag pauses.

The current accumulated point cloud remains visible in RViz.

---

## 10. Select RViz Publish Point

In the RViz toolbar, select:

```text
Publish Point
```

The existing Mission 4 RViz configuration publishes selected points to:

```text
/clicked_point
```

Click near the center of the suspected object in the point cloud.

You do not need to copy the coordinates manually.

---

## 11. Verify the finding appears on the map

The Findings Map automatically receives the RViz click.

A new marker should appear immediately:

```text
Finding 1
Finding 2
Finding 3
...
```

The app stores:

- RViz X coordinate
- RViz Y coordinate
- RViz Z coordinate
- Latitude
- Longitude
- ROS timestamp
- Classification
- Object guess
- Confidence
- Notes

The coordinate conversion uses the Mission 4 geographic origin:

```text
Latitude:  40.595009
Longitude: -79.999740
Replay map heading: 0 degrees
```

The replay map heading is intentionally `0` even though the Gazebo world's
`<spherical_coordinates>` block contains `<heading_deg>180</heading_deg>`.
The Findings Map is converting the replayed `/model/.../odometry` X/Y
coordinates used by RViz. Applying the world's 180-degree spherical heading
again rotates both axes a second time.

For the standard Mission 4 bag replay:

```text
+X = East
-X = West
+Y = North
-Y = South
```

The `heading_deg` launch argument remains available for bags that use a
different odometry convention.

---

## 12. Classify the finding

Select the new finding in the web app.

Choose a classification:

```text
Unclassified
Hazard
Non-hazard
```

Enter an optional object guess:

```text
Truck
Drum
Boat
Airplane
Canoe
Unknown
```

Set the confidence:

```text
0% ---------------- 100%
```

Add notes if desired.

Example:

```text
Finding 4

Classification: Hazard
Object guess: Truck
Confidence: 85%

Notes:
Large rectangular object with a raised center section.
```

Select:

```text
Save finding
```

The marker remains on the map.

---

## 13. Resume the replay

Return to the bag terminal and press:

```text
Space
```

again.

Continue watching the map build.

Repeat:

```text
See object in RViz
        |
        v
Pause bag
        |
        v
RViz Publish Point
        |
        v
Click object
        |
        v
Marker automatically appears
        |
        v
Classify finding
        |
        v
Save
        |
        v
Resume bag
```

---

# Working with Findings

## Select an existing finding

Click a finding in the list.

The map pans to that marker and opens its location.

You can update:

- Classification
- Object guess
- Confidence
- Notes

---

## Delete an incorrect finding

Select the finding and use:

```text
Delete
```

This is useful if the wrong point was clicked in RViz.

---

## Clear the activity

Use:

```text
Clear findings
```

to remove all findings.

This does not change the ROS bag or bathymetry maps.

---

# Exporting Results

## CSV

Select:

```text
Export CSV
```

The exported file contains columns including:

```text
id
classification
object_guess
confidence
notes
x
y
z
latitude
longitude
frame_id
ros_time_sec
```

This is useful for spreadsheets and scoring.

---

## JSON

Select:

```text
Export JSON
```

The JSON export includes:

- Mission 4 geographic origin
- All findings
- All four reconstructed boat paths

This is useful for later automated scoring against the Mission 4 seed-generated
ground truth.

---

# Faster Replay

The bag can be replayed faster than real time:

```bash
ros2 bag play mission4_run -r 2.0
```

or:

```bash
ros2 bag play mission4_run -r 4.0
```

You can still pause with the space bar when an object needs closer inspection.

For object-identification activities, normal speed or `2.0` is usually easier
than very fast replay.

---

# Restarting a Replay

The bathymetry mapper accumulates points in memory.

The Findings Map also accumulates boat paths and findings in memory.

For a completely clean replay:

1. Stop `ros2 bag play`.
2. Stop all four bathymetry mapper nodes.
3. Stop the Findings Map node.
4. Restart the four bathymetry mappers.
5. Restart the Findings Map.
6. Refresh the web page.
7. Start `ros2 bag play` again.

RViz itself does not normally need to be restarted.

---

# Troubleshooting

## Findings Map opens but no boat routes appear

Make sure the bag contains:

```text
/model/blueboat/odometry
/model/blueboat2/odometry
/model/blueboat3/odometry
/model/blueboat4/odometry
```

Check:

```bash
ros2 bag info mission4_run
```

and while the bag is playing:

```bash
ros2 topic hz /model/blueboat/odometry
```

---

## RViz click does not create a marker

Confirm that RViz is publishing:

```text
/clicked_point
```

Run:

```bash
ros2 topic echo /clicked_point
```

Then select **Publish Point** in RViz and click the point cloud.

A `geometry_msgs/msg/PointStamped` message should appear.

Also verify the Findings Map node is running:

```bash
ros2 node list | grep mission4_findings
```

---

## Point clouds do not appear in RViz

Check that all four mapper nodes are running:

```bash
ros2 node list | grep bathymetry_mapper
```

Check that the bag is publishing scans:

```bash
ros2 topic hz /bathymetry/scan
```

Check that Boat 1's mapper is publishing its reconstructed map:

```bash
ros2 topic hz /blueboat/ocean_floor/map_cloud
```

Repeat with the other boat namespaces if necessary.

---

## Satellite imagery does not appear

The satellite and street basemaps are loaded from online tile services.

Verify that the host browser has internet access.

The ROS node and findings workflow can still operate without map tiles, but the
geographic background will not display.

---

## Map markers appear in the wrong geographic location

The standard Mission 4 bag replay maps the RViz / odometry axes directly:

```text
+X = East
+Y = North
heading_deg = 0
```

This replay-map heading is separate from Gazebo's world
`<spherical_coordinates>` heading. Do not copy the world's
`heading_deg=180` into the Findings Map for the standard Mission 4 replay;
doing that rotates the boat paths and findings by 180 degrees.

If another bag uses a rotated odometry frame, override only the Findings Map
conversion:

```bash
ros2 launch move_blueboat mission4_findings.launch.py \
  latitude_deg:=40.595009 \
  longitude_deg:=-79.999740 \
  heading_deg:=0.0
```

---

# Recommended Classroom Workflow

A complete post-mission activity can be run as:

```text
1. Complete Mission 4
2. Stop the bag recording
3. Shut down Gazebo, ArduPilot, and QGroundControl

4. Start four bathymetry mappers
5. Open RViz
6. Start Mission 4 Findings Map
7. Open http://127.0.0.1:8090
8. Play the Mission 4 ROS bag

9. Find object in RViz
10. Pause bag
11. Publish Point
12. Click object
13. Classify the automatic map marker
14. Resume bag
15. Repeat

16. Export CSV / JSON
17. Compare student findings against Mission 4 ground truth
```

This keeps the analysis activity completely separate from the live simulation.
