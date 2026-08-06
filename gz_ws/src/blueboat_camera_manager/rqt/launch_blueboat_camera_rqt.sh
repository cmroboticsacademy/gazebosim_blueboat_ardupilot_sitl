#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PERSPECTIVE_FILE="$SCRIPT_DIR/BlueBoatCameraManager.perspective"
WORKSPACE_SETUP="${BLUEBOAT_WS_SETUP:-$HOME/gz_ws/install/setup.bash}"
WAIT_SECONDS="${BLUEBOAT_RQT_WAIT_SECONDS:-30}"

# Colcon-generated setup scripts may read optional variables such as
# COLCON_TRACE without first assigning them. Temporarily disable Bash nounset
# while sourcing ROS environments, then restore the launcher's strict mode.
source_setup_file() {
  local setup_file="$1"
  local nounset_was_enabled=0
  local source_status=0

  case "$-" in
    *u*)
      nounset_was_enabled=1
      set +u
      ;;
  esac

  if source "$setup_file"; then
    source_status=0
  else
    source_status=$?
  fi

  if (( nounset_was_enabled )); then
    set -u
  fi

  return "$source_status"
}

if [[ -z "${ROS_DISTRO:-}" ]]; then
  for distro in jazzy humble iron rolling; do
    if [[ -f "/opt/ros/$distro/setup.bash" ]]; then
      # shellcheck disable=SC1090
      if ! source_setup_file "/opt/ros/$distro/setup.bash"; then
        echo "ERROR: Failed to source /opt/ros/$distro/setup.bash" >&2
        exit 1
      fi
      break
    fi
  done
fi

if [[ -z "${ROS_DISTRO:-}" ]]; then
  echo "ERROR: ROS 2 was not sourced and no installation was found under /opt/ros." >&2
  exit 1
fi

if [[ -f "$WORKSPACE_SETUP" ]]; then
  # shellcheck disable=SC1090
  if ! source_setup_file "$WORKSPACE_SETUP"; then
    echo "ERROR: Failed to source workspace setup: $WORKSPACE_SETUP" >&2
    exit 1
  fi
else
  echo "WARNING: Workspace setup file was not found: $WORKSPACE_SETUP" >&2
  echo "The custom BlueBoat service types may not be visible to RQt." >&2
fi

if ! command -v rqt >/dev/null 2>&1; then
  echo "ERROR: rqt is not installed." >&2
  echo "Install it with:" >&2
  echo "  sudo apt install ros-$ROS_DISTRO-rqt ros-$ROS_DISTRO-rqt-service-caller" >&2
  exit 1
fi

if ! ros2 pkg prefix rqt_service_caller >/dev/null 2>&1; then
  echo "ERROR: rqt_service_caller is not installed." >&2
  echo "Install it with:" >&2
  echo "  sudo apt install ros-$ROS_DISTRO-rqt-service-caller" >&2
  exit 1
fi

if ! ros2 interface show blueboat_camera_manager/srv/SetCameraLag >/dev/null 2>&1; then
  echo "WARNING: SetCameraLag is not visible in the current environment." >&2
  echo "Build and source the camera manager package before opening RQt:" >&2
  echo "  cd ~/gz_ws" >&2
  echo "  colcon build --packages-select blueboat_camera_manager" >&2
  echo "  source ~/gz_ws/install/setup.bash" >&2
fi

if [[ "$WAIT_SECONDS" =~ ^[0-9]+$ ]] && (( WAIT_SECONDS > 0 )); then
  echo "NAH  to ${WAIT_SECONDS}s for /blueboat_camera_manager/status..."
  found=0
  for ((i=0; i<WAIT_SECONDS; i++)); do
    if ros2 service list 2>/dev/null | grep -Fxq '/blueboat_camera_manager/status'; then
      found=1
      break
    fi
    sleep 1
  done
  if (( found == 0 )); then
    echo "WARNING: Camera manager services were not detected." >&2
    echo "RQt will still open, but service selections may remain blank until the simulator is running." >&2
  fi
fi

exec rqt --perspective-file "$PERSPECTIVE_FILE"
