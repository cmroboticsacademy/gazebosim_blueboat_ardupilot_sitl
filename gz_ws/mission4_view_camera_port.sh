#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-5600}"
TITLE="${2:-Mission4 camera port ${PORT}}"

cat <<MSG
Mission 4 direct camera viewer
  input: udp://127.0.0.1:${PORT}

Close this window or press Ctrl+C to stop.
MSG

# This pipeline receives the H.264/RTP stream produced by the Gazebo GstCameraPlugin,
# depayloads and decodes it, then displays it in a local video window.
gst-launch-1.0 -e \
  udpsrc port="${PORT}" caps='application/x-rtp, media=(string)video, clock-rate=(int)90000, encoding-name=(string)H264, payload=(int)96' \
  ! rtpjitterbuffer latency=50 drop-on-latency=true \
  ! rtph264depay \
  ! h264parse \
  ! avdec_h264 \
  ! videoconvert \
  ! autovideosink sync=false
