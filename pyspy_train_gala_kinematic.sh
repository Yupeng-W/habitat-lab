#!/usr/bin/env bash
py-spy record --idle --function --native --subprocesses --rate 50 --output pyspy_$1.speedscope --format speedscope -- python ./habitat_baselines/run.py --exp-config habitat_baselines/config/rearrange/gala_kinematic.yaml --run-type train
