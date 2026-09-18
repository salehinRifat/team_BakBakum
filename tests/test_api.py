"""
Test suite validating API behavior, health check, and error handling.
"""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_malformed_request_missing_field():
    # Missing battery object
    bad_payload = {
        "scenario_id": "TEST-BAD",
        "operator_notes": ["Note 1"],
        "hours": [{"hour": i, "demand_kwh": 100, "solar_kwh": 10, "tariff_bdt_per_kwh": 5} for i in range(24)]
    }
    response = client.post("/optimize-energy", json=bad_payload)
    assert response.status_code == 400


def test_invalid_hours_length():
    # Only 23 hours instead of 24
    bad_payload = {
        "scenario_id": "TEST-BAD-HOURS",
        "operator_notes": ["Note 1"],
        "hours": [{"hour": i, "demand_kwh": 100, "solar_kwh": 10, "tariff_bdt_per_kwh": 5} for i in range(23)],
        "battery": {
            "capacity_kwh": 500,
            "initial_energy_kwh": 200,
            "minimum_energy_kwh": 50,
            "max_charge_kwh_per_hour": 100,
            "max_discharge_kwh_per_hour": 100
        }
    }
    response = client.post("/optimize-energy", json=bad_payload)
    assert response.status_code == 400
