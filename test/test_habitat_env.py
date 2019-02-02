import json
import multiprocessing as mp
import os

import habitat
import numpy as np
from habitat.config.default import cfg
from habitat.core.simulator import AgentState
from habitat.sims.habitat_simulator import (
    SimActions,
    SIM_ACTION_TO_NAME,
    SIM_NAME_TO_ACTION,
)
from habitat.tasks.nav.nav_task import NavigationEpisode

CFG_TEST = "test/habitat_all_sensors_test.yaml"
MULTIHOUSE_RESOURCES_PATH = "data/habitat-sim/multihouse-resources"
MULTIHOUSE_INITIALIZATIONS_PATH = (
    "data/habitat-sim/multihouse_initializations.json"
)


class DatasetTest(habitat.Dataset):
    def __init__(self, multihouse_initializations, ind_house):
        house_id = sorted(os.listdir(MULTIHOUSE_RESOURCES_PATH))[ind_house]
        path = os.path.join(
            MULTIHOUSE_RESOURCES_PATH, house_id, "{}.glb".format(house_id)
        )
        start_position = multihouse_initializations[house_id]["start_position"]
        start_rotation = multihouse_initializations[house_id]["start_rotation"]
        house_episode = NavigationEpisode(
            episode_id=str(ind_house),
            scene_id=path,
            start_position=start_position,
            start_rotation=start_rotation,
            goals=[],
        )
        self._episodes = [house_episode]

    @property
    def episodes(self):
        return self._episodes


class DummyRLEnv(habitat.RLEnv):
    def get_reward_range(self):
        return -1.0, 1.0

    def get_reward(self, observations):
        return 0.0

    def get_done(self, observations):
        done = False
        if self._env.episode_over:
            done = True
        return done

    def get_info(self, observations):
        return {}


def _load_test_data():
    assert os.path.exists(MULTIHOUSE_RESOURCES_PATH), (
        "Multihouse test data missing, "
        "please download and place it in {}".format(MULTIHOUSE_RESOURCES_PATH)
    )
    assert os.path.isfile(MULTIHOUSE_INITIALIZATIONS_PATH), (
        "Multhouse initialization points missing, "
        "please download and place it in {}".format(
            MULTIHOUSE_INITIALIZATIONS_PATH
        )
    )
    with open(MULTIHOUSE_INITIALIZATIONS_PATH, "r") as f:
        multihouse_initializations = json.load(f)

    configs = []
    num_envs = len(os.listdir(MULTIHOUSE_RESOURCES_PATH))
    datasets = []
    for i in range(num_envs):
        datasets.append(DatasetTest(multihouse_initializations, i))
        config = cfg(CFG_TEST)
        config.SIMULATOR.SCENE = datasets[-1].episodes[0].scene_id
        configs.append(config)

    return configs, datasets


def _vec_env_test_fn(configs, datasets, multiprocessing_start_method):
    num_envs = len(configs)
    env_fn_args = tuple(zip(configs, datasets, range(num_envs)))
    envs = habitat.VectorEnv(
        env_fn_args=env_fn_args,
        multiprocessing_start_method=multiprocessing_start_method,
    )
    envs.reset()
    non_stop_actions = [
        k for k, v in SIM_ACTION_TO_NAME.items() if v != SimActions.STOP.value
    ]

    for _ in range(2 * configs[0].ENVIRONMENT.MAX_EPISODE_STEPS):
        observations = envs.step(np.random.choice(non_stop_actions, num_envs))
        assert len(observations) == num_envs

    envs.close()


def test_vectorized_envs_forkserver():
    configs, datasets = _load_test_data()
    _vec_env_test_fn(configs, datasets, "forkserver")


def test_vectorized_envs_spawn():
    configs, datasets = _load_test_data()
    _vec_env_test_fn(configs, datasets, "spawn")


def _fork_test_target(configs, datasets):
    _vec_env_test_fn(configs, datasets, "fork")


def test_vectorized_envs_fork():
    configs, datasets = _load_test_data()
    # 'fork' works in a process that has yet to use the GPU
    # this test uses spawns a new python instance, which allows us to fork
    mp_ctx = mp.get_context("spawn")
    p = mp_ctx.Process(target=_fork_test_target, args=(configs, datasets))
    p.start()
    p.join()
    assert p.exitcode == 0


def test_threaded_vectorized_env():
    configs, datasets = _load_test_data()
    num_envs = len(configs)
    env_fn_args = tuple(zip(configs, datasets, range(num_envs)))
    envs = habitat.ThreadedVectorEnv(env_fn_args=env_fn_args)
    envs.reset()
    non_stop_actions = [
        k for k, v in SIM_ACTION_TO_NAME.items() if v != SimActions.STOP.value
    ]

    for i in range(2 * configs[0].ENVIRONMENT.MAX_EPISODE_STEPS):
        observations = envs.step(np.random.choice(non_stop_actions, num_envs))
        assert len(observations) == num_envs

    envs.close()


def test_env():
    config = cfg(CFG_TEST)
    assert os.path.exists(config.SIMULATOR.SCENE), (
        "Habitat-Sim test data missing, please download and place it in "
        "data/habitat-sim/test/"
    )
    env = habitat.Env(config=config, dataset=None)
    env.episodes = [
        NavigationEpisode(
            episode_id="0",
            scene_id=config.SIMULATOR.SCENE,
            start_position=[03.00611, 0.072447, -2.67867],
            start_rotation=[0, 0.163276, 0, 0.98658],
            goals=[],
        )
    ]

    env.reset()
    non_stop_actions = [
        k for k, v in SIM_ACTION_TO_NAME.items() if v != SimActions.STOP.value
    ]
    for _ in range(config.ENVIRONMENT.MAX_EPISODE_STEPS):
        env.step(np.random.choice(non_stop_actions))

    # check for steps limit on environment
    assert env.episode_over is True, (
        "episode should be over after " "max_episode_steps"
    )

    env.reset()

    env.step(SIM_NAME_TO_ACTION[SimActions.STOP.value])
    # check for STOP action
    assert env.episode_over is True, (
        "episode should be over after STOP " "action"
    )

    env.close()


def make_rl_env(config, dataset, rank: int = 0):
    """Constructor for default habitat Env.
    :param config: configurations for environment
    :param dataset: dataset for environment
    :param rank: rank for setting seeds for environment
    :return: constructed habitat Env
    """
    env = DummyRLEnv(config=config, dataset=dataset)
    env.seed(config.SEED + rank)
    return env


def test_rl_vectorized_envs():
    configs, datasets = _load_test_data()

    num_envs = len(configs)
    env_fn_args = tuple(zip(configs, datasets, range(num_envs)))
    envs = habitat.VectorEnv(make_env_fn=make_rl_env, env_fn_args=env_fn_args)
    envs.reset()
    non_stop_actions = [
        k for k, v in SIM_ACTION_TO_NAME.items() if v != SimActions.STOP.value
    ]

    for i in range(2 * configs[0].ENVIRONMENT.MAX_EPISODE_STEPS):
        outputs = envs.step(np.random.choice(non_stop_actions, num_envs))
        observations, rewards, dones, infos = [list(x) for x in zip(*outputs)]
        assert len(observations) == num_envs
        assert len(rewards) == num_envs
        assert len(dones) == num_envs
        assert len(infos) == num_envs
        if (i + 1) % configs[0].ENVIRONMENT.MAX_EPISODE_STEPS == 0:
            assert all(dones), "dones should be true after max_episode steps"

    envs.close()


def test_rl_env():
    config = cfg(CFG_TEST)
    assert os.path.exists(config.SIMULATOR.SCENE), (
        "Habitat-Sim test data missing, please download and place it in "
        "data/habitat-sim/test/"
    )
    env = DummyRLEnv(config=config, dataset=None)
    env.episodes = [
        NavigationEpisode(
            episode_id="0",
            scene_id=config.SIMULATOR.SCENE,
            start_position=[03.00611, 0.072447, -2.67867],
            start_rotation=[0, 0.163276, 0, 0.98658],
            goals=[],
        )
    ]

    done = False
    observation = env.reset()

    non_stop_actions = [
        k for k, v in SIM_ACTION_TO_NAME.items() if v != SimActions.STOP.value
    ]
    for _ in range(config.ENVIRONMENT.MAX_EPISODE_STEPS):
        observation, reward, done, info = env.step(
            np.random.choice(non_stop_actions)
        )

    # check for steps limit on environment
    assert done is True, "episodes should be over after max_episode_steps"

    env.reset()
    observation, reward, done, info = env.step(
        SIM_NAME_TO_ACTION[SimActions.STOP.value]
    )
    assert done is True, "done should be true after STOP action"

    env.close()


def test_action_space_shortest_path():
    config = cfg()
    assert os.path.exists(config.SIMULATOR.SCENE), (
        "Habitat-Sim test data missing, please download and place it in "
        "data/habitat-sim/test/"
    )
    env = habitat.Env(config=config, dataset=None)

    # action space shortest path
    source_position = env.sim.sample_navigable_point()
    angles = [x for x in range(-180, 180, config.SIMULATOR.TURN_ANGLE)]
    angle = np.radians(np.random.choice(angles))
    source_rotation = [0, np.sin(angle / 2), 0, np.cos(angle / 2)]
    source = AgentState(source_position, source_rotation)

    reachable_targets = []
    unreachable_targets = []
    while len(reachable_targets) < 5:
        position = env.sim.sample_navigable_point()
        angles = [x for x in range(-180, 180, config.SIMULATOR.TURN_ANGLE)]
        angle = np.radians(np.random.choice(angles))
        rotation = [0, np.sin(angle / 2), 0, np.cos(angle / 2)]
        if env.sim.geodesic_distance(source_position, position) != np.inf:
            reachable_targets.append(AgentState(position, rotation))

    while len(unreachable_targets) < 3:
        position = env.sim.sample_navigable_point()
        angles = [x for x in range(-180, 180, config.SIMULATOR.TURN_ANGLE)]
        angle = np.radians(np.random.choice(angles))
        rotation = [0, np.sin(angle / 2), 0, np.cos(angle / 2)]
        if env.sim.geodesic_distance(source_position, position) == np.inf:
            unreachable_targets.append(AgentState(position, rotation))

    targets = reachable_targets
    shortest_path1 = env.sim.action_space_shortest_path(source, targets)
    assert shortest_path1 != []

    targets = unreachable_targets
    shortest_path2 = env.sim.action_space_shortest_path(source, targets)
    assert shortest_path2 == []

    targets = reachable_targets + unreachable_targets
    shortest_path3 = env.sim.action_space_shortest_path(source, targets)

    # shortest_path1 should be identical to shortest_path3
    assert len(shortest_path1) == len(shortest_path3)
    for i in range(len(shortest_path1)):
        assert np.allclose(
            shortest_path1[i].position, shortest_path3[i].position
        )
        assert np.allclose(
            shortest_path1[i].rotation, shortest_path3[i].rotation
        )
        assert shortest_path1[i].action == shortest_path3[i].action

    targets = unreachable_targets + [source]
    shortest_path4 = env.sim.action_space_shortest_path(source, targets)
    assert len(shortest_path4) == 1
    assert np.allclose(shortest_path4[0].position, source.position)
    assert np.allclose(shortest_path4[0].rotation, source.rotation)
    assert shortest_path4[0].action is None

    env.close()
