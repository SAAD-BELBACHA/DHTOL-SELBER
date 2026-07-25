from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from dhtol_analyzer.models import (
    BoardInput,
    BoardResult,
    Evidence,
    FaultType,
    RunResult,
    Status,
    TestRunInput,
)
from dhtol_analyzer.parsers import (
    parse_board_data,
    parse_host_timeouts,
    scan_board_logs,
)
from dhtol_analyzer.settings import AnalysisSettings


def calculate_post_stress_seconds(
    planned_seconds: float,
    stress_seconds: float,
) -> float:
    return max(0.0, float(planned_seconds) - float(stress_seconds))


def _temperature_evidence(
    frame: pd.DataFrame,
    source_path,
    settings: AnalysisSettings,
) -> list[Evidence]:
    evidence: list[Evidence] = []
    if frame.empty:
        return evidence

    timestamps = pd.to_datetime(frame["timestamp"])
    seconds = timestamps.diff().dt.total_seconds()

    for sensor in ("t0", "t1"):
        values = pd.to_numeric(frame[sensor], errors="coerce")
        invalid = (
            values.isna()
            | values.lt(settings.temperature_min_c)
            | values.gt(settings.temperature_max_c)
        )

        for index in frame.index[invalid][: settings.max_evidence_per_rule]:
            evidence.append(
                Evidence(
                    level=Status.REVIEW,
                    rule="temperature_bounds",
                    reason=f"{sensor.upper()} is outside physical limits.",
                    source_path=source_path,
                    timestamp=timestamps.iloc[index].to_pydatetime(),
                    measured_value=float(values.iloc[index])
                    if pd.notna(values.iloc[index])
                    else "NaN",
                    threshold=(
                        f"{settings.temperature_min_c} to "
                        f"{settings.temperature_max_c} °C"
                    ),
                )
            )

        rates = values.diff().abs().div(seconds.where(seconds > 0))
        too_fast = rates.gt(settings.temperature_max_rate_c_per_s)
        for index in frame.index[too_fast][: settings.max_evidence_per_rule]:
            evidence.append(
                Evidence(
                    level=Status.REVIEW,
                    rule="temperature_rate",
                    reason=f"{sensor.upper()} changed too quickly.",
                    source_path=source_path,
                    timestamp=timestamps.iloc[index].to_pydatetime(),
                    measured_value=float(rates.iloc[index]),
                    threshold=settings.temperature_max_rate_c_per_s,
                )
            )

    return evidence


def _fault_evidence(
    board: BoardInput,
    board_events,
    host_events,
    settings: AnalysisSettings,
) -> list[Evidence]:
    evidence: list[Evidence] = []

    for event in board_events:
        if event.fault_type is FaultType.NONE:
            continue

        confirmed = any(
            board.dut_name.lower() in host.text.lower()
            and host.fault_type is event.fault_type
            and abs((host.timestamp - event.timestamp).total_seconds())
            <= settings.fault_confirmation_window_seconds
            for host in host_events
        )

        evidence.append(
            Evidence(
                level=Status.FAIL if confirmed else Status.REVIEW,
                rule="confirmed_fault" if confirmed else "board_fault_event",
                reason=(
                    f"{event.fault_type.value} confirmed by board and host logs."
                    if confirmed
                    else f"{event.fault_type.value} requires engineer review."
                ),
                source_path=event.source_path,
                timestamp=event.timestamp,
                measured_value=event.text,
                threshold=settings.fault_confirmation_window_seconds,
            )
        )

    return evidence


def _status_from_evidence(evidence: list[Evidence]) -> Status:
    if any(item.level is Status.FAIL for item in evidence):
        return Status.FAIL
    if any(item.level is Status.REVIEW for item in evidence):
        return Status.REVIEW
    return Status.PASS


def analyze_board(
    run: TestRunInput,
    board: BoardInput,
    host_events,
    settings: AnalysisSettings,
) -> BoardResult:
    log_scan = scan_board_logs(
        board.log_paths,
        max_points=settings.max_chart_points_per_board,
    )
    metadata = parse_board_data(board.data_path) if board.data_path else None
    stress_seconds = metadata.stress_seconds if metadata else 0.0
    evidence: list[Evidence] = []

    if board.data_path is None:
        evidence.append(
            Evidence(
                level=Status.REVIEW,
                rule="missing_data",
                reason="Board DATA file is missing.",
            )
        )

    if not board.log_paths:
        evidence.append(
            Evidence(
                level=Status.REVIEW,
                rule="missing_board_log",
                reason="Board LOG file is missing.",
            )
        )

    missing_log_seconds = max(
        0.0,
        stress_seconds - log_scan.available_seconds,
    )
    if missing_log_seconds > settings.missing_log_warning_seconds:
        evidence.append(
            Evidence(
                level=Status.REVIEW,
                rule="missing_log_coverage",
                reason="Board LOG duration is shorter than DATA stress duration.",
                source_path=board.data_path,
                measured_value=missing_log_seconds,
                threshold=settings.missing_log_warning_seconds,
            )
        )

    first_log = board.log_paths[0] if board.log_paths else None
    evidence.extend(
        _temperature_evidence(
            log_scan.measurements,
            first_log,
            settings,
        )
    )
    evidence.extend(
        _fault_evidence(
            board,
            log_scan.events,
            host_events,
            settings,
        )
    )

    return BoardResult(
        board=board,
        status=_status_from_evidence(evidence),
        planned_seconds=run.planned_seconds,
        stress_seconds=stress_seconds,
        post_stress_seconds=calculate_post_stress_seconds(
            run.planned_seconds,
            stress_seconds,
        ),
        available_log_seconds=log_scan.available_seconds,
        evidence=evidence,
        measurements=log_scan.measurements,
    )


def analyze_run(
    run: TestRunInput,
    settings: AnalysisSettings,
    progress_callback=None,
) -> RunResult:
    host_events = parse_host_timeouts(run.host_log_paths)
    results: list[BoardResult] = []
    total = max(1, len(run.boards))

    for index, board in enumerate(run.boards, start=1):
        results.append(analyze_board(run, board, host_events, settings))
        if progress_callback:
            progress_callback(index / total, f"Analyzed {board.key}")

    return RunResult(
        run=run,
        boards=results,
        generated_at=datetime.now(UTC),
    )
