from datetime import UTC, datetime, timedelta

import pandas as pd

from dhtol_analyzer.analysis import (
    _temperature_evidence,
    calculate_post_stress_seconds,
)
from dhtol_analyzer.settings import AnalysisSettings


def test_post_stress_is_planned_minus_stress():
    assert calculate_post_stress_seconds(1000, 640) == 360


def test_post_stress_never_becomes_negative():
    assert calculate_post_stress_seconds(100, 120) == 0


def test_temperature_level_is_not_flagged_when_stable():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    frame = pd.DataFrame(
        {
            "timestamp": [start, start + timedelta(seconds=1)],
            "t0": [300.0, 300.0],
            "t1": [-50.0, -50.0],
        }
    )

    assert _temperature_evidence(frame, None, AnalysisSettings()) == []


def test_implausible_temperature_jump_is_flagged():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    frame = pd.DataFrame(
        {
            "timestamp": [
                start,
                start + timedelta(seconds=1),
                start + timedelta(seconds=2),
            ],
            "t0": [200.0, 10.0, 150.0],
            "t1": [100.0, 100.0, 100.0],
        }
    )

    evidence = _temperature_evidence(frame, None, AnalysisSettings())

    assert len(evidence) == 2
    assert all(item.rule == "temperature_rate" for item in evidence)
