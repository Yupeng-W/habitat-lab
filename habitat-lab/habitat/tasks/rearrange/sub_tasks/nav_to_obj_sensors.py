#!/usr/bin/env python3

# Copyright (c) Meta Platforms, Inc. and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import magnum as mn
import numpy as np
from gym import spaces

import habitat_sim
from habitat.core.embodied_task import Measure
from habitat.core.registry import registry
from habitat.core.simulator import Sensor, SensorTypes
from habitat.tasks.rearrange.rearrange_sensors import (
    DoesWantTerminate,
    RearrangeReward,
)
from habitat.tasks.rearrange.utils import UsesArticulatedAgentInterface
from habitat.tasks.utils import cartesian_to_polar

BASE_ACTION_NAME = "base_velocity"


@registry.register_sensor
class NavGoalPointGoalSensor(UsesArticulatedAgentInterface, Sensor):
    """
    GPS and compass sensor relative to the starting object position or goal
    position.
    """

    cls_uuid: str = "goal_to_agent_gps_compass"

    def __init__(self, *args, sim, task, **kwargs):
        self._task = task
        self._sim = sim
        self._goal_is_human = True
        super().__init__(*args, task=task, **kwargs)

    def _get_uuid(self, *args, **kwargs):
        return NavGoalPointGoalSensor.cls_uuid

    def _get_sensor_type(self, *args, **kwargs):
        return SensorTypes.TENSOR

    def _get_observation_space(self, *args, config, **kwargs):
        return spaces.Box(
            shape=(2,),
            low=np.finfo(np.float32).min,
            high=np.finfo(np.float32).max,
            dtype=np.float32,
        )

    def get_observation(self, task, *args, **kwargs):
        articulated_agent_T = self._sim.get_agent_data(
            self.agent_id
        ).articulated_agent.base_transformation

        if self._goal_is_human:
            human_pos = self._sim.get_agent_data(1).articulated_agent.base_pos
            task.nav_goal_pos = np.array(human_pos)

        dir_vector = articulated_agent_T.inverted().transform_point(
            task.nav_goal_pos
        )
        rho, phi = cartesian_to_polar(dir_vector[0], dir_vector[1])

        return np.array([rho, -phi], dtype=np.float32)


@registry.register_sensor
class OracleNavigationActionSensor(Sensor):
    cls_uuid: str = "oracle_nav_actions"

    def __init__(self, sim, config, *args, **kwargs):
        super().__init__(config=config)
        self._sim = sim

    def _get_uuid(self, *args, **kwargs):
        return OracleNavigationActionSensor.cls_uuid

    def _get_sensor_type(self, *args, **kwargs):
        return SensorTypes.TENSOR

    def _get_observation_space(self, *args, config, **kwargs):
        return spaces.Box(
            shape=(3,),
            low=np.finfo(np.float32).min,
            high=np.finfo(np.float32).max,
            dtype=np.float32,
        )

    def _path_to_point(self, point):
        agent_pos = self._sim.articulated_agent.base_pos

        path = habitat_sim.ShortestPath()
        path.requested_start = agent_pos
        path.requested_end = point
        found_path = self._sim.pathfinder.find_path(path)
        if not found_path:
            return [agent_pos, point]
        return path.points

    def get_observation(self, task, *args, **kwargs):
        path = self._path_to_point(task.nav_target_pos)
        return path[1]


@registry.register_measure
class NavToObjReward(RearrangeReward):
    cls_uuid: str = "nav_to_obj_reward"

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return NavToObjReward.cls_uuid

    def reset_metric(self, *args, episode, task, observations, **kwargs):
        task.measurements.check_measure_dependencies(
            self.uuid,
            [
                NavToObjSuccess.cls_uuid,
                DistToGoal.cls_uuid,
                RotDistToGoal.cls_uuid,
            ],
        )
        self._cur_angle_dist = -1.0
        self._prev_dist = -1.0
        super().reset_metric(
            *args,
            episode=episode,
            task=task,
            observations=observations,
            **kwargs,
        )

    def update_metric(self, *args, episode, task, observations, **kwargs):
        reward = 0.0
        cur_dist = task.measurements.measures[DistToGoal.cls_uuid].get_metric()
        if self._prev_dist < 0.0:
            dist_diff = 0.0
        else:
            dist_diff = self._prev_dist - cur_dist

        reward += self._config.dist_reward * dist_diff
        self._prev_dist = cur_dist

        if (
            self._config.should_reward_turn
            and cur_dist < self._config.turn_reward_dist
        ):
            angle_dist = task.measurements.measures[
                RotDistToGoal.cls_uuid
            ].get_metric()

            if self._cur_angle_dist < 0:
                angle_diff = 0.0
            else:
                angle_diff = self._cur_angle_dist - angle_dist

            reward += self._config.angle_dist_reward * angle_diff
            self._cur_angle_dist = angle_dist

        self._metric = reward


@registry.register_measure
class DistToGoal(Measure):
    cls_uuid: str = "dist_to_goal"

    def __init__(self, *args, sim, config, task, **kwargs):
        self._config = config
        self._sim = sim
        self._prev_dist = None
        self._use_geo_distance = config.use_geo_distance
        super().__init__(*args, sim=sim, config=config, task=task, **kwargs)

    def reset_metric(self, *args, episode, task, observations, **kwargs):
        self._prev_dist = self._get_cur_geo_dist(task)
        self.update_metric(
            *args,
            episode=episode,
            task=task,
            observations=observations,
            **kwargs,
        )

    def _get_cur_geo_dist(self, task):
        position_robot = np.array(
            self._sim.get_agent_data(0).articulated_agent.base_pos
        )

        if self._use_geo_distance:
            path = habitat_sim.ShortestPath()
            path.requested_start = np.array(position_robot)
            path.requested_end = task.nav_goal_pos
            found_path = self._sim.pathfinder.find_path(path)

        if not self._use_geo_distance or not found_path:
            return np.linalg.norm(
                np.array(
                    self._sim.get_agent_data(0).articulated_agent.base_pos
                )[[0, 2]]
                - task.nav_goal_pos[[0, 2]]
            )
        else:
            position_robot = np.array(
                self._sim.get_agent_data(0).articulated_agent.base_pos
            )
            return self._sim.geodesic_distance(
                position_robot, task.nav_goal_pos
            )

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return DistToGoal.cls_uuid

    def update_metric(self, *args, episode, task, observations, **kwargs):
        self._metric = self._get_cur_geo_dist(task)


@registry.register_measure
class RotDistToGoal(Measure):
    cls_uuid: str = "rot_dist_to_goal"

    def __init__(self, *args, sim, **kwargs):
        self._sim = sim
        super().__init__(*args, sim=sim, **kwargs)

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return RotDistToGoal.cls_uuid

    def reset_metric(self, *args, **kwargs):
        self.update_metric(
            *args,
            **kwargs,
        )

    def update_metric(self, *args, episode, task, observations, **kwargs):
        targ = task.nav_goal_pos
        # Get the agent
        robot = self._sim.articulated_agent
        # Get the base transformation
        T = robot.base_transformation
        # Do transformation
        pos = T.inverted().transform_point(targ)
        # Project to 2D plane (x,y,z=0)
        pos[2] = 0.0
        # Unit vector of the pos
        pos = pos.normalized()
        # Define the coordinate of the robot
        pos_robot = np.array([1.0, 0.0, 0.0])
        # Get the angle
        angle = np.arccos(np.dot(pos, pos_robot))
        self._metric = np.abs(float(angle))


@registry.register_measure
class NavToPosSucc(Measure):
    cls_uuid: str = "nav_to_pos_success"

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return NavToPosSucc.cls_uuid

    def __init__(self, *args, config, **kwargs):
        self._config = config
        super().__init__(*args, config=config, **kwargs)

    def reset_metric(self, *args, task, **kwargs):
        task.measurements.check_measure_dependencies(
            self.uuid,
            [DistToGoal.cls_uuid],
        )
        self.update_metric(*args, task=task, **kwargs)

    def update_metric(self, *args, episode, task, observations, **kwargs):
        dist = task.measurements.measures[DistToGoal.cls_uuid].get_metric()
        self._metric = dist < self._config.success_distance


@registry.register_measure
class NavToObjSuccess(Measure):
    cls_uuid: str = "nav_to_obj_success"

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return NavToObjSuccess.cls_uuid

    def reset_metric(self, *args, task, **kwargs):
        task.measurements.check_measure_dependencies(
            self.uuid,
            [NavToPosSucc.cls_uuid, RotDistToGoal.cls_uuid],
        )
        self.update_metric(*args, task=task, **kwargs)

    def __init__(self, *args, config, **kwargs):
        self._config = config
        super().__init__(*args, config=config, **kwargs)

    def update_metric(self, *args, episode, task, observations, **kwargs):
        angle_dist = task.measurements.measures[
            RotDistToGoal.cls_uuid
        ].get_metric()

        nav_pos_succ = task.measurements.measures[
            NavToPosSucc.cls_uuid
        ].get_metric()

        called_stop = task.measurements.measures[
            DoesWantTerminate.cls_uuid
        ].get_metric()

        if self._config.must_look_at_targ:
            self._metric = (
                nav_pos_succ and angle_dist < self._config.success_angle_dist
            )
        else:
            self._metric = nav_pos_succ

        if self._config.must_call_stop:
            if called_stop:
                task.should_end = True
            else:
                self._metric = False


@registry.register_measure
class SocialNavSeekSuccess(Measure):
    cls_uuid: str = "nav_seek_success"

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return SocialNavSeekSuccess.cls_uuid

    def reset_metric(self, *args, task, **kwargs):
        task.measurements.check_measure_dependencies(
            self.uuid,
            [NavToPosSucc.cls_uuid, RotDistToGoal.cls_uuid],
        )
        self._following_step = 0
        self.update_metric(*args, task=task, **kwargs)

    def __init__(self, *args, config, sim, **kwargs):
        self._config = config
        self._sim = sim

        super().__init__(*args, config=config, **kwargs)
        self._following_step = 0
        self._following_step_succ_threshold = (
            config.following_step_succ_threshold
        )  # prev: 300
        self._safe_dis_min = config.safe_dis_min
        self._safe_dis_max = config.safe_dis_max
        self._use_geo_distance = config.use_geo_distance
        self._need_to_face_human = config.need_to_face_human
        self._facing_threshold = config.facing_threshold

    def update_metric(self, *args, episode, task, observations, **kwargs):
        angle_dist = task.measurements.measures[
            RotDistToGoal.cls_uuid
        ].get_metric()

        position_human = observations["agent_1_localization_sensor"][:3]
        position_robot = observations["agent_0_localization_sensor"][:3]

        if self._use_geo_distance:
            dist = self._sim.geodesic_distance(position_robot, position_human)
        else:
            dist = task.measurements.measures[DistToGoal.cls_uuid].get_metric()

        # for computing facing to human
        vector_human_robot = position_human - position_robot
        vector_human_robot = vector_human_robot / np.linalg.norm(
            vector_human_robot
        )
        base_T = self._sim.get_agent_data(
            0
        ).articulated_agent.base_transformation
        forward_robot = base_T.transform_vector(mn.Vector3(1, 0, 0))
        facing = (
            np.dot(forward_robot.normalized(), vector_human_robot)
            > self._facing_threshold
        )

        if (
            dist >= self._safe_dis_min
            and dist < self._safe_dis_max
            and self._need_to_face_human
            and facing
        ):
            self._following_step += 1

        nav_pos_succ = False
        if self._following_step >= self._following_step_succ_threshold:
            nav_pos_succ = True

        called_stop = task.measurements.measures[
            DoesWantTerminate.cls_uuid
        ].get_metric()

        if self._config.must_look_at_targ:
            self._metric = (
                nav_pos_succ and angle_dist < self._config.success_angle_dist
            )
        else:
            self._metric = nav_pos_succ

        if self._config.must_call_stop:
            if called_stop:
                task.should_end = True
            else:
                self._metric = False
