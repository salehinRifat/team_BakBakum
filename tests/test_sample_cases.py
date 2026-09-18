"""
Test suite validating the 10 public sample cases from
BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json.
"""

import json
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

with open("BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json") as f:
    PUBLIC_CASES = json.load(f)["cases"]


@pytest.mark.parametrize("case", PUBLIC_CASES, ids=[c["id"] for c in PUBLIC_CASES])
def test_public_sample_case(case):
    req_data = case["input"]
    exp_output = case["expected_output"]

    response = client.post("/optimize-energy", json=req_data)
    assert response.status_code == 200, f"Failed with {response.status_code}: {response.text}"

    resp_json = response.json()

    # 1. Scenario ID check
    assert resp_json["scenario_id"] == exp_output["scenario_id"]

    # 2. Directive Interpretation checks
    expected_directives = exp_output["directive_interpretation"]
    actual_directives = resp_json["directive_interpretation"]
    assert len(actual_directives) == len(expected_directives)

    for idx, (act, exp) in enumerate(zip(actual_directives, expected_directives)):
        assert act["note_index"] == idx, f"Note index mismatch: {act['note_index']} != {idx}"
        assert act["applies"] == exp["applies"], f"Applies mismatch in note {idx}: {act['applies']} != {exp['applies']}"
        assert act["directive_type"] == exp["directive_type"], f"Directive type mismatch in note {idx}: {act['directive_type']} != {exp['directive_type']}"
        assert act["structured_adjustment"] == exp["structured_adjustment"], f"Adjustment mismatch in note {idx}: {act['structured_adjustment']} != {exp['structured_adjustment']}"

    # 3. Hourly Plan checks
    hourly_plan = resp_json["hourly_plan"]
    assert len(hourly_plan) == 24

    # 4. Numeric totals checks (within 0.01 tolerance)
    tol = 0.01
    cost_diff = abs(resp_json["total_cost_bdt"] - exp_output["total_cost_bdt"])
    assert cost_diff <= tol, f"Total cost mismatch: got {resp_json['total_cost_bdt']}, exp {exp_output['total_cost_bdt']}, diff {cost_diff}"

    grid_diff = abs(resp_json["total_grid_kwh"] - exp_output["total_grid_kwh"])
    assert grid_diff <= tol, f"Total grid mismatch: got {resp_json['total_grid_kwh']}, exp {exp_output['total_grid_kwh']}, diff {grid_diff}"

    peak_diff = abs(resp_json["peak_grid_kwh"] - exp_output["peak_grid_kwh"])
    assert peak_diff <= tol, f"Peak grid mismatch: got {resp_json['peak_grid_kwh']}, exp {exp_output['peak_grid_kwh']}, diff {peak_diff}"
