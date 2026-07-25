from __future__ import annotations

import ast
import json
import math
import operator
import re
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from dhtol_analyzer.models import (
    BoardEvent,
    BoardLogScan,
    BoardMetadata,
    FaultType,
    OvenplanEntry,
    ParsedConfig,
)

MEASUREMENT_COLUMNS = [
    "timestamp",
    "v_in",
    "current",
    "vg_diff",
    "vout_dut",
    "vout_brd",
    "v_ls",
    "t0",
    "t1",
]

_DUT_ID_PATTERN = re.compile(r"(\d+)_(\d+)_(\d+)$")
_ZONE_PATTERN = re.compile(r"(?:^|_)([ABC])(?:_|$)", re.IGNORECASE)
_STOP_TIME_PATTERN = re.compile(
    r"\bstop\s*=\s*\{.*?\btime\s*=\s*([0-9eE+\-*/().\s]+)",
    re.DOTALL,
)
_HOST_TIMEOUT_PATTERN = re.compile(
    r"TARGET:\s*(?P<target>[^,]+),\s*"
    r"TIMED OUT on:\s*(?P<timestamp>[^,]+),\s*"
    r"Error occured:\s*(?P<error>[^,]+),\s*"
    r"Time stressed:\s*(?P<stress>[^,]+),\s*"
    r"DUT NAME:\s*(?P<dut>.+)$",
    re.IGNORECASE,
)

_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_UNARY_OPERATORS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _walk(value: Any) -> Iterator[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def parse_config_json(path: Path) -> ParsedConfig:
    warnings: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return ParsedConfig(
            test_name=path.stem,
            source_path=path,
            warnings=[f"Cannot read JSON: {error}"],
        )

    test_name = str(data.get("Test Name") or path.stem)
    zone_match = _ZONE_PATTERN.search(test_name)
    fallback_zone = zone_match.group(1).upper() if zone_match else ""
    ovenplan = data.get("Ovenplan", [])

    if not isinstance(ovenplan, list):
        return ParsedConfig(
            test_name=test_name,
            source_path=path,
            warnings=["Ovenplan is not a list."],
        )

    entries: list[OvenplanEntry] = []
    for index, row in enumerate(ovenplan, start=1):
        if not isinstance(row, dict):
            warnings.append(f"Ovenplan row {index} is not an object.")
            continue

        dut_name = str(row.get("DUT") or "").strip()
        zone = str(row.get("Zone") or fallback_zone).strip().upper()
        try:
            position = int(str(row.get("Slot") or "").strip())
        except ValueError:
            position = 0

        if not dut_name or zone not in {"A", "B", "C"} or position <= 0:
            warnings.append(f"Ovenplan row {index} has invalid DUT, zone, or slot.")
            continue

        entries.append(
            OvenplanEntry(
                zone=zone,
                position=position,
                dut_name=dut_name,
                hw_target=str(row.get("HW Target") or "").strip(),
            )
        )

    return ParsedConfig(
        test_name=test_name,
        entries=entries,
        source_path=path,
        warnings=warnings,
    )


def _safe_number(expression: str) -> float | None:
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError:
        return None

    def evaluate(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
            function = _BINARY_OPERATORS[type(node.op)]
            return function(evaluate(node.left), evaluate(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
            function = _UNARY_OPERATORS[type(node.op)]
            return function(evaluate(node.operand))
        raise ValueError("Unsupported expression")

    try:
        value = evaluate(tree)
    except (ValueError, TypeError, ZeroDivisionError, OverflowError):
        return None
    return value if value >= 0 else None


def parse_planned_seconds(path: Path) -> float | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None

    for item in _walk(data):
        if not isinstance(item, dict):
            continue
        if str(item.get("templateName", "")).strip() != "stop_time":
            continue
        value = _safe_number(str(item.get("templateValue", "")))
        if value is not None:
            return value

    for item in _walk(data):
        if not isinstance(item, str):
            continue
        match = _STOP_TIME_PATTERN.search(item)
        if match:
            value = _safe_number(match.group(1))
            if value is not None:
                return value
    return None


def parse_board_data(path: Path) -> BoardMetadata | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None

    test_info = data.get("Test Info") or {}
    history = data.get("HW History") or []
    latest = history[-1] if isinstance(history, list) and history else {}
    version = (latest.get("HW Info") or {}).get("version") or {}

    try:
        seconds = max(0.0, float(test_info.get("Seconds") or 0.0))
    except (TypeError, ValueError):
        seconds = 0.0

    return BoardMetadata(
        stress_seconds=seconds,
        firmware_version=str(version.get("fw") or ""),
        source_path=path,
    )


def fault_type_from_text(text: str) -> FaultType:
    normalized = text.upper()
    if "OC ERR" in normalized or normalized.strip() == "OC":
        return FaultType.OC
    if "OV ERR" in normalized or normalized.strip() == "OV":
        return FaultType.OV
    if (
        "OT ERR" in normalized
        or "TEMP ERR" in normalized
        or normalized.strip() in {"OT", "TEMP", "TEMPERR"}
    ):
        return FaultType.OT
    if "GERR" in normalized:
        return FaultType.GERR
    if "NETWORK" in normalized:
        return FaultType.NETWORK
    return FaultType.NONE


def _is_relevant_event(text: str) -> bool:
    normalized = text.upper()
    return any(
        marker in normalized
        for marker in (
            "OC ERR",
            "OV ERR",
            "OT ERR",
            "TEMP ERR",
            "GERR",
            "PIC STOPPED",
        )
    )


def _parse_measurement_line(
    raw_line: str,
) -> tuple[datetime, tuple[float, ...]] | None:
    parts = raw_line.rstrip("\r\n").split("\t", 1)
    if len(parts) != 2:
        return None

    timestamp_text, payload = parts
    if payload.count(";") != 7:
        return None

    try:
        timestamp = datetime.fromisoformat(timestamp_text)
        values = tuple(float(value) for value in payload.split(";"))
    except (TypeError, ValueError):
        return None
    return timestamp, values


def scan_board_logs(
    paths: list[Path],
    max_points: int = 5_000,
) -> BoardLogScan:
    ordered = sorted(paths, key=lambda path: path.name)
    total_bytes = sum(path.stat().st_size for path in ordered if path.exists())
    sample_step = max(1, total_bytes // max(1, max_points * 75))

    rows: list[tuple[object, ...]] = []
    events: list[BoardEvent] = []
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    last_measurement: tuple[object, ...] | None = None
    measurement_count = 0
    skipped_lines = 0

    for path in ordered:
        try:
            handle = path.open("r", encoding="utf-8", errors="replace")
        except OSError:
            skipped_lines += 1
            continue

        with handle:
            for raw_line in handle:
                measurement = _parse_measurement_line(raw_line)
                if measurement is not None:
                    timestamp, values = measurement
                    first_timestamp = first_timestamp or timestamp
                    last_timestamp = timestamp
                    row = (timestamp, *values)
                    last_measurement = row

                    if measurement_count % sample_step == 0:
                        rows.append(row)
                    measurement_count += 1
                    continue

                parts = raw_line.rstrip("\r\n").split("\t", 1)
                if len(parts) != 2:
                    skipped_lines += 1
                    continue
                timestamp_text, payload = parts
                if not _is_relevant_event(payload):
                    continue
                try:
                    timestamp = datetime.fromisoformat(timestamp_text)
                except ValueError:
                    skipped_lines += 1
                    continue
                events.append(
                    BoardEvent(
                        timestamp=timestamp,
                        text=payload.strip(),
                        fault_type=fault_type_from_text(payload),
                        source_path=path,
                    )
                )

    if last_measurement is not None and (
        not rows or rows[-1][0] != last_measurement[0]
    ):
        rows.append(last_measurement)

    frame = pd.DataFrame.from_records(rows, columns=MEASUREMENT_COLUMNS)
    if not frame.empty:
        frame = (
            frame.sort_values("timestamp")
            .drop_duplicates("timestamp")
            .reset_index(drop=True)
        )
        if len(frame) > max_points:
            step = math.ceil(len(frame) / max_points)
            frame = frame.iloc[::step].reset_index(drop=True)

    return BoardLogScan(
        measurements=frame,
        events=events,
        first_timestamp=first_timestamp,
        last_timestamp=last_timestamp,
        measurement_count=measurement_count,
        skipped_lines=skipped_lines,
    )


def parse_host_timeouts(paths: list[Path]) -> list[BoardEvent]:
    events: list[BoardEvent] = []
    for path in sorted(paths, key=lambda item: item.name):
        try:
            handle = path.open("r", encoding="utf-8", errors="replace")
        except OSError:
            continue

        with handle:
            for raw_line in handle:
                payload = raw_line.rstrip("\r\n").split("\t", 1)[-1]
                match = _HOST_TIMEOUT_PATTERN.search(payload)
                if not match:
                    continue
                try:
                    timestamp = datetime.fromisoformat(match.group("timestamp").strip())
                except ValueError:
                    continue
                fault = fault_type_from_text(match.group("error"))
                events.append(
                    BoardEvent(
                        timestamp=timestamp,
                        text=(
                            f"{match.group('dut').strip()} "
                            f"{match.group('error').strip()}"
                        ),
                        fault_type=fault,
                        source_path=path,
                    )
                )
    return sorted(events, key=lambda event: event.timestamp)
