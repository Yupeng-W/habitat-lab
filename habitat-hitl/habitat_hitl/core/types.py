#!/usr/bin/env python3

# Copyright (c) Meta Platforms, Inc. and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from dataclasses import dataclass
from typing import Any, Dict, List

# Dictionary that is serialized to or from JSON.
DataDict = Dict[str, Any]

# Server -> Client communication dictionary originating from habitat-sim (loads, updates, deletions, ...).
Keyframe = DataDict

# Server -> Client communication dictionary that is user specific and added to keyframes before sending the payload to the user (keyframe["message"]).
Message = DataDict

# Kick signal.
@dataclass
class KickSignal:
    user_index: int
    error_message: str

# Keyframe and all user messages for a specific frame.
@dataclass
class KeyframeAndMessages:
    keyframe: Keyframe
    messages: List[Message]

    def __init__(self, keyframe: Keyframe, messages: List[Message]):
        self.keyframe = keyframe
        self.messages = messages


# Client -> Server communication dictionary (inputs, etc.).
ClientState = DataDict

# Dictionary that contains data about a new connection.
ConnectionRecord = DataDict

# Dictionary that contains data about a terminated connection.
DisconnectionRecord = DataDict
