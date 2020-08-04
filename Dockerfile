# Base image
FROM nvidia/cuda:10.1-devel-ubuntu18.04

# Setup basic packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        git \
        curl \
        vim \
        ca-certificates \
        cmake \
        libjpeg-dev \
        libpng-dev \
        libglfw3-dev \
        libglm-dev \
        libsm6 \
        libx11-dev \
        libomp-dev \
        libegl1-mesa-dev \
        pkg-config \
        wget \
        zip \
        unzip \
    && rm -rf /var/lib/apt/lists/*

# Install conda
RUN curl -o ~/miniconda.sh \
        -O  https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh  && \
    chmod +x ~/miniconda.sh && \
    ~/miniconda.sh -b -p /opt/conda && \
    rm ~/miniconda.sh
ENV PATH /opt/conda/bin:$PATH
RUN conda install \
        numpy \
        pyyaml \
        scipy \
        ipython \
        mkl \
        mkl-include \
    && conda clean -ya

# Conda environment
RUN conda create -n habitat

# Setup habitat-sim
RUN git clone --branch stable https://github.com/facebookresearch/habitat-sim.git
RUN /bin/bash -c ". activate habitat; cd habitat-sim; pip install -r requirements.txt; python setup.py install --headless"

# Install challenge specific habitat-api
RUN git clone --branch stable https://github.com/facebookresearch/habitat-api.git
RUN /bin/bash -c ". activate habitat; cd habitat-api; pip install -e ."

# Silence habitat-sim logs
ENV GLOG_minloglevel=2
ENV MAGNUM_LOG="quiet"
