#!/usr/bin/env bash
set -euo pipefail

# Mission 4 two-BlueBoat camera mixer for QGroundControl.
# Default setup:
#   Boat 1 raw camera input: UDP RTP/H264 on 127.0.0.1:5600
#   Boat 2 raw camera input: UDP RTP/H264 on 127.0.0.1:5601
#   Mixed side-by-side output: UDP RTP/H264 on 127.0.0.1:5602
#
# In QGroundControl set:
#   Application Settings -> General -> Video
#   Video Source: UDP h.264 Video Stream
#   URL/Port: 5602
#
# Override ports if needed, for example:
#   IN1_PORT=5700 IN2_PORT=5701 OUT_PORT=5600 ./mission4_video_grid.sh

IN1_PORT="${IN1_PORT:-5600}"
IN2_PORT="${IN2_PORT:-5601}"
OUT_HOST="${OUT_HOST:-127.0.0.1}"
OUT_PORT="${OUT_PORT:-5602}"
WIDTH="${WIDTH:-640}"
HEIGHT="${HEIGHT:-360}"
FPS="${FPS:-15}"
BITRATE="${BITRATE:-1800}"

RTP_CAPS='application/x-rtp, media=(string)video, clock-rate=(int)90000, encoding-name=(string)H264, payload=(int)96'

cat <<EOF
Mission 4 video grid mixer
  input 1: udp://127.0.0.1:${IN1_PORT}
  input 2: udp://127.0.0.1:${IN2_PORT}
  output : udp://${OUT_HOST}:${OUT_PORT}

Set QGroundControl video URL/Port to: ${OUT_PORT}
EOF

exec gst-launch-1.0 -e \
  compositor name=mix background=black ignore-inactive-pads=true \
    sink_0::xpos=0 sink_0::ypos=0 sink_0::width="${WIDTH}" sink_0::height="${HEIGHT}" \
    sink_1::xpos="${WIDTH}" sink_1::ypos=0 sink_1::width="${WIDTH}" sink_1::height="${HEIGHT}" ! \
  video/x-raw,width=$((WIDTH * 2)),height="${HEIGHT}",framerate="${FPS}"/1 ! \
  videoconvert ! \
  x264enc tune=zerolatency speed-preset=ultrafast bitrate="${BITRATE}" key-int-max="${FPS}" ! \
  video/x-h264,profile=baseline ! \
  rtph264pay config-interval=1 pt=96 ! \
  udpsink host="${OUT_HOST}" port="${OUT_PORT}" sync=false async=false \
  udpsrc port="${IN1_PORT}" caps="${RTP_CAPS}" ! \
    queue ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! videoscale ! \
    video/x-raw,width="${WIDTH}",height="${HEIGHT}",framerate="${FPS}"/1 ! queue ! mix.sink_0 \
  udpsrc port="${IN2_PORT}" caps="${RTP_CAPS}" ! \
    queue ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! videoscale ! \
    video/x-raw,width="${WIDTH}",height="${HEIGHT}",framerate="${FPS}"/1 ! queue ! mix.sink_1
