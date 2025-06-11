#!/bin/bash

apt-get update && apt-get install -y \
    build-essential \
    cmake \
    gfortran \
    libopenblas-dev \
    liblapack-dev \
    libx11-dev \
    libgtk-3-dev \
    libboost-all-dev \
    libatlas-base-dev \
    python3-dev \
    libglib2.0-0 \
    ffmpeg \
    libsm6 \
    libxext6
