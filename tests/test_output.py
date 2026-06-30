"""Tests for the output renderer."""

import io
import json

from openproject_cli.output import emit, to_human


def _emit(data, human):
    buf = io.StringIO()
    emit(data, human=human, stream=buf)
    return buf.getvalue()


def test_json_is_default():
    out = _emit({"id": 1, "subject": "x"}, human=False)
    assert json.loads(out) == {"id": 1, "subject": "x"}


def test_json_keeps_unicode():
    out = _emit({"name": "Пример"}, human=False)
    assert "Пример" in out  # ensure_ascii=False


def test_human_mapping():
    out = to_human({"id": 1, "subject": "fix"})
    assert "id:" in out
    assert "subject:" in out
    assert "fix" in out


def test_human_list_of_dicts_is_tabular():
    out = to_human([{"id": 1, "subject": "a"}, {"id": 2, "subject": "b"}])
    lines = out.splitlines()
    assert lines[0] == "id\tsubject"
    assert lines[1] == "1\ta"
    assert lines[2] == "2\tb"


def test_human_empty_list():
    assert to_human([]) == "(no results)"


def test_human_nested_value_is_json():
    out = to_human({"links": {"a": 1}})
    assert '{"a": 1}' in out
