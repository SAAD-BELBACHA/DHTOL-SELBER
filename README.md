# DHTOL Analyzer V2

Local application for analyzing DHTOL measurement folders.

## Goals

- Read large measurement folders directly from disk
- Support macOS
- Calculate stress and post-stress duration
- Detect measurement faults and temperature problems
- Explain Pass, Review, and Fail decisions
- Produce charts and PDF reports

## Requirements

- macOS
- Python 3.12
- Git

## Installation

Clone the repository and run the setup script:

```bash
git clone https://github.com/SAAD-BELBACHA/DHTOL-SELBER.git
cd DHTOL-SELBER
./scripts/setup_macos.sh
```

## Run

Start the local Streamlit application:

```bash
./scripts/run_macos.command
```

Then open <http://localhost:8501> if the browser does not open automatically.

## Quality checks

```bash
source .venv/bin/activate
pytest -v
pytest --cov=dhtol_analyzer --cov-report=term-missing
ruff check src tests app.py
ruff format --check src tests app.py
```

## Data safety

Measurement folders are read directly from disk. They are not uploaded or
copied into this repository. Keep real measurement data outside version
control.

## MVP limitations

- Temperature-rate checks use downsampled chart data.
- Filename discovery requires validation against sanitized real filenames.
- PDF reports contain summaries and evidence, but no chart images.
- Engineers must validate final test disposition.
