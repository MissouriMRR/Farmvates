FROM --platform=linux/arm64 debian:bookworm

ENV DEBIAN_FRONTEND=noninteractive

# Install build tools and dependencies
RUN apt update && apt install -y \
    cmake \
    build-essential \
    git \
    wget \
    pkg-config \
    libgtk-3-dev \
    libavcodec-dev \
    libavformat-dev \
    libavutil-dev \
    libswscale-dev \
    libavdevice-dev \
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    libv4l-dev \
    libxvidcore-dev \
    libx264-dev \
    libatlas-base-dev \
    gfortran


# Install MAVSDK
RUN wget https://github.com/mavlink/MAVSDK/releases/download/v3.15.0/libmavsdk-dev_3.15.0_debian12_arm64.deb && \
    dpkg -i libmavsdk-dev_3.15.0_debian12_arm64.deb && \
    rm libmavsdk-dev_3.15.0_debian12_arm64.deb
# Build OpenCV 4.11.0 from source
RUN git clone https://github.com/opencv/opencv.git && \
    cd opencv && \
    git checkout 4.11.0 && \
    mkdir build && cd build && \
    cmake .. -DCMAKE_BUILD_TYPE=Release \
             -DCMAKE_INSTALL_PREFIX=/usr/local \
             -DBUILD_TESTS=OFF \
             -DBUILD_PERF_TESTS=OFF \
             -DBUILD_EXAMPLES=OFF && \
    make -j4 && \
    make install && \
    ldconfig && \
    cd / && rm -rf opencv

WORKDIR /project