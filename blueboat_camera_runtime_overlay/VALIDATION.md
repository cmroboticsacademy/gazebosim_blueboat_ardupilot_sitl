# Validation performed

- Parsed the new `package.xml`, camera pod `model.config`, and camera pod
  `model.sdf` as XML.
- Compiled the installer and ROS 2 manager Python files with `py_compile`.
- Checked `apply.sh` with `bash -n`.
- Applied the installer to a synthetic checkout containing the same target
  anchors used by the current main-branch files, then parsed all resulting SDF
  and package XML and compiled the resulting launch file.
- Verified the installer is idempotent on that synthetic checkout.

The artifact environment does not contain Gazebo Garden, ROS 2, OpenCV, or
GStreamer development packages, so the two C++ plugins could not be compiled or
run here. Build and runtime verification commands are included in `README.md`.
