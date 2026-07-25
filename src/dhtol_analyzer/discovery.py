from __future__ import annotations

from pathlib import Path

from dhtol_analyzer.models import BoardInput, TestRunInput
from dhtol_analyzer.parsers import parse_config_json, parse_planned_seconds


def _matching_file(
    root: Path,
    suffix: str,
    test_name: str,
    dut_name: str | None = None,
) -> Path | None:
    candidates = []
    for path in root.glob(f"*{suffix}"):
        name = path.name.lower()
        if test_name.lower() not in name:
            continue
        if dut_name and dut_name.lower() not in name:
            continue
        candidates.append(path)
    return sorted(candidates, key=lambda path: path.name)[0] if candidates else None


def _matching_logs(
    root: Path,
    test_name: str,
    dut_name: str,
) -> list[Path]:
    return sorted(
        [
            path
            for path in root.glob("*.log")
            if test_name.lower() in path.name.lower()
            and dut_name.lower() in path.name.lower()
        ],
        key=lambda path: path.name,
    )


def discover_runs(root: Path) -> list[TestRunInput]:
    runs: list[TestRunInput] = []

    for config_path in sorted(root.rglob("*.json")):
        config = parse_config_json(config_path)
        if not config.entries:
            continue

        run_root = config_path.parent
        mtpx_path = _matching_file(run_root, ".mtpx", config.test_name)
        planned_seconds = (
            parse_planned_seconds(mtpx_path) if mtpx_path else None
        )
        warnings = list(config.warnings)
        if planned_seconds is None:
            planned_seconds = 0.0
            warnings.append("No planned duration found in MTPX.")

        boards: list[BoardInput] = []
        for entry in config.entries:
            boards.append(
                BoardInput(
                    zone=entry.zone,
                    position=entry.position,
                    dut_name=entry.dut_name,
                    hw_target=entry.hw_target,
                    data_path=_matching_file(
                        run_root,
                        ".data",
                        config.test_name,
                        entry.dut_name,
                    ),
                    log_paths=_matching_logs(
                        run_root,
                        config.test_name,
                        entry.dut_name,
                    ),
                )
            )

        board_log_paths = {
            path.resolve()
            for board in boards
            for path in board.log_paths
        }
        host_log_paths = sorted(
            [
                path
                for path in run_root.glob("*.log")
                if config.test_name.lower() in path.name.lower()
                and path.resolve() not in board_log_paths
            ],
            key=lambda path: path.name,
        )

        runs.append(
            TestRunInput(
                test_name=config.test_name,
                root_path=run_root,
                planned_seconds=planned_seconds,
                boards=boards,
                host_log_paths=host_log_paths,
                warnings=warnings,
            )
        )

    return runs