# Mission 4 seeded hazard placement

This bundle replaces the fixed hazard grid in `level6.sdf` with launch-time,
seeded placement inside the four buoy zones. It preserves the existing four
boats, Gazebo/ArduPilot bridges, bathymetry mappers, RViz configuration, dock,
terrain, lake floor, buoys, and delayed camera-stream startup.

The repository's actual launch filename is `mission4_sim.launch.py`.

## Files in this bundle

- `gz_ws/src/move_blueboat/launch/mission4_sim.launch.py` — adds the `seed`
  launch argument and starts Gazebo with the generated world.
- `gz_ws/src/move_blueboat/move_blueboat/mission4_world_generator.py` — assigns
  and places hazards, renders a temporary SDF, and reports the seed.
- `gz_ws/src/asv_wave_sim/gz-waves-models/worlds/level6.sdf` — keeps the
  existing world but replaces the fixed hazard includes with two insertion
  markers.

No `setup.py` change is needed. The new Python module is automatically included
in the existing `move_blueboat` setuptools package.

## Placement behavior

On every launch, the generator:

1. Uses the supplied integer seed, or generates a random 32-bit seed.
2. Shuffles all seven positive and four negative hazards.
3. Gives every zone at least one positive and one negative hazard.
4. Assigns every remaining hazard exactly once while enforcing the five-object
   zone limit.
5. Chooses seeded X, Y, and yaw values. Every Z value is exactly `-10`.
6. Rotates each model's measured visual footprint by its candidate yaw and uses
   a separating-axis collision test before accepting the position.
7. Keeps the complete footprint at least 2 m inside the buoy-zone boundary and
   maintains at least 1 m clearance between footprint envelopes.
8. Keeps the nearest point of every rotated object footprint at least 15 m from
   each of the four buoy poses defining its zone.
9. Names each Gazebo entity as
   `zone_<number>__<category>__<original_model_name>` so the Entity Tree groups
   objects by zone and clearly identifies positive and negative hazards.
10. Writes `/tmp/mission4_level6_seed_<seed>.sdf` and launches Gazebo with that
   generated file.

For example, the tree will contain names such as:

```text
zone_1__negative__cmra_canoe
zone_1__positive__cmra_airplane
zone_2__negative__cmra_couch
zone_2__positive__cmra_bus
```

The prefix changes only the included model instance name. The model URI remains
unchanged, such as `model://cmra_models/airplane`.

### Collision calculation

The footprint bounds were calculated from every vertex in the current OBJ
meshes after applying each model's SDF scale and its 90-degree Y-up-to-Z-up
rotation. The resulting enclosing dimensions are:

| Hazard | Footprint width (m) | Footprint length (m) |
| --- | ---: | ---: |
| Airplane | 6.506 | 4.897 |
| Boat | 2.303 | 6.262 |
| Bus | 2.244 | 10.417 |
| Wrecked car | 2.699 | 4.210 |
| Drone | 1.022 | 1.232 |
| Drum | 0.590 | 0.587 |
| Truck | 2.688 | 6.064 |
| Canoe | 1.185 | 4.820 |
| Couch | 2.362 | 1.017 |
| Picnic table | 2.475 | 2.525 |
| Seaweed | 2.907 | 2.903 |

Each footprint retains its actual offset from the model origin. It is rotated
around that origin by the generated yaw. The generator rejects a candidate if
its oriented rectangle overlaps another object's clearance envelope or extends
outside its zone. The buoy test inverse-rotates each buoy pose into the model's
local frame and calculates the shortest distance to the footprint rectangle.
This means the 15 m rule applies to the nearest edge of the visible object, not
only to its center.

The current hazard `model.sdf` files contain visual meshes but no `<collision>`
elements. This calculation prevents visible mesh intersection at spawn. Adding
physical Gazebo collision behavior would require collision geometry in those
model files as a separate change.

The four bounds are derived from the current `level6.sdf` buoy coordinates:

| Zone | X range | Y range | Buoys |
| --- | ---: | ---: | --- |
| 1 | -40 to 40 | -80 to -40 | B1–B4 |
| 2 | 100 to 180 | -40 to 0 | B5–B8 |
| 3 | 150 to 190 | 40 to 120 | B9–B12 |
| 4 | 90 to 170 | 145 to 185 | B13–B16 |

## Install

Place the ZIP in the root of the cloned repository, where `gz_ws` and
`SITL_Models` are visible, then run:

```bash
unzip -o mission4_seeded_hazard_placement.zip
cd gz_ws
colcon build --symlink-install --merge-install --packages-select move_blueboat
source install/setup.bash
source gazebo_exports.sh
```

The `source gazebo_exports.sh` step matters because the generator resolves
`level6.sdf` through the same `GZ_SIM_RESOURCE_PATH` used by Gazebo. If your
container's shell startup already sources this script, running it again is
harmless.

## Launch

To generate a random layout:

```bash
ros2 launch move_blueboat mission4_sim.launch.py
```

The terminal prints a line such as:

```text
Mission 4 hazard seed: 3187462051
```

Save that number to recreate the layout later:

```bash
ros2 launch move_blueboat mission4_sim.launch.py seed:=3187462051
```

Any integer is valid, including `0`. A non-integer seed stops the launch with a
clear validation error.

## Project flow after this change

1. `ros2 launch` loads the installed `mission4_sim.launch.py`.
2. The launch argument is resolved before Gazebo starts.
3. `mission4_world_generator.py` finds the source `level6.sdf`, assigns all 11
   hazards, and replaces only the content between
   `MISSION4_HAZARDS_START` and `MISSION4_HAZARDS_END` in a temporary copy.
4. Gazebo 7 starts with the absolute path to that temporary world.
5. The existing ROS–Gazebo parameter bridge starts for all four boats.
6. The four existing bathymetry mapper nodes and RViz start unchanged.
7. After 10 seconds, the existing four camera streaming commands run unchanged.

The source `level6.sdf` no longer displays the old fixed grid. Do not delete or
rename the two `MISSION4_HAZARDS_*` marker comments; the generator uses them as
the insertion point.

## Customizing later

Edit the constants near the top of
`move_blueboat/mission4_world_generator.py` to change `ZONE_EDGE_CLEARANCE`,
`OBJECT_CLEARANCE`, `BUOY_CLEARANCE`, maximum objects per zone, model lists,
footprint bounds, or zone bounds. If a mesh or its SDF scale changes,
recalculate its `Footprint`. If buoy coordinates change, update the matching
`ZONES` entry so placement remains inside the new rectangle.
