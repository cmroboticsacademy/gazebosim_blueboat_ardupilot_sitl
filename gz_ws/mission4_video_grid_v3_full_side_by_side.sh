#!/usr/bin/env bash
set -euo pipefail

# Mission 4 two-BlueBoat camera mixer for QGroundControl.
#
# Purpose:
#   Show both full camera images side by side inside a normal 16:9 video frame.
#   This avoids QGC cropping a very-wide 32:9 stream.
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
#   Aspect Ratio: 1.7777778, or 0.0 to ignore QGC's aspect-ratio scaling
#   Disabled When Disarmed: off
#
# Override ports if needed, for example:
#   IN1_PORT=5700 IN2_PORT=5701 OUT_PORT=5600 ./mission4_video_grid_v3_full_side_by_side.sh
#
# Override layout if needed, for example:
#   CANVAS_WIDTH=1920 CANVAS_HEIGHT=1080 TILE_WIDTH=960 TILE_HEIGHT=540 ./mission4_video_grid_v3_full_side_by_side.sh

IN1_PORT="${IN1_PORT:-5600}"
IN2_PORT="${IN2_PORT:-5601}"
OUT_HOST="${OUT_HOST:-127.0.0.1}"
OUT_PORT="${OUT_PORT:-5602}"

# The BlueBoat model camera is 640x360 by default. Two full frames side by side
# are placed in a 1280x720 16:9 canvas with black letterbox space above and below.
CANVAS_WIDTH="${CANVAS_WIDTH:-1280}"
CANVAS_HEIGHT="${CANVAS_HEIGHT:-720}"
TILE_WIDTH="${TILE_WIDTH:-640}"
TILE_HEIGHT="${TILE_HEIGHT:-360}"
FPS="${FPS:-15}"
BITRATE="${BITRATE:-3000}"
JITTER_LATENCY_MS="${JITTER_LATENCY_MS:-80}"

PAIR_WIDTH=$((TILE_WIDTH * 2))
LEFT_X="${LEFT_X:-$(((CANVAS_WIDTH - PAIR_WIDTH) / 2))}"
TOP_Y="${TOP_Y:-$(((CANVAS_HEIGHT - TILE_HEIGHT) / 2))}"
RIGHT_X=$((LEFT_X + TILE_WIDTH))

RTP_CAPS='application/x-rtp, media=(string)video, clock-rate=(int)90000, encoding-name=(string)H264, payload=(int)96'

cat <<MSG
Mission 4 video grid mixer v3 - full side-by-side cameras
  input 1: udp://127.0.0.1:${IN1_PORT}
  input 2: udp://127.0.0.1:${IN2_PORT}
  output : udp://${OUT_HOST}:${OUT_PORT}

  canvas: ${CANVAS_WIDTH}x${CANVAS_HEIGHT}
  boat 1 tile: ${TILE_WIDTH}x${TILE_HEIGHT} at x=${LEFT_X}, y=${TOP_Y}
  boat 2 tile: ${TILE_WIDTH}x${TILE_HEIGHT} at x=${RIGHT_X}, y=${TOP_Y}

Set QGroundControl video URL/Port to: ${OUT_PORT}
Set QGroundControl video Aspect Ratio to 1.7777778, or 0.0 to ignore aspect scaling.
Do not leave QGC listening on ${IN1_PORT} or ${IN2_PORT}; those are mixer input ports.
MSG

exec gst-launch-1.0 -e \
  compositor name=mix background=black ignore-inactive-pads=true \
    sink_0::xpos=0 sink_0::ypos=0 sink_0::width="${CANVAS_WIDTH}" sink_0::height="${CANVAS_HEIGHT}" sink_0::zorder=0 \
    sink_1::xpos="${LEFT_X}" sink_1::ypos="${TOP_Y}" sink_1::width="${TILE_WIDTH}" sink_1::height="${TILE_HEIGHT}" sink_1::zorder=1 sink_1::sizing-policy=keep-aspect-ratio \
    sink_2::xpos="${RIGHT_X}" sink_2::ypos="${TOP_Y}" sink_2::width="${TILE_WIDTH}" sink_2::height="${TILE_HEIGHT}" sink_2::zorder=1 sink_2::sizing-policy=keep-aspect-ratio ! \
  video/x-raw,width="${CANVAS_WIDTH}",height="${CANVAS_HEIGHT}",framerate="${FPS}"/1 ! \
  queue leaky=downstream max-size-buffers=2 ! \
  videoconvert ! \
  x264enc tune=zerolatency speed-preset=ultrafast bitrate="${BITRATE}" key-int-max="${FPS}" ! \
  video/x-h264,profile=baseline ! \
  rtph264pay config-interval=1 pt=96 ! \
  udpsink host="${OUT_HOST}" port="${OUT_PORT}" sync=false async=false \
  videotestsrc is-live=true pattern=black ! \
    video/x-raw,width="${CANVAS_WIDTH}",height="${CANVAS_HEIGHT}",framerate="${FPS}"/1 ! \
    queue leaky=downstream max-size-buffers=2 ! mix.sink_0 \
  udpsrc port="${IN1_PORT}" caps="${RTP_CAPS}" buffer-size=524288 do-timestamp=true ! \
    queue leaky=downstream max-size-buffers=2 ! \
    rtpjitterbuffer latency="${JITTER_LATENCY_MS}" drop-on-latency=true ! \
    rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! videoscale ! videorate ! \
    video/x-raw,framerate="${FPS}"/1 ! \
    queue leaky=downstream max-size-buffers=2 ! mix.sink_1 \
  udpsrc port="${IN2_PORT}" caps="${RTP_CAPS}" buffer-size=524288 do-timestamp=true ! \
    queue leaky=downstream max-size-buffers=2 ! \
    rtpjitterbuffer latency="${JITTER_LATENCY_MS}" drop-on-latency=true ! \
    rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! videoscale ! videorate ! \
    video/x-raw,framerate="${FPS}"/1 ! \
    queue leaky=downstream max-size-buffers=2 ! mix.sink_2
