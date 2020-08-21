#!/usr/bin/env python3

# Copyright (c) Facebook, Inc. and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import importlib
import os
import sqlite3
import sys
from io import StringIO
from unittest.mock import patch

from habitat.utils import compare_profiles


# Create an sqlite database profile in memory. Populate the NVTX table with
# profiling events. Verify compare_profiles functionality including creating and
# printing a timing summary.
def test_compare_profiles():

    c = sqlite3.connect(":memory:")

    # Parse a sqlite database which is missing the expected table.
    events = compare_profiles.get_sqlite_events(c)
    assert len(events) == 0

    # This create statement corresponds to the sqlite database that Nsight Nsys
    # creates.
    c.execute(
        """CREATE TABLE NVTX_EVENTS (start INTEGER NOT NULL, end INTEGER, text TEXT, globalTid INTEGER)"""
    )

    # Save (commit) the changes
    c.commit()

    # Parse a table with no rows.
    events = compare_profiles.get_sqlite_events(c)
    assert len(events) == 0

    # Try to print a list of empty summaries.
    expected_output = """All summaries are empty. The sqlite databases are missing NVTX events.\n"""

    summary = compare_profiles.create_summary_from_events(events)
    with patch("sys.stdout", new=StringIO()) as fake_out:
        compare_profiles.print_summaries(
            [summary], compare_profiles.create_arg_parser().parse_args([]),
        )
        assert fake_out.getvalue() == expected_output

    # Insert some events. An event has a start time, end time, name, and thread
    # ID.
    # Thread 1
    # 01234567890
    # .[        )   incl 90   excl 20  root A
    # .[ ).......   incl 20   excl 10  child 0
    # ..[).......   incl 10   excl 10  child 1
    # ....[...)..   incl 40   excl 10  child 2
    # .....[...).   incl 40   excl 30  child 3
    # ......[)...   incl 10   excl 10  child 4

    # Thread 2
    # 01234567890
    # ..[......).   incl 70   excl 10  root B
    # ...[.....).   incl 60   excl 60  child 6

    # note on child 3: it's unrealistic for a child event to extend beyond the
    # end time of its parent (child 2 in this case), but we expect to handle it
    # anyway.

    # event names are numbered here based on chronological ordering, but we
    # insert them in random order.
    c.execute("INSERT INTO NVTX_EVENTS VALUES (60, 70, 'child 4', 1)")
    c.execute("INSERT INTO NVTX_EVENTS VALUES (20, 30, 'child 1', 1)")
    c.execute("INSERT INTO NVTX_EVENTS VALUES (10, 30, 'child 0', 1)")
    c.execute("INSERT INTO NVTX_EVENTS VALUES (10, 100, 'root A', 1)")
    c.execute("INSERT INTO NVTX_EVENTS VALUES (50, 90, 'child 3', 1)")
    c.execute("INSERT INTO NVTX_EVENTS VALUES (40, 80, 'child 2', 1)")

    c.execute("INSERT INTO NVTX_EVENTS VALUES (20, 90, 'root B', 2)")
    c.execute("INSERT INTO NVTX_EVENTS VALUES (30, 90, 'child 6', 2)")

    # Save (commit) the changes
    c.commit()

    # use compare_profiles functionality to create timing summary
    events = compare_profiles.get_sqlite_events(c)
    summary = compare_profiles.create_summary_from_events(events)

    assert summary["root A"]._time_inclusive == 90
    assert summary["root A"]._time_exclusive == 20
    assert summary["child 0"]._time_inclusive == 20
    assert summary["child 0"]._time_exclusive == 10
    assert summary["child 1"]._time_inclusive == 10
    assert summary["child 1"]._time_exclusive == 10
    assert summary["child 2"]._time_inclusive == 40
    assert summary["child 2"]._time_exclusive == 10
    assert summary["child 3"]._time_inclusive == 40
    assert summary["child 3"]._time_exclusive == 30
    assert summary["child 4"]._time_inclusive == 10
    assert summary["child 4"]._time_exclusive == 10

    assert summary["root B"]._time_inclusive == 70
    assert summary["root B"]._time_exclusive == 10
    assert summary["child 6"]._time_inclusive == 60
    assert summary["child 6"]._time_exclusive == 60

    # verify print output (exact string match)
    expected_output = """event name   incl (ms)     excl (ms)  \nroot A             90            20  \nroot B             70            10  \nchild 6            60            60  \nchild 2            40            10  \nchild 3            40            30  \nchild 0            20            10  \nchild 1            10            10  \nchild 4            10            10  \n"""

    with patch("sys.stdout", new=StringIO()) as fake_out:
        compare_profiles.print_summaries(
            [summary],
            compare_profiles.create_arg_parser().parse_args(
                ["--source-time-units-per-second", "1000"]
            ),
        )
        assert fake_out.getvalue() == expected_output
