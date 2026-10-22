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

"""Tests for reading a Harness2 harness tree."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import trees  # noqa: E402

from harness2_dsh import tree as harness_tree  # noqa: E402


def test_rejects_a_directory_that_is_not_a_harness(tmp_path):
    (tmp_path / "random.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="not a Harness2 harness tree"):
        harness_tree.load(tmp_path)


def test_rejects_missing_directory(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        harness_tree.load(tmp_path / "nope")


def test_reads_all_components(tmp_path):
    root = trees.make_tree(
        tmp_path / "h",
        with_subagent=True,
        with_plugin=True,
        with_skill_script=True,
    )
    harness = harness_tree.load(root)
    assert harness.always_on_text
    assert [s.name for s in harness.skills] == ["ledger-reconciliation"]
    assert harness.skills[0].scripts == {"check.py": "print('ok')\n"}
    assert [a.name for a in harness.subagents] == ["ledger-auditor"]
    assert sorted(harness.scripts) == ["summarize.py"]
    assert harness.plugins == ["ledger.ts"]


def test_readme_stubs_are_not_components(tmp_path):
    root = trees.make_tree(tmp_path / "h", with_skill=False, with_script=False)
    harness = harness_tree.load(root)
    assert harness.skills == []
    assert harness.scripts == {}


def test_always_on_order_matches_harness2(tmp_path):
    root = trees.make_tree(tmp_path / "h")
    harness = harness_tree.load(root)
    text = harness.always_on_text
    assert text.index("Reconcile the ledger") < text.index("ledger total includes every row")
    assert text.index("ledger total includes every row") < text.index("`amount` is signed")
    assert text.index("`amount` is signed") < text.index("Run the helper")


def test_underscore_skill_name_is_folded_to_kebab_case(tmp_path):
    root = trees.make_tree(tmp_path / "h", with_skill=False, with_underscore_skill=True)
    harness = harness_tree.load(root)
    assert [s.name for s in harness.skills] == ["ledger-math"]
    assert any("renamed to 'ledger-math'" in w for w in harness.warnings)


def test_skill_without_description_gets_one_and_a_warning(tmp_path):
    root = trees.make_tree(
        tmp_path / "h", with_skill=False, with_descriptionless_skill=True
    )
    harness = harness_tree.load(root)
    skill = harness.skills[0]
    assert skill.name == "helper-skill"
    assert skill.description
    assert any("no description" in w for w in harness.warnings)


def test_opencode_plugins_are_reported_not_converted(tmp_path):
    root = trees.make_tree(tmp_path / "h", with_plugin=True)
    harness = harness_tree.load(root)
    assert harness.plugins == ["ledger.ts"]
    assert any("not converted" in w for w in harness.warnings)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ledger_math", "ledger-math"),
        ("Ledger Recon", "ledger-recon"),
        ("a--b", "a-b"),
        ("--x--", "x"),
    ],
)
def test_dsh_skill_name_normalisation(raw, expected):
    assert harness_tree.dsh_skill_name(raw) == expected


def test_dsh_skill_name_rejects_pure_punctuation():
    with pytest.raises(ValueError):
        harness_tree.dsh_skill_name("___")


def test_generated_names_satisfy_dsh_grammar(tmp_path):
    root = trees.make_tree(tmp_path / "h", with_underscore_skill=True)
    harness = harness_tree.load(root)
    for skill in harness.skills:
        assert harness_tree.is_dsh_skill_name(skill.name), skill.name
