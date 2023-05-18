#!/usr/bin/env python3

# Copyright (c) Meta Platforms, Inc. and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.


import numpy as np

from habitat.core.embodied_task import Measure
from habitat.core.registry import registry
from habitat.tasks.rearrange.sub_tasks.cat_nav_to_obj_sensors import (
    OvmmRotDistToGoal,
)
from habitat.tasks.rearrange.sub_tasks.nav_to_obj_sensors import (
    DistToGoal,
    NavToObjSuccess,
    NavToPosSucc,
)


# Sensors for measuring success to pick goals
@registry.register_measure
class OvmmDistToPickGoal(DistToGoal):
    """Distance to the closest viewpoint of a candidate pick object"""

    cls_uuid: str = "ovmm_dist_to_pick_goal"

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return OvmmDistToPickGoal.cls_uuid

    def _get_goals(self, task, episode):
        return np.stack(
            [
                view_point.agent_state.position
                for goal in episode.candidate_objects
                for view_point in goal.view_points
            ],
            axis=0,
        )


@registry.register_measure
class OvmmRotDistToPickGoal(OvmmRotDistToGoal, Measure):
    """Angle between agent's forward vector and the vector from agent's position to the closest candidate pick object"""

    cls_uuid: str = "ovmm_rot_dist_to_pick_goal"

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return OvmmRotDistToPickGoal.cls_uuid

    def __init__(self, *args, sim, config, dataset, task, **kwargs):
        super().__init__(
            *args, sim=sim, config=config, dataset=dataset, task=task, **kwargs
        )
        self._is_nav_to_obj = True


@registry.register_measure
class OvmmNavToPickSucc(NavToPosSucc):
    """Whether the agent has navigated within `success_distance` of the closest viewpoint of a candidate pick object"""

    cls_uuid: str = "ovmm_nav_to_pick_succ"

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return OvmmNavToPickSucc.cls_uuid

    @property
    def _dist_to_goal_cls_uuid(self):
        return OvmmDistToPickGoal.cls_uuid


@registry.register_measure
class OvmmNavOrientToPickSucc(NavToObjSuccess):
    """Whether the agent has navigated within `success_distance` of the closest viewpoint of a candidate pick object and oriented itself within `success_angle` of the object"""

    cls_uuid: str = "ovmm_nav_orient_to_pick_succ"

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return OvmmNavOrientToPickSucc.cls_uuid

    @property
    def _nav_to_pos_succ_cls_uuid(self):
        return OvmmNavToPickSucc.cls_uuid

    @property
    def _rot_dist_to_goal_cls_uuid(self):
        return OvmmRotDistToPickGoal.cls_uuid


# Sensors for measuring success to place goals
@registry.register_measure
class OvmmDistToPlaceGoal(DistToGoal):
    """Distance to the closest viewpoint of a candidate place receptacle"""

    cls_uuid: str = "ovmm_dist_to_place_goal"

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return OvmmDistToPlaceGoal.cls_uuid

    def _get_goals(self, task, episode):
        return np.stack(
            [
                view_point.agent_state.position
                for goal in episode.candidate_goal_receps
                for view_point in goal.view_points
            ],
            axis=0,
        )


@registry.register_measure
class OvmmRotDistToPlaceGoal(OvmmRotDistToGoal):
    """Angle between agent's forward vector and the vector from agent's position to the center of the closest candidate place receptacle"""

    cls_uuid: str = "ovmm_rot_dist_to_place_goal"

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return OvmmRotDistToPlaceGoal.cls_uuid

    def __init__(self, *args, sim, config, dataset, task, **kwargs):
        super().__init__(
            *args, sim=sim, config=config, dataset=dataset, task=task, **kwargs
        )
        self._is_nav_to_obj = False


@registry.register_measure
class OvmmNavToPlaceSucc(NavToPosSucc):
    """Whether the agent has navigated within `success_distance` of the center of the closest candidate place receptacle"""

    cls_uuid: str = "ovmm_nav_to_place_succ"

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return OvmmNavToPlaceSucc.cls_uuid

    @property
    def _dist_to_goal_cls_uuid(self):
        return OvmmDistToPlaceGoal.cls_uuid


@registry.register_measure
class OvmmNavOrientToPlaceSucc(NavToObjSuccess):
    """Whether the agent has navigated within `success_distance` of the center of the closest candidate place receptacle and oriented itself within `success_angle` of the receptacle"""

    cls_uuid: str = "ovmm_nav_orient_to_place_succ"

    @staticmethod
    def _get_uuid(*args, **kwargs):
        return OvmmNavOrientToPlaceSucc.cls_uuid

    @property
    def _nav_to_pos_succ_cls_uuid(self):
        return OvmmNavToPlaceSucc.cls_uuid

    @property
    def _rot_dist_to_goal_cls_uuid(self):
        return OvmmRotDistToPlaceGoal.cls_uuid
