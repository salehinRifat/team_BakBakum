"""
Deterministic guardrail validator for interpreted operator directives.
Implements Section 08 and Section 05.1 of BUP CSE Fest 2026 Problem Statement.
"""

import math
from typing import List
from app.schemas import DirectiveInterpretation, BatteryData

ALLOWED_DIRECTIVE_TYPES = {
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op",
}


def validate_and_sanitize_directives(
    directives: List[DirectiveInterpretation],
    num_notes: int,
    battery: BatteryData
) -> List[DirectiveInterpretation]:
    """
    Validates and deterministically sanitizes directives before optimization.
    Ensures safe failure without crashing or hallucinating constraints.
    """
    sanitized: List[DirectiveInterpretation] = []

    # Map by note_index to guarantee exact 0..N-1 order
    dir_by_index = {d.note_index: d for d in directives if 0 <= d.note_index < num_notes}

    for idx in range(num_notes):
        d = dir_by_index.get(idx)
        if not d:
            # Safe failure: missing note index becomes safe no_op
            sanitized.append(
                DirectiveInterpretation(
                    note_index=idx,
                    applies=False,
                    directive_type="no_op",
                    structured_adjustment=None,
                    explanation="Defaulted to no_op due to missing interpretation entry."
                )
            )
            continue

        dtype = d.directive_type
        if dtype not in ALLOWED_DIRECTIVE_TYPES:
            # Unsupported type becomes no_op
            sanitized.append(
                DirectiveInterpretation(
                    note_index=idx,
                    applies=False,
                    directive_type="no_op",
                    structured_adjustment=None,
                    explanation=f"Unsupported directive type '{dtype}' mapped to safe no_op."
                )
            )
            continue

        if dtype == "no_op":
            sanitized.append(
                DirectiveInterpretation(
                    note_index=idx,
                    applies=False,
                    directive_type="no_op",
                    structured_adjustment=None,
                    explanation=d.explanation or "No operational scheduling impact."
                )
            )
            continue

        # For non-no_op: applies MUST be true
        applies = True
        adj = d.structured_adjustment or {}

        # Validate hours
        raw_hours = adj.get("hours", [])
        if not isinstance(raw_hours, list):
            raw_hours = []

        valid_hours = sorted(list(set(
            int(h) for h in raw_hours if isinstance(h, (int, float)) and 0 <= int(h) <= 23
        )))

        clean_adj = {"hours": valid_hours}

        if dtype == "solar_reduction":
            raw_factor = adj.get("factor", 1.0)
            try:
                factor = float(raw_factor)
                if math.isnan(factor) or math.isinf(factor):
                    factor = 1.0
                factor = max(0.0, min(1.0, factor))
            except (ValueError, TypeError):
                factor = 1.0
            clean_adj["factor"] = factor

        elif dtype == "minimum_battery_reserve":
            raw_min = adj.get("minimum_energy_kwh", battery.minimum_energy_kwh)
            try:
                min_kwh = float(raw_min)
                if math.isnan(min_kwh) or math.isinf(min_kwh):
                    min_kwh = battery.minimum_energy_kwh
                min_kwh = max(0.0, min(battery.capacity_kwh, min_kwh))
            except (ValueError, TypeError):
                min_kwh = battery.minimum_energy_kwh
            clean_adj["minimum_energy_kwh"] = min_kwh

        elif dtype == "max_grid_window":
            raw_max = adj.get("max_grid_kwh", float("inf"))
            try:
                max_grid = float(raw_max)
                if math.isnan(max_grid) or max_grid < 0:
                    max_grid = 0.0
            except (ValueError, TypeError):
                max_grid = 0.0
            clean_adj["max_grid_kwh"] = max_grid

        sanitized.append(
            DirectiveInterpretation(
                note_index=idx,
                applies=applies,
                directive_type=dtype,
                structured_adjustment=clean_adj,
                explanation=d.explanation
            )
        )

    return sanitized
