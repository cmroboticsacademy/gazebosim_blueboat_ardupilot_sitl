FROM osrf/ros:humble-desktop AS base

ARG USERNAME=blueboat_sitl
ARG USER_UID=1000
ARG USER_GID=$USER_UID
ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get upgrade -y

# Install a few handy tools
RUN apt-get update \
  && apt-get -y --quiet --no-install-recommends install \
    bash-completion \
    build-essential \
    git \
    glmark2 \
    gnupg \
    iputils-ping \
    lsb-release \
    mlocate \
    software-properties-common \
    sudo \
    wget \
    vim \
  && rm -rf /var/lib/apt/lists/*

# Install NVIDIA software
RUN apt-get update \
 && apt-get -y --quiet --no-install-recommends install \
    libglvnd0 \
    libgl1 \
    libglx0 \
    libegl1 \
    libxext6 \
    libx11-6 \
  && rm -rf /var/lib/apt/lists/*
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=graphics,utility,compute
ENV QT_X11_NO_MITSHM=1

# Install some ardupilot and ardupilot_gazebo prereqs
RUN apt-get update \
 && apt-get -y --quiet --no-install-recommends install \
    python3-wxgtk4.0 \
    rapidjson-dev \
    xterm \
  && rm -rf /var/lib/apt/lists/*

# Install Gazebo Garden and other required packages
RUN wget https://packages.osrfoundation.org/gazebo.gpg -O /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg \
  && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable $(lsb_release -cs) main" | tee /etc/apt/sources.list.d/gazebo-stable.list > /dev/null \
  && apt-get update \
  && apt-get -y --quiet --no-install-recommends install \
    libgz-sim7-dev \
    libopencv-dev \
    libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-libav \
    gstreamer1.0-gl \
    gz-garden \
  && rm -rf /var/lib/apt/lists/*

# Set up rosdep for Gazebo Garden
RUN sudo bash -c 'wget https://raw.githubusercontent.com/osrf/osrf-rosdep/master/gz/00-gazebo.list -O /etc/ros/rosdep/sources.list.d/00-gazebo.list' \
  && rosdep update

# Create a non-root user
RUN groupadd --gid $USER_GID $USERNAME \
  && useradd -s /bin/bash --uid $USER_UID --gid $USER_GID -m $USERNAME \
  && echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME \
  && chmod 0440 /etc/sudoers.d/$USERNAME \
  && echo "\n# Added by blueboat_sitl Dockerfile:" >> /home/$USERNAME/.bashrc \
  && echo "source /usr/share/bash-completion/completions/git" >> /home/$USERNAME/.bashrc

# Switch to our new user
USER $USERNAME
ENV USER=$USERNAME
ENV GZ_VERSION=garden

# Clone ArduSub code
# Clone ArduSub code
WORKDIR /home/$USERNAME
RUN git clone --branch ArduSub-4.5.3 https://github.com/ArduPilot/ardupilot.git --recurse-submodules
WORKDIR /home/$USERNAME/ardupilot
#RUN git checkout aca9940534


# Install ArduSub prereqs (this also appends to .bashrc)
WORKDIR /home/$USERNAME/ardupilot
ENV SKIP_AP_EXT_ENV=1 SKIP_AP_GRAPHIC_ENV=1 SKIP_AP_COV_ENV=1 SKIP_AP_GIT_CHECK=1
RUN Tools/environment_install/install-prereqs-ubuntu.sh -y

# Build ArduSub
WORKDIR /home/$USERNAME/ardupilot
RUN modules/waf/waf-light configure --board sitl \
  && modules/waf/waf-light build --target bin/ardusub

# Clone ardupilot_gazebo code
WORKDIR /home/$USERNAME
RUN git clone https://github.com/ArduPilot/ardupilot_gazebo.git

# Build ardupilot_gazebo
RUN [ "/bin/bash" , "-c" , " \
  cd ardupilot_gazebo \
  && mkdir build \
  && cd build \
  && cmake .. -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  && make -j4" ]

# Create colcon workspace and copy workspace.repos file
WORKDIR /home/$USERNAME
RUN mkdir -p colcon_ws/src/blueboat_sitl
COPY --chown=$USER_UID:$USER_GID blueboat_sitl.repos colcon_ws/src/blueboat_sitl

# Get workspace repos
WORKDIR /home/$USERNAME/colcon_ws/src
RUN vcs import < blueboat_sitl/blueboat_sitl.repos

# Run rosdep update before installing dependencies
RUN rosdep update

# Downgrade setuptools to a compatible version
RUN python3 -m pip install --upgrade pip setuptools==59.6.0

# Run rosdep over workspace repos
RUN rosdep install -y --from-paths . --ignore-src --skip-keys="gz-transport12 gz-sim7 gz-math7 gz-msgs9"

# Build everything so far
WORKDIR /home/$USERNAME/colcon_ws
RUN [ "/bin/bash" , "-c" , "\
  source /opt/ros/humble/setup.bash \
  && colcon build" ]

# Run rosdep over blueboat package.xml files
RUN rosdep update \
  && rosdep install -y --from-paths . --ignore-src --skip-keys="gz-transport12 gz-sim7 gz-math7 gz-msgs9"

# MAVROS depends on GeographicLib, and GeographicLib needs some datasets
RUN [ "/bin/bash" , "-c" , "\
  wget https://raw.githubusercontent.com/mavlink/mavros/master/mavros/scripts/install_geographiclib_datasets.sh \
  && chmod +x install_geographiclib_datasets.sh \
  && sudo ./install_geographiclib_datasets.sh" ]

# Copy everything
COPY --chown=$USER_UID:$USER_GID . src/blueboat_sitl

# Build everything
RUN [ "/bin/bash" , "-c" , "\
  source /opt/ros/humble/setup.bash \
  && colcon build" ]

# Set up the environment
WORKDIR /home/$USERNAME/colcon_ws
ENV GZ_VERSION=garden
ENV GZ_SIM_SYSTEM_PLUGIN_PATH=/home/blueboat_sitl/ardupilot_gazebo/build
ENV GST_PLUGIN_PATH=/usr/lib/x86_64-linux-gnu/gstreamer-1.0
RUN echo "export PATH=/home/$USERNAME/.local/bin:\$PATH" >> /home/$USERNAME/.bashrc \
 && echo "export PYTHONPATH=/home/$USERNAME/.local/lib/python3.10/site-packages:\$PYTHONPATH" >> /home/$USERNAME/.bashrc \
 && echo "source /home/$USERNAME/colcon_ws/src/blueboat_sitl/setup.bash" >> /home/$USERNAME/.bashrc \
 && echo '[ -f /home/'"$USERNAME"'/gz_ws/install/setup.bash ] && source /home/'"$USERNAME"'/gz_ws/install/setup.bash' >> /home/$USERNAME/.bashrc \
 && echo '[ -f /home/'"$USERNAME"'/gz_ws/gazebo_exports.sh ] && source /home/'"$USERNAME"'/gz_ws/gazebo_exports.sh' >> /home/$USERNAME/.bashrc 

RUN echo 'export GZ_VERSION=garden' >> /home/$USERNAME/.bashrc \
&& echo 'export GZ_SIM_SYSTEM_PLUGIN_PATH=/home/'"$USERNAME"'/ardupilot_gazebo/build:$GZ_SIM_SYSTEM_PLUGIN_PATH' >> /home/$USERNAME/.bashrc \
&& echo 'export GST_PLUGIN_PATH=/usr/lib/x86_64-linux-gnu/gstreamer-1.0:$GST_PLUGIN_PATH' >> /home/$USERNAME/.bashrc

USER root
RUN apt-get update && apt-get install -y nano
RUN apt-get -y --quiet --no-install-recommends install \
 libcgal-dev \
 libfftw3-dev

RUN python3 -m pip install opencv-python

RUN apt-get update && apt-get install -y \
    ros-humble-joy \
    && rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y \
    ros-humble-joy-linux \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install transforms3d pymavlink transformations geopy

ENV DIST=humble
RUN apt update \
 && apt install -y --no-install-recommends \
    ros-${DIST}-plotjuggler-ros \
 && apt clean

RUN apt-get update && apt-get install -y \
    qml-module-qtpositioning \
    qml-module-qtlocation

RUN apt-get install -y \
    python3-tk    

RUN python3 -m pip install gekko  

RUN apt update && apt install -y \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav 
    
USER $USERNAME

USER root

RUN apt-get update && apt-get install -y ros-humble-joint-state-publisher

USER $USERNAME
