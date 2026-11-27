"""A blocked provider must not be reported as a wrong canvas decision."""

import pytest

from scripts.benchmark_canvas_live_selection import CASES, parse_target, summarize


def test_probe_targets_and_strict_json_contract():
    assert len({case.fixture for case in CASES}) == len(CASES)
    assert parse_target('{"element_id":"Review"}') == "Review"
    assert parse_target('{"element_id":null}') is None
    with pytest.raises(ValueError):
        parse_target('{"element_id":"Review","extra":1}')


def test_provider_error_does_not_count_as_incorrect_model_answer():
    report = summarize([
        {"representation": "map", "parsed": None, "correct": None,
         "usage": None, "latency_ms": 1000, "error_type": "RateLimitError"},
        {"representation": "xml", "parsed": True, "correct": True,
         "usage": {"total": 120}, "latency_ms": 200},
    ])
    assert report["map"]["completed"] == 0
    assert report["map"]["provider_errors"] == 1
    assert report["map"]["correct"] == 0
    assert report["map"]["parse_failures"] == 0
    assert report["xml"]["correct"] == 1
    assert report["xml"]["median_total_tokens"] == 120
