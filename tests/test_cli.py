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

"""Tests for the command line interface."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import trees  # noqa: E402

from harness2_dsh.cli import main  # noqa: E402


def test_inspect_prints_a_summary(tmp_path, capsys):
    src = trees.make_tree(tmp_path / "h")
    assert main(["inspect", str(src)]) == 0
    out = capsys.readouterr().out
    assert "always-on text" in out
    assert "ledger-reconciliation" in out


def test_inspect_json_is_machine_readable(tmp_path, capsys):
    src = trees.make_tree(tmp_path / "h")
    assert main(["inspect", str(src), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["skills"] == ["ledger-reconciliation"]
    assert data["scripts"] == ["summarize.py"]
    assert data["source_kind"] == "harness directory"


def test_inspect_on_a_non_harness_returns_2(tmp_path, capsys):
    (tmp_path / "junk").mkdir()
    assert main(["inspect", str(tmp_path / "junk")]) == 2
    assert "could not find a harness tree" in capsys.readouterr().err


def test_convert_writes_a_bundle_and_prints_the_install_hint(tmp_path, capsys):
    src = trees.make_tree(tmp_path / "h")
    out = tmp_path / "bundle"
    code = main(
        [
            "convert",
            str(src),
            "--out",
            str(out),
            "--preset-id",
            "ledger-recon",
            "--name",
            "Ledger Recon",
            "--profile",
            "web",
        ]
    )
    assert code == 0
    text = capsys.readouterr().out
    assert "wrote bundle" in text
    assert "dsh plugin --profile web add" in text
    assert (out / "cordis.patch.yml").is_file()


def test_convert_json_reports_files(tmp_path, capsys):
    src = trees.make_tree(tmp_path / "h")
    out = tmp_path / "bundle"
    assert main(["convert", str(src), "--out", str(out), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["preset_id"]
    assert any(p.endswith("cordis.patch.yml") for p in data["files"])


def test_convert_refuses_a_non_empty_output(tmp_path, capsys):
    src = trees.make_tree(tmp_path / "h")
    out = tmp_path / "bundle"
    out.mkdir()
    (out / "x").write_text("y", encoding="utf-8")
    assert main(["convert", str(src), "--out", str(out)]) == 2
    assert "refusing to overwrite" in capsys.readouterr().err


def test_preset_id_defaults_from_the_output_directory(tmp_path):
    src = trees.make_tree(tmp_path / "h")
    out = tmp_path / "my-preset"
    assert main(["convert", str(src), "--out", str(out)]) == 0
    patch = (out / "cordis.patch.yml").read_text(encoding="utf-8")
    assert "id: my-preset" in patch
