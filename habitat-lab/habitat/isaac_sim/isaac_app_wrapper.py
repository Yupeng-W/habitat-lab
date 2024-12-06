# Copyright (c) Meta Platforms, Inc. and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import time

def do_isaacsim_imports():
    from omni.isaac.core import World
    from omni.isaac.core.objects import DynamicCuboid
    from omni.isaac.core.utils.stage import add_reference_to_stage
    from omni.isaac.core.utils.types import ArticulationAction
    from omni.isaac.core.robots import Robot
    from omni.isaac.core.prims.rigid_prim import RigidPrim
    from omni.isaac.core.prims.rigid_prim_view import RigidPrimView

    from pxr import UsdGeom, Sdf, Usd, UsdPhysics, PhysxSchema
    import omni.physx.scripts.utils as physxUtils

    # todo: explain this hack
    globals().update(locals())

class IsaacAppWrapper:
    def __init__(self, headless=True):
                
        self._headless = headless

        try:
            from isaacsim import SimulationApp
        except ImportError:
            raise ImportError(
                "Need to install Isaac Sim! See habitat-lab/habitat/isaac_sim/README.md."
            )

        if self._headless:
            experience_path = "habitat-lab/habitat/isaac_sim/_internal/isaac_sim_habitat_headless.kit"
        else: 
            experience_path = ""
        self._simulation_app = SimulationApp({"headless": self._headless}, experience_path)

        do_isaacsim_imports()

        # todo: change this so app works without internet
        # default_asset_root = carb.settings.get_settings().get("/persistent/isaac/asset_root/default")

        if self._headless:
            import carb
            val = carb.settings.get_settings().get("/app/extensions/fsWatcherEnabled")
            assert val == 0

        self._world = World()

        # sloppy: Initialize our scene here, just a ground plane.
        # todo: initialize a proper scene with objects based on the episode. But don't do this in this class.
        self._world.scene.add_default_ground_plane()
        # fancy_cube =  world.scene.add(
        #     DynamicCuboid(
        #         prim_path="/World/random_cube",
        #         name="fancy_cube",
        #         position=np.array([0, 0, 1.0]),
        #         scale=np.array([0.5015, 0.5015, 0.5015]),
        #         color=np.array([0, 0, 1.0]),
        #     ))

    # todo: get rid of this
    def add_kitchen_set(self, env_id, origin):
        print(f"Adding Kitchen_Set for {env_id}...")
        kitchen_prim_path = f"/World/{env_id}/Kitchen_Set"
        asset_path = "/home/eric/Downloads/Kitchen_set/Kitchen_set.usd"
        add_reference_to_stage(usd_path=asset_path, prim_path=kitchen_prim_path)
        prim = self._world.stage.GetPrimAtPath(kitchen_prim_path)
        xform = UsdGeom.Xformable(prim)
        scale_factor = 0.01
        xform.AddScaleOp().Set((scale_factor, scale_factor, scale_factor))
        xform.AddTranslateOp().Set((origin[0] / scale_factor, origin[1] / scale_factor, origin[2] / scale_factor))
        add_convex_hull_collision_for_meshes(self._world.stage, kitchen_prim_path)
        print("Done adding Kitchen_Set")    
        
    @property
    def world(self):
        return self._world

    def step(self):
        # todo: think about dt here
        if self._headless:
            self._world.step(render=False, step_sim=True)
        else:
            # todo: not sure about this
            self._simulation_app.update()
            # sleep a bit to avoid 100% CPU usage and thus keep the OS windowing environment responsive
            time.sleep(0.01)

    # probably don't ever need to close simulation_app
    # def close(self):
    #     self._simulation_app.close() # close Isaac Sim