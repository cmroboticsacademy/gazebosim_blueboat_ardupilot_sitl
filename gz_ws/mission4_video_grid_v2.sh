#!/usr/bin/env bash
set -euo pipefail

# Mission 4 two-BlueBoat camera mixer for QGroundControl.
#
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
#   IN1_PORT=5700 IN2_PORT=5701 OUT_PORT=5600 ./mission4_video_grid_v2.sh

IN1_PORT="${IN1_PORT:-5600}"
IN2_PORT="${IN2_PORT:-5601}"
OUT_HOST="${OUT_HOST:-127.0.0.1}"
OUT_PORT="${OUT_PORT:-5602}"
WIDTH="${WIDTH:-640}"
HEIGHT="${HEIGHT:-360}"
FPS="${FPS:-15}"
BITRATE="${BITRATE:-1800}"
JITTER_LATENCY_MS="${JITTER_LATENCY_MS:-50}"

FULL_WIDTH=$((WIDTH * 2))
RTP_CAPS='application/x-rtp, media=(string)video, clock-rate=(int)90000, encoding-name=(string)H264, payload=(int)96'

cat <<MSG
Mission 4 video grid mixer v2
  input 1: udp://127.0.0.1:${IN1_PORT}
  input 2: udp://127.0.0.1:${IN2_PORT}
  output : udp://${OUT_HOST}:${OUT_PORT}

Set QGroundControl video URL/Port to: ${OUT_PORT}
Close QGroundControl or set it to ${OUT_PORT} before starting this mixer.
Do not leave QGC listening on ${IN1_PORT} or ${IN2_PORT}; those are mixer input ports.
MSG

exec gst-launch-1.0 \
  compositor name=mix background=black ignore-inactive-pads=true \
    sink_0::xpos=0 sink_0::ypos=0 sink_0::width="${FULL_WIDTH}" sink_0::height="${HEIGHT}" sink_0::zorder=0 \
    sink_1::xpos=0 sink_1::ypos=0 sink_1::width="${WIDTH}" sink_1::height="${HEIGHT}" sink_1::zorder=1 \
    sink_2::xpos="${WIDTH}" sink_2::ypos=0 sink_2::width="${WIDTH}" sink_2::height="${HEIGHT}" sink_2::zorder=1 ! \
  video/x-raw,width="${FULL_WIDTH}",height="${HEIGHT}",framerate="${FPS}"/1 ! \
  queue leaky=downstream max-size-buffers=2 ! \
  videoconvert ! \
  x264enc tune=zerolatency speed-preset=ultrafast bitrate="${BITRATE}" key-int-max="${FPS}" ! \
  video/x-h264,profile=baseline ! \
  rtph264pay config-interval=1 pt=96 ! \
  udpsink host="${OUT_HOST}" port="${OUT_PORT}" sync=false async=false \
  videotestsrc is-live=true pattern=black ! \
    video/x-raw,width="${FULL_WIDTH}",height="${HEIGHT}",framerate="${FPS}"/1 ! \
    queue leaky=downstream max-size-buffers=2 ! mix.sink_0 \
  udpsrc port="${IN1_PORT}" caps="${RTP_CAPS}" buffer-size=524288 do-timestamp=true ! \
    queue leaky=downstream max-size-buffers=2 ! \
    rtpjitterbuffer latency="${JITTER_LATENCY_MS}" drop-on-latency=true ! \
    rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! videoscale ! videorate ! \
    video/x-raw,width="${WIDTH}",height="${HEIGHT}",framerate="${FPS}"/1 ! \
    queue leaky=downstream max-size-buffers=2 ! mix.sink_1 \
  udpsrc port="${IN2_PORT}" caps="${RTP_CAPS}" buffer-size=524288 do-timestamp=true ! \
    queue leaky=downstream max-size-buffers=2 ! \
    rtpjitterbuffer latency="${JITTER_LATENCY_MS}" drop-on-latency=true ! \
    rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! videoscale ! videorate ! \
    video/x-raw,width="${WIDTH}",height="${HEIGHT}",framerate="${FPS}"/1 ! \
    queue leaky=downstream max-size-buffers=2 ! mix.sink_2
