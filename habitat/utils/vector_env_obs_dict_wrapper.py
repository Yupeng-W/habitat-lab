from typing import List, Optional, Tuple, Union

import numpy as np
from gym import spaces
from gym.core import ObsType
from gym.vector import VectorEnv, VectorEnvWrapper


class VectorEnvObsDictWrapper(VectorEnvWrapper):
    OBSERVATION_KEY = "obs"

    def __init__(self, env: VectorEnv):
        """
        Wraps a VectorEnv environment and makes sure its obervation space is a
        Dictionary (If it is a Box, it will be wrapped into a dictionary)
        """
        super().__init__(env)
        self._requires_dict = False
        if isinstance(self.observation_space, spaces.Box):
            self._requires_dict = True
            self.observation_space = spaces.Dict(
                {self.OBSERVATION_KEY: self.observation_space}
            )

    def call_async(self, name: str, *args, **kwargs):
        return self.env.call_async(name, *args, **kwargs)

    def call_wait(self, timeout: Optional[Union[int, float]] = None) -> list:
        return self.env.call_wait(timeout)

    def step_wait(
        self, timeout: Optional[Union[int, float]] = None
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, List[dict]]:
        obs, reward, done, info = self.env.step_wait(timeout)
        if self._requires_dict:
            obs = {self.OBSERVATION_KEY: obs}
        return obs, reward, done, info

    def reset_wait(
        self,
        timeout: Optional[Union[int, float]] = None,
        seed: Optional[int] = None,
        return_info: bool = False,
        options: Optional[dict] = None,
    ) -> Union[ObsType, Tuple[ObsType, List[dict]]]:
        if return_info and self._requires_dict:
            obs, info = self.env.reset_wait(
                timeout, seed, return_info, options
            )
            return {self.OBSERVATION_KEY: obs}, info
        if not return_info and self._requires_dict:
            obs = self.env.reset_wait(timeout, seed, return_info, options)
            return {self.OBSERVATION_KEY: obs}
        return self.env.reset_wait(timeout, seed, return_info, options)
