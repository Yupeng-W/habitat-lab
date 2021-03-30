import pytest
from habitat.config import get_crl_config
from habitat.core.env import CLEnv
import os

TEST_CFG_PATH = 'configs/test/habitat_cl_example.yaml'

def get_config(name: str):
    # use test dataset for lighter testing
    datapath = (
        "data/datasets/pointnav/habitat-test-scenes/v1/{split}/{split}.json.gz"
    )
    cfg = get_crl_config(name)
    if not os.path.exists(cfg.SIMULATOR.SCENE):
        pytest.skip("Please download Habitat test data to data folder.")
    if len(cfg.TASKS) < 2:
        pytest.skip("Please use a configuration with at least 2 tasks for testing.")
    cfg.defrost()
    cfg.DATASET.DATA_PATH = datapath
    cfg.DATASET.SPLIT = 'test'
    # also make sure tasks config are overriden
    for task in cfg.TASKS:
        task.DATASET.DATA_PATH = datapath
        task.DATASET.SPLIT = 'test'
    # and work with small observations for testing
    if 'RGB_SENSOR' in cfg:
        cfg.RGB_SENSOR.WIDTH = 64
        cfg.RGB_SENSOR.HEIGHT = 64
    if 'DEPTH_SENSOR' in cfg:
        cfg.DEPTH_SENSOR.WIDTH = 64
        cfg.DEPTH_SENSOR.HEIGHT = 64
    cfg.freeze()
    return cfg


def test_standard_config_compatibility():
    cfg = get_crl_config('configs/tasks/pointnav.yaml')
    env = CLEnv(config=cfg)
    obs = env.reset()
    actions = 0

    while not env.episode_over:
        # execute random action
        obs = env.step(env.action_space.sample())
        actions += 1
    assert actions >= 1, 'You should have performed at least one step with no interruptions'
    env.close()


def test_simple_fixed_change_task():
    cfg = get_config(TEST_CFG_PATH)
    cfg.defrost()
    cfg.CHANGE_TASK_BEHAVIOUR.TYPE = 'FIXED'
    cfg.CHANGE_TASK_BEHAVIOUR.AFTER_N_EPISODES = 1
    cfg.CHANGE_TASK_BEHAVIOUR.AFTER_N_CUM_STEPS = None
    cfg.CHANGE_TASK_BEHAVIOUR.LOOP = "ORDER"
    # test meant for 2 tasks
    cfg.TASKS = cfg.TASKS[:2]
    cfg.freeze()
    env = CLEnv(config=cfg)
    task_bit = False
    for _ in range(5):
        obs = env.reset()
        assert env._curr_task_idx == task_bit, 'Task should change at each new episode'
        task_bit = not (task_bit)
        while not env.episode_over:
            # execute random action
            obs = env.step(env.action_space.sample())
    env.close()


def test_fixed_change_multiple_tasks():
    change_after = 3
    cfg = get_config(TEST_CFG_PATH)
    cfg.defrost()
    cfg.CHANGE_TASK_BEHAVIOUR.TYPE = 'FIXED'
    cfg.CHANGE_TASK_BEHAVIOUR.AFTER_N_EPISODES = change_after
    cfg.CHANGE_TASK_BEHAVIOUR.AFTER_N_CUM_STEPS = None
    cfg.CHANGE_TASK_BEHAVIOUR.LOOP = "ORDER"
    cfg.freeze()
    env = CLEnv(config=cfg)
    task_idx = 0
    for i in range(10):
        obs = env.reset()
        if i > 0 and i % change_after == 0:
            task_idx = (task_idx + 1) % len(cfg.TASKS)
        assert env._curr_task_idx == task_idx, 'Task should change every {} episodes'.format(
            change_after)
        while not env.episode_over:
            # execute random action
            obs = env.step(env.action_space.sample())
    env.close()


def test_cum_steps_change_tasks_same_scene():
    change_after = 5
    cfg = get_config(TEST_CFG_PATH)
    cfg.defrost()
    cfg.CHANGE_TASK_BEHAVIOUR.TYPE = 'FIXED'
    cfg.CHANGE_TASK_BEHAVIOUR.AFTER_N_EPISODES = None
    cfg.CHANGE_TASK_BEHAVIOUR.AFTER_N_CUM_STEPS = change_after
    cfg.CHANGE_TASK_BEHAVIOUR.LOOP = "ORDER"
    cfg.freeze()
    env = CLEnv(config=cfg)
    task_idx = 0
    actions = 0
    for i in range(10):
        obs = env.reset()

        while not env.episode_over:
            # execute random action
            obs = env.step(env.action_space.sample())
            actions += 1
            if actions >= change_after:
                actions = 0
                task_idx = (task_idx + 1) % len(cfg.TASKS)
            assert env._curr_task_idx == task_idx, 'Task should change every {} steps'.format(
                change_after)
    env.close()


def test_cum_steps_change_tasks_different_scene():
    change_after = 3
    cfg = get_config(TEST_CFG_PATH)
    cfg.defrost()
    cfg.CHANGE_TASK_BEHAVIOUR.TYPE = 'FIXED'
    cfg.CHANGE_TASK_BEHAVIOUR.AFTER_N_EPISODES = None
    cfg.CHANGE_TASK_BEHAVIOUR.AFTER_N_CUM_STEPS = change_after
    cfg.CHANGE_TASK_BEHAVIOUR.LOOP = "ORDER"
    cfg.TASKS[0].DATASET.SPLIT = 'train' # get different split for this task
    cfg.freeze()
    env = CLEnv(config=cfg)
    task_idx = 0
    actions = 0
    for i in range(10):
        obs = env.reset()

        while not env.episode_over:
            # execute random action
            obs = env.step(env.action_space.sample())
            actions += 1
            if actions >= change_after:
                actions = 0
                task_idx = (task_idx + 1) % len(cfg.TASKS)
            assert env._curr_task_idx == task_idx, 'Task should change every {} steps'.format(
                change_after)
    env.close()


def test_ep_or_steps_change_tasks():
    change_after_eps = 2
    change_after_steps = 10
    cfg = get_config(TEST_CFG_PATH)
    cfg.defrost()
    cfg.CHANGE_TASK_BEHAVIOUR.TYPE = 'FIXED'
    cfg.CHANGE_TASK_BEHAVIOUR.AFTER_N_EPISODES = change_after_eps
    cfg.CHANGE_TASK_BEHAVIOUR.AFTER_N_CUM_STEPS = change_after_steps
    cfg.CHANGE_TASK_BEHAVIOUR.LOOP = "ORDER"
    cfg.freeze()
    env = CLEnv(config=cfg)
    task_idx = 0
    actions = 0
    for i in range(10):
        obs = env.reset()
        if i > 0 and i % change_after_eps == 0:
            task_idx = (task_idx + 1) % len(cfg.TASKS)
        assert env._curr_task_idx == task_idx, 'Task should change every {} episodes'.format(
            change_after_eps)
        while not env.episode_over:
            # execute random action
            obs = env.step(env.action_space.sample())
            actions += 1
            if actions >= change_after_steps:
                actions = 0
                task_idx = (task_idx + 1) % len(cfg.TASKS)
            assert env._curr_task_idx == task_idx, 'Task should change every {} steps'.format(
                change_after_steps)
    env.close()


def test_random_change_tasks():
    change_after = 3
    cfg = get_config(TEST_CFG_PATH)
    cfg.defrost()
    cfg.CHANGE_TASK_BEHAVIOUR.TYPE = 'RANDOM'
    cfg.CHANGE_TASK_BEHAVIOUR.CHANGE_TASK_PROB = 1.
    cfg.CHANGE_TASK_BEHAVIOUR.AFTER_N_EPISODES = change_after
    cfg.CHANGE_TASK_BEHAVIOUR.AFTER_N_CUM_STEPS = None
    cfg.CHANGE_TASK_BEHAVIOUR.LOOP = "ORDER"
    cfg.freeze()
    env = CLEnv(config=cfg)
    task_idx = 0
    for i in range(change_after * 2 + 1):
        obs = env.reset()
        if i > 0 and i % change_after == 0:
            task_idx = (task_idx + 1) % len(cfg.TASKS)
        assert env._curr_task_idx == task_idx, 'Task should change every {} episodes'.format(
            change_after)

        while not env.episode_over:
            # execute random action
            obs = env.step(env.action_space.sample())
    env.close()
    # it should never change now
    cfg.defrost()
    cfg.CHANGE_TASK_BEHAVIOUR.CHANGE_TASK_PROB = 0.
    cfg.freeze()
    env = CLEnv(config=cfg)
    task_idx = 0
    for i in range(change_after * 2 + 1):
        obs = env.reset()
        assert env._curr_task_idx == task_idx, 'Task should not change'

        while not env.episode_over:
            # execute random action
            obs = env.step(env.action_space.sample())
    env.close()

def test_random_task_loop():
    change_after = 3
    cfg = get_config(TEST_CFG_PATH)
    cfg.defrost()
    cfg.CHANGE_TASK_BEHAVIOUR.TYPE = 'FIXED'
    cfg.CHANGE_TASK_BEHAVIOUR.AFTER_N_EPISODES = change_after
    cfg.CHANGE_TASK_BEHAVIOUR.AFTER_N_CUM_STEPS = None
    cfg.CHANGE_TASK_BEHAVIOUR.LOOP = "RANDOM"
    cfg.freeze()
    env = CLEnv(config=cfg)
    task_idx = 0
    for i in range(10):
        obs = env.reset()
        if i > 0 and i % change_after == 0:
            assert env._curr_task_idx != task_idx, 'Task should change every {} episodes'.format(
            change_after)
            task_idx = env._curr_task_idx
        while not env.episode_over:
            # execute random action
            obs = env.step(env.action_space.sample())
    env.close()
