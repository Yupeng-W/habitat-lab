import itertools
from collections import Counter
from enum import Enum, auto
from typing import List

import magnum as mn
import numpy as np

import habitat_sim
from habitat.core.simulator import AgentState
from habitat.datasets.rearrange.geometry_utils import direction_to_quaternion
from habitat.datasets.rearrange.viz_utils import (
    save_topdown_map,
    save_viewpoint_frame,
)
from habitat.tasks.nav.object_nav_task import ObjectViewLocation
from habitat.tasks.rearrange.utils import get_aabb
from habitat.tasks.utils import compute_pixel_coverage
from habitat_sim.utils.common import quat_to_coeffs

ISLAND_RADIUS_LIMIT = 3.5


class ViewpointType(Enum):
    not_on_active_island = auto()
    too_far = auto()
    down_unnavigable = auto()
    outdoor_viewpoint = auto()
    low_visibility = auto()
    good = auto()


def populate_semantic_graph(sim):
    rom = sim.get_rigid_object_manager()
    for handle in rom.get_object_handles():
        obj = rom.get_object_by_handle(handle)
        for node in obj.visual_scene_nodes:
            node.semantic_id = obj.object_id + 1


def generate_viewpoints(
    sim: habitat_sim.Simulator,
    obj,
    object_transform: mn.Matrix4 = None,
    debug_viz: bool = False,
) -> List[ObjectViewLocation]:
    """Generates a list of viewpoints for an object.
    A viewpoint is a 3D position and rotation from where the agent
    can see the object. The viewpoints are generated by sampling
    points on a grid around the object and then checking if the
    agent can see the object from each point using its semantic
    sensor."""
    assert obj is not None

    cached_obj_transform = obj.transformation
    if object_transform:
        obj.transformation = object_transform

    object_id = obj.object_id
    object_aabb = get_aabb(object_id, sim, transformed=True)
    object_position = object_aabb.center()

    center = np.array(obj.translation)
    sizes = np.array(obj.root_scene_node.cumulative_bb.size())
    rotation = obj.rotation
    object_obb = habitat_sim.geo.OBB(center, sizes, rotation)

    eps = 1e-5

    object_nodes = obj.visual_scene_nodes
    assert all(
        node.semantic_id == object_id + 1 for node in object_nodes
    ), "Semantic IDs are not the right values. Did you populate the semantic graph?"
    semantic_id = object_nodes[0].semantic_id

    object_nodes = obj.visual_scene_nodes
    assert all(
        node.semantic_id == object_id + 1 for node in object_nodes
    ), "Semantic IDs are not the right values. Did you populate the semantic graph?"
    semantic_id = object_nodes[0].semantic_id

    max_distance = 1.0
    cell_size = 0.3 / 2.0
    x_len, _, z_len = object_aabb.size() / 2.0 + mn.Vector3(max_distance)
    x_bxp = np.arange(-x_len, x_len + eps, step=cell_size) + object_position[0]
    z_bxp = np.arange(-z_len, z_len + eps, step=cell_size) + object_position[2]
    candidate_poses = [
        np.array([x, object_position[1], z])
        for x, z in itertools.product(x_bxp, z_bxp)
    ]

    def down_is_navigable(pt, search_dist=2.0):
        pf = sim.pathfinder
        delta_y = 0.05
        max_steps = int(search_dist / delta_y)
        step = 0
        is_navigable = pf.is_navigable(pt, 2)
        while not is_navigable:
            pt[1] -= delta_y
            is_navigable = pf.is_navigable(pt)
            step += 1
            if step == max_steps:
                return False
        return True

    def _get_iou(x, y, z):
        pt = np.array([x, y, z])
        pf = sim.pathfinder
        pt = np.array(
            pf.snap_point(
                pt,
                island_index=sim.navmesh_classification_results[
                    "active_island"
                ],
            )
        )
        if np.isnan(pt).any():
            return -1, pt, None, ViewpointType.not_on_active_island

        if not object_obb.distance(pt) <= max_distance:
            return -1, pt, None, ViewpointType.too_far

        if not down_is_navigable(pt):
            return -1, pt, None, ViewpointType.down_unnavigable

        pt[1] += pf.nav_mesh_settings.agent_height

        goal_direction = object_position - pt
        goal_direction[1] = 0

        q = direction_to_quaternion(goal_direction)

        agent = sim.get_agent(0)
        agent_state = agent.get_state()
        agent_state.position = pt
        agent_state.rotation = q
        agent.set_state(agent_state)

        cov = 0
        for act_idx, act in enumerate(
            [
                "look_down",
                "look_up",
                "look_up",
            ]
        ):
            agent.act(act)
            obs = sim.get_sensor_observations(0)
            cov += compute_pixel_coverage(obs["semantic"], semantic_id)

            if debug_viz:
                save_viewpoint_frame(obs, obj.handle, semantic_id, act_idx)

        pt[1] -= pf.nav_mesh_settings.agent_height

        keep_thresh = 0.001
        if cov < keep_thresh:
            return -1, pt, None, ViewpointType.low_visibility

        return cov, pt, q, ViewpointType.good

    candidate_poses_ious_orig = [_get_iou(*pos) for pos in candidate_poses]
    poses_type_counter: Counter = Counter()
    for p in candidate_poses_ious_orig:
        poses_type_counter[p[-1]] += 1
    candidate_poses_ious = [p for p in candidate_poses_ious_orig if p[0] > 0]

    view_locations = [
        ObjectViewLocation(
            AgentState(pt.tolist(), quat_to_coeffs(q).tolist()), iou
        )
        for iou, pt, q, _ in candidate_poses_ious
    ]
    view_locations = sorted(view_locations, reverse=True, key=lambda v: v.iou)

    if debug_viz and len(view_locations) == 0:
        save_topdown_map(
            sim,
            view_locations,
            candidate_poses_ious_orig,
            poses_type_counter,
            obj.handle,
            object_position,
            object_aabb,
            semantic_id,
            ISLAND_RADIUS_LIMIT,
        )

    obj.transformation = cached_obj_transform

    return view_locations
