import abc
from typing import TYPE_CHECKING, Any, Dict, List, Set, Tuple, Union

import torch
from numpy import ndarray
from torch import Tensor

from habitat import VectorEnv
from habitat_baselines.common.env_spec import EnvironmentSpec
from habitat_baselines.common.obs_transformers import ObservationTransformer
from habitat_baselines.common.tensorboard_utils import TensorboardWriter
from habitat_baselines.rl.ppo.habitat_evaluator import Evaluator, pause_envs
from habitat_baselines.rl.ppo.policy import Policy

if TYPE_CHECKING:
    from omegaconf import DictConfig


class Evaluator(abc.ABC):
    """
    Generic evaluator interface for evaluation loops over provided checkpoints.
    Extend for environment or project specific evaluation.
    """

    @abc.abstractmethod
    def evaluate_agent(
        self,
        agent: Policy,
        envs: VectorEnv,
        config: "DictConfig",
        checkpoint_index: int,
        step_id: int,
        writer: TensorboardWriter,
        device: torch.device,
        obs_transforms: List[ObservationTransformer],
        env_spec: EnvironmentSpec,
        rank0_keys: Set[str],
    ) -> None:
        pass


def pause_envs(
    envs_to_pause: List[int],
    envs: VectorEnv,
    test_recurrent_hidden_states: Tensor,
    not_done_masks: Tensor,
    current_episode_reward: Tensor,
    prev_actions: Tensor,
    batch: Dict[str, Tensor],
    rgb_frames: Union[List[List[Any]], List[List[ndarray]]],
) -> Tuple[
    VectorEnv,
    Tensor,
    Tensor,
    Tensor,
    Tensor,
    Dict[str, Tensor],
    List[List[Any]],
]:
    # pausing self.envs with no new episode
    if len(envs_to_pause) > 0:
        state_index = list(range(envs.num_envs))
        for idx in reversed(envs_to_pause):
            state_index.pop(idx)
            envs.pause_at(idx)

        # indexing along the batch dimensions
        test_recurrent_hidden_states = test_recurrent_hidden_states[
            state_index
        ]
        not_done_masks = not_done_masks[state_index]
        current_episode_reward = current_episode_reward[state_index]
        prev_actions = prev_actions[state_index]

        for k, v in batch.items():
            batch[k] = v[state_index]

        rgb_frames = [rgb_frames[i] for i in state_index]
        # actor_critic.do_pause(state_index)

    return (
        envs,
        test_recurrent_hidden_states,
        not_done_masks,
        current_episode_reward,
        prev_actions,
        batch,
        rgb_frames,
    )
