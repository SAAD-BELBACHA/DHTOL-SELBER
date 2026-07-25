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
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.whitesmoke],
                ),
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


def save_pdf(
    result: RunResult,
    destination: Path,
    engineer_notes: str = "",
) -> Path:
    destination.write_bytes(build_pdf(result, engineer_notes))
    return destination
