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
from habitat_baselines.rl.hrl.utils import skill_io_manager
from habitat_baselines.utils.common import get_num_actions


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

        # Get the skill io manager
        self.sm = skill_io_manager()
        self._num_ac = get_num_actions(action_space)

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
        success_ang = float("inf")  # 261799
        success = False

        for i, batch_i in enumerate(batch_idx):
            if self._cur_skill_args[batch_i].is_target:
                replace_sensor = TargetGoalGpsCompassSensor.cls_uuid
            else:
                replace_sensor = TargetStartGpsCompassSensor.cls_uuid
            pos = observations[replace_sensor][i][0:2]
        print(pos)
        if pos[0] <= success_pos and abs(pos[1]) <= success_ang:
            success = True

        if success:
            return torch.ones(1, dtype=torch.bool).to(masks.device)
        else:
            return torch.zeros(1, dtype=torch.bool).to(masks.device)

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
        if self.sm.hidden_state is None:
            self.sm.init_hidden_state(
                observations,
                self._wrap_policy.net._hidden_size,
                self._wrap_policy.num_recurrent_layers,
            )
            self.sm.init_prev_action(prev_actions, self._num_ac)

        action = super()._internal_act(
            observations,
            self.sm.hidden_state,
            self.sm.prev_action,
            masks,
            cur_batch_idx,
            deterministic,
        )

        # Update the hidden state / action
        self.sm.hidden_state = action.rnn_hidden_states
        self.sm.prev_action = action.actions

        return action
