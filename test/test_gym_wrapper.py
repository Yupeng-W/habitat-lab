import gym.spaces as spaces
import numpy as np

import habitat_baselines.utils.env_utils
from habitat_baselines.common.environments import get_env_class
from habitat_baselines.config.default import get_config as baselines_get_config
from habitat_baselines.utils.gym_adapter import HabGymWrapper
from habitat_baselines.utils.render_wrapper import HabRenderWrapper


def test_gym_pick_wrapper():
    config = baselines_get_config(
        "habitat_baselines/config/rearrange/ddppo_rearrangepick.yaml"
    )
    env_class = get_env_class(config.ENV_NAME)

    env = habitat_baselines.utils.env_utils.make_env_fn(
        env_class=env_class, config=config
    )
    env = HabGymWrapper(env)
    env = HabRenderWrapper(env)
    assert isinstance(env.action_space, spaces.Box)
    obs = env.reset()
    assert isinstance(obs, np.ndarray), f"Obs {obs}"
    assert obs.shape == env.observation_space.shape
    obs, _, _, info = env.step(env.action_space.sample())
    assert isinstance(obs, np.ndarray), f"Obs {obs}"
    assert obs.shape == env.observation_space.shape

    frame = env.render()
    assert isinstance(frame, np.ndarray)
    assert len(frame.shape) == 3 and frame.shape[-1] == 3

    for _, v in info.items():
        assert not isinstance(v, dict)
