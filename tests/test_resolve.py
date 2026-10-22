# Copyright 2026 harness2-dsh contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for locating the harness inside a Harness2 run or library layout."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import trees  # noqa: E402

from harness2_dsh import tree as harness_tree  # noqa: E402


def test_direct_harness_directory(tmp_path):
    root = trees.make_tree(tmp_path / "h")
    found, how = harness_tree.resolve_harness_root(root)
    assert found == root
    assert how == "harness directory"


def test_library_entry_layout(tmp_path):
    """<domain>/harnesses/<task>/{harness, EXPERIENCE.md}"""
    entry = tmp_path / "lib" / "accounting" / "harnesses" / "ledger-2"
    trees.make_tree(entry / "harness")
    (entry / "EXPERIENCE.md").write_text("# ledger-2\n", encoding="utf-8")
    found, how = harness_tree.resolve_harness_root(entry)
    assert found == entry / "harness"
    assert "library entry" in how


def test_task_run_directory_uses_the_adopted_harness(tmp_path):
    run = tmp_path / "runs" / "ledger-1"
    trees.make_tree(run / "harnesses" / "base")
    trees.make_tree(run / "harnesses" / "agg1")
    trees.make_tree(run / "harnesses" / "agg2")
    (run / "summary.json").write_text(
        json.dumps({"selections": {"agg": {"chosen_label": "agg2"}}}), encoding="utf-8"
    )
    found, how = harness_tree.resolve_harness_root(run)
    assert found == run / "harnesses" / "agg2"
    assert "agg=agg2" in how


def test_task_run_directory_falls_back_to_the_last_final(tmp_path):
    run = tmp_path / "runs" / "ledger-1"
    for label in ("base", "inv1", "agg1"):
        trees.make_tree(run / "harnesses" / label)
    (run / "summary.json").write_text(
        json.dumps({"modes": {"agg": {"finals": ["agg1"]}}}), encoding="utf-8"
    )
    found, how = harness_tree.resolve_harness_root(run)
    assert found == run / "harnesses" / "agg1"
    assert "final harness" in how


def test_task_run_without_any_harness_is_an_error(tmp_path):
    run = tmp_path / "runs" / "ledger-1"
    run.mkdir(parents=True)
    (run / "summary.json").write_text(json.dumps({"modes": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="no adopted or final harness"):
        harness_tree.resolve_harness_root(run)


def test_unreadable_summary_is_an_error(tmp_path):
    run = tmp_path / "runs" / "x"
    run.mkdir(parents=True)
    (run / "summary.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not readable JSON"):
        harness_tree.resolve_harness_root(run)


def test_single_library_entry_is_found(tmp_path):
    domain = tmp_path / "lib" / "accounting"
    trees.make_tree(domain / "harnesses" / "ledger-1" / "harness")
    found, how = harness_tree.resolve_harness_root(domain)
    assert found == domain / "harnesses" / "ledger-1" / "harness"
    assert how == "the only library entry"


def test_ambiguous_directory_is_an_error(tmp_path):
    domain = tmp_path / "lib" / "accounting"
    trees.make_tree(domain / "harnesses" / "a" / "harness")
    trees.make_tree(domain / "harnesses" / "b" / "harness")
    with pytest.raises(ValueError, match="could not find a harness tree"):
        harness_tree.resolve_harness_root(domain)
