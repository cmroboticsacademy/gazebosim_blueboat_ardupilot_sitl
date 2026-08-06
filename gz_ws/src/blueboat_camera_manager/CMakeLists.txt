cmake_minimum_required(VERSION 3.8)
project(blueboat_camera_manager)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclpy REQUIRED)
find_package(std_msgs REQUIRED)
find_package(std_srvs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(gz-sim7 REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "srv/SetCameraConfig.srv"
  "srv/SetCameraEnabled.srv"
  "srv/SetCameraLag.srv"
)

add_library(BlueBoatCameraTriggerPlugin SHARED
  src/BlueBoatCameraTriggerPlugin.cc
)
target_compile_features(BlueBoatCameraTriggerPlugin PUBLIC cxx_std_17)
target_link_libraries(BlueBoatCameraTriggerPlugin PRIVATE gz-sim7::gz-sim7)

install(PROGRAMS
  blueboat_camera_manager/camera_manager_node.py
  DESTINATION lib/${PROJECT_NAME}
  RENAME camera_manager_node
)
install(PROGRAMS
  blueboat_camera_manager/camera_web_node.py
  DESTINATION lib/${PROJECT_NAME}
  RENAME camera_web_node
)
install(TARGETS
  BlueBoatCameraTriggerPlugin
  LIBRARY DESTINATION lib
)
install(DIRECTORY launch config web
  DESTINATION share/${PROJECT_NAME}
)
install(FILES LICENSE DESTINATION share/${PROJECT_NAME})

ament_environment_hooks(
  "hooks/blueboat_camera_manager.dsv.in"
  "hooks/blueboat_camera_manager.sh.in"
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
