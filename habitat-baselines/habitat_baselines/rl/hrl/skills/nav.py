# Copyright (c) Meta Platforms, Inc. and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from dataclasses import dataclass

import gym.spaces as spaces
import torch

from habitat.tasks.rearrange.rearrange_sensors import (
    TargetGoalGpsCompassSensor,
    TargetStartGpsCompassSensor,
)
from habitat.tasks.rearrange.sub_tasks.nav_to_obj_sensors import (
    NavGoalPointGoalSensor,
)
from habitat_baselines.common.tensor_dict import TensorDict
from habitat_baselines.rl.hrl.skills.nn_skill import NnSkillPolicy


class NavSkillPolicy(NnSkillPolicy):
    @dataclass(frozen=True)
    class NavArgs:
        obj_idx: int
        is_target: bool

    def __init__(
        self,
        wrap_policy,
        config,
        action_space: spaces.Space,
        filtered_obs_space: spaces.Space,
        filtered_action_space: spaces.Space,
        batch_size,
    ):
        super().__init__(
            wrap_policy,
            config,
            action_space,
            filtered_obs_space,
            filtered_action_space,
            batch_size,
            should_keep_hold_state=True,
        )

    def _get_filtered_obs(self, observations, cur_batch_idx) -> TensorDict:
        ret_obs = super()._get_filtered_obs(observations, cur_batch_idx)
        if NavGoalPointGoalSensor.cls_uuid in ret_obs:
            for i, batch_i in enumerate(cur_batch_idx):
                if self._cur_skill_args[batch_i].is_target:
                    replace_sensor = TargetGoalGpsCompassSensor.cls_uuid
                else:
                    replace_sensor = TargetStartGpsCompassSensor.cls_uuid
                ret_obs[NavGoalPointGoalSensor.cls_uuid][i] = observations[
                    replace_sensor
                ][i][0:2]
        return ret_obs

    def _get_multi_sensor_index(self, batch_idx):
        return [self._cur_skill_args[i].obj_idx for i in batch_idx]

    def _is_skill_done(
        self, observations, rnn_hidden_states, prev_actions, masks, batch_idx
    ) -> torch.BoolTensor:
        success_pos = 1.5
        success_ang = 3.0  # 261799
        if (
            observations[TargetGoalGpsCompassSensor.cls_uuid][batch_idx][0, 0]
            < success_pos
            and abs(
                observations[TargetGoalGpsCompassSensor.cls_uuid][batch_idx][
                    0, 1
                ]
            )
            < success_ang
            and self._cur_skill_args[0].is_target
        ):
            return torch.ones(1, dtype=torch.bool).to(masks.device)
        elif (
            observations[TargetStartGpsCompassSensor.cls_uuid][batch_idx][0, 0]
            < success_pos
            and abs(
                observations[TargetStartGpsCompassSensor.cls_uuid][batch_idx][
                    0, 1
                ]
            )
            < success_ang
            and not self._cur_skill_args[0].is_target
        ):
            return torch.ones(1, dtype=torch.bool).to(masks.device)
        else:
            return torch.zeros(1, dtype=torch.bool).to(masks.device)
        # return (self._did_want_done[batch_idx] > 0.0).to(masks.device)

    def _parse_skill_arg(self, skill_arg):
        targ_name, targ_idx = skill_arg[-2].split("|")
        return NavSkillPolicy.NavArgs(
            obj_idx=int(targ_idx), is_target=targ_name.startswith("TARGET")
        )

    def _internal_act(
        self,
        observations,
        rnn_hidden_states,
        prev_actions,
        masks,
        cur_batch_idx,
        deterministic=False,
    ):
        action = super()._internal_act(
            observations,
            rnn_hidden_states,
            prev_actions,
            masks,
            cur_batch_idx,
            deterministic,
        )
        # print("action:", action)
        return action
