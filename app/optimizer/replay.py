"""
Replay verification and metrics calculation engine.
Audits every hour of the schedule against canonical physical and directive rules.
"""

from typing import List, Tuple
from app.schemas import (
    HourData,
    BatteryData,
    DirectiveInterpretation,
    HourlyPlanItem,
)


def replay_and_audit_schedule(
    plan: List[HourlyPlanItem],
    hours: List[HourData],
    battery: BatteryData,
    directives: List[DirectiveInterpretation],
) -> Tuple[float, float, float, str]:
    """
    Replays the 24-hour schedule, verifies zero constraint violations,
    recalculates totals, and generates a concise strategy summary.
    """
    n_hours = 24
    if len(plan) != n_hours:
        raise ValueError(f"Expected 24 plan items, got {len(plan)}")

    # 1. Compute effective solar and active bounds
    eff_solar = [h.solar_kwh for h in hours]
    min_res = [battery.minimum_energy_kwh] * n_hours
    max_charge = [battery.max_charge_kwh_per_hour] * n_hours
    max_discharge = [battery.max_discharge_kwh_per_hour] * n_hours
    max_grid = [float("inf")] * n_hours

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

    tol = 0.01  # Problem Statement tolerance
    prev_energy = battery.initial_energy_kwh
    total_grid = 0.0
    total_cost = 0.0
    peak_grid = 0.0

    charge_count = 0
    discharge_count = 0

    for h in range(n_hours):
        item = plan[h]
        g = item.grid_kwh
        s = item.solar_used_kwh
        act = item.battery_action
        b_kwh = item.battery_kwh
        e_after = item.battery_energy_after_kwh
        demand = hours[h].demand_kwh
        tariff = hours[h].tariff_bdt_per_kwh

        # Accumulate metrics
        total_grid += g
        total_cost += g * tariff
        if g > peak_grid:
            peak_grid = g

        c_val = b_kwh if act == "charge" else 0.0
        d_val = b_kwh if act == "discharge" else 0.0

        if act == "charge":
            charge_count += 1
        elif act == "discharge":
            discharge_count += 1

        # Check energy balance: grid + solar + discharge = demand + charge
        bal_diff = abs((g + s + d_val) - (demand + c_val))
        if bal_diff > tol:
            raise ValueError(f"Energy balance failed at hour {h}: diff={bal_diff:.4f}")

        # Check solar limit
        if s > eff_solar[h] + tol:
            raise ValueError(f"Solar overuse at hour {h}: used {s} > effective {eff_solar[h]}")

        # Check rate limits & windows
        if c_val > max_charge[h] + tol:
            raise ValueError(f"Charge rate or window violation at hour {h}: {c_val} > {max_charge[h]}")
        if d_val > max_discharge[h] + tol:
            raise ValueError(f"Discharge rate or window violation at hour {h}: {d_val} > {max_discharge[h]}")
        if g > max_grid[h] + tol:
            raise ValueError(f"Grid cap violation at hour {h}: grid {g} > cap {max_grid[h]}")

        # Check battery transition
        expected_e_after = prev_energy + c_val - d_val
        if abs(e_after - expected_e_after) > tol:
            raise ValueError(f"Battery transition mismatch at hour {h}: reported {e_after}, expected {expected_e_after}")

        # Check bounds
        if e_after < min_res[h] - tol:
            raise ValueError(f"Battery below reserve at hour {h}: {e_after} < {min_res[h]}")
        if e_after > battery.capacity_kwh + tol:
            raise ValueError(f"Battery above capacity at hour {h}: {e_after} > {battery.capacity_kwh}")

        prev_energy = e_after

    # Neutrality check
    if abs(prev_energy - battery.initial_energy_kwh) > tol:
        raise ValueError(f"End-of-day neutrality violated: final {prev_energy} != initial {battery.initial_energy_kwh}")

    # Generate plan summary
    active_directives_count = sum(1 for d in directives if d.applies)
    summary = (
        f"Optimized 24-hour campus energy schedule applying {active_directives_count} active operator directive(s). "
        f"Scheduled {charge_count} charging and {discharge_count} discharging cycles to shift load away from peak tariff "
        f"hours while maintaining all reserve margins and end-of-day battery neutrality. "
        f"Total grid cost: {round(total_cost, 2)} BDT with peak import of {round(peak_grid, 2)} kWh."
    )

    return round(total_grid, 4), round(total_cost, 4), round(peak_grid, 4), summary
