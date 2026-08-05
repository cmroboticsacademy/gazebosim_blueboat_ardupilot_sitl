cmake_minimum_required(VERSION 3.8)
project(blueboat_camera_manager)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)
find_package(rclpy REQUIRED)
find_package(std_msgs REQUIRED)
find_package(std_srvs REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(gz-sim7 REQUIRED)
find_package(OpenCV REQUIRED COMPONENTS core imgproc)
find_package(PkgConfig REQUIRED)
pkg_check_modules(GSTREAMER REQUIRED IMPORTED_TARGET
  gstreamer-1.0
  gstreamer-app-1.0
)

rosidl_generate_interfaces(${PROJECT_NAME}
  "srv/SetCameraConfig.srv"
  "srv/SetCameraEnabled.srv"
  "srv/SelectCamera.srv"
)

add_library(BlueBoatGstCameraPlugin SHARED
  src/BlueBoatGstCameraPlugin.cc
)
target_compile_features(BlueBoatGstCameraPlugin PUBLIC cxx_std_17)
target_include_directories(BlueBoatGstCameraPlugin PRIVATE ${OpenCV_INCLUDE_DIRS})
target_link_libraries(BlueBoatGstCameraPlugin PRIVATE
  gz-sim7::gz-sim7
  ${OpenCV_LIBRARIES}
  PkgConfig::GSTREAMER
)

add_library(BlueBoatCameraFollowerPlugin SHARED
  src/BlueBoatCameraFollowerPlugin.cc
)
target_compile_features(BlueBoatCameraFollowerPlugin PUBLIC cxx_std_17)
target_link_libraries(BlueBoatCameraFollowerPlugin PRIVATE gz-sim7::gz-sim7)

ament_python_install_package(${PROJECT_NAME})
install(PROGRAMS
  blueboat_camera_manager/camera_manager_node.py
  DESTINATION lib/${PROJECT_NAME}
  RENAME camera_manager_node
)
install(TARGETS
  BlueBoatGstCameraPlugin
  BlueBoatCameraFollowerPlugin
  LIBRARY DESTINATION lib
)
install(DIRECTORY launch config
  DESTINATION share/${PROJECT_NAME}
)
install(FILES LICENSE DESTINATION share/${PROJECT_NAME})

ament_environment_hooks(
  "hooks/blueboat_camera_manager.dsv.in"
  "hooks/blueboat_camera_manager.sh.in"
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
