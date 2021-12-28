#!/usr/bin/env python3

# Copyright (c) Facebook, Inc. and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from typing import (
    Dict,
    Optional,
    List,
    Any,
)

from gym.spaces import Box
import numpy as np
from gym import spaces
from habitat.utils import profiling_wrapper
from collections import OrderedDict

import torch  # isort:skip # noqa: F401  must import torch before importing bps_pytorch


class BatchedEnv:
    r"""Todo
    """

    # observation_spaces: List[spaces.Dict]
    # number_of_episodes: List[Optional[int]]
    # action_spaces: List[spaces.Dict]
    _num_envs: int
    _auto_reset_done: bool

    def __init__(
        self,
        config,
        auto_reset_done: bool = True,
    ) -> None:
        """Todo
        """
        self._is_closed = True
        assert config.BATCHED_ENV

        assert (
            config.NUM_ENVIRONMENTS > 0
        ), "number of environments to be created should be greater than 0"

        self._num_envs = config.NUM_ENVIRONMENTS

        self._auto_reset_done = auto_reset_done
        self._config = config

        SIMULATOR_GPU_ID = self._config.SIMULATOR_GPU_ID
        agent_0_name = config.SIMULATOR.AGENTS[0]
        agent_0_config = getattr(config.SIMULATOR, agent_0_name)
        sensor_0_name = agent_0_config.SENSORS[0]
        agent_0_sensor_0_config = getattr(config.SIMULATOR, sensor_0_name)
        sensor_width, sensor_height = agent_0_sensor_0_config.WIDTH, agent_0_sensor_0_config.HEIGHT

        if not config.STUB_BATCH_SIMULATOR:
            from habitat_sim._ext.habitat_sim_bindings import BatchedSimulator, BatchedSimulatorConfig
            bsim_config = BatchedSimulatorConfig()
            bsim_config.gpu_id = SIMULATOR_GPU_ID
            print("bsim_config.gpu_id: ", bsim_config.gpu_id)
            bsim_config.num_envs = self._num_envs
            bsim_config.sensor0.width = sensor_width
            bsim_config.sensor0.height = sensor_height
            bsim_config.sensor0.hfov = 60.0
            bsim_config.force_random_actions = True
            bsim_config.do_async_physics_step = self._config.OVERLAP_PHYSICS
            bsim_config.max_episode_length = 100
            self._bsim = BatchedSimulator(bsim_config)
        else:
            self._bsim = None

        double_buffered = False
        buffer_index = 0
        
        observations = OrderedDict()
        if self._bsim:
            import bps_pytorch  # see https://github.com/shacklettbp/bps-nav#building
            observations["rgb"] = bps_pytorch.make_color_tensor(
                self._bsim.rgba(buffer_index),
                SIMULATOR_GPU_ID,
                self._num_envs // (2 if double_buffered else 1),
                [sensor_height, sensor_width],
            )[..., 0:3].permute(0, 1, 2, 3)  # todo: get rid of no-op permute
        else:
            observations["rgb"] = torch.rand([self._num_envs, sensor_height, sensor_width, 3], dtype=torch.float32) * 255
        self._observations = observations

        # print('observations["rgb"].shape: ', observations["rgb"].shape)

        self._is_closed = False

        num_other_actions = 1  # doAttemptGrip
        num_base_degrees = 2  # rotate and move-forward/back
        num_joint_degrees = 15  # hard-coded to match Fetch
        self.action_dim = num_other_actions + num_base_degrees + num_joint_degrees

        # assert False 
        # todo: figure out why these are needed

        RGBSENSOR_DIMENSION = 3

        rgb_obs = spaces.Box(
            low=0,
            high=255,
            shape=(
                agent_0_sensor_0_config.HEIGHT,
                agent_0_sensor_0_config.WIDTH,
                RGBSENSOR_DIMENSION,
            ),
            dtype=np.uint8,
        )
        obs_dict = spaces.Dict({"rgb": rgb_obs})

        self.observation_spaces = [obs_dict] * 1  # config.NUM_ENVIRONMENTS  # note we only ever read element #0 of this array

        action_space = Box(low=-1.0, high=1.0, shape=(self.action_dim,), dtype=np.float32)

        self.action_spaces = [action_space] * 1  # note we only ever read element #0 of this array
        # self.number_of_episodes = []
        self._paused: List[int] = []

    @property
    def num_envs(self):
        r"""number of individual environments."""
        return self._num_envs - len(self._paused)

    def current_episodes(self):
        # todo: get current episode name from envs
        assert False
        results = []
        return results

    def count_episodes(self):
        assert False
        results = []
        return results

    def episode_over(self):
        assert False
        results = []
        return results

    def get_metrics(self):
        assert False
        results = []
        return results

    def reset(self):
        r"""Reset all the vectorized environments

        :return: list of outputs from the reset method of envs.
        """
        if self._bsim:
            # sloppy: need to do explicit reset here
            if self._config.OVERLAP_PHYSICS:
                self._bsim.auto_reset_or_start_async_step_physics()
            else: 
                self._bsim.auto_reset_or_step_physics()
            self._bsim.start_render()
            self._bsim.wait_for_frame()
        return self._observations
        
    def async_step(
        self, actions
    ) -> None:
        r"""Asynchronously step in the environments.
        """
        scale = self._config.HACK_ACTION_SCALE
        if self._config.HACK_ACTION_SCALE != 1.0:
            actions = torch.mul(actions, scale)

        actions_flat_list = actions.flatten().tolist()
        assert len(actions_flat_list) == self.num_envs * self.action_dim
        if self._bsim:
            if self._config.OVERLAP_PHYSICS:
                self._bsim.wait_async_step_physics()

                self._bsim.set_actions(actions_flat_list)  # note possible wasted (unused) actions
                self._bsim.auto_reset_or_start_async_step_physics()
                self._bsim.start_render()
            else:
                self._bsim.set_actions(actions_flat_list)  # note possible wasted (unused) actions
                self._bsim.auto_reset_or_step_physics()
                self._bsim.start_render()

    @profiling_wrapper.RangeContext("wait_step")
    def wait_step(self) -> List[Any]:
        r"""Todo"""

        if self._bsim:

            # this updates self._observations tensor
            self._bsim.wait_for_frame()

            # hack: these aren't one frame behind like the observations
            rewards = self._bsim.get_rewards()
            assert len(rewards) == self._num_envs
            dones = self._bsim.get_dones()
            assert len(dones) == self._num_envs
            if self._config.REWARD_SCALE != 1.0:
                # perf todo: avoid dynamic list construction
                rewards = [r * self._config.REWARD_SCALE for r in rewards]

        else:
            # rgb_observations = self._observations["rgb"]
            # torch.rand(rgb_observations.shape, dtype=torch.float32, out=rgb_observations)
            # torch.mul(rgb_observations, 255, out=rgb_observations)
            rewards = [0.0] * self._num_envs
            dones = [False] * self._num_envs

        observations = self._observations
        
        # temp stub for infos
        # infos = [{"distance_to_goal": 0.0, "success":0.0, "spl":0.0}] * self._num_envs
        infos = [{}] * self._num_envs
        return (observations, rewards, dones, infos)

    def step(
        self, actions
    ) -> List[Any]:
        r"""Perform actions in the vectorized environments.

        :return: list of outputs from the step method of envs.
        """
        self.async_step(actions)
        return self.wait_step()

    def close(self) -> None:
        if self._is_closed:
            return

        self._bsim.close()
        self._bsim = None

        self._is_closed = True

    def pause_at(self, index: int) -> None:
        r"""Pauses computation on this env without destroying the env.
        """
        self._paused.append(index)

    def resume_all(self) -> None:
        r"""Resumes any paused envs."""
        self._paused = []

    def __del__(self):
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

