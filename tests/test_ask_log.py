"""Logging real questions, so the gold set can grow from use rather than
from one person's imagination.

The first full run made the case: `match_detail` scored 0% and nobody had
predicted it. Questions the developer actually types carry proof that someone
wanted the answer, which is signal no invented question has.
"""

from __future__ import annotations

import json

import ask


def test_log_appends_one_json_object_per_question(tmp_path):
    path = tmp_path / "ask_log.jsonl"
    ask.log_question(path, question="soru 1", sql="select 1", ok=True, rows=5)
    ask.log_question(path, question="soru 2", sql=None, ok=False, rows=None)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["question"] == "soru 1"
    assert first["sql"] == "select 1"
    assert first["ok"] is True
    assert first["rows"] == 5
    assert "asked_at" in first


def test_log_creates_the_parent_directory(tmp_path):
    path = tmp_path / "nested" / "ask_log.jsonl"
    ask.log_question(path, question="soru", sql="select 1", ok=True, rows=1)
    assert path.exists()


def test_log_survives_an_unwritable_path(tmp_path):
    """Bookkeeping must never break the thing the user asked for."""
    path = tmp_path / "ask_log.jsonl"
    path.mkdir()  # a directory where a file should be
    ask.log_question(path, question="soru", sql="select 1", ok=True, rows=1)


def test_log_keeps_turkish_characters_readable(tmp_path):
    path = tmp_path / "ask_log.jsonl"
    ask.log_question(path, question="en çok şut çeken", sql="select 1", ok=True, rows=1)
    assert "en çok şut çeken" in path.read_text(encoding="utf-8")
