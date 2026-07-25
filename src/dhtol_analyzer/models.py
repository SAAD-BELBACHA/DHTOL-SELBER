from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

import pandas as pd


class Status(str, Enum):
    PASS = "Pass"
    REVIEW = "Review"
    FAIL = "Fail"


class FaultType(str, Enum):
    OC = "OC"
    OV = "OV"
    OT = "OT"
    NETWORK = "Network"
    GERR = "GERR"
    NONE = "None"


@dataclass(frozen=True)
class OvenplanEntry:
    zone: str
    position: int
    dut_name: str
    hw_target: str


@dataclass
class ParsedConfig:
    test_name: str
    entries: list[OvenplanEntry] = field(default_factory=list)
    source_path: Path | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class BoardMetadata:
    stress_seconds: float
    firmware_version: str
    source_path: Path


@dataclass(frozen=True)
class BoardEvent:
    timestamp: datetime
    text: str
    fault_type: FaultType
    source_path: Path


@dataclass
class BoardLogScan:
    measurements: pd.DataFrame
    events: list[BoardEvent]
    first_timestamp: datetime | None
    last_timestamp: datetime | None
    measurement_count: int
    skipped_lines: int

    @property
    def available_seconds(self) -> float:
        if self.first_timestamp is None or self.last_timestamp is None:
            return 0.0
        return max(
            0.0,
            (self.last_timestamp - self.first_timestamp).total_seconds(),
        )


@dataclass
class BoardInput:
    zone: str
    position: int
    dut_name: str
    hw_target: str
    data_path: Path | None
    log_paths: list[Path]

    @property
    def key(self) -> str:
        return f"{self.zone}{self.position}:{self.dut_name}"


@dataclass
class TestRunInput:
    test_name: str
    root_path: Path
    planned_seconds: float
    boards: list[BoardInput]
    host_log_paths: list[Path]
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Evidence:
    level: Status
    rule: str
    reason: str
    source_path: Path | None = None
    timestamp: datetime | None = None
    measured_value: float | str | None = None
    threshold: float | str | None = None


@dataclass
class BoardResult:
    board: BoardInput
    status: Status
    planned_seconds: float
    stress_seconds: float
    post_stress_seconds: float
    available_log_seconds: float
    evidence: list[Evidence]
    measurements: pd.DataFrame


@dataclass
class RunResult:
    run: TestRunInput
    boards: list[BoardResult]
    generated_at: datetime