"""
Mathematical Energy Optimization Solver for GridWise.
Uses Linear Programming (SciPy HiGHS) to find the globally optimal 24-hour schedule.
"""

import math
from typing import List, Tuple
import numpy as np
from scipy.optimize import linprog

from app.schemas import (
    HourData,
    BatteryData,
    DirectiveInterpretation,
    HourlyPlanItem,
)


def solve_energy_schedule(
    hours: List[HourData],
    battery: BatteryData,
    directives: List[DirectiveInterpretation],
) -> List[HourlyPlanItem]:
    """
    Formulates and solves the 24-hour cost minimization LP subject to all physical,
    battery, and operator-directive constraints.
    """
    n_hours = 24
    eff_solar = [h.solar_kwh for h in hours]
    min_res = [battery.minimum_energy_kwh] * n_hours
    max_charge = [battery.max_charge_kwh_per_hour] * n_hours
    max_discharge = [battery.max_discharge_kwh_per_hour] * n_hours
    max_grid = [float("inf")] * n_hours

    # Apply valid directives
    for d in directives:
        if not d.applies or not d.structured_adjustment:
            continue
        dtype = d.directive_type
        adj = d.structured_adjustment
        hrs = adj.get("hours", [])

        if dtype == "solar_reduction":
            factor = adj.get("factor", 1.0)
            for hr in hrs:
                if 0 <= hr < n_hours:
                    eff_solar[hr] = hours[hr].solar_kwh * factor

        elif dtype == "minimum_battery_reserve":
            min_kwh = adj.get("minimum_energy_kwh", battery.minimum_energy_kwh)
            for hr in hrs:
                if 0 <= hr < n_hours:
                    min_res[hr] = max(min_res[hr], min_kwh)

        elif dtype == "no_charge_window":
            for hr in hrs:
                if 0 <= hr < n_hours:
                    max_charge[hr] = 0.0

        elif dtype == "no_discharge_window":
            for hr in hrs:
                if 0 <= hr < n_hours:
                    max_discharge[hr] = 0.0

        elif dtype == "max_grid_window":
            g_cap = adj.get("max_grid_kwh", float("inf"))
            for hr in hrs:
                if 0 <= hr < n_hours:
                    max_grid[hr] = min(max_grid[hr], g_cap)

    # 120 variables:
    # 0..23:   grid_kwh (g_h)
    # 24..47:  solar_used_kwh (s_h)
    # 48..71:  battery_charge_kwh (c_h)
    # 72..95:  battery_discharge_kwh (d_h)
    # 96..119: battery_energy_after_kwh (E_h)
    total_vars = 120

    # Objective: min sum(g_h * tariff[h]) + small penalty for battery wear to prefer idle
    c_obj = np.zeros(total_vars)
    for h in range(n_hours):
        c_obj[h] = hours[h].tariff_bdt_per_kwh
        c_obj[48 + h] = 1e-6
        c_obj[72 + h] = 1e-6

    bounds: List[Tuple[float, float | None]] = []
    for h in range(n_hours):
        bounds.append((0.0, None if math.isinf(max_grid[h]) else max_grid[h]))
    for h in range(n_hours):
        bounds.append((0.0, eff_solar[h]))
    for h in range(n_hours):
        bounds.append((0.0, max_charge[h]))
    for h in range(n_hours):
        bounds.append((0.0, max_discharge[h]))
    for h in range(n_hours):
        bounds.append((min_res[h], battery.capacity_kwh))

    # Equalities:
    # 1. g_h + s_h + d_h - c_h = demand[h]  (24 eq)
    # 2. E_0 - c_0 + d_0 = initial_energy  (1 eq)
    # 3. E_h - E_{h-1} - c_h + d_h = 0      (23 eq)
    # 4. E_23 = initial_energy             (1 eq)
    n_eq = 49
    A_eq = np.zeros((n_eq, total_vars))
    b_eq = np.zeros(n_eq)

    # 1. Hourly Energy Balance
    for h in range(n_hours):
        A_eq[h, h] = 1.0
        A_eq[h, 24 + h] = 1.0
        A_eq[h, 72 + h] = 1.0
        A_eq[h, 48 + h] = -1.0
        b_eq[h] = hours[h].demand_kwh

    # 2. Battery State Transitions
    init_e = battery.initial_energy_kwh
    A_eq[24, 96 + 0] = 1.0
    A_eq[24, 48 + 0] = -1.0
    A_eq[24, 72 + 0] = 1.0
    b_eq[24] = init_e

    for h in range(1, n_hours):
        A_eq[24 + h, 96 + h] = 1.0
        A_eq[24 + h, 96 + h - 1] = -1.0
        A_eq[24 + h, 48 + h] = -1.0
        A_eq[24 + h, 72 + h] = 1.0
        b_eq[24 + h] = 0.0

    # 3. End-of-Day Neutrality
    A_eq[48, 96 + 23] = 1.0
    b_eq[48] = init_e

    res = linprog(c_obj, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")
    if not res.success:
        raise RuntimeError(f"Energy optimization failed: {res.message}")

    x = res.x
    plan: List[HourlyPlanItem] = []

    for h in range(n_hours):
        grid = max(0.0, float(x[h]))
        solar = max(0.0, min(eff_solar[h], float(x[24 + h])))
        charge = max(0.0, float(x[48 + h]))
        discharge = max(0.0, float(x[72 + h]))
        energy_after = max(min_res[h], min(battery.capacity_kwh, float(x[96 + h])))

        if charge > 1e-4:
            action = "charge"
            b_kwh = charge
        elif discharge > 1e-4:
            action = "discharge"
            b_kwh = discharge
        else:
            action = "idle"
            b_kwh = 0.0

        plan.append(
            HourlyPlanItem(
                hour=h,
                grid_kwh=round(grid, 4),
                solar_used_kwh=round(solar, 4),
                battery_action=action,
                battery_kwh=round(b_kwh, 4),
                battery_energy_after_kwh=round(energy_after, 4),
            )
        )

    return plan
