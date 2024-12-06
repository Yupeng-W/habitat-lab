# Copyright (c) Meta Platforms, Inc. and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from typing import Dict, List, Optional, Set

import attr
import magnum as mn
import numpy as np

from habitat.articulated_agents.mobile_manipulator import MobileManipulatorParams

from habitat.isaac_sim._internal.robot_wrapper import RobotWrapper

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from omni.isaac.core import World

class IsaacMobileManipulator:
    """Robot with a controllable base and arm."""

    def __init__(
        self,
        params: MobileManipulatorParams,
        agent_cfg,
        isaac_world: World,  # todo: do IsaacGlobals, IsaacServices, or IsaacWrapper intead of World here
        # limit_robo_joints: bool = True,
        # fixed_base: bool = True,
        # maintain_link_order: bool = False,
        # base_type="mobile",
    ):
        self._world = isaac_world
        self._robot_wrapper = RobotWrapper(world=self._world, instance_id=0)


    def reconfigure(self) -> None:
        """Instantiates the robot the scene. Loads the URDF, sets initial state of parameters, joints, motors, etc..."""
        # todo
        pass

    def update(self) -> None:
        """Updates the camera transformations and performs necessary checks on
        joint limits and sleep states.
        """
        # todo
        pass

    def reset(self) -> None:
        """Reset the joints on the existing robot.
        NOTE: only arm and gripper joint motors (not gains) are reset by default, derived class should handle any other changes.
        """
        # todo
        pass
