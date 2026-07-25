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
