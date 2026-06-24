#!/usr/bin/env bash

PORT=$(printf "5600\n5601\n5602\n5603\n" | rofi -dmenu -p "Camera port")
# If you do not have rofi, replace the line above with:
# PORT=$(printf "5600\n5601\n5602\n5603\n" | fzf)

[ -z "$PORT" ] && exit 0

gst-launch-1.0 -v \
  udpsrc port="$PORT" caps="application/x-rtp, media=video, encoding-name=H264, payload=96" \
  ! rtph264depay \
  ! h264parse \
  ! avdec_h264 \
  ! videoconvert \
  ! autovideosink sync=false