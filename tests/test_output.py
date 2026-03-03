"""Tests for output module."""

import json

import pytest

from pumpfun_cli.output import error, render, render_json, set_json_mode


@pytest.fixture(autouse=True)
def _reset_json_mode():
    """Reset module-level json_mode after each test."""
    yield
    set_json_mode(False)


def test_render_json_mode(capsys):
    data = {"key": "value", "num": 42}
    result = render(data, json_mode=True)
    assert result is True
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["key"] == "value"
    assert parsed["num"] == 42


def test_render_json_directly(capsys):
    render_json({"a": 1})
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["a"] == 1


def test_error_exits():
    with pytest.raises(SystemExit) as exc_info:
        error("something broke")
    assert exc_info.value.code == 1


def test_error_custom_exit_code():
    with pytest.raises(SystemExit) as exc_info:
        error("graduated", exit_code=3)
    assert exc_info.value.code == 3


def test_error_json_mode_emits_json_to_stdout(capsys):
    set_json_mode(True)
    with pytest.raises(SystemExit):
        error("something broke", hint="try again", exit_code=2)
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed == {"error": "something broke", "hint": "try again", "exit_code": 2}


def test_error_json_mode_still_prints_stderr(capsys):
    set_json_mode(True)
    with pytest.raises(SystemExit):
        error("something broke")
    captured = capsys.readouterr()
    assert "something broke" in captured.err


def test_error_json_mode_exits_with_correct_code():
    set_json_mode(True)
    with pytest.raises(SystemExit) as exc_info:
        error("fail", exit_code=5)
    assert exc_info.value.code == 5


def test_error_json_mode_null_hint(capsys):
    set_json_mode(True)
    with pytest.raises(SystemExit):
        error("no hint here")
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["hint"] is None


def test_error_no_json_mode_no_stdout(capsys):
    set_json_mode(False)
    with pytest.raises(SystemExit):
        error("just stderr")
    captured = capsys.readouterr()
    assert captured.out == ""


def test_set_json_mode_toggles(capsys):
    set_json_mode(True)
    set_json_mode(False)
    with pytest.raises(SystemExit):
        error("toggled off")
    captured = capsys.readouterr()
    assert captured.out == ""
