#!/bin/bash

# Copyright (c) Meta Platforms, Inc. and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

# NOTE: run this script from habitat-lab/ directory
# TO PLOT RESULTS SEE RUN `python scripts/hab2_bench/plot_bench.py`
mkdir -p data/profile
NUM_STEPS=300
set -e

export OMP_NUM_THREADS=2
export MAGNUM_LOG=quiet
export HABITAT_SIM_LOG=quiet

USE_ORACLE_ACTION=
#NOTE: this creates a new URDF with no accompanying ao_config to avoid skinning
cp data/humanoids/humanoid_data/female2_0.urdf data/humanoids/humanoid_data/female2_0_no_skinning.urdf
NO_SKINNING="habitat.simulator.agents.agent_1.articulated_agent_urdf='data/humanoids/humanoid_data/female2_0_no_skinning.urdf'"

TASK_SPEC="habitat.task.task_spec=rearrange_easy_fp"
PDDL_DOMAIN_DEF="habitat.task.pddl_domain_def=fp"

REMOVE_ORACLE="~habitat.task.actions.oracle_nav_action"
REMOVE_PICK="~habitat.task.actions.humanoid_pick_action"

#different datasets for different combinations of clutter objects (2,5,10) and scene complexity (small, medium, large)
OBJ2_SMALL="habitat.dataset.data_path=data/hab3_bench_assets/episode_datasets/small_small.json.gz"
OBJ2_MED="habitat.dataset.data_path=data/hab3_bench_assets/episode_datasets/medium_small.json.gz"
OBJ2_LRG="habitat.dataset.data_path=data/hab3_bench_assets/episode_datasets/large_small.json.gz"
OBJ5_SMALL="habitat.dataset.data_path=data/hab3_bench_assets/episode_datasets/small_medium.json.gz"
OBJ5_MED="habitat.dataset.data_path=data/hab3_bench_assets/episode_datasets/medium_medium.json.gz"
OBJ5_LRG="habitat.dataset.data_path=data/hab3_bench_assets/episode_datasets/large_medium.json.gz"
OBJ10_SMALL="habitat.dataset.data_path=data/hab3_bench_assets/episode_datasets/small_large.json.gz"
OBJ10_MED="habitat.dataset.data_path=data/hab3_bench_assets/episode_datasets/medium_large.json.gz"
OBJ10_LRG="habitat.dataset.data_path=data/hab3_bench_assets/episode_datasets/large_large.json.gz"
#default for all trials withou a specific override
DATA_DEFAULT=$OBJ2_SMALL

postfixes=("2obj_small_scn_" "2obj_medium_scn_" "2obj_large_scn_" "5obj_small_scn_" "5obj_medium_scn_" "5obj_large_scn_" "10obj_small_scn_" "10obj_medium_scn_" "10obj_large_scn_")
ep_overrides=("$OBJ2_SMALL" "$OBJ2_MED" "$OBJ2_LRG" "$OBJ5_SMALL" "$OBJ5_MED" "$OBJ5_LRG" "$OBJ10_SMALL" "$OBJ10_MED" "$OBJ10_LRG")

# number of processes
# shellcheck disable=SC2043
for j in 1 16
do
  #number of trials
  for i in {1..10}
  do

    #NOTE: add '--render' for debug output

    #TODO: different configs for different agent pairs. Can we make a single high-level config
    # Humanoid pick
    python scripts/hab3_bench/hab3_benchmark.py --cfg benchmark/rearrange/hab3_bench/humanoid_oracle.yaml --n-steps "$NUM_STEPS" --n-procs "$j" --out-name "human_pick_$i" "$TASK_SPEC" "$PDDL_DOMAIN_DEF" "$DATA_DEFAULT" "$REMOVE_ORACLE"

    # Humanoid oracle
    python scripts/hab3_bench/hab3_benchmark.py --cfg benchmark/rearrange/hab3_bench/humanoid_oracle.yaml --n-steps "$NUM_STEPS" --n-procs "$j" --out-name "human_oracle_$i" "$TASK_SPEC" "$PDDL_DOMAIN_DEF" "$DATA_DEFAULT" "$REMOVE_PICK"

    #Single agent robot
    python scripts/hab3_bench/hab3_benchmark.py --cfg benchmark/rearrange/hab3_bench/spot_oracle.yaml --n-steps "$NUM_STEPS" --n-procs "$j" --out-name "robot_oracle_$i" "$TASK_SPEC" "$PDDL_DOMAIN_DEF" "$DATA_DEFAULT"

    #Single agent robot - multiple object and scene complexities
    for ix in "${!postfixes[@]}"; do
      python scripts/hab3_bench/hab3_benchmark.py --cfg benchmark/rearrange/hab3_bench/spot_oracle.yaml --n-steps "$NUM_STEPS" --n-procs "$j" --out-name "robot_oracle_${postfixes[$ix]}$i" "$TASK_SPEC" "$PDDL_DOMAIN_DEF" "${ep_overrides[$ix]}"
    done

    # Humanoid oracle
    python scripts/hab3_bench/hab3_benchmark.py --cfg benchmark/rearrange/hab3_bench/humanoid_oracle.yaml --n-steps "$NUM_STEPS" --n-procs "$j" --out-name "human_oracle_$i" "$TASK_SPEC" "$PDDL_DOMAIN_DEF" "$DATA_DEFAULT"


    #multi-agent robots
    python scripts/hab3_bench/hab3_benchmark.py --cfg benchmark/rearrange/hab3_bench/spot_spot_vel.yaml --n-steps "$NUM_STEPS" --n-procs "$j" --out-name "robots_vel_$i" "$TASK_SPEC" "$PDDL_DOMAIN_DEF" "$DATA_DEFAULT"

    #multi-agent robot, human (no skinning)
    #python scripts/hab3_bench/hab3_benchmark.py --cfg benchmark/rearrange/hab3_bench/spot_humanoid_vel.yaml --n-steps "$NUM_STEPS" --n-procs "$j" --out-name "robot_human_vel_noskin_$i" "$NO_SKINNING"

    #multi-agent robot, human (+skinning)
    # python scripts/hab3_bench/hab3_benchmark.py --cfg benchmark/rearrange/hab3_bench/spot_humanoid_vel.yaml --n-steps 1 --n-procs "$j" --out-name test --render
    python scripts/hab3_bench/hab3_benchmark.py --cfg benchmark/rearrange/hab3_bench/spot_humanoid_vel.yaml --n-steps "$NUM_STEPS" --n-procs "$j" --out-name "robot_human_vel_$i" "$TASK_SPEC" "$PDDL_DOMAIN_DEF" "$DATA_DEFAULT"

    #multi-agent robot, human (+skinning) + path actions
    python scripts/hab3_bench/hab3_benchmark.py --cfg benchmark/rearrange/hab3_bench/spot_humanoid_oracle.yaml --n-steps "$NUM_STEPS" --n-procs "$j" --out-name "robot_human_oracle_$i" "$TASK_SPEC" "$PDDL_DOMAIN_DEF" "$DATA_DEFAULT"

    #stretch features:
    #HSSD vs ReplicaCAD
    #pick/place vs nav (requires calling skills)
    #joints vs base control
    #robot continuous control modes (backup vs no backup)

  done
done
