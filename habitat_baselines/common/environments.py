#!/usr/bin/env python3

# Copyright (c) Facebook, Inc. and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
r"""
This file hosts task-specific or trainer-specific environments for trainers.
All environments here should be a (direct or indirect ) subclass of Env class
in habitat. Customized environments should be registered using
``@baseline_registry.register_env(name="myEnv")` for reusability
"""

from typing import Optional, Type

import habitat
from habitat import Config, Dataset
from habitat_baselines.common.baseline_registry import baseline_registry


def get_env_class(env_name: str) -> Type[habitat.RLEnv]:
    r"""Return environment class based on name.

    Args:
        env_name: name of the environment.

    Returns:
        Type[habitat.RLEnv]: env class.
    """
    return baseline_registry.get_env(env_name)


@baseline_registry.register_env(name="NavRLEnv")
class NavRLEnv(habitat.RLEnv):
    def __init__(self, config: Config, dataset: Optional[Dataset] = None):
        self._rl_config = config.habitat_baselines.rl
        self._config = config
        self._reward_measure_name = self._rl_config.reward_measure
        self._success_measure_name = self._rl_config.success_measure

        self._previous_measure = None
        self._previous_action = None
        super().__init__(self._config, dataset)

    def reset(self):
        self._previous_action = None
        observations = super().reset()
        self._previous_measure = self._env.get_metrics()[
            self._reward_measure_name
        ]
        return observations

    def step(self, *args, **kwargs):
        self._previous_action = kwargs["action"]
        return super().step(*args, **kwargs)

    def get_reward_range(self):
        return (
            self._rl_config.slack_reward - 1.0,
            self._rl_config.success_reward + 1.0,
        )

    def get_reward(self, observations):
        reward = self._rl_config.slack_reward

        current_measure = self._env.get_metrics()[self._reward_measure_name]

        reward += self._previous_measure - current_measure
        self._previous_measure = current_measure

        if self._episode_success():
            reward += self._rl_config.success_reward

        return reward

    def _episode_success(self):
        return self._env.get_metrics()[self._success_measure_name]

    def get_done(self, observations):
        done = False
        if self._env.episode_over or self._episode_success():
            done = True
        return done

    def get_info(self, observations):
        return self.habitat_env.get_metrics()
