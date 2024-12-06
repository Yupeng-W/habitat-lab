

# Habitat Isaac Sim Integration

## Isaac Sim Installation

This has been tested with Ubuntu 22.04 and python 3.10.
```
# install Isaac Sim
pip install isaacsim==4.2.0.2 isaacsim-extscache-physics==4.2.0.2 isaacsim-extscache-kit==4.2.0.2 isaacsim-extscache-kit-sdk==4.2.0.2 --extra-index-url https://pypi.nvidia.com

# verify install and accept EULA
python -c "import isaacsim; print(isaacsim)"

# Isaac Lab is only needed for doing asset conversion to USD format. If you've already been provided Isaac Sim USD files, you can skip this.
clone IsaacLab
cd IsaacLab
./isaaclab.sh --install "none"
```

If you encounter issues, see [official instructions for installing Isaac Sim and Isaac Lab](https://isaac-sim.github.io/IsaacLab/main/source/setup/installation/pip_installation.html#installing-isaac-lab).  

