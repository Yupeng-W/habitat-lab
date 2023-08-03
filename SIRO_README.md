# SIRo Project 

Project-specific README for SIRo.

# Installation

1. Clone the Habitat-lab [SIRo branch](https://github.com/facebookresearch/habitat-lab/tree/SIRo).
1. Install Habitat-lab using [instructions](https://github.com/facebookresearch/habitat-lab/tree/SIRo#installation).
1. Install Habitat-sim `main` branch.
    * [Build from source](https://github.com/facebookresearch/habitat-sim/blob/main/BUILD_FROM_SOURCE.md), or install the [conda nightly build](https://github.com/facebookresearch/habitat-sim#recommended-conda-packages).
        * Be sure to include Bullet physics, e.g. `python setup.py install --bullet`.
    * Anecdotally, building from source is working more reliably (versus the conda nightly build).
    * If you build from source, configure `PYTHONPATH` and ensure that Python `import habitat_sim` imports your locally-built version of Habitat-sim.
    * Keep an eye on relevant [commits to main](https://github.com/facebookresearch/habitat-sim/commits/main) to help you decide when to update/rebuild Habitat-sim.
    * If you encounter the issue about cmake when building from source using Mac `missing xcrun at: /Library/Developer/CommandLineTools/usr/bin/xcrun`, you can solve this by first install the tools `xcode-select --install`.
1. Download humanoid data.
    * Manually download `humanoids_skinned.zip` from [this link](https://drive.google.com/file/d/19gUvwaxJpd-Z6Djq8kmCpYotduwZvOfZ/view?usp=sharing) and uncompress to `data`
1. Download other required datasets:
    * `python -m habitat_sim.utils.datasets_download --uids ycb hab_fetch hab_spot_arm replica_cad_dataset rearrange_pick_dataset_v0 rearrange_dataset_v1 --data-path data/`
1. Optional: install the HSSD Dataset below.

# HSSD Dataset

HSSD is actually four distinct pieces: (1) HSSD scenes, (2) Amazon-Berkeley objects, (3) Google Scanned objects, and (4) HSSD compatible episodes. (YCB objects should have been already downloaded as part of the earlier SIRo install steps)

(2) and (3) are not used in current episodes and do not need to be downloaded.

1. Download HSSD Scenes:
```
# 1. Go to the habitat data directory
cd habitat-lab/data
# 2. Install Git LFS from https://git-lfs.com/ (if not installed yet)
# 3. Set up Git LFS for your user account (if not set up yet)
git lfs install
# 4. Clone HSSD dataset (it will take a while to finish)
git clone https://huggingface.co/datasets/fpss/fphab
# 5. Checkout the 'f141a8192de29e4d92fe61577c62e0058fc7a9c3' commit. Other versions do not work with SIRo.
git checkout f141a8192de29e4d92fe61577c62e0058fc7a9c3
# 6. Create a link to HSSD in the data folder
ln -s /path/to/fphab data/fpss
# 7. Sanity check for one of the scenes (this should open HSSD scene in the habitat viewer)
# ./build/viewer if compiling locally
habitat-viewer --enable-physics --dataset /path/to/data/fpss/hssd-hab-uncluttered.scene_dataset_config.json -- 108294897_176710602
```
2. (skip) Download [Amazon and Google object archives](https://drive.google.com/drive/folders/1x6i3sDYheCWoi59lv27ZyPG4Ii2GhEZB)
3. (skip) Extract these two object datasets into `habitat-lab/data` as follows:
```
cd objects
tar -xvf ~/Downloads/google_object_dataset.tar.gz
tar -xvf ~/Downloads/amazon_berkeley.tar.gz
```
4. Download HSSD episodes:
```
# Go to the habitat datasets directory
cd habitat-lab/data/datasets
# Clone dataset
git clone https://github.com/jimmytyyang/floorplanner.git
```
5. Now you should be able to use HSSD. For more detail (e.g., stats, train-test split), please read [here](https://docs.google.com/document/d/11m66SUawGPFxWYHN2E8rDw3g679dpiBf8Es-o3PRl5I/edit?usp=sharing).

# Sandbox Tool

see [Sandbox Tool Readme](./examples/siro_sandbox/README.md)

# Training

## Multi-Agent

### Fetch-Fetch
Fetch-Fetch in ReplicaCAD multi-agent training, single GPU. From `habitat-lab` directory:
```bash
HABITAT_SIM_LOG=warning:physics,metadata=quiet MAGNUM_LOG=warning \
python habitat-baselines/habitat_baselines/run.py -m hydra/output=path \
--config-name experiments_hab3/pop_play_kinematic_oracle.yaml
```
This will create a directory `outputs/pop-play/<date>/<time>/0` and store data like checkpoints and logs into that folder. If you would like to edit the path where your run data is stored, you can edit `config/hydra/output/path.yaml` to take other paths.

### Fetch-Humanoid
To run a Fetch-Humanoid Policy on ReplicaCAD, single GPU, you will need to run:
```bash
HABITAT_SIM_LOG=warning:physics,metadata=quiet MAGNUM_LOG=warning \
python habitat-baselines/habitat_baselines/run.py -m hydra/output=path \
--config-name experiments_hab3/pop_play_kinematic_oracle_humanoid.yaml
```
Note that the default value for population here is [1,1], meaning that we will be training a single policy for each agent. The argument `rl.agent.num_pool_agents_per_type` can be changed to [1,8] for population based training, where the humanoid is samples from 8 policies.

### Spot-Humanoid
To train a Spot-Humanoid Policy on FP, single GPU, you will need to run:
```bash
HABITAT_SIM_LOG=warning:physics,metadata=quiet MAGNUM_LOG=warning \
python habitat-baselines/habitat_baselines/run.py -m hydra/output=path habitat_baselines.rl.agent.num_pool_agents_per_type=[1,1] habitat_baselines.num_environments=1 habitat.task.measurements.cooperate_subgoal_reward.end_on_collide=False \
--config-name experiments_hab3/pop_play_kinematic_oracle_humanoid_spot_fp.yaml
```

# Eval

To run evaluation, run, from `habitat-lab` directory:

```
sh eval_sweep.sh
```

You will be prompted to enter a directory `$SWEEP_SUBDIR` name where the checkpoints and config files are saved (normally in the format `name/yyyy-dd-mm/hh-mm-ss`). The script will generate videos of evaluation at `$SWEEP_SUBDIR/0/video`.

## Demo Fetch-Human Fixed Planner

You can also run a Fetch-Humanoid where both work with a Fixed Planner, using:

```
python  habitat-baselines/habitat_baselines/run.py -m  habitat_baselines.evaluate=True habitat_baselines.num_environments=1 habitat_baselines.eval.should_load_ckpt=False  --config-name experiments_hab3/rearrange_fetch_human_planner.yaml
```

To run evaluation on population-based training checkpoints:
1. GTCoord training
```
python habitat-baselines/habitat_baselines/run.py -m --config-name experiments_hab3/pop_play_kinematic_oracle_humanoid_spot_fp.yaml habitat_baselines.num_environments=1  habitat_baselines.eval_ckpt_path_dir='checkpoints/GTCoord_latest.pth' habitat_baselines.evaluate=True habitat_baselines.eval.should_load_ckpt=True habitat_baselines.rl.agent.num_pool_agents_per_type=[1,1] habitat.task.measurements.cooperate_subgoal_reward.end_on_collide=False habitat.task.actions.agent_0_oracle_nav_with_backing_up_action.longitudinal_lin_speed=10.0 habitat.task.actions.agent_1_oracle_nav_with_backing_up_action.lin_speed=10.0
```

2. PBT training
```
python habitat-baselines/habitat_baselines/run.py -m --config-name experiments_hab3/pop_play_kinematic_oracle_humanoid_spot_fp.yaml habitat_baselines.num_environments=1  habitat_baselines.eval_ckpt_path_dir='checkpoints/PBT8_latest.pth' habitat_baselines.evaluate=True habitat_baselines.eval.should_load_ckpt=True habitat_baselines.rl.agent.num_pool_agents_per_type=[1,8] habitat.task.measurements.cooperate_subgoal_reward.end_on_collide=False habitat.task.actions.agent_0_oracle_nav_with_backing_up_action.longitudinal_lin_speed=10.0
habitat.task.actions.agent_1_oracle_nav_with_backing_up_action.lin_speed=10.0 
```

3. BDP training
```
python habitat-baselines/habitat_baselines/run.py -m --config-name experiments_hab3/bdp_kinematic_oracle_humanoid_spot.yaml habitat_baselines.num_environments=1  habitat_baselines.eval_ckpt_path_dir='checkpoints/BDP16_latest.pth' habitat_baselines.evaluate=True habitat_baselines.eval.should_load_ckpt=True habitat_baselines.rl.agent.num_pool_agents_per_type=[1,1] habitat.task.measurements.cooperate_subgoal_reward.end_on_collide=False habitat.task.actions.agent_0_oracle_nav_with_backing_up_action.longitudinal_lin_speed=10.0
habitat.task.actions.agent_1_oracle_nav_with_backing_up_action.lin_speed=10.0
```

The coordination agent (checkpoint for Spot) in all of the above cases is the 0th index in the `state_dict` in the checkpoint. 

Note: Right now, PBT training is resulting in the coordination agent staying stationary, while the partners do the full task. This is known behavior, and a function of the RL training. We will fix this with hyperparameter tuning. For now, you can either evaluate with the coordination agent that stays stationary, or use one of the population agents (indexes 1-8 in `state_dict`) for testing now.

For evaluating against the training population, for PBT training set `habitat_baselines.rl.agent.force_partner_sample_idx` to be a partner index. In BDP, make number of environments same as number of latent dimensions: `habitat_baselines.num_environments=16 habitat_baselines.rl.agent.force_all_agents=True`.

# Spot robot

## Testing the Spot

To run Spot in FP (`pop_play_kinematic_oracle_spot_fp.yaml`), please follows the following instruction

1. Download HSSD Dataset (see above).
1. From `habitat-lab` directory:
```bash
srun -v --gpus-per-node=1 --partition=siro --time=1:00:00 --cpus-per-task 1 \
python -u habitat-baselines/habitat_baselines/run.py \
-m --config-name=experiments_hab3/pop_play_kinematic_oracle_spot_fp.yaml \
habitat_baselines.num_environments=1
```

or for running HRL fix policy:
```bash
python habitat-baselines/habitat_baselines/run.py \
-m --config-name=rearrange/rl_hierarchical_oracle_nav_spot_fp.yaml \
habitat_baselines.evaluate=True \
habitat.simulator.kinematic_mode=True \
habitat.simulator.step_physics=False \
habitat.task.measurements.force_terminate.max_accum_force=-1.0 \
habitat.task.measurements.force_terminate.max_instant_force=-1.0 \
habitat_baselines.num_environments=1 \
habitat_baselines/rl/policy/hierarchical_policy/defined_skills@habitat_baselines.rl.policy.main_agent.hierarchical_policy.defined_skills=oracle_skills
```

or for running HRL human-robot fix policy (multi-agent setting)
```bash
python habitat-baselines/habitat_baselines/run.py \
-m --config-name=experiments_hab3/pop_play_kinematic_oracle_humanoid_spot_fp.yaml \
habitat_baselines.evaluate=True \
habitat.simulator.kinematic_mode=True \
habitat.simulator.step_physics=False \
habitat_baselines.num_environments=1
```

TODO
1. Generate more scenes
2. Fix Spot robot navmesh issue
