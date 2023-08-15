#!/usr/bin/env python3

# Copyright (c) Meta Platforms, Inc. and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.


import numpy as np

from habitat.core.embodied_task import Measure
from habitat.core.registry import registry
from habitat.tasks.rearrange.rearrange_sensors import (
    EndEffectorToGoalDistance,
    EndEffectorToRestDistance,
    ForceTerminate,
    JointToRestDistance,
    ObjAtGoal,
    ObjectToGoalDistance,
    RearrangeReward,
    RobotForce,
)
from habitat.tasks.rearrange.utils import rearrange_logger


@registry.register_measure
class PlaceReward(RearrangeReward):
    cls_uuid: str = "place_reward"

    def __init__(self, *args, sim, config, task, **kwargs):
        self._prev_dist = -1.0
        self._prev_dropped = False
        self._metric = None
        self._last_pos = None
        self._last_rot = None

        super().__init__(*args, sim=sim, config=config, task=task, **kwargs)

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return PlaceReward.cls_uuid

    def reset_metric(self, *args, episode, task, observations, **kwargs):
        task.measurements.check_measure_dependencies(
            self.uuid,
            [
                ObjectToGoalDistance.cls_uuid,
                ObjAtGoal.cls_uuid,
                EndEffectorToRestDistance.cls_uuid,
                RobotForce.cls_uuid,
                ForceTerminate.cls_uuid,
            ],
        )
        self._prev_dist = -1.0
        self._prev_dropped = not self._sim.grasp_mgr.is_grasped

        super().reset_metric(
            *args,
            episode=episode,
            task=task,
            observations=observations,
            **kwargs
        )

    def update_metric(self, *args, episode, task, observations, **kwargs):
        super().update_metric(
            *args,
            episode=episode,
            task=task,
            observations=observations,
            **kwargs
        )
        reward = self._metric

        # Penalize the base movement
        # Check if the robot moves or not
        move = 0.0
        if self._last_pos is not None:
            cur_pos = np.array(self._sim.articulated_agent.base_pos)
            last_rot = float(self._sim.articulated_agent.base_rot)
            if (
                np.linalg.norm(self._last_pos - cur_pos) >= 0.01
                or abs(self._last_rot - last_rot) >= 0.01
            ):
                move = 1.0

        # Get the control inputs
        lin_vel = np.array(
            self._task.actions["base_velocity"].base_vel_ctrl.linear_velocity
        )
        lin_vel_norm = np.linalg.norm(lin_vel)

        ang_vel = np.array(
            self._task.actions["base_velocity"].base_vel_ctrl.angular_velocity
        )
        ang_vel_norm = np.linalg.norm(ang_vel)

        if self._config.enable_vel_penality != -1:
            self._metric -= (
                move
                * self._config.enable_vel_penality
                * (lin_vel_norm**2 + ang_vel_norm**2)
            )

        # Update the last location of the robot
        self._last_pos = np.array(self._sim.articulated_agent.base_pos)
        self._last_rot = float(self._sim.articulated_agent.base_rot)

        ee_to_goal_dist = task.measurements.measures[
            EndEffectorToGoalDistance.cls_uuid
        ].get_metric()
        obj_to_goal_dist = task.measurements.measures[
            ObjectToGoalDistance.cls_uuid
        ].get_metric()
        ee_to_rest_distance = task.measurements.measures[
            EndEffectorToRestDistance.cls_uuid
        ].get_metric()
        obj_at_goal = task.measurements.measures[
            ObjAtGoal.cls_uuid
        ].get_metric()[str(task.targ_idx)]

        snapped_id = self._sim.grasp_mgr.snap_idx
        cur_picked = snapped_id is not None

        if (not obj_at_goal) or cur_picked:
            if self._config.use_ee_dist:
                dist_to_goal = ee_to_goal_dist[str(task.targ_idx)]
            else:
                dist_to_goal = obj_to_goal_dist[str(task.targ_idx)]
            min_dist = self._config.min_dist_to_goal
        else:
            dist_to_goal = ee_to_rest_distance
            min_dist = 0.0

        if (not self._prev_dropped) and (not cur_picked):
            self._prev_dropped = True
            if obj_at_goal:
                reward += self._config.place_reward
                # If we just transitioned to the next stage our current
                # distance is stale.
                self._prev_dist = -1
            else:
                # Dropped at wrong location
                reward -= self._config.drop_pen
                if self._config.wrong_drop_should_end:
                    rearrange_logger.debug(
                        "Dropped to wrong place, ending episode."
                    )
                    self._task.should_end = True
                    self._metric = reward
                    return

        if dist_to_goal >= min_dist:
            if self._config.use_diff:
                if self._prev_dist < 0:
                    dist_diff = 0.0
                else:
                    dist_diff = self._prev_dist - dist_to_goal

                # Filter out the small fluctuations
                dist_diff = round(dist_diff, 3)
                reward += self._config.dist_reward * dist_diff
            else:
                reward -= self._config.dist_reward * dist_to_goal
        self._prev_dist = dist_to_goal

        self._metric = reward


@registry.register_measure
class PlaceSuccess(Measure):
    cls_uuid: str = "place_success"

    def __init__(self, sim, config, *args, **kwargs):
        self._config = config
        self._sim = sim
        super().__init__(**kwargs)

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return PlaceSuccess.cls_uuid

    def reset_metric(self, *args, episode, task, observations, **kwargs):
        task.measurements.check_measure_dependencies(
            self.uuid,
            [
                ObjAtGoal.cls_uuid,
                EndEffectorToRestDistance.cls_uuid,
            ],
        )
        self.update_metric(
            *args,
            episode=episode,
            task=task,
            observations=observations,
            **kwargs
        )

    def update_metric(self, *args, episode, task, observations, **kwargs):
        is_obj_at_goal = task.measurements.measures[
            ObjAtGoal.cls_uuid
        ].get_metric()[str(task.targ_idx)]
        is_holding = self._sim.grasp_mgr.is_grasped

        ee_to_rest_distance = task.measurements.measures[
            EndEffectorToRestDistance.cls_uuid
        ].get_metric()

        self._metric = (
            not is_holding
            and is_obj_at_goal
            and ee_to_rest_distance < self._config.ee_resting_success_threshold
        )


@registry.register_measure
class PlaceSuccessJoint(Measure):
    cls_uuid: str = "place_success_joint"

    def __init__(self, sim, config, *args, **kwargs):
        self._config = config
        self._sim = sim
        super().__init__(**kwargs)

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return PlaceSuccessJoint.cls_uuid

    def reset_metric(self, *args, episode, task, observations, **kwargs):
        task.measurements.check_measure_dependencies(
            self.uuid,
            [
                ObjAtGoal.cls_uuid,
                EndEffectorToRestDistance.cls_uuid,
            ],
        )
        self.update_metric(
            *args,
            episode=episode,
            task=task,
            observations=observations,
            **kwargs
        )

    def update_metric(self, *args, episode, task, observations, **kwargs):
        is_obj_at_goal = task.measurements.measures[
            ObjAtGoal.cls_uuid
        ].get_metric()[str(task.targ_idx)]
        is_holding = self._sim.grasp_mgr.is_grasped

        joint_to_rest_distance = task.measurements.measures[
            JointToRestDistance.cls_uuid
        ].get_metric()

        self._metric = (
            not is_holding
            and is_obj_at_goal
            and joint_to_rest_distance
            < self._config.joint_resting_success_threshold
        )
