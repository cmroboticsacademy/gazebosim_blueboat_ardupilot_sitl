sim_vehicle.py -v Rover -f gazebo-rover --model JSON \
  --add-param-file=../gz_ws/cmra_boat.params \
  --add-param-file=../gz_ws/cmra_boat1_sysid.params \
  -w -I0 --no-extra-ports \
  -l 40.595009,-79.99974,0,0 \
  --out=udp:127.0.0.1:14550

  sim_vehicle.py -v Rover -f gazebo-rover --model JSON \
  --add-param-file=../gz_ws/cmra_boat.params \
  --add-param-file=../gz_ws/cmra_boat2_sysid.params \
  -w -I1 --no-extra-ports \
  -l 40.595009,-79.99974,0,0 \
  --out=udp:127.0.0.1:14550