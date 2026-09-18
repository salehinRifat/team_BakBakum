"""
GridWise Smart Campus Energy Optimization Service.
Main FastAPI Application Entrypoint.
BUP CSE Fest 2026 Hackathon Preliminary Round.
"""

import logging
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import (
    OptimizeEnergyRequest,
    OptimizeEnergyResponse,
    HealthResponse,
)
from app.interpreter.llm_client import interpret_operator_notes
from app.guardrails.validator import validate_and_sanitize_directives
from app.optimizer.solver import solve_energy_schedule
from app.optimizer.replay import replay_and_audit_schedule

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("gridwise")

app = FastAPI(
    title="GridWise Campus Energy Optimization API",
    description="LLM-Assisted Smart Campus Energy Scheduling Service for BUP CSE Fest 2026",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Returns HTTP 400 on malformed or structurally invalid JSON as specified in Section 6.1."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": exc.errors(), "message": "Malformed JSON or structurally invalid request."},
    )


@app.get("/health", response_model=HealthResponse, tags=["Readiness"])
async def health_check():
    """Health check readiness endpoint."""
    return HealthResponse(status="ok")


@app.post("/optimize-energy", response_model=OptimizeEnergyResponse, tags=["Optimization"])
async def optimize_energy(payload: OptimizeEnergyRequest):
    """
    Main energy optimization endpoint.
    1. Interprets operator notes via LLM (with deterministic fallback).
    2. Enforces deterministic guardrails.
    3. Solves the 24-hour cost-optimal energy schedule.
    4. Audits schedule and recalculates totals.
    """
    try:
        # Step 1: LLM Interpretation
        raw_directives = await interpret_operator_notes(
            operator_notes=payload.operator_notes,
            capacity_kwh=payload.battery.capacity_kwh,
        )

        # Step 2: Deterministic Guardrails
        sanitized_directives = validate_and_sanitize_directives(
            directives=raw_directives,
            num_notes=len(payload.operator_notes),
            battery=payload.battery,
        )

        # Step 3: Mathematical LP Optimization
        hourly_plan = solve_energy_schedule(
            hours=payload.hours,
            battery=payload.battery,
            directives=sanitized_directives,
        )

        # Step 4: Replay Verification & Metrics Recalculation
        total_grid, total_cost, peak_grid, summary = replay_and_audit_schedule(
            plan=hourly_plan,
            hours=payload.hours,
            battery=payload.battery,
            directives=sanitized_directives,
        )

        # Step 5: Construct Verified API Response
        return OptimizeEnergyResponse(
            scenario_id=payload.scenario_id,
            directive_interpretation=sanitized_directives,
            hourly_plan=hourly_plan,
            total_grid_kwh=total_grid,
            total_cost_bdt=total_cost,
            peak_grid_kwh=peak_grid,
            plan_summary=summary,
        )

    except Exception as e:
        logger.error(f"Error processing scenario {payload.scenario_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Controlled internal server error during energy optimization."
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
