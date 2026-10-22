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

"""Tests for the YAML emitter.

The emitter must produce YAML the Cordis Loader parses identically to what we
intended, including the `!!js` tag, literal blocks, and quoting of scalars that
YAML would otherwise re-type.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from harness2_dsh.yaml_emit import JsExpression, dump  # noqa: E402


def test_empty_containers():
    assert dump({"a": {}, "b": []}) == "a: {}\nb: []\n"


def test_scalars_are_typed():
    out = dump({"t": True, "f": False, "z": None, "i": 3, "s": "x"})
    assert out == "t: true\nf: false\nz: null\ni: 3\ns: x\n"


@pytest.mark.parametrize(
    "value",
    ["true", "false", "null", "~", "yes", "123", "1.5", "0x1f", "-dash", "a: b", "x #y", ""],
)
def test_ambiguous_scalars_are_quoted(value):
    out = dump({"k": value})
    assert out == f'k: "{value}"\n'


def test_multiline_uses_literal_block():
    out = dump({"prefix": "line one\nline two\n"})
    assert out == "prefix: |\n  line one\n  line two\n"


def test_nested_lists_of_mappings():
    doc = {"insert": [{"id": "a", "name": "@x/y"}]}
    assert dump(doc) == "insert:\n  - id: a\n    name: \"@x/y\"\n"


def test_js_expression_renders_tagged():
    out = dump({"disabled": JsExpression("process.platform === 'win32'")})
    assert out == "disabled: !!js process.platform === 'win32'\n"


def test_js_expression_inside_list_of_mappings():
    doc = {"insert": [{"id": "t", "disabled": JsExpression("a && b")}]}
    assert dump(doc) == "insert:\n  - id: t\n    disabled: !!js a && b\n"


def test_empty_js_expression_rejected():
    with pytest.raises(ValueError):
        JsExpression("   ")


def test_output_ends_with_single_newline():
    out = dump({"a": "b"})
    assert out.endswith("\n") and not out.endswith("\n\n")


def test_top_level_scalar_rejected():
    with pytest.raises(TypeError):
        dump("not-a-mapping")
