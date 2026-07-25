import json
from datetime import datetime

from dhtol_analyzer.models import FaultType
from dhtol_analyzer.parsers import (
    parse_board_data,
    parse_config_json,
    parse_planned_seconds,
    scan_board_logs,
)


def test_parse_config_json(tmp_path):
    path = tmp_path / "run_A_config.json"
    path.write_text(
        json.dumps(
            {
                "Test Name": "demo_A_1A",
                "Ovenplan": [
                    {
                        "Zone": "A",
                        "Slot": 1,
                        "DUT": "DUT_001",
                        "HW Target": "target-a",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = parse_config_json(path)

    assert result.test_name == "demo_A_1A"
    assert result.entries[0].dut_name == "DUT_001"
    assert result.entries[0].position == 1


def test_parse_planned_seconds_accepts_safe_expression(tmp_path):
    path = tmp_path / "run.mtpx"
    path.write_text(
        json.dumps(
            {
                "templateName": "stop_time",
                "templateValue": "1000 * 3600",
            }
        ),
        encoding="utf-8",
    )

    assert parse_planned_seconds(path) == 3_600_000.0


def test_parse_board_data(tmp_path):
    path = tmp_path / "board.data"
    path.write_text(
        json.dumps(
            {
                "Test Info": {"Seconds": 3600},
                "HW History": [{"HW Info": {"version": {"fw": "1.2.3"}}}],
            }
        ),
        encoding="utf-8",
    )

    result = parse_board_data(path)

    assert result is not None
    assert result.stress_seconds == 3600
    assert result.firmware_version == "1.2.3"


def test_scan_board_log_keeps_measurements_and_faults(tmp_path):
    path = tmp_path / "board.log"
    path.write_text(
        "2026-01-01T10:00:00\t12.0;1.0;0.1;5.0;5.0;0.2;125.0;126.0\n"
        "2026-01-01T10:00:01\tOC ERR\n"
        "2026-01-01T10:00:02\t12.0;0.0;0.1;5.0;5.0;0.2;125.0;126.0",
        encoding="utf-8",
    )

    result = scan_board_logs([path])

    assert result.measurement_count == 2
    assert len(result.events) == 1
    assert result.events[0].fault_type is FaultType.OC
    assert result.first_timestamp == datetime.fromisoformat("2026-01-01T10:00:00")
