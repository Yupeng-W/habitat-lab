#!/usr/bin/env python3

# Copyright (c) Meta Platforms, Inc. and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.


from collections import defaultdict, deque

import magnum as mn
import numpy as np
from gym import spaces

from habitat.core.embodied_task import Measure
from habitat.core.registry import registry
from habitat.core.simulator import Sensor, SensorTypes
from habitat.tasks.nav.nav import PointGoalSensor
from habitat.tasks.rearrange.rearrange_sim import RearrangeSim
from habitat.tasks.rearrange.utils import (
    CollisionDetails,
    UsesArticulatedAgentInterface,
    batch_transform_point,
    get_angle_to_pos,
    rearrange_logger,
)
from habitat.tasks.utils import cartesian_to_polar


class MultiObjSensor(PointGoalSensor):
    """
    Abstract parent class for a sensor that specifies the locations of all targets.
    """

    def __init__(self, *args, task, **kwargs):
        self._task = task
        self._sim: RearrangeSim
        super().__init__(*args, task=task, **kwargs)

    def _get_observation_space(self, *args, **kwargs):
        n_targets = self._task.get_n_targets()
        return spaces.Box(
            shape=(n_targets * 3,),
            low=np.finfo(np.float32).min,
            high=np.finfo(np.float32).max,
            dtype=np.float32,
        )


@registry.register_sensor
class TargetCurrentSensor(UsesArticulatedAgentInterface, MultiObjSensor):
    """
    This is the ground truth object position sensor relative to the robot end-effector coordinate frame.
    """

    cls_uuid: str = "obj_goal_pos_sensor"

    def _get_observation_space(self, *args, **kwargs):
        return spaces.Box(
            shape=(3,),
            low=np.finfo(np.float32).min,
            high=np.finfo(np.float32).max,
            dtype=np.float32,
        )

    def get_observation(self, observations, episode, *args, **kwargs):
        self._sim: RearrangeSim
        T_inv = (
            self._sim.get_agent_data(self.agent_id)
            .articulated_agent.ee_transform()
            .inverted()
        )

        idxs, _ = self._sim.get_targets()
        scene_pos = self._sim.get_scene_pos()
        pos = scene_pos[idxs]

        for i in range(pos.shape[0]):
            pos[i] = T_inv.transform_point(pos[i])

        return pos.reshape(-1)


@registry.register_sensor
class TargetStartSensor(UsesArticulatedAgentInterface, MultiObjSensor):
    """
    Relative position from end effector to target object
    """

    cls_uuid: str = "obj_start_sensor"

    def get_observation(self, *args, observations, episode, **kwargs):
        self._sim: RearrangeSim
        global_T = self._sim.get_agent_data(
            self.agent_id
        ).articulated_agent.ee_transform()
        T_inv = global_T.inverted()
        pos = self._sim.get_target_objs_start()
        return batch_transform_point(pos, T_inv, np.float32).reshape(-1)


class PositionGpsCompassSensor(UsesArticulatedAgentInterface, Sensor):
    def __init__(self, *args, sim, task, **kwargs):
        self._task = task
        self._sim = sim
        super().__init__(*args, task=task, **kwargs)

    def _get_sensor_type(self, *args, **kwargs):
        return SensorTypes.TENSOR

    def _get_observation_space(self, *args, config, **kwargs):
        n_targets = self._task.get_n_targets()
        self._polar_pos = np.zeros(n_targets * 2, dtype=np.float32)
        return spaces.Box(
            shape=(n_targets * 2,),
            low=np.finfo(np.float32).min,
            high=np.finfo(np.float32).max,
            dtype=np.float32,
        )

    def _get_positions(self) -> np.ndarray:
        raise NotImplementedError("Must override _get_positions")

    def get_observation(self, task, *args, **kwargs):
        pos = self._get_positions()
        articulated_agent_T = self._sim.get_agent_data(
            self.agent_id
        ).articulated_agent.base_transformation

        rel_pos = batch_transform_point(
            pos, articulated_agent_T.inverted(), np.float32
        )
        self._polar_pos = np.zeros_like(self._polar_pos)
        for i, rel_obj_pos in enumerate(rel_pos):
            rho, phi = cartesian_to_polar(rel_obj_pos[0], rel_obj_pos[1])
            self._polar_pos[(i * 2) : (i * 2) + 2] = [rho, -phi]

        return self._polar_pos


@registry.register_sensor
class TargetStartGpsCompassSensor(PositionGpsCompassSensor):
    cls_uuid: str = "obj_start_gps_compass"

    def _get_uuid(self, *args, **kwargs):
        return TargetStartGpsCompassSensor.cls_uuid

    def _get_positions(self) -> np.ndarray:
        return self._sim.get_target_objs_start()


@registry.register_sensor
class TargetGoalGpsCompassSensor(PositionGpsCompassSensor):
    cls_uuid: str = "obj_goal_gps_compass"

    def _get_uuid(self, *args, **kwargs):
        return TargetGoalGpsCompassSensor.cls_uuid

    def _get_positions(self) -> np.ndarray:
        _, pos = self._sim.get_targets()
        return pos


@registry.register_sensor
class AbsTargetStartSensor(MultiObjSensor):
    """
    Relative position from end effector to target object
    """

    cls_uuid: str = "abs_obj_start_sensor"

    def get_observation(self, observations, episode, *args, **kwargs):
        pos = self._sim.get_target_objs_start()
        return pos.reshape(-1)


@registry.register_sensor
class GoalSensor(UsesArticulatedAgentInterface, MultiObjSensor):
    """
    Relative to the end effector
    """

    cls_uuid: str = "obj_goal_sensor"

    def get_observation(self, observations, episode, *args, **kwargs):
        global_T = self._sim.get_agent_data(
            self.agent_id
        ).articulated_agent.ee_transform()
        T_inv = global_T.inverted()

        _, pos = self._sim.get_targets()
        return batch_transform_point(pos, T_inv, np.float32).reshape(-1)


@registry.register_sensor
class AbsGoalSensor(MultiObjSensor):
    cls_uuid: str = "abs_obj_goal_sensor"

    def get_observation(self, *args, observations, episode, **kwargs):
        _, pos = self._sim.get_targets()
        return pos.reshape(-1)


@registry.register_sensor
class JointSensor(UsesArticulatedAgentInterface, Sensor):
    def __init__(self, sim, config, *args, **kwargs):
        super().__init__(config=config)
        self._sim = sim

    def _get_uuid(self, *args, **kwargs):
        return "joint"

    def _get_sensor_type(self, *args, **kwargs):
        return SensorTypes.TENSOR

    def _get_observation_space(self, *args, config, **kwargs):
        return spaces.Box(
            shape=(config.dimensionality,),
            low=np.finfo(np.float32).min,
            high=np.finfo(np.float32).max,
            dtype=np.float32,
        )

    def get_observation(self, observations, episode, *args, **kwargs):
        joints_pos = self._sim.get_agent_data(
            self.agent_id
        ).articulated_agent.arm_joint_pos
        return np.array(joints_pos, dtype=np.float32)


@registry.register_sensor
class HumanoidJointSensor(UsesArticulatedAgentInterface, Sensor):
    def __init__(self, sim, config, *args, **kwargs):
        super().__init__(config=config)
        self._sim = sim

    def _get_uuid(self, *args, **kwargs):
        return "humanoid_joint_sensor"

    def _get_sensor_type(self, *args, **kwargs):
        return SensorTypes.TENSOR

    def _get_observation_space(self, *args, config, **kwargs):
        return spaces.Box(
            shape=(config.dimensionality,),
            low=np.finfo(np.float32).min,
            high=np.finfo(np.float32).max,
            dtype=np.float32,
        )

    def get_observation(self, observations, episode, *args, **kwargs):
        curr_agent = self._sim.get_agent_data(self.agent_id).articulated_agent
        if hasattr(curr_agent, "get_joint_transform"):
            joints_pos = curr_agent.get_joint_transform()[0]
            return np.array(joints_pos, dtype=np.float32)
        else:
            return np.zeros(self.observation_space.shape, dtype=np.float32)


@registry.register_sensor
class JointVelocitySensor(UsesArticulatedAgentInterface, Sensor):
    def __init__(self, sim, config, *args, **kwargs):
        super().__init__(config=config)
        self._sim = sim

    def _get_uuid(self, *args, **kwargs):
        return "joint_vel"

    def _get_sensor_type(self, *args, **kwargs):
        return SensorTypes.TENSOR

    def _get_observation_space(self, *args, config, **kwargs):
        return spaces.Box(
            shape=(config.dimensionality,),
            low=np.finfo(np.float32).min,
            high=np.finfo(np.float32).max,
            dtype=np.float32,
        )

    def get_observation(self, observations, episode, *args, **kwargs):
        joints_pos = self._sim.get_agent_data(
            self.agent_id
        ).articulated_agent.arm_velocity
        return np.array(joints_pos, dtype=np.float32)


@registry.register_sensor
class EEPositionSensor(UsesArticulatedAgentInterface, Sensor):
    cls_uuid: str = "ee_pos"

    def __init__(self, sim, config, *args, **kwargs):
        super().__init__(config=config)
        self._sim = sim

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return EEPositionSensor.cls_uuid

    def _get_sensor_type(self, *args, **kwargs):
        return SensorTypes.TENSOR

    def _get_observation_space(self, *args, **kwargs):
        return spaces.Box(
            shape=(3,),
            low=np.finfo(np.float32).min,
            high=np.finfo(np.float32).max,
            dtype=np.float32,
        )

    def get_observation(self, observations, episode, *args, **kwargs):
        trans = self._sim.get_agent_data(
            self.agent_id
        ).articulated_agent.base_transformation
        ee_pos = (
            self._sim.get_agent_data(self.agent_id)
            .articulated_agent.ee_transform()
            .translation
        )
        local_ee_pos = trans.inverted().transform_point(ee_pos)

        return np.array(local_ee_pos, dtype=np.float32)


@registry.register_sensor
class RelativeRestingPositionSensor(UsesArticulatedAgentInterface, Sensor):
    cls_uuid: str = "relative_resting_position"

    def _get_uuid(self, *args, **kwargs):
        return RelativeRestingPositionSensor.cls_uuid

    def __init__(self, sim, config, *args, **kwargs):
        super().__init__(config=config)
        self._sim = sim

    def _get_sensor_type(self, *args, **kwargs):
        return SensorTypes.TENSOR

    def _get_observation_space(self, *args, **kwargs):
        return spaces.Box(
            shape=(3,),
            low=np.finfo(np.float32).min,
            high=np.finfo(np.float32).max,
            dtype=np.float32,
        )

    def get_observation(self, observations, episode, task, *args, **kwargs):
        base_trans = self._sim.get_agent_data(
            self.agent_id
        ).articulated_agent.base_transformation
        ee_pos = (
            self._sim.get_agent_data(self.agent_id)
            .articulated_agent.ee_transform()
            .translation
        )
        local_ee_pos = base_trans.inverted().transform_point(ee_pos)

        relative_desired_resting = task.desired_resting - local_ee_pos

        return np.array(relative_desired_resting, dtype=np.float32)


@registry.register_sensor
class RestingPositionSensor(Sensor):
    """
    Desired resting position in the articulated_agent coordinate frame.
    """

    cls_uuid: str = "resting_position"

    def _get_uuid(self, *args, **kwargs):
        return RestingPositionSensor.cls_uuid

    def __init__(self, sim, config, *args, **kwargs):
        super().__init__(config=config)
        self._sim = sim

    def _get_sensor_type(self, *args, **kwargs):
        return SensorTypes.TENSOR

    def _get_observation_space(self, *args, **kwargs):
        return spaces.Box(
            shape=(3,),
            low=np.finfo(np.float32).min,
            high=np.finfo(np.float32).max,
            dtype=np.float32,
        )

    def get_observation(self, observations, episode, task, *args, **kwargs):
        return np.array(task.desired_resting, dtype=np.float32)


@registry.register_sensor
class LocalizationSensor(UsesArticulatedAgentInterface, Sensor):
    """
    The position and angle of the articulated_agent in world coordinates.
    """

    cls_uuid = "localization_sensor"

    def __init__(self, sim, config, *args, **kwargs):
        super().__init__(config=config)
        self._sim = sim

    def _get_uuid(self, *args, **kwargs):
        return LocalizationSensor.cls_uuid

    def _get_sensor_type(self, *args, **kwargs):
        return SensorTypes.TENSOR

    def _get_observation_space(self, *args, **kwargs):
        return spaces.Box(
            shape=(4,),
            low=np.finfo(np.float32).min,
            high=np.finfo(np.float32).max,
            dtype=np.float32,
        )

    def get_observation(self, observations, episode, *args, **kwargs):
        articulated_agent = self._sim.get_agent_data(
            self.agent_id
        ).articulated_agent
        T = articulated_agent.base_transformation
        forward = np.array([1.0, 0, 0])
        heading_angle = get_angle_to_pos(T.transform_vector(forward))
        return np.array(
            [*articulated_agent.base_pos, heading_angle], dtype=np.float32
        )


@registry.register_sensor
class NavigationTargetPositionSensor(UsesArticulatedAgentInterface, Sensor):
    """
    To check if the agent is in the goal or not
    """

    cls_uuid = "navigation_target_position_sensor"

    def __init__(self, sim, config, *args, **kwargs):
        super().__init__(config=config)
        self._sim = sim

    def _get_uuid(self, *args, **kwargs):
        return NavigationTargetPositionSensor.cls_uuid

    def _get_sensor_type(self, *args, **kwargs):
        return SensorTypes.TENSOR

    def _get_observation_space(self, *args, **kwargs):
        return spaces.Box(
            shape=(1,),
            low=np.finfo(np.float32).min,
            high=np.finfo(np.float32).max,
            dtype=np.float32,
        )

    def get_observation(self, observations, episode, *args, **kwargs):
        action_name = "oracle_nav_with_backing_up_action"
        task = kwargs["task"]
        if (
            "agent_"
            + str(self.agent_id)
            + "_oracle_nav_with_backing_up_action"
            in task.actions
        ):
            action_name = (
                "agent_"
                + str(self.agent_id)
                + "_oracle_nav_with_backing_up_action"
            )
        at_goal = task.actions[action_name].at_goal
        return np.array([at_goal])


@registry.register_sensor
class IsHoldingSensor(UsesArticulatedAgentInterface, Sensor):
    """
    Binary if the robot is holding an object or grasped onto an articulated object.
    """

    cls_uuid: str = "is_holding"

    def __init__(self, sim, config, *args, **kwargs):
        super().__init__(config=config)
        self._sim = sim

    def _get_uuid(self, *args, **kwargs):
        return IsHoldingSensor.cls_uuid

    def _get_sensor_type(self, *args, **kwargs):
        return SensorTypes.TENSOR

    def _get_observation_space(self, *args, **kwargs):
        return spaces.Box(shape=(1,), low=0, high=1, dtype=np.float32)

    def get_observation(self, observations, episode, *args, **kwargs):
        return np.array(
            int(self._sim.get_agent_data(self.agent_id).grasp_mgr.is_grasped),
            dtype=np.float32,
        ).reshape((1,))


@registry.register_measure
class ObjectToGoalDistance(Measure):
    """
    Euclidean distance from the target object to the goal.
    """

    cls_uuid: str = "object_to_goal_distance"

    def __init__(self, sim, config, *args, **kwargs):
        self._sim = sim
        self._config = config
        super().__init__(**kwargs)

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return ObjectToGoalDistance.cls_uuid

    def reset_metric(self, *args, episode, **kwargs):
        self.update_metric(*args, episode=episode, **kwargs)

    def update_metric(self, *args, episode, **kwargs):
        idxs, goal_pos = self._sim.get_targets()
        scene_pos = self._sim.get_scene_pos()
        target_pos = scene_pos[idxs]
        distances = np.linalg.norm(target_pos - goal_pos, ord=2, axis=-1)
        self._metric = {str(idx): dist for idx, dist in enumerate(distances)}


@registry.register_measure
class GfxReplayMeasure(Measure):
    cls_uuid: str = "gfx_replay_keyframes_string"

    def __init__(self, sim, config, *args, **kwargs):
        self._sim = sim
        self._enable_gfx_replay_save = (
            self._sim.sim_config.sim_cfg.enable_gfx_replay_save
        )
        super().__init__(**kwargs)

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return GfxReplayMeasure.cls_uuid

    def reset_metric(self, *args, **kwargs):
        self._gfx_replay_keyframes_string = None
        self.update_metric(*args, **kwargs)

    def update_metric(self, *args, task, **kwargs):
        is_timeout = False
        if "is_timeout" in kwargs:
            is_timeout = kwargs["is_timeout"]
        if (
            is_timeout or not task._is_episode_active
        ) and self._enable_gfx_replay_save:
            self._metric = (
                self._sim.gfx_replay_manager.write_saved_keyframes_to_string()
            )
        else:
            self._metric = ""

    def get_metric(self, force_get=False):
        if force_get and self._enable_gfx_replay_save:
            return (
                self._sim.gfx_replay_manager.write_saved_keyframes_to_string()
            )
        return super().get_metric()


@registry.register_measure
class ObjAtGoal(Measure):
    """
    Returns if the target object is at the goal (binary) for each of the target
    objects in the scene.
    """

    cls_uuid: str = "obj_at_goal"

    def __init__(self, *args, sim, config, task, **kwargs):
        self._config = config
        self._succ_thresh = self._config.succ_thresh
        super().__init__(*args, sim=sim, config=config, task=task, **kwargs)

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return ObjAtGoal.cls_uuid

    def reset_metric(self, *args, episode, task, observations, **kwargs):
        task.measurements.check_measure_dependencies(
            self.uuid,
            [
                ObjectToGoalDistance.cls_uuid,
            ],
        )
        self.update_metric(
            *args,
            episode=episode,
            task=task,
            observations=observations,
            **kwargs,
        )

    def update_metric(self, *args, episode, task, observations, **kwargs):
        obj_to_goal_dists = task.measurements.measures[
            ObjectToGoalDistance.cls_uuid
        ].get_metric()

        self._metric = {
            str(idx): dist < self._succ_thresh
            for idx, dist in obj_to_goal_dists.items()
        }


@registry.register_measure
class EndEffectorToGoalDistance(UsesArticulatedAgentInterface, Measure):
    cls_uuid: str = "ee_to_goal_distance"

    def __init__(self, sim, *args, **kwargs):
        self._sim = sim
        super().__init__(**kwargs)

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return EndEffectorToGoalDistance.cls_uuid

    def reset_metric(self, *args, episode, **kwargs):
        self.update_metric(*args, episode=episode, **kwargs)

    def update_metric(self, *args, observations, **kwargs):
        ee_pos = (
            self._sim.get_agent_data(self.agent_id)
            .articulated_agent.ee_transform()
            .translation
        )

        goals = self._sim.get_targets()[1]

        distances = np.linalg.norm(goals - ee_pos, ord=2, axis=-1)

        self._metric = {str(idx): dist for idx, dist in enumerate(distances)}


@registry.register_measure
class EndEffectorToObjectDistance(UsesArticulatedAgentInterface, Measure):
    """
    Gets the distance between the end-effector and all current target object COMs.
    """

    cls_uuid: str = "ee_to_object_distance"

    def __init__(self, sim, config, *args, **kwargs):
        self._sim = sim
        self._config = config
        super().__init__(**kwargs)

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return EndEffectorToObjectDistance.cls_uuid

    def reset_metric(self, *args, episode, **kwargs):
        self.update_metric(*args, episode=episode, **kwargs)

    def update_metric(self, *args, episode, **kwargs):
        ee_pos = (
            self._sim.get_agent_data(self.agent_id)
            .articulated_agent.ee_transform()
            .translation
        )

        idxs, _ = self._sim.get_targets()
        scene_pos = self._sim.get_scene_pos()
        target_pos = scene_pos[idxs]

        distances = np.linalg.norm(target_pos - ee_pos, ord=2, axis=-1)

        self._metric = {str(idx): dist for idx, dist in enumerate(distances)}


@registry.register_measure
class EndEffectorToRestDistance(Measure):
    """
    Distance between current end effector position and position where end effector rests within the robot body.
    """

    cls_uuid: str = "ee_to_rest_distance"

    def __init__(self, sim, config, *args, **kwargs):
        self._sim = sim
        self._config = config
        super().__init__(**kwargs)

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return EndEffectorToRestDistance.cls_uuid

    def reset_metric(self, *args, episode, **kwargs):
        self.update_metric(*args, episode=episode, **kwargs)

    def update_metric(self, *args, episode, task, observations, **kwargs):
        to_resting = observations[RelativeRestingPositionSensor.cls_uuid]
        rest_dist = np.linalg.norm(to_resting)

        self._metric = rest_dist


@registry.register_measure
class ReturnToRestDistance(UsesArticulatedAgentInterface, Measure):
    """
    Distance between end-effector and resting position if the articulated agent is holding the object.
    """

    cls_uuid: str = "return_to_rest_distance"

    def __init__(self, sim, config, *args, **kwargs):
        self._sim = sim
        self._config = config
        super().__init__(**kwargs)

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return ReturnToRestDistance.cls_uuid

    def reset_metric(self, *args, episode, **kwargs):
        self.update_metric(*args, episode=episode, **kwargs)

    def update_metric(self, *args, episode, task, observations, **kwargs):
        to_resting = observations[RelativeRestingPositionSensor.cls_uuid]
        rest_dist = np.linalg.norm(to_resting)

        snapped_id = self._sim.get_agent_data(self.agent_id).grasp_mgr.snap_idx
        abs_targ_obj_idx = self._sim.scene_obj_ids[task.abs_targ_idx]
        picked_correct = snapped_id == abs_targ_obj_idx

        if picked_correct:
            self._metric = rest_dist
        else:
            T_inv = (
                self._sim.get_agent_data(self.agent_id)
                .articulated_agent.ee_transform()
                .inverted()
            )
            idxs, _ = self._sim.get_targets()
            scene_pos = self._sim.get_scene_pos()
            pos = scene_pos[idxs][0]
            pos = T_inv.transform_point(pos)

            self._metric = np.linalg.norm(task.desired_resting - pos)


@registry.register_measure
class RobotCollisions(UsesArticulatedAgentInterface, Measure):
    """
    Returns a dictionary with the counts for different types of collisions.
    """

    cls_uuid: str = "robot_collisions"

    def __init__(self, *args, sim, config, task, **kwargs):
        self._sim = sim
        self._config = config
        self._task = task
        super().__init__(*args, sim=sim, config=config, task=task, **kwargs)

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return RobotCollisions.cls_uuid

    def reset_metric(self, *args, episode, task, observations, **kwargs):
        self._accum_coll_info = CollisionDetails()
        self.update_metric(
            *args,
            episode=episode,
            task=task,
            observations=observations,
            **kwargs,
        )

    def update_metric(self, *args, episode, task, observations, **kwargs):
        cur_coll_info = self._task.get_cur_collision_info(self.agent_id)
        self._accum_coll_info += cur_coll_info
        self._metric = {
            "total_collisions": self._accum_coll_info.total_collisions,
            "robot_obj_colls": self._accum_coll_info.robot_obj_colls,
            "robot_scene_colls": self._accum_coll_info.robot_scene_colls,
            "obj_scene_colls": self._accum_coll_info.obj_scene_colls,
        }


@registry.register_measure
class RobotForce(UsesArticulatedAgentInterface, Measure):
    """
    The amount of force in newton's accumulatively applied by the robot.
    """

    cls_uuid: str = "articulated_agent_force"

    def __init__(self, *args, sim, config, task, **kwargs):
        self._sim = sim
        self._config = config
        self._task = task
        self._count_obj_collisions = self._task._config.count_obj_collisions
        self._min_force = self._config.min_force
        super().__init__(*args, sim=sim, config=config, task=task, **kwargs)

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return RobotForce.cls_uuid

    def reset_metric(self, *args, episode, task, observations, **kwargs):
        self._accum_force = 0.0
        self._prev_force = None
        self._cur_force = None
        self._add_force = None
        self.update_metric(
            *args,
            episode=episode,
            task=task,
            observations=observations,
            **kwargs,
        )

    @property
    def add_force(self):
        return self._add_force

    def update_metric(self, *args, episode, task, observations, **kwargs):
        articulated_agent_force, _, overall_force = self._task.get_coll_forces(
            self.agent_id
        )
        if self._count_obj_collisions:
            self._cur_force = overall_force
        else:
            self._cur_force = articulated_agent_force

        if self._prev_force is not None:
            self._add_force = self._cur_force - self._prev_force
            if self._add_force > self._min_force:
                self._accum_force += self._add_force
                self._prev_force = self._cur_force
            elif self._add_force < 0.0:
                self._prev_force = self._cur_force
            else:
                self._add_force = 0.0
        else:
            self._prev_force = self._cur_force
            self._add_force = 0.0

        self._metric = {
            "accum": self._accum_force,
            "instant": self._cur_force,
        }


@registry.register_measure
class NumStepsMeasure(Measure):
    """
    The number of steps elapsed in the current episode.
    """

    cls_uuid: str = "num_steps"

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return NumStepsMeasure.cls_uuid

    def reset_metric(self, *args, episode, task, observations, **kwargs):
        self._metric = 0

    def update_metric(self, *args, episode, task, observations, **kwargs):
        self._metric += 1


@registry.register_measure
class ForceTerminate(Measure):
    """
    If the accumulated force throughout this episode exceeds the limit.
    """

    cls_uuid: str = "force_terminate"

    def __init__(self, *args, sim, config, task, **kwargs):
        self._sim = sim
        self._config = config
        self._max_accum_force = self._config.max_accum_force
        self._max_instant_force = self._config.max_instant_force
        self._task = task
        super().__init__(*args, sim=sim, config=config, task=task, **kwargs)

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return ForceTerminate.cls_uuid

    def reset_metric(self, *args, episode, task, observations, **kwargs):
        task.measurements.check_measure_dependencies(
            self.uuid,
            [
                RobotForce.cls_uuid,
            ],
        )

        self.update_metric(
            *args,
            episode=episode,
            task=task,
            observations=observations,
            **kwargs,
        )

    def update_metric(self, *args, episode, task, observations, **kwargs):
        force_info = task.measurements.measures[
            RobotForce.cls_uuid
        ].get_metric()
        accum_force = force_info["accum"]
        instant_force = force_info["instant"]
        if self._max_accum_force > 0 and accum_force > self._max_accum_force:
            rearrange_logger.debug(
                f"Force threshold={self._max_accum_force} exceeded with {accum_force}, ending episode"
            )
            self._task.should_end = True
            self._metric = True
        elif (
            self._max_instant_force > 0
            and instant_force > self._max_instant_force
        ):
            rearrange_logger.debug(
                f"Force instant threshold={self._max_instant_force} exceeded with {instant_force}, ending episode"
            )
            self._task.should_end = True
            self._metric = True
        else:
            self._metric = False


@registry.register_measure
class DidViolateHoldConstraintMeasure(UsesArticulatedAgentInterface, Measure):
    cls_uuid: str = "did_violate_hold_constraint"

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return DidViolateHoldConstraintMeasure.cls_uuid

    def __init__(self, *args, sim, **kwargs):
        self._sim = sim

        super().__init__(*args, sim=sim, **kwargs)

    def reset_metric(self, *args, episode, task, observations, **kwargs):
        self.update_metric(
            *args,
            episode=episode,
            task=task,
            observations=observations,
            **kwargs,
        )

    def update_metric(self, *args, **kwargs):
        self._metric = self._sim.get_agent_data(
            self.agent_id
        ).grasp_mgr.is_violating_hold_constraint()


class RearrangeReward(UsesArticulatedAgentInterface, Measure):
    """
    An abstract class defining some measures that are always a part of any
    reward function in the Habitat 2.0 tasks.
    """

    def __init__(self, *args, sim, config, task, **kwargs):
        self._sim = sim
        self._config = config
        self._task = task
        self._force_pen = self._config.force_pen
        self._max_force_pen = self._config.max_force_pen
        super().__init__(*args, sim=sim, config=config, task=task, **kwargs)

    def reset_metric(self, *args, episode, task, observations, **kwargs):
        task.measurements.check_measure_dependencies(
            self.uuid,
            [
                RobotForce.cls_uuid,
                ForceTerminate.cls_uuid,
            ],
        )

        self.update_metric(
            *args,
            episode=episode,
            task=task,
            observations=observations,
            **kwargs,
        )

    def update_metric(self, *args, episode, task, observations, **kwargs):
        reward = 0.0

        reward += self._get_coll_reward()

        if self._sim.get_agent_data(
            self.agent_id
        ).grasp_mgr.is_violating_hold_constraint():
            reward -= self._config.constraint_violate_pen

        force_terminate = task.measurements.measures[
            ForceTerminate.cls_uuid
        ].get_metric()
        if force_terminate:
            reward -= self._config.force_end_pen

        self._metric = reward

    def _get_coll_reward(self):
        reward = 0

        force_metric = self._task.measurements.measures[RobotForce.cls_uuid]
        # Penalize the force that was added to the accumulated force at the
        # last time step.
        reward -= max(
            0,  # This penalty is always positive
            min(
                self._force_pen * force_metric.add_force,
                self._max_force_pen,
            ),
        )
        return reward


@registry.register_measure
class DoesWantTerminate(Measure):
    """
    Returns 1 if the agent has called the stop action and 0 otherwise.
    """

    cls_uuid: str = "does_want_terminate"

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return DoesWantTerminate.cls_uuid

    def reset_metric(self, *args, **kwargs):
        self.update_metric(*args, **kwargs)

    def update_metric(self, *args, task, **kwargs):
        self._metric = task.actions["rearrange_stop"].does_want_terminate


@registry.register_measure
class BadCalledTerminate(Measure):
    """
    Returns 0 if the agent has called the stop action when the success
    condition is also met or not called the stop action when the success
    condition is not met. Returns 1 otherwise.
    """

    cls_uuid: str = "bad_called_terminate"

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return BadCalledTerminate.cls_uuid

    def __init__(self, config, task, *args, **kwargs):
        super().__init__(**kwargs)
        self._success_measure_name = task._config.success_measure
        self._config = config

    def reset_metric(self, *args, task, **kwargs):
        task.measurements.check_measure_dependencies(
            self.uuid,
            [DoesWantTerminate.cls_uuid, self._success_measure_name],
        )
        self.update_metric(*args, task=task, **kwargs)

    def update_metric(self, *args, task, **kwargs):
        does_action_want_stop = task.measurements.measures[
            DoesWantTerminate.cls_uuid
        ].get_metric()
        is_succ = task.measurements.measures[
            self._success_measure_name
        ].get_metric()

        self._metric = (not is_succ) and does_action_want_stop


@registry.register_sensor
class HasFinishedOracleNavSensor(UsesArticulatedAgentInterface, Sensor):
    """
    Returns 1 if the agent has finished the oracle nav action. Returns 0 otherwise.
    """

    cls_uuid: str = "has_finished_oracle_nav"

    def __init__(self, sim, config, *args, task, **kwargs):
        self._task = task
        self._sim = sim
        super().__init__(config=config)

    def _get_uuid(self, *args, **kwargs):
        return HasFinishedOracleNavSensor.cls_uuid

    def _get_sensor_type(self, *args, **kwargs):
        return SensorTypes.TENSOR

    def _get_observation_space(self, *args, config, **kwargs):
        return spaces.Box(shape=(1,), low=0, high=1, dtype=np.float32)

    def get_observation(self, observations, episode, *args, **kwargs):
        if self.agent_id is not None:
            use_k = f"agent_{self.agent_id}_oracle_nav_action"
            if (
                f"agent_{self.agent_id}_oracle_nav_with_backing_up_action"
                in self._task.actions
            ):
                use_k = (
                    f"agent_{self.agent_id}_oracle_nav_with_backing_up_action"
                )
        else:
            use_k = "oracle_nav_action"
            if "oracle_nav_with_backing_up_action" in self._task.actions:
                use_k = "oracle_nav_with_backing_up_action"

        nav_action = self._task.actions[use_k]

        return np.array(nav_action.skill_done, dtype=np.float32)[..., None]


@registry.register_measure
class ContactTestStats(Measure):
    """
    Did agent collide with objects?
    """

    cls_uuid: str = "contact_test_stats"

    def __init__(self, sim, config, *args, **kwargs):
        super().__init__(**kwargs)
        self._sim = sim
        self._config = config

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return ContactTestStats.cls_uuid

    def reset_metric(self, *args, task, **kwargs):
        self._contact_flag = []
        self._metric = 0

    def update_metric(self, *args, episode, task, observations, **kwargs):
        flag = self._sim.contact_test(
            self._sim.articulated_agent.get_robot_sim_id()
        )
        self._contact_flag.append(flag)
        self._metric = np.average(self._contact_flag)


@registry.register_sensor
class HumanoidDetectorSensor(UsesArticulatedAgentInterface, Sensor):
    def __init__(self, sim, config, *args, **kwargs):
        super().__init__(config=config)
        self._sim = sim
        self._human_id = config.human_id
        self._human_pixel_threshold = config.human_pixel_threshold

    def _get_uuid(self, *args, **kwargs):
        return "humanoid_detector_sensor"

    def _get_sensor_type(self, *args, **kwargs):
        return SensorTypes.TENSOR

    def _get_observation_space(self, *args, config, **kwargs):
        return spaces.Box(
            shape=(1,),
            low=np.finfo(np.float32).min,
            high=np.finfo(np.float32).max,
            dtype=np.float32,
        )

    def get_observation(self, observations, episode, *args, **kwargs):
        found_human = False

        if (
            np.sum(
                observations["agent_0_articulated_agent_arm_panoptic"]
                == self._human_id
            )
            > self._human_pixel_threshold
        ):
            found_human = True

        if found_human:
            return np.ones(1, dtype=np.float32)
        else:
            return np.zeros(1, dtype=np.float32)


@registry.register_measure
class RuntimePerfStats(Measure):
    cls_uuid: str = "habitat_perf"

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return RuntimePerfStats.cls_uuid

    def __init__(self, sim, config, *args, **kwargs):
        self._sim = sim
        self._sim.enable_perf_logging()
        self._disable_logging = config.disable_logging
        super().__init__()

    def reset_metric(self, *args, **kwargs):
        self._metric_queue = defaultdict(deque)
        self._metric = {}

    def update_metric(self, *args, task, **kwargs):
        for k, v in self._sim.get_runtime_perf_stats().items():
            self._metric_queue[k].append(v)
        if self._disable_logging:
            self._metric = {}
        else:
            self._metric = {
                k: np.mean(v) for k, v in self._metric_queue.items()
            }


@registry.register_measure
class SocialNavStats(UsesArticulatedAgentInterface, Measure):
    """
    The measure for social navigation
    """

    cls_uuid: str = "social_nav_stats"

    def __init__(self, sim, config, *args, **kwargs):
        super().__init__(**kwargs)
        self._sim = sim
        self._config = config
        self._check_human_in_frame = self._config.check_human_in_frame
        self._min_dis_human = self._config.min_dis_human
        self._max_dis_human = self._config.max_dis_human
        self._human_id = self._config.human_id
        self._human_detect_threshold = (
            self._config.human_detect_pixel_threshold
        )

        self._start_end_episode_distance = None
        self._min_start_end_episode_step = None
        self._agent_episode_distance = None
        self._has_found_human_step = 1500
        self._has_found_human_step_dis = 1500
        self._prev_pos = None
        self._prev_human_pos = None
        self._has_found_human = False
        self._has_found_human_dis = False
        self._found_human_times = 0
        self._found_human_times_dis = 0
        self._after_found_human_times = 0
        self._after_found_human_times_dis = 0
        self._dis = 0
        self._step = 0
        self._step_after_found = 1
        self._dis_after_found = 0
        self._update_human_pos_x = 0
        self._update_human_pos_y = 0
        self._update_human_pos_z = 0
        self._robot_init_pos = None
        self._robot_init_trans = None
        self._total_step = self._config.total_steps
        self.human_pos_list = []
        self.robot_pos_list = []
        self._first_debug = True
        self._enable_shortest_path_computation = (
            self._config.enable_shortest_path_computation
        )

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return SocialNavStats.cls_uuid

    def _compute_min_path_step(self):
        human_pos = np.array(
            self._sim.get_agent_data(1).articulated_agent.base_pos
        )
        dist_step = self._sim.geodesic_distance(
            self._robot_init_pos, human_pos
        ) / (10.0 / 120.0)

        if dist_step <= self._step:
            return self._step
        else:
            return float("inf")

    def reset_metric(self, *args, task, **kwargs):
        robot_pos = np.array(
            self._sim.get_agent_data(0).articulated_agent.base_pos
        )
        human_pos = np.array(
            self._sim.get_agent_data(1).articulated_agent.base_pos
        )
        self._start_end_episode_distance = np.linalg.norm(
            robot_pos - human_pos, ord=2, axis=-1
        )
        self._robot_init_pos = robot_pos
        self._robot_init_trans = mn.Matrix4(
            self._sim.get_agent_data(
                0
            ).articulated_agent.sim_obj.transformation
        )
        self._min_start_end_episode_step = float("inf")
        self._agent_episode_distance = 0.0
        self._prev_pos = robot_pos
        self._prev_human_pos = human_pos
        self._has_found_human = False
        self._has_found_human_dis = False
        self._has_found_human_step = 1500
        self._has_found_human_step_dis = 1500
        self._found_human_times = 0
        self._found_human_times_dis = 0
        self._after_found_human_times = 0
        self._after_found_human_times_dis = 0
        self._step = 0
        self._step_after_found = 1
        self._dis = 0
        self._dis_after_found = 0
        self.update_metric(*args, task=task, **kwargs)
        self.human_pos_list = []
        self.robot_pos_list = []
        self._first_debug = True

    def _check_human_dis(self, robot_pos, human_pos):
        # We use geo geodesic distance here
        dis = self._sim.geodesic_distance(robot_pos, human_pos)
        return dis >= self._min_dis_human and dis <= self._max_dis_human

    def _check_human_frame(self, obs):
        if not self._check_human_in_frame:
            return True

        panoptic = obs["agent_0_articulated_agent_arm_panoptic"]
        return (
            np.sum(panoptic == self._human_id) > self._human_detect_threshold
        )

    def _check_look_at_human(self, human_pos, robot_pos):
        vector_human_robot = human_pos - robot_pos
        vector_human_robot = vector_human_robot / np.linalg.norm(
            vector_human_robot
        )
        base_T = self._sim.get_agent_data(
            0
        ).articulated_agent.sim_obj.transformation
        forward_robot = base_T.transform_vector(mn.Vector3(1, 0, 0))
        facing = np.dot(forward_robot.normalized(), vector_human_robot) > 0.5
        return facing

    @property
    def update_human_pos(self):
        return [
            self._update_human_pos_x,
            self._update_human_pos_y,
            self._update_human_pos_z,
        ]

    @update_human_pos.setter
    def update_human_pos(self, val):
        if val is not None:
            self._update_human_pos_x = val[0]
            self._update_human_pos_y = val[1]
            self._update_human_pos_z = val[2]

    def update_metric(self, *args, episode, task, observations, **kwargs):
        # Get the agent locations
        robot_pos = np.array(
            self._sim.get_agent_data(0).articulated_agent.base_pos
        )
        human_pos = np.array(
            self._sim.get_agent_data(1).articulated_agent.base_pos
        )

        self.human_pos_list.append(human_pos)
        self.robot_pos_list.append(robot_pos)

        # Compute the distance based on the L2 norm
        dis = np.linalg.norm(robot_pos - human_pos, ord=2, axis=-1)
        # Add the current distance to compute average distance
        self._dis += dis

        # Increase the step counter
        self._step += 1

        # Check if human has been found
        found_human = False
        if self._check_human_dis(
            robot_pos, human_pos
        ) and self._check_look_at_human(human_pos, robot_pos):
            found_human = True
            self._has_found_human = True
            self._found_human_times += 1

        # Check if the human has been found based on one condition
        found_human_dis = False
        if self._check_human_dis(robot_pos, human_pos):
            found_human_dis = True
            self._has_found_human_dis = True
            self._found_human_times_dis += 1

        # We increase the travel distance if the robot has not yet found the human
        if not found_human and not self._has_found_human:
            self._agent_episode_distance += np.linalg.norm(
                self._prev_pos - robot_pos, ord=2, axis=-1
            )

        # Compute the metrics after finding the human
        if self._has_found_human:
            self._dis_after_found += dis
            self._after_found_human_times += found_human

        if self._has_found_human_dis:
            self._after_found_human_times_dis += found_human_dis

        # Record the step taken to find the human
        if self._has_found_human and self._has_found_human_step == 1500:
            self._has_found_human_step = self._step

        # Record the step taken to find the human based on distance condition
        if (
            self._has_found_human_dis
            and self._has_found_human_step_dis == 1500
        ):
            self._has_found_human_step_dis = self._step

        # Compute the minimum distance only when the minimum distance has not found yet
        if (
            self._min_start_end_episode_step == float("inf")
            and self._enable_shortest_path_computation
        ):
            robot_to_human_min_step = task.actions[
                "agent_1_oracle_nav_randcoord_action"
            ]._compute_robot_to_human_min_step(
                self._robot_init_trans, human_pos, self.human_pos_list
            )

            if robot_to_human_min_step <= self._step:
                robot_to_human_min_step = self._step
            else:
                robot_to_human_min_step = float("inf")

            # Update the minimum SPL
            self._min_start_end_episode_step = min(
                self._min_start_end_episode_step, robot_to_human_min_step
            )

        # Compute the SPL before finding the human

        try:
            first_found_spl = (
                self._has_found_human
                * self._start_end_episode_distance
                / max(
                    self._start_end_episode_distance,
                    self._agent_episode_distance,
                )
            )
            first_encounter_spl = (
                self._has_found_human
                * self._min_start_end_episode_step
                / max(
                    self._min_start_end_episode_step,
                    self._has_found_human_step,
                )
            )
            first_encounter_spl_dis = (
                self._has_found_human_dis
                * self._min_start_end_episode_step
                / max(
                    self._min_start_end_episode_step,
                    self._has_found_human_step_dis,
                )
            )
        except Exception:
            first_found_spl = 0.0
            first_encounter_spl = 0.0
            first_encounter_spl_dis = 0.0

        if np.isnan(first_found_spl):
            first_found_spl = 0.0
        if np.isnan(first_encounter_spl):
            first_encounter_spl = 0.0
        if np.isnan(first_encounter_spl_dis):
            first_encounter_spl_dis = 0.0

        human_rotate = 1
        if np.linalg.norm(self._prev_human_pos - human_pos) > 0.001:
            human_rotate = 0

        self._prev_pos = robot_pos
        self._prev_human_pos = human_pos

        self._metric = {
            "human_goal_x": self._update_human_pos_x,
            "human_goal_y": self._update_human_pos_y,
            "human_goal_z": self._update_human_pos_z,
            "human_rotate": human_rotate,
            "found_human": found_human,
            "dis": dis,
            "has_found_human": self._has_found_human,
            "found_human_rate_over_epi": self._found_human_times / self._step,
            "found_human_rate_after_found_over_epi": self._after_found_human_times
            / self._step_after_found,
            "avg_robot_to_human_dis_over_epi": self._dis / self._step,
            "avg_robot_to_human_after_found_dis_over_epi": self._dis_after_found
            / self._step_after_found,
            "first_found_spl": first_found_spl,
            # The ones we use to report in the paper
            "first_encounter_spl": first_encounter_spl,
            "frist_ecnounter_steps": self._has_found_human_step,
            "frist_ecnounter_steps_ratio": self._has_found_human_step
            / self._min_start_end_episode_step,
            "follow_human_steps_after_frist_encounter": self._after_found_human_times,
            "follow_human_steps_ratio_after_frist_encounter": self._after_found_human_times
            / (self._total_step - self._min_start_end_episode_step),
            # The ones we use to report in the paper only based on the distance condition
            "first_encounter_spl_dis": first_encounter_spl_dis,
            "frist_ecnounter_steps_dis": self._has_found_human_step_dis,
            "frist_ecnounter_steps_ratio_dis": self._has_found_human_step_dis
            / self._min_start_end_episode_step,
            "follow_human_steps_after_frist_encounter_dis": self._after_found_human_times_dis,
            "follow_human_steps_ratio_after_frist_encounter_dis": self._after_found_human_times_dis
            / (self._total_step - self._min_start_end_episode_step),
        }

        if self._has_found_human:
            self._step_after_found += 1
