from dataclasses import dataclass


@dataclass(frozen=True)
class AnalysisSettings:
    temperature_max_rate_c_per_s: float = 20.0
    missing_log_warning_seconds: float = 300.0
    fault_confirmation_window_seconds: float = 2.0
    max_chart_points_per_board: int = 5_000
    max_evidence_per_rule: int = 100
