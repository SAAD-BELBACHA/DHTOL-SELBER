from dhtol_analyzer.analysis import calculate_post_stress_seconds


def test_post_stress_is_planned_minus_stress():
    assert calculate_post_stress_seconds(1000, 640) == 360


def test_post_stress_never_becomes_negative():
    assert calculate_post_stress_seconds(100, 120) == 0
