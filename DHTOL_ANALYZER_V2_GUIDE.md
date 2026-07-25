# DHTOL Analyzer V2 — Complete Guided Build

This document is an instruction manual. You run every command and create every
project file yourself. Follow sections in order. Do not copy the entire guide
into the terminal.

The finished MVP:

- runs locally with Python 3.12 and Streamlit;
- runs on your MacBook;
- reads measurement folders directly from disk;
- does not upload or copy folders larger than 2 GB;
- parses JSON, MTPX, DATA, board LOG, and host LOG files;
- displays Pass, Review, and Fail with supporting evidence;
- creates downsampled Plotly charts;
- exports a PDF summary;
- excludes Docker, cloud deployment, TDMS, accounts, and databases.

---

## 1. Install tools

Install Homebrew from <https://brew.sh> if it is missing. Then run:

```bash
brew install python@3.12 git gh
python3.12 --version
git --version
gh --version
gh auth login
```

Python runs application code. Git records local history. GitHub stores pushed
commits online. GitHub CLI creates and manages repository from terminal.

---

## 2. Create project and GitHub repository

```bash
cd ~/Desktop
mkdir dhtol-analyzer-v2
cd dhtol-analyzer-v2
git init
git branch -M main
```

Create `README.md`:

```markdown
# DHTOL Analyzer V2

Local application for analyzing DHTOL measurement folders.

## Goals

- Read large measurement folders directly from disk
- Support macOS
- Calculate stress and post-stress duration
- Detect measurement faults and temperature problems
- Explain Pass, Review, and Fail decisions
- Produce charts and PDF reports
```

Commit and create GitHub repository:

```bash
git add README.md
git commit -m "Initialize DHTOL Analyzer V2"
gh repo create dhtol-analyzer-v2 --public --source=. --remote=origin --push
```

`git commit` saves snapshot locally. `git push` sends committed snapshots to
GitHub.

---

## 3. Create Python environment

A virtual environment isolates this project's packages from other Python
projects.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

The terminal prompt should now start with `(.venv)`.

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=75"]
build-backend = "setuptools.build_meta"

[project]
name = "dhtol-analyzer"
version = "0.1.0"
description = "Local DHTOL measurement analyzer"
requires-python = ">=3.12,<3.13"
dependencies = [
    "streamlit>=1.47,<2",
    "pandas>=2.2,<3",
    "numpy>=2.0,<3",
    "plotly>=6,<7",
    "reportlab>=4,<5",
    "kaleido>=1,<2",
]

[project.optional-dependencies]
dev = [
    "pytest>=8,<9",
    "pytest-cov>=6,<7",
    "ruff>=0.12,<1",
]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]

[tool.ruff]
line-length = 88
target-version = "py312"
```

Create `.gitignore`:

```gitignore
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.coverage
htmlcov/
build/
dist/
*.egg-info/
.DS_Store
Thumbs.db
.streamlit/secrets.toml
reports/
measurement-data/
*.tdms
```

Install project:

```bash
python -m pip install -e ".[dev]"
python -m pip list
```

`-e` means editable install. Changes under `src/` become available without
reinstalling package.

Commit:

```bash
git add pyproject.toml .gitignore
git commit -m "Configure Python environment"
git push
```

---

## 4. Create project structure

Create folders.

```bash
mkdir -p src/dhtol_analyzer tests scripts
touch src/dhtol_analyzer/__init__.py
```

Final structure:

```text
dhtol-analyzer-v2/
├── app.py
├── pyproject.toml
├── README.md
├── src/
│   └── dhtol_analyzer/
│       ├── __init__.py
│       ├── models.py
│       ├── settings.py
│       ├── folder_picker.py
│       ├── folder_scan.py
│       ├── parsers.py
│       ├── discovery.py
│       ├── analysis.py
│       ├── charts.py
│       └── pdf_report.py
├── tests/
│   ├── test_folder_scan.py
│   ├── test_parsers.py
│   └── test_analysis.py
└── scripts/
```

Dependency direction:

```text
Streamlit UI -> discovery/analysis/reporting -> parsers -> models/settings
```

Parsers must not import Streamlit. This keeps file logic testable without
starting browser interface.

---

## 5. Define shared data models

Create `src/dhtol_analyzer/models.py`:

```python
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
```

Dataclasses describe application data. Enums prevent inconsistent status
spellings. `Path` represents macOS filesystem paths safely.

Create `src/dhtol_analyzer/settings.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class AnalysisSettings:
    temperature_min_c: float = -10.0
    temperature_max_c: float = 250.0
    temperature_max_rate_c_per_s: float = 20.0
    missing_log_warning_seconds: float = 300.0
    fault_confirmation_window_seconds: float = 2.0
    max_chart_points_per_board: int = 5_000
    max_evidence_per_rule: int = 100
```

Named settings explain every threshold and allow tests to override defaults.

Commit:

```bash
git add src
git commit -m "Add shared data models and analysis settings"
git push
```

---

## 6. Select and scan measurement folder

Create `src/dhtol_analyzer/folder_picker.py`:

```python
from __future__ import annotations

import subprocess


def choose_directory() -> str | None:
    command = [
        "osascript",
        "-e",
        'POSIX path of (choose folder with prompt "Select measurement folder")',
    ]

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    selected = completed.stdout.strip()
    return selected or None
```

Native macOS dialog works because app and browser run on same MacBook. Manual
path field remains fallback.

Create `src/dhtol_analyzer/folder_scan.py`:

```python
from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


SUPPORTED_SUFFIXES = {".json", ".mtpx", ".data", ".log"}


@dataclass
class FolderScan:
    root: Path
    files: list[Path]
    counts: dict[str, int]
    total_bytes: int


def validate_folder(value: str) -> tuple[Path | None, str | None]:
    text = value.strip()
    if not text:
        return None, "Select or enter a measurement folder."

    root = Path(text).expanduser()
    if not root.exists():
        return None, "Folder does not exist."
    if not root.is_dir():
        return None, "Selected path is not a folder."
    if not os.access(root, os.R_OK):
        return None, "Folder is not readable."
    return root.resolve(), None


def scan_folder(root: Path) -> FolderScan:
    files: list[Path] = []
    counts: Counter[str] = Counter()
    total_bytes = 0

    for current_root, directory_names, file_names in os.walk(root):
        directory_names[:] = [
            name for name in directory_names if not name.startswith(".")
        ]
        current = Path(current_root)

        for name in file_names:
            path = current / name
            suffix = path.suffix.lower()
            if suffix not in SUPPORTED_SUFFIXES:
                continue
            files.append(path)
            counts[suffix] += 1
            try:
                total_bytes += path.stat().st_size
            except OSError:
                continue

    files.sort(key=lambda path: str(path.relative_to(root)).lower())
    return FolderScan(
        root=root,
        files=files,
        counts=dict(counts),
        total_bytes=total_bytes,
    )
```

`os.walk` visits paths without reading file contents. Scanning 2 GB therefore
does not load 2 GB into memory.

Create `tests/test_folder_scan.py`:

```python
from dhtol_analyzer.folder_scan import scan_folder, validate_folder


def test_scan_counts_only_supported_files(tmp_path):
    (tmp_path / "run.json").write_text("{}", encoding="utf-8")
    (tmp_path / "board.log").write_text("line", encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("ignored", encoding="utf-8")

    result = scan_folder(tmp_path)

    assert result.counts == {".json": 1, ".log": 1}
    assert len(result.files) == 2


def test_validate_rejects_missing_folder(tmp_path):
    root, error = validate_folder(str(tmp_path / "missing"))

    assert root is None
    assert error == "Folder does not exist."
```

Run:

```bash
pytest tests/test_folder_scan.py -v
```

Commit:

```bash
git add src/dhtol_analyzer/folder_picker.py \
  src/dhtol_analyzer/folder_scan.py tests/test_folder_scan.py
git commit -m "Add local folder selection and scanning"
git push
```

---

## 7. Implement file parsers

Create `src/dhtol_analyzer/parsers.py`:

```python
from __future__ import annotations

import ast
import json
import math
import operator
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

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
            warnings.append(
                f"Ovenplan row {index} has invalid DUT, zone, or slot."
            )
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
    total_bytes = sum(
        path.stat().st_size for path in ordered if path.exists()
    )
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

    if last_measurement is not None:
        if not rows or rows[-1][0] != last_measurement[0]:
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
                    timestamp = datetime.fromisoformat(
                        match.group("timestamp").strip()
                    )
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
```

Important large-file behavior:

- each LOG file is read one line at a time;
- only downsampled measurements enter dataframe;
- fault events remain preserved;
- entire measurement folder never enters memory;
- first and last measurements remain present.

Create `tests/test_parsers.py`:

```python
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
                "HW History": [
                    {"HW Info": {"version": {"fw": "1.2.3"}}}
                ],
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
        "\n".join(
            [
                "2026-01-01T10:00:00\t"
                "12.0;1.0;0.1;5.0;5.0;0.2;125.0;126.0",
                "2026-01-01T10:00:01\tOC ERR",
                "2026-01-01T10:00:02\t"
                "12.0;0.0;0.1;5.0;5.0;0.2;125.0;126.0",
            ]
        ),
        encoding="utf-8",
    )

    result = scan_board_logs([path])

    assert result.measurement_count == 2
    assert len(result.events) == 1
    assert result.events[0].fault_type is FaultType.OC
    assert result.first_timestamp == datetime(2026, 1, 1, 10, 0, 0)
```

Run:

```bash
pytest tests/test_parsers.py -v
ruff check src tests
```

Commit:

```bash
git add src/dhtol_analyzer/parsers.py tests/test_parsers.py
git commit -m "Add DHTOL file parsers"
git push
```

---

## 8. Discover test runs and map boards

Create `src/dhtol_analyzer/discovery.py`:

```python
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
```

This version intentionally uses clear filename matching. Test it against real
folder names. Change matching rules only after recording failing real examples
as tests.

Commit:

```bash
git add src/dhtol_analyzer/discovery.py
git commit -m "Add test-run discovery and board mapping"
git push
```

---

## 9. Implement analysis and status rules

Create `src/dhtol_analyzer/analysis.py`:

```python
from __future__ import annotations

from datetime import datetime

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

        for index in frame.index[invalid][
            : settings.max_evidence_per_rule
        ]:
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
        for index in frame.index[too_fast][
            : settings.max_evidence_per_rule
        ]:
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
        generated_at=datetime.now(),
    )
```

Status meaning:

- Pass: no evidence requiring action.
- Review: missing data, suspicious temperature, unconfirmed fault, or incomplete
  log coverage.
- Fail: same fault appears in board and host logs within confirmation window.

Create `tests/test_analysis.py`:

```python
from dhtol_analyzer.analysis import calculate_post_stress_seconds


def test_post_stress_is_planned_minus_stress():
    assert calculate_post_stress_seconds(1000, 640) == 360


def test_post_stress_never_becomes_negative():
    assert calculate_post_stress_seconds(100, 120) == 0
```

Run:

```bash
pytest -v
ruff check src tests
```

Commit:

```bash
git add src/dhtol_analyzer/analysis.py tests/test_analysis.py
git commit -m "Add analysis and status engine"
git push
```

---

## 10. Create charts

Create `src/dhtol_analyzer/charts.py`:

```python
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from dhtol_analyzer.models import RunResult


def stress_chart(result: RunResult) -> go.Figure:
    rows = []
    for board in result.boards:
        rows.extend(
            [
                {
                    "Board": board.board.key,
                    "Duration": "Stress",
                    "Hours": board.stress_seconds / 3600,
                },
                {
                    "Board": board.board.key,
                    "Duration": "Post-stress",
                    "Hours": board.post_stress_seconds / 3600,
                },
            ]
        )
    frame = pd.DataFrame(rows)
    return px.bar(
        frame,
        x="Board",
        y="Hours",
        color="Duration",
        barmode="stack",
        title="Stress and post-stress duration",
    )


def temperature_chart(result: RunResult) -> go.Figure:
    figure = go.Figure()
    for board in result.boards:
        frame = board.measurements
        if frame.empty:
            continue
        figure.add_trace(
            go.Scattergl(
                x=frame["timestamp"],
                y=frame["t0"],
                mode="lines",
                name=f"{board.board.key} T0",
            )
        )
        figure.add_trace(
            go.Scattergl(
                x=frame["timestamp"],
                y=frame["t1"],
                mode="lines",
                name=f"{board.board.key} T1",
            )
        )
    figure.update_layout(
        title="Board temperatures",
        xaxis_title="Time",
        yaxis_title="Temperature [°C]",
    )
    return figure


def current_chart(result: RunResult) -> go.Figure:
    figure = go.Figure()
    for board in result.boards:
        frame = board.measurements
        if frame.empty:
            continue
        figure.add_trace(
            go.Scattergl(
                x=frame["timestamp"],
                y=frame["current"],
                mode="lines",
                name=board.board.key,
            )
        )
    figure.update_layout(
        title="Board current",
        xaxis_title="Time",
        yaxis_title="Current [A]",
    )
    return figure


def voltage_chart(result: RunResult) -> go.Figure:
    figure = go.Figure()
    for board in result.boards:
        frame = board.measurements
        if frame.empty:
            continue
        figure.add_trace(
            go.Scattergl(
                x=frame["timestamp"],
                y=frame["v_in"],
                mode="lines",
                name=f"{board.board.key} Vin",
            )
        )
        figure.add_trace(
            go.Scattergl(
                x=frame["timestamp"],
                y=frame["vout_dut"],
                mode="lines",
                name=f"{board.board.key} Vout DUT",
            )
        )
    figure.update_layout(
        title="Board voltages",
        xaxis_title="Time",
        yaxis_title="Voltage [V]",
    )
    return figure
```

`Scattergl` uses browser GPU rendering and works better for thousands of
points. Downsampling happens during parsing, before chart creation.

Commit:

```bash
git add src/dhtol_analyzer/charts.py
git commit -m "Add analysis charts"
git push
```

---

## 11. Create PDF report

Create `src/dhtol_analyzer/pdf_report.py`:

```python
from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from dhtol_analyzer.models import RunResult


def report_filename(test_name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", test_name).strip("._")
    return f"dhtol_report_{safe or 'run'}.pdf"


def build_pdf(result: RunResult, engineer_notes: str = "") -> bytes:
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=30,
        rightMargin=30,
        topMargin=30,
        bottomMargin=30,
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph("DHTOL Analysis Report", styles["Title"]),
        Spacer(1, 12),
        Paragraph(f"Test run: {result.run.test_name}", styles["BodyText"]),
        Paragraph(
            f"Generated: {result.generated_at.isoformat(timespec='seconds')}",
            styles["BodyText"],
        ),
        Spacer(1, 12),
    ]

    rows = [
        [
            "Board",
            "Status",
            "Planned [h]",
            "Stress [h]",
            "Post-stress [h]",
            "Evidence",
        ]
    ]
    for board in result.boards:
        rows.append(
            [
                board.board.key,
                board.status.value,
                f"{board.planned_seconds / 3600:.2f}",
                f"{board.stress_seconds / 3600:.2f}",
                f"{board.post_stress_seconds / 3600:.2f}",
                str(len(board.evidence)),
            ]
        )

    table = Table(rows, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.whitesmoke]),
            ]
        )
    )
    story.extend([table, Spacer(1, 16)])

    if engineer_notes.strip():
        story.extend(
            [
                Paragraph("Engineer notes", styles["Heading2"]),
                Paragraph(engineer_notes.strip(), styles["BodyText"]),
                Spacer(1, 12),
            ]
        )

    story.append(Paragraph("Evidence", styles["Heading2"]))
    for board in result.boards:
        story.append(
            Paragraph(
                f"{board.board.key} — {board.status.value}",
                styles["Heading3"],
            )
        )
        if not board.evidence:
            story.append(Paragraph("No issues detected.", styles["BodyText"]))
        for item in board.evidence:
            timestamp = (
                item.timestamp.isoformat(timespec="seconds")
                if item.timestamp
                else "No timestamp"
            )
            story.append(
                Paragraph(
                    f"{timestamp} | {item.rule} | {item.reason}",
                    styles["BodyText"],
                )
            )

    document.build(story)
    return buffer.getvalue()


def save_pdf(result: RunResult, destination: Path, engineer_notes: str = "") -> Path:
    destination.write_bytes(build_pdf(result, engineer_notes))
    return destination
```

First PDF version contains same calculations and evidence as UI. Add chart images
only after table values match, because correctness matters before decoration.

Commit:

```bash
git add src/dhtol_analyzer/pdf_report.py
git commit -m "Add PDF report generation"
git push
```

---

## 12. Build guided Streamlit interface

Create `app.py`:

```python
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from dhtol_analyzer.analysis import analyze_run
from dhtol_analyzer.charts import (
    current_chart,
    stress_chart,
    temperature_chart,
    voltage_chart,
)
from dhtol_analyzer.discovery import discover_runs
from dhtol_analyzer.folder_picker import choose_directory
from dhtol_analyzer.folder_scan import scan_folder, validate_folder
from dhtol_analyzer.pdf_report import build_pdf, report_filename
from dhtol_analyzer.settings import AnalysisSettings


st.set_page_config(
    page_title="DHTOL Analyzer V2",
    page_icon="📊",
    layout="wide",
)

st.title("DHTOL Analyzer V2")
st.caption("Local measurement analysis with explainable results")

if "folder_path" not in st.session_state:
    st.session_state.folder_path = ""
if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None

st.header("1. Select measurement folder")
folder_column, button_column = st.columns([5, 1])
with folder_column:
    folder_value = st.text_input(
        "Folder path",
        key="folder_path",
        placeholder="/path/to/measurement/folder",
    )
with button_column:
    st.write("")
    st.write("")
    if st.button("Browse"):
        selected = choose_directory()
        if selected:
            st.session_state.folder_path = selected
            st.session_state.analysis_result = None
            st.rerun()

root, folder_error = validate_folder(folder_value)
if folder_error:
    st.info(folder_error)
    st.stop()

st.header("2. Validate files")
with st.spinner("Scanning supported files..."):
    folder_scan = scan_folder(root)

metric_columns = st.columns(5)
for column, suffix in zip(
    metric_columns,
    [".json", ".mtpx", ".data", ".log"],
):
    column.metric(suffix.upper(), folder_scan.counts.get(suffix, 0))
metric_columns[4].metric(
    "Supported size",
    f"{folder_scan.total_bytes / (1024 ** 3):.2f} GB",
)

if not folder_scan.files:
    st.error("No supported files found.")
    st.stop()

st.header("3. Review test run and board mapping")
runs = discover_runs(root)
if not runs:
    st.error("No test run with a valid Ovenplan was discovered.")
    st.stop()

run_names = [run.test_name for run in runs]
selected_name = st.selectbox("Test run", run_names)
selected_run = runs[run_names.index(selected_name)]

for warning in selected_run.warnings:
    st.warning(warning)

mapping_rows = [
    {
        "Zone": board.zone,
        "Position": board.position,
        "DUT": board.dut_name,
        "HW target": board.hw_target,
        "DATA": str(board.data_path or ""),
        "LOG files": len(board.log_paths),
    }
    for board in selected_run.boards
]
st.dataframe(pd.DataFrame(mapping_rows), hide_index=True, use_container_width=True)

st.header("4. Configure analysis")
with st.expander("Advanced settings"):
    minimum_temperature = st.number_input(
        "Minimum physical temperature [°C]",
        value=-10.0,
    )
    maximum_temperature = st.number_input(
        "Maximum physical temperature [°C]",
        value=250.0,
    )
    maximum_rate = st.number_input(
        "Maximum temperature rate [°C/s]",
        min_value=0.1,
        value=20.0,
    )
    missing_log_warning = st.number_input(
        "Missing log warning [seconds]",
        min_value=0.0,
        value=300.0,
    )

settings = AnalysisSettings(
    temperature_min_c=minimum_temperature,
    temperature_max_c=maximum_temperature,
    temperature_max_rate_c_per_s=maximum_rate,
    missing_log_warning_seconds=missing_log_warning,
)

st.header("5. Run analysis")
if st.button("Run analysis", type="primary"):
    progress = st.progress(0.0, text="Starting analysis...")

    def update_progress(value: float, message: str) -> None:
        progress.progress(value, text=message)

    st.session_state.analysis_result = analyze_run(
        selected_run,
        settings,
        progress_callback=update_progress,
    )
    progress.empty()

result = st.session_state.analysis_result
if result is None:
    st.stop()

st.header("6. Review results")
status_counts = pd.Series(
    [board.status.value for board in result.boards]
).value_counts()
summary_columns = st.columns(3)
summary_columns[0].metric("Pass", int(status_counts.get("Pass", 0)))
summary_columns[1].metric("Review", int(status_counts.get("Review", 0)))
summary_columns[2].metric("Fail", int(status_counts.get("Fail", 0)))

overview_rows = [
    {
        "Board": board.board.key,
        "Status": board.status.value,
        "Planned [h]": board.planned_seconds / 3600,
        "Stress [h]": board.stress_seconds / 3600,
        "Post-stress [h]": board.post_stress_seconds / 3600,
        "Board LOG [h]": board.available_log_seconds / 3600,
        "Evidence": len(board.evidence),
    }
    for board in result.boards
]
st.dataframe(
    pd.DataFrame(overview_rows),
    hide_index=True,
    use_container_width=True,
)

overview_tab, board_tab, chart_tab = st.tabs(
    ["Overview", "Board evidence", "Charts"]
)

with overview_tab:
    st.plotly_chart(stress_chart(result), use_container_width=True)

with board_tab:
    board_keys = [board.board.key for board in result.boards]
    selected_board_key = st.selectbox("Board", board_keys)
    board_result = next(
        board
        for board in result.boards
        if board.board.key == selected_board_key
    )
    st.subheader(f"{board_result.status.value}: {selected_board_key}")
    evidence_rows = [
        {
            "Level": item.level.value,
            "Rule": item.rule,
            "Reason": item.reason,
            "Timestamp": item.timestamp,
            "Value": item.measured_value,
            "Threshold": item.threshold,
            "Source": str(item.source_path or ""),
        }
        for item in board_result.evidence
    ]
    if evidence_rows:
        st.dataframe(
            pd.DataFrame(evidence_rows),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.success("No issues detected.")

with chart_tab:
    st.plotly_chart(temperature_chart(result), use_container_width=True)
    st.plotly_chart(current_chart(result), use_container_width=True)
    st.plotly_chart(voltage_chart(result), use_container_width=True)

st.header("7. Export report")
engineer_notes = st.text_area("Engineer notes")
pdf_bytes = build_pdf(result, engineer_notes)
st.download_button(
    "Download PDF report",
    data=pdf_bytes,
    file_name=report_filename(result.run.test_name),
    mime="application/pdf",
)

if st.button("Reset session"):
    st.session_state.analysis_result = None
    st.rerun()
```

Run application:

```bash
streamlit run app.py
```

Browser address:

```text
http://localhost:8501
```

Streamlit reruns `app.py` after widget changes. `st.session_state` keeps selected
folder and completed analysis between reruns.

Stop server with `Control+C`.

Commit:

```bash
git add app.py
git commit -m "Add guided Streamlit workflow"
git push
```

---

## 13. Add macOS setup and launch scripts

Create `scripts/setup_macos.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
pytest
```

Create `scripts/run_macos.command`:

```bash
#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate
python -m streamlit run app.py
```

Make macOS scripts executable:

```bash
chmod +x scripts/setup_macos.sh scripts/run_macos.command
```

Commit:

```bash
git add scripts
git commit -m "Add macOS setup and launch scripts"
git push
```

---

## 14. Quality checks

Run before every release:

```bash
pytest -v
pytest --cov=dhtol_analyzer --cov-report=term-missing
ruff check src tests app.py
ruff format --check src tests app.py
```

Apply formatting when required:

```bash
ruff format src tests app.py
```

Review Git changes:

```bash
git status
git diff
```

Commit only understood changes:

```bash
git add .
git commit -m "Improve analyzer quality"
git push
```

---

## 15. Test with real data safely

Never commit real measurement data.

1. Start application.
2. Select sanitized measurement folder.
3. Check detected file counts.
4. Check board mapping against Ovenplan.
5. Check planned time against MTPX.
6. Check stress time against DATA.
7. Open several boards and compare chart values with raw LOG lines.
8. Check every Fail has matching board and host evidence.
9. Check incomplete files become Review instead of Pass.
10. Export PDF and compare values with UI.

If filename mapping fails, add failing filename to test before changing
`discovery.py`. Real naming conventions are part of parser specification.

For performance measurement:

```bash
/usr/bin/time -l python -m pytest
```

The parser must continue reading logs line by line. Do not replace it with
`read_text()`, `readlines()`, or one large `pandas.read_csv()` for multi-GB
logs.

---

## 16. Create local release

Ensure clean tests:

```bash
pytest
ruff check src tests app.py
git status
```

Update version in `pyproject.toml` to `0.1.0`, update README installation
instructions, then:

```bash
git add .
git commit -m "Prepare v0.1.0 local release"
git push
git tag -a v0.1.0 -m "DHTOL Analyzer V2 MVP"
git push origin v0.1.0
gh release create v0.1.0 \
  --title "DHTOL Analyzer V2 v0.1.0" \
  --notes "Local macOS MVP."
```

Fresh-machine installation:

```bash
git clone https://github.com/SAAD-BELBACHA/dhtol-analyzer-v2.git
cd dhtol-analyzer-v2
```

```bash
./scripts/setup_macos.sh
./scripts/run_macos.command
```

---

## Important MVP limitations

- Temperature rate checks operate on downsampled chart data in this first
  version. Move exact temperature checks into streaming parser before using
  status for formal production decisions.
- Filename discovery must be validated against sanitized real filenames.
- Fail confirmation currently requires matching fault type, DUT name, and time
  between board and host logs.
- PDF contains summaries and evidence but not chart images yet.
- Zone-current analysis, instability/dead-sensor windows, cancellation, editable
  mapping, chart images in PDF, and advanced cache invalidation are next
  iterations.
- Application remains engineering support tool. Engineer validates final test
  disposition.

Do not add TDMS, Docker, cloud hosting, login, database, or saved analysis
history until MVP calculations and real-folder tests are reliable.
