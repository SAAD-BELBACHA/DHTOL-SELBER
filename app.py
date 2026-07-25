from __future__ import annotations

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
    strict=False,
):
    column.metric(suffix.upper(), folder_scan.counts.get(suffix, 0))
metric_columns[4].metric(
    "Supported size",
    f"{folder_scan.total_bytes / (1024**3):.2f} GB",
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

overview_tab, board_tab, chart_tab = st.tabs(["Overview", "Board evidence", "Charts"])

with overview_tab:
    st.plotly_chart(stress_chart(result), use_container_width=True)

with board_tab:
    board_keys = [board.board.key for board in result.boards]
    selected_board_key = st.selectbox("Board", board_keys)
    board_result = next(
        board for board in result.boards if board.board.key == selected_board_key
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
