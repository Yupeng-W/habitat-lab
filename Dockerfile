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
        ipython \
        mkl \
        mkl-include \
        numpy \
        pyyaml \
        scipy \
    && conda clean -ya

# Conda environment
RUN conda create -n habitat
WORKDIR /opt
SHELL ["/bin/bash", "-c"]

# Setup habitat-sim
RUN git clone --branch stable https://github.com/facebookresearch/habitat-sim.git
ARG SIM_INSTALL_OPTION="--headless"
RUN source activate habitat && \
    cd habitat-sim && \
    pip install -r requirements.txt && \
    pip install -e . --install-option="$SIM_INSTALL_OPTION"

# Install challenge specific habitat-api
RUN git clone --branch stable https://github.com/facebookresearch/habitat-api.git
RUN source activate habitat && \
    cd habitat-api && \
    pip install -r requirements.txt && \
    pip install -e .

# Silence habitat-sim logs
ENV GLOG_minloglevel=2
ENV MAGNUM_LOG="quiet"

# setup entrypoint
COPY ./entrypoint.sh /
ENTRYPOINT ["/entrypoint.sh"]
SHELL ["/bin/sh", "-c"]
CMD ["bash"]

# WORKDIR /opt/habitat-api
# RUN wget http://dl.fbaipublicfiles.com/habitat/habitat-test-scenes.zip && \
#     unzip habitat-test-scenes.zip
