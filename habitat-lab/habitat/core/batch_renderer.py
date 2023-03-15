#!/usr/bin/env python3

# Copyright (c) Meta Platforms, Inc. and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import os
from collections import OrderedDict
from typing import Callable, Dict, List, Union

import magnum as mn
import numpy as np
from omegaconf import DictConfig
from torch import Tensor

import habitat_sim
from habitat.core.batch_renderer_constants import (
    KEYFRAME_OBSERVATION_KEY,
    KEYFRAME_SENSOR_PREFIX,
)
from habitat.core.logging import logger
from habitat.core.registry import registry
from habitat.core.simulator import Observations
from habitat.core.simulator import SensorSuite as CoreSensorSuite
from habitat.sims.habitat_simulator.habitat_simulator import (
    HabitatSimSensor,
    overwrite_config,
)
from habitat_sim import ReplayRenderer, ReplayRendererConfiguration
from habitat_sim.sensor import SensorSpec as BackendSensorSpec


class BatchRenderer:
    r"""
    Wrapper for batch rendering functionality, which renders visual sensors of N environments simultaneously.

    Batch rendering reduces multi-environment memory usage and loading time by pre-loading all graphics assets once.
    This is accomplished by loading a composite GLTF file that contains all assets that will be used during a rollout.
    It also increases rendering performance by batching, leveraging data locality, minimizing amount of contexts.

    Internally, the system is a replay renderer, meaning that it renders gfx-replay keyframes emitted by simulators.
    When batch rendering, simulators produce keyframes and add them to observations as KEYFRAME_OBSERVATION_KEY.
    In "post_step", the renderer aggregates these observations, reconstitutes each state then renders them simultaneously.

    This feature is experimental and may change at any time.
    """
    _num_envs: int = 1
    _gpu_gpu: bool = False

    _sensor_suite: CoreSensorSuite = None
    _sensor_specifications: List[BackendSensorSpec] = None

    _replay_renderer_cfg: ReplayRendererConfiguration = None
    _replay_renderer: ReplayRenderer = None

    _gpu_to_cpu_images: List[mn.ImageView2D] = None
    _gpu_to_cpu_buffer: np.ndarray = None

    def __init__(self, config: DictConfig, num_envs: int) -> None:
        r"""
        Initialize the batch renderer.

        :param config: Base configuration.
        :param num_envs: Number of concurrent environments to render.
        """
        assert config.habitat.simulator.enable_batch_renderer
        logger.warn(
            "Batch rendering enabled. This feature is experimental and may change at any time."
        )

        self._num_envs = num_envs
        self._gpu_gpu = config.habitat.simulator.habitat_sim_v0.gpu_gpu

        # TODO: GPU-to-GPU code path is not yet implemented.
        if self._gpu_gpu:
            raise NotImplementedError

        self._sensor_suite = BatchRenderer._create_core_sensor_suite(config)
        self._sensor_specifications = (
            BatchRenderer._create_sensor_specifications(
                config, self._sensor_suite
            )
        )
        self._replay_renderer_cfg = BatchRenderer._create_replay_renderer_cfg(
            config,
            self._num_envs,
            self._sensor_specifications,
        )
        self._replay_renderer: ReplayRenderer = (
            ReplayRenderer.create_batch_replay_renderer(
                self._replay_renderer_cfg
            )
        )

        # Pre-load graphics assets using composite GLTF file.
        if os.path.isfile(config.habitat.dataset.composite_file):
            logger.info(
                "Pre-loading composite file: "
                + config.habitat.dataset.composite_file
            )
            self._replay_renderer.preload_file(
                config.habitat.dataset.composite_file
            )
        else:
            logger.warn(
                "No composite file pre-loaded. Batch rendering performance won't be optimal."
            )

    def post_step(self, observations: List[OrderedDict]) -> List[OrderedDict]:
        r"""
        Renders observations for all environments by consuming keyframe observations.

        :param observations: List of observations for each environment.
        :return: List of rendered observations for each environment.
        """
        assert len(observations) == self._num_envs

        # Pop KEYFRAME_OBSERVATION_KEY from observations and apply to replay renderer.
        # See HabitatSim.add_keyframe_to_observations().
        for env_index in range(self._num_envs):
            env_obs = observations[env_index]
            keyframe = env_obs.pop(KEYFRAME_OBSERVATION_KEY)
            self._replay_renderer.set_environment_keyframe(
                env_index, keyframe
            )
            self._replay_renderer.set_sensor_transforms_from_keyframe(
                env_index, KEYFRAME_SENSOR_PREFIX
            )

        # Render observations
        batch_observations: Dict[str, Union[np.ndarray, Tensor]] = {}
        for sensor_spec in self._sensor_specifications:
            batch_observations[sensor_spec.uuid] = self.draw_observations(
                sensor_spec
            )

        # Process and format observations
        output: List[OrderedDict] = []
        for env_index in range(self._num_envs):
            env_observations = observations[env_index]["observation"]
            for sensor_spec in self._sensor_specifications:
                env_observations[sensor_spec.uuid] = batch_observations[
                    sensor_spec.uuid
                ][env_index]
            # Post-process sim sensor output using lab sensor interface.
            # The same lab sensors are re-used for all environments.
            processed_obs: Observations = self._sensor_suite.get_observations(
                env_observations
            )
            for key, value in processed_obs.items():
                env_observations[key] = value
            output.append(env_observations)
        return output

    def draw_observations(
        self, sensor_spec: BackendSensorSpec
    ) -> Union[np.ndarray, "Tensor"]:
        r"""
        Draw observations for all environments.

        :param sensor_spec: Habitat-sim sensor specifications.
        :return: A numpy ndarray in GPU-to-CPU mode, or a torch tensor in GPU-to-GPU mode.
        """
        draw_fn: Callable = (
            self.draw_observations_gpu_to_gpu
            if self._gpu_gpu
            else self.draw_observations_gpu_to_cpu
        )
        return draw_fn(sensor_spec)

    def draw_observations_gpu_to_cpu(
        self, sensor_spec: BackendSensorSpec
    ) -> np.ndarray:
        r"""
        Draw observations for all environments.
        Copies sensors output from GPU memory into CPU ndarrays, during which the thread is blocked.

        :param sensor_spec: Habitat-sim sensor specifications.
        :return: ndarray containing renders.
        """
        # TODO: Currently only one color sensor is supported.
        if sensor_spec.sensor_type == habitat_sim.SensorType.COLOR:
            if self._gpu_to_cpu_images is None:
                # Allocate the transfer buffers
                self._gpu_to_cpu_images = []
                storage = mn.PixelStorage()
                storage.alignment = 2
                self._gpu_to_cpu_buffer = np.empty(
                    (
                        self._num_envs,
                        sensor_spec.resolution[0],
                        sensor_spec.resolution[1],
                        sensor_spec.channels,
                    ),
                    dtype=np.uint8,
                )

                for env_idx in range(self._num_envs):
                    # Create image view for writing into buffer from Magnum
                    env_img_view = mn.MutableImageView2D(
                        mn.PixelFormat.RGBA8_UNORM,
                        [sensor_spec.resolution[1], sensor_spec.resolution[0]],
                        self._gpu_to_cpu_buffer[env_idx],
                    )
                    self._gpu_to_cpu_images.append(env_img_view)

                # Flip the transfer buffer view vertically for presentation
                self._gpu_to_cpu_buffer = np.flip(
                    self._gpu_to_cpu_buffer.view(), axis=1
                )
        else:
            raise NotImplementedError

        # Render
        self._replay_renderer.render(self._gpu_to_cpu_images)
        return self._gpu_to_cpu_buffer

    def draw_observations_gpu_to_gpu(
        self, sensor_spec: BackendSensorSpec
    ) -> "Tensor":
        raise NotImplementedError

    def copy_output_to_image(self) -> List[np.ndarray]:
        r"""
        Utility function that creates a list of RGB images (as ndarrays) for each
        environment using unprocessed data that was rendered during the last
        post_step call. For testing and debugging only.

        :return: List of RGB images as ndarrays.
        """
        # TODO: Only one color sensor supported.
        output: List[np.ndarray] = []
        if self._gpu_gpu:
            raise NotImplementedError
        else:
            for env_idx in range(self._num_envs):
                output.append(self._gpu_to_cpu_buffer[env_idx][..., 0:3])
        return output

    @staticmethod
    def _create_core_sensor_suite(
        config: DictConfig,
    ) -> CoreSensorSuite:
        r"""
        Instantiates a core sensor suite from configuration that only contains visual sensors.

        :param config: Base configuration.
        """
        sim_sensors = []
        for agent_cfg in config.habitat.simulator.agents.values():
            for sensor_cfg in agent_cfg.sim_sensors.values():
                sensor_type = registry.get_sensor(sensor_cfg.type)
                if sensor_type.sim_sensor_type in [  # type: ignore
                    habitat_sim.SensorType.COLOR,
                    habitat_sim.SensorType.DEPTH,
                ]:
                    sim_sensors.append(sensor_type(sensor_cfg))
        return CoreSensorSuite(sim_sensors)

    @staticmethod
    def _create_sensor_specifications(
        config: DictConfig, sensor_suite: CoreSensorSuite
    ) -> List[BackendSensorSpec]:
        r"""
        Creates a list of Habitat-Sim sensor specifications from a specified core sensor suite.

        :param config: Base configuration.
        :param sensor_suite: Core sensor suite that only contains visual sensors. See _create_core_sensor_suite().

        :return: List of Habitat-Sim sensor specifications
        """
        # Note: Copied from habitat_simulator.create_sim_config().
        sensor_specifications: list = []
        for sensor in sensor_suite.sensors.values():
            assert isinstance(sensor, HabitatSimSensor)
            sim_sensor_cfg = sensor._get_default_spec()  # type: ignore
            overwrite_config(
                config_from=sensor.config,
                config_to=sim_sensor_cfg,
                # These keys are only used by Hab-Lab
                # or translated into the sensor config manually
                ignore_keys=sensor._config_ignore_keys,
                # TODO consider making trans_dict a sensor class var too.
                trans_dict={
                    "sensor_model_type": lambda v: getattr(
                        habitat_sim.FisheyeSensorModelType, v
                    ),
                    "sensor_subtype": lambda v: getattr(
                        habitat_sim.SensorSubType, v
                    ),
                },
            )
            sim_sensor_cfg.uuid = sensor.uuid
            sim_sensor_cfg.resolution = list(
                sensor.observation_space.shape[:2]
            )
            sim_sensor_cfg.sensor_type = sensor.sim_sensor_type
            sim_sensor_cfg.gpu2gpu_transfer = (
                config.habitat.simulator.habitat_sim_v0.gpu_gpu
            )
            sensor_specifications.append(sim_sensor_cfg)
        return sensor_specifications

    @staticmethod
    def _create_replay_renderer_cfg(
        config: DictConfig,
        num_env: int,
        sensor_specifications: List[BackendSensorSpec],
    ) -> ReplayRendererConfiguration:
        r"""
        Creates the configuration info for creating a replay renderer.

        :param config: Base configuration.
        :param num_env: Number of environments.
        :param sensor_specifications: Habitat-Sim visual sensor specifications. See _create_sensor_specifications().
        :return: Replay renderer configuration.
        """
        replay_renderer_cfg: ReplayRendererConfiguration = (
            ReplayRendererConfiguration()
        )
        replay_renderer_cfg.num_environments = num_env
        replay_renderer_cfg.standalone = True
        replay_renderer_cfg.sensor_specifications = sensor_specifications
        replay_renderer_cfg.gpu_device_id = (
            config.habitat.simulator.habitat_sim_v0.gpu_device_id
        )
        replay_renderer_cfg.force_separate_semantic_scene_graph = False
        replay_renderer_cfg.leave_context_with_background_renderer = False
        return replay_renderer_cfg
