"""
Pydantic schemas for the GridWise Smart Campus Energy Optimization Service.
Strict adherence to BUP CSE Fest 2026 specifications.
"""

from typing import Any, List, Literal, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator


DirectiveType = Literal[
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op",
]

BatteryAction = Literal["charge", "discharge", "idle"]


class HourData(BaseModel):
    hour: int = Field(..., ge=0, le=23, description="Hour index from 0 to 23")
    demand_kwh: float = Field(..., ge=0.0, description="Demand in kWh")
    solar_kwh: float = Field(..., ge=0.0, description="Forecast solar output in kWh")
    tariff_bdt_per_kwh: float = Field(..., ge=0.0, description="Electricity price in BDT per kWh")


class BatteryData(BaseModel):
    capacity_kwh: float = Field(..., gt=0.0, description="Total battery capacity in kWh")
    initial_energy_kwh: float = Field(..., ge=0.0, description="Initial battery state of charge")
    minimum_energy_kwh: float = Field(..., ge=0.0, description="Baseline reserve floor")
    max_charge_kwh_per_hour: float = Field(..., ge=0.0, description="Maximum charge rate in 1 hour")
    max_discharge_kwh_per_hour: float = Field(..., ge=0.0, description="Maximum discharge rate in 1 hour")

    @model_validator(mode="after")
    def validate_battery_levels(self) -> "BatteryData":
        if self.minimum_energy_kwh > self.capacity_kwh:
            raise ValueError("minimum_energy_kwh cannot exceed capacity_kwh")
        if self.initial_energy_kwh > self.capacity_kwh:
            raise ValueError("initial_energy_kwh cannot exceed capacity_kwh")
        if self.initial_energy_kwh < self.minimum_energy_kwh:
            raise ValueError("initial_energy_kwh cannot be less than minimum_energy_kwh")
        return self


class OptimizeEnergyRequest(BaseModel):
    scenario_id: str = Field(..., min_length=1, description="Unique scenario identifier")
    operator_notes: List[str] = Field(..., min_length=1, max_length=3, description="1-3 natural-language operator notes")
    hours: List[HourData] = Field(..., min_length=24, max_length=24, description="Hourly data for 24 hours")
    battery: BatteryData = Field(..., description="Battery specifications")

    @field_validator("hours")
    @classmethod
    def validate_hours(cls, v: List[HourData]) -> List[HourData]:
        if len(v) != 24:
            raise ValueError("Must provide exactly 24 hourly entries")
        seen_hours = set()
        for idx, h in enumerate(v):
            if h.hour != idx:
                raise ValueError(f"Hour entry at index {idx} has hour {h.hour}, expected {idx}")
            seen_hours.add(h.hour)
        if len(seen_hours) != 24:
            raise ValueError("Hours must contain all integers from 0 to 23")
        return v


class DirectiveInterpretation(BaseModel):
    note_index: int = Field(..., ge=0, description="Zero-based index of corresponding operator note")
    applies: bool = Field(..., description="True for non-no_op, False only for no_op")
    directive_type: DirectiveType = Field(..., description="Supported directive type")
    structured_adjustment: Optional[dict[str, Any]] = Field(
        default=None,
        description="Machine-checkable adjustment object or null for no_op"
    )
    explanation: str = Field(..., description="Short explanation of interpretation")


class HourlyPlanItem(BaseModel):
    hour: int = Field(..., ge=0, le=23, description="Hour index from 0 to 23")
    grid_kwh: float = Field(..., ge=0.0, description="Grid electricity imported in kWh")
    solar_used_kwh: float = Field(..., ge=0.0, description="Solar electricity consumed in kWh")
    battery_action: BatteryAction = Field(..., description="Battery state: charge, discharge, or idle")
    battery_kwh: float = Field(..., ge=0.0, description="Battery energy transferred in this hour")
    battery_energy_after_kwh: float = Field(..., ge=0.0, description="Battery energy after this hour")


class OptimizeEnergyResponse(BaseModel):
    scenario_id: str = Field(..., description="Echo of request scenario_id")
    directive_interpretation: List[DirectiveInterpretation] = Field(..., description="One entry per operator note")
    hourly_plan: List[HourlyPlanItem] = Field(..., min_length=24, max_length=24, description="24-hour schedule")
    total_grid_kwh: float = Field(..., ge=0.0, description="Sum of grid_kwh over 24 hours")
    total_cost_bdt: float = Field(..., ge=0.0, description="Total grid electricity cost in BDT")
    peak_grid_kwh: float = Field(..., ge=0.0, description="Maximum hourly grid_kwh")
    plan_summary: str = Field(..., description="Concise explanation of the optimized strategy")


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
