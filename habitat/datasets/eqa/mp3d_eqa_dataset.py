#!/usr/bin/env python3

# Copyright (c) Facebook, Inc. and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import gzip
import json
import os
from typing import List, Optional

from habitat.config import Config
from habitat.core.dataset import Dataset
from habitat.core.registry import registry
from habitat.core.simulator import AgentState
from habitat.datasets.utils import VocabDict, VocabFromText
from habitat.tasks.eqa.eqa import EQAEpisode, QuestionData
from habitat.tasks.nav.nav import ShortestPathPoint
from habitat.tasks.nav.object_nav_task import ObjectGoal

EQA_MP3D_V1_VAL_EPISODE_COUNT = 1950
DEFAULT_SCENE_PATH_PREFIX = "data/scene_datasets/"


def get_default_mp3d_v1_config(split: str = "val"):
    config = Config()
    config.name = "MP3DEQA-v1"
    config.DATA_PATH = "data/datasets/eqa/mp3d/v1/{split}.json.gz"
    config.SPLIT = split
    return config


@registry.register_dataset(name="MP3DEQA-v1")
class Matterport3dDatasetV1(Dataset):
    r"""Class inherited from Dataset that loads Matterport3D
    Embodied Question Answering dataset.

    This class can then be used as follows::
        eqa_config.dataset = get_default_mp3d_v1_config()
        eqa = habitat.make_task(eqa_config.task_name, config=eqa_config)
    """

    episodes: List[EQAEpisode]
    answer_vocab: VocabDict
    question_vocab: VocabDict

    @staticmethod
    def check_config_paths_exist(config: Config) -> bool:
        return os.path.exists(config.DATA_PATH.format(split=config.SPLIT))

    def __init__(self, config: Config = None) -> None:
        self.episodes = []

        if config is None:
            return

        with gzip.open(config.DATA_PATH.format(split=config.SPLIT), "rt") as f:
            self.from_json(f.read(), scenes_dir=config.SCENES_DIR)

        self.episodes = self.filter_episodes(
            self.build_content_scenes_filter(config)
        )

    def from_json(
        self, json_str: str, scenes_dir: Optional[str] = None
    ) -> None:
        deserialized = json.loads(json_str)
        self.__dict__.update(deserialized)
        self.answer_vocab = VocabDict(word_list=self.answer_vocab["word_list"])
        self.question_vocab = VocabDict(
            word_list=self.question_vocab["word_list"]
        )

        for ep_index, episode in enumerate(deserialized["episodes"]):
            episode = EQAEpisode(**episode)
            if scenes_dir is not None:
                if episode.scene_id.startswith(DEFAULT_SCENE_PATH_PREFIX):
                    episode.scene_id = episode.scene_id[
                        len(DEFAULT_SCENE_PATH_PREFIX) :
                    ]
                episode.scene_id = os.path.join(scenes_dir, episode.scene_id)
            episode.question = QuestionData(**episode.question)
            for g_index, goal in enumerate(episode.goals):
                episode.goals[g_index] = ObjectGoal(**goal)
                new_goal = episode.goals[g_index]
                if new_goal.view_points is not None:
                    for p_index, agent_state in enumerate(
                        new_goal.view_points
                    ):
                        new_goal.view_points[p_index] = AgentState(
                            **agent_state
                        )
            if episode.shortest_paths is not None:
                for path in episode.shortest_paths:
                    for p_index, point in enumerate(path):
                        path[p_index] = ShortestPathPoint(**point)
            self.episodes[ep_index] = episode
