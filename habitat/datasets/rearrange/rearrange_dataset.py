import json
import os.path as osp
from typing import List, Optional

import attr

from habitat.config import Config
from habitat.core.dataset import Episode
from habitat.core.registry import registry
from habitat.core.simulator import ShortestPathPoint
from habitat.core.utils import DatasetFloatJSONEncoder, not_none_validator
from habitat.datasets.pointnav.pointnav_dataset import PointNavDatasetV1
from habitat.tasks.nav.nav import NavigationGoal


@attr.s(auto_attribs=True, kw_only=True)
class RearrangeEpisode(Episode):
    art_objs: object
    static_objs: object
    targets: object
    fixed_base: bool
    art_states: object
    nav_mesh_path: str
    scene_config_path: str
    allowed_region: List = []
    markers: List = []
    force_spawn_pos: List = None


@registry.register_dataset(name="RearrangeDataset-v0")
class RearrangeDatasetV0(PointNavDatasetV1):
    r"""Class inherited from PointNavDataset that loads Rearrangement dataset."""
    episodes: List[RearrangeEpisode]
    content_scenes_path: str = "{data_path}/content/{scene}.json.gz"

    def to_json(self) -> str:
        result = DatasetFloatJSONEncoder().encode(self)
        return result

    def __init__(self, config: Optional[Config] = None) -> None:
        super().__init__(config)

    def from_json(
        self, json_str: str, scenes_dir: Optional[str] = None
    ) -> None:
        deserialized = json.loads(json_str)
        dir_path = osp.dirname(osp.realpath(__file__))

        for i, episode in enumerate(deserialized["episodes"]):
            rearrangement_episode = RearrangeEpisode(**episode)
            rearrangement_episode.episode_id = str(i)
            self.episodes.append(rearrangement_episode)
