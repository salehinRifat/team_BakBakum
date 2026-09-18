# GridWise — Smart Campus Energy Optimization Service
**BUP CSE Fest 2026 Hackathon · Online Preliminary Round**

GridWise is an autonomous microgrid scheduling service designed for the Bangladesh University of Professionals (BUP) smart campus. It combines a **Large Language Model (LLM)** for natural language operator note interpretation, **deterministic guardrails** for validation, and a **high-performance Linear Programming (LP) solver** to generate cost-optimal 24-hour schedules for campus grid electricity import, rooftop solar utilization, and battery energy storage.

---

## Table of Contents
1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Why and How the LLM is Used](#3-why-and-how-the-llm-is-used)
4. [Deterministic Guardrails](#4-deterministic-guardrails)
5. [Optimizer & Solver](#5-optimizer--solver)
6. [Dependencies & Technology Stack](#6-dependencies--technology-stack)
7. [Installation (Clean Environment Quickstart)](#7-installation-clean-environment-quickstart)
8. [Exact Run Command](#8-exact-run-command)
9. [Environment Variables & Configuration](#9-environment-variables--configuration)
10. [LLM / Model + Provider Configuration](#10-llm--model--provider-configuration)
11. [API Endpoints & Examples](#11-api-endpoints--examples)
    * [GET /health Example](#a-get-health)
    * [POST /optimize-energy Example](#b-post-optimize-energy)
12. [Public Sample Test Command & Expected Result](#12-public-sample-test-command--expected-result)
13. [Docker Instructions (Fallback Execution Path)](#13-docker-instructions-fallback-execution-path)
14. [Known Limitations](#14-known-limitations)
15. [Secret-Handling Information](#15-secret-handling-information)

---

## 1. Project Overview

During normal campus operations, hourly electrical demand, rooftop solar forecasts, and utility grid tariffs fluctuate throughout the day. Campus operators often provide 1 to 3 short, unstructured natural-language notes specifying temporary operational conditions (such as panel washing, maintenance outages, emergency battery reserve margins, or feeder intake caps), alongside realistic non-operational distractor notes.

GridWise automates the interpretation of these notes, converts them into machine-checkable mathematical constraints, solves the resulting 24-hour energy schedule, and guarantees physical microgrid feasibility, end-of-day battery neutrality, and minimum grid electricity cost.

---

## 2. Architecture

GridWise implements a strict 4-stage pipeline separating generative language interpretation from deterministic validation and mathematical optimization:

```
                  Incoming Request (POST /optimize-energy)
                                     │
                                     ▼
      ┌─────────────────────────────────────────────────────────────┐
      │  Stage 1: LLM Directive Interpreter (app/interpreter/)       │
      │  • Generative LLM processes 1-3 operator notes               │
      │  • Extracts directive_type, applies, and structured JSON    │
      │  • Built-in deterministic NLP fallback for zero downtime    │
      └─────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
      ┌─────────────────────────────────────────────────────────────┐
      │  Stage 2: Deterministic Guardrails (app/guardrails/)        │
      │  • Validates directive types and exact note_index (0..N-1)   │
      │  • Enforces applies semantics (false only for no_op)        │
      │  • Sorts & deduplicates hours array: unique [0..23]         │
      │  • Clamps solar factor [0..1] and checks battery capacity   │
      └─────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
      ┌─────────────────────────────────────────────────────────────┐
      │  Stage 3: LP Mathematical Optimizer (app/optimizer/solver.py)│
      │  • Formulates 120-variable, 49-constraint Linear Program    │
      │  • Solves via SciPy HiGHS Dual-Simplex Solver in < 10ms     │
      │  • Minimizes total electricity cost: sum(grid * tariff)     │
      └─────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
      ┌─────────────────────────────────────────────────────────────┐
      │  Stage 4: Replay Audit & Recalculation (app/optimizer/replay)│
      │  • Replays hour-by-hour balance & rate limits               │
      │  • Verifies end-of-day battery neutrality: E[23] == E_init  │
      │  • Recalculates total_cost_bdt, total_grid_kwh, peak_grid   │
      └─────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
                     Verified JSON Response (HTTP 200)
```

---

## 3. Why and How the LLM is Used

* **Why It Is Used**: Human operator notes are written in varied, unstructured natural language (e.g. colloquial time expressions like *"from noon until 2 PM"*, percentage reductions like *"expect an 80% reduction"*, or distractor campus announcements). An LLM is required to understand human phrasing, filter irrelevant distractors, and extract structured operational parameters without relying on brittle hardcoded strings.
* **How It Is Used**: The LLM is **directly on the interpretation path**. In `app/interpreter/llm_client.py`, incoming notes are dispatched to the language model with an explicit system prompt and few-shot examples. The LLM parses each note into:
  1. `note_index`: 0-based integer mapping.
  2. `directive_type`: One of the 6 canonical types.
  3. `applies`: Boolean (`true` for active constraints, `false` for `no_op`).
  4. `structured_adjustment`: Validated parameters (hours list, factor fraction, minimum kWh, or max grid kWh).
  5. `explanation`: Rationale for the interpretation.

---

## 4. Deterministic Guardrails

In strict compliance with Section 08 of the Problem Statement, LLM output is treated as untrusted data until validated by deterministic guardrails (`app/guardrails/validator.py`):
1. **Allowed Directives**: Enforces that `directive_type` belongs strictly to:
   * `solar_reduction`
   * `minimum_battery_reserve`
   * `no_charge_window`
   * `no_discharge_window`
   * `max_grid_window`
   * `no_op`
2. **Note Mapping & Sequence**: Every note index `0` through `N-1` must appear exactly once in sequential order.
3. **Applies Semantics**: For `no_op`, `applies` must be `false` and `structured_adjustment` must be `null`. For all active directives, `applies` must be `true` with a non-null adjustment.
4. **Hour Array Sorting**: Extracted hours are verified, deduplicated, and strictly sorted in ascending order within range `[0..23]`.
5. **Numeric Bounds**:
   * `solar_reduction`: `factor` clamped between `0.0` and `1.0`.
   * `minimum_battery_reserve`: `minimum_energy_kwh` bounded between `0.0` and `capacity_kwh`.
   * `max_grid_window`: `max_grid_kwh` must be finite and $\ge 0.0$.
6. **Safe Failure**: Any malformed, hallucinated, or unparseable output safely defaults to a compliant `no_op` without crashing.

---

## 5. Optimizer & Solver

* **Formulation**: Formulated as a Linear Program (LP) over the 24-hour planning horizon ($T = 24$ hours).
* **Solver Engine**: Solved using `scipy.optimize.linprog` with the **HiGHS dual-simplex engine**, solving the entire daily schedule in $< 10\text{ms}$.
* **Variables ($120$ continuous variables)**:
  * $g_h \ge 0$: Grid electricity imported (kWh)
  * $s_h \ge 0$: Solar energy consumed (kWh)
  * $c_h \ge 0$: Battery energy charged (kWh)
  * $d_h \ge 0$: Battery energy discharged (kWh)
  * $E_h \ge 0$: Battery energy after hour $h$ (kWh)
* **Objective Function**:
  $$\min \sum_{h=0}^{23} \Big( g_h \times \text{tariff}[h] + 10^{-6}(c_h + d_h) \Big)$$
  *(The tiny tie-breaking penalty $10^{-6}$ prevents unnecessary battery cycling and prioritizes idle states).*
* **Constraints Enforced**:
  1. **Hourly Energy Balance**: $g_h + s_h + d_h = \text{demand}[h] + c_h$ for all $h \in \{0..23\}$.
  2. **Effective Solar & Zero Export**: $0 \le s_h \le \text{effective\_solar}[h]$ (excess solar is curtailed).
  3. **Battery Dynamics**:
     $$E_0 = E_{\text{initial}} + c_0 - d_0, \quad E_h = E_{h-1} + c_h - d_h \quad (\forall h \ge 1)$$
  4. **Battery Energy Bounds**:
     $$\max\big(\text{base\_min}, \text{directive\_min}[h]\big) \le E_h \le \text{capacity}$$
  5. **Charge & Discharge Rate Limits**:
     $c_h \le \text{max\_charge}[h]$, $d_h \le \text{max\_discharge}[h]$.
  6. **Directive Windows**:
     $c_h = 0$ during `no_charge_window`; $d_h = 0$ during `no_discharge_window`; $g_h \le \text{max\_grid}[h]$ during `max_grid_window`.
  7. **End-of-Day Neutrality**:
     $$E_{23} = E_{\text{initial}}$$

---

## 6. Dependencies & Technology Stack

The project relies on standard, production-tested open-source libraries:
* **Python**: 3.10+ (tested on Python 3.11, 3.12, 3.14)
* **FastAPI (`>=0.110.0`)**: High-performance asynchronous API framework
* **Uvicorn (`>=0.28.0`)**: ASGI production web server
* **Pydantic (`>=2.6.0`) & Pydantic-Settings**: Strict data schema validation
* **SciPy (`>=1.12.0`) & NumPy (`>=1.26.0`)**: Mathematical linear programming optimization (HiGHS)
* **HTTPX (`>=0.27.0`)**: Async HTTP client for LLM API communication
* **python-dotenv (`>=1.0.0`)**: Secure environment variable configuration
* **pytest (`>=8.0.0`)**: Automated test runner

---

## 7. Installation (Clean Environment Quickstart)

To reproduce and run the service from a clean environment without assistance:

```bash
# 1. Clone repository
git clone <YOUR_REPOSITORY_URL>
cd BUP_CSE_FEST_2026_Participant_Docs

# 2. Create virtual environment
python3 -m venv .venv

# 3. Activate virtual environment
source .venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Configure environment variables (optional, fallback parser works offline)
cp .env.example .env
```

---

## 8. Exact Run Command

Start the API service binding to all interfaces on port `8000`:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The service starts immediately and binds to `http://0.0.0.0:8000`.

---

## 9. Environment Variables & Configuration

Configure settings in `.env` or pass them directly as system environment variables:

| Variable | Type | Default | Description |
|---|---|---|---|
| `LLM_PROVIDER` | `str` | `gemini` | Model provider: `"gemini"`, `"openai"`, `"groq"`, or `"fallback"` |
| `GEMINI_API_KEY` | `str` | *(None)* | Google AI Studio API Key |
| `OPENAI_API_KEY` | `str` | *(None)* | OpenAI / Groq API Key |
| `OPENAI_BASE_URL` | `str` | *(None)* | Optional custom URL for Groq, Ollama, or OpenRouter |
| `MODEL_NAME` | `str` | `gemini-flash-lite-latest` | Language model identifier |
| `HOST` | `str` | `0.0.0.0` | Service listening host |
| `PORT` | `int` | `8000` | Service listening port |
| `TIMEOUT_SECONDS` | `float` | `25.0` | Per-request timeout safeguard |

---

## 10. LLM / Model + Provider Configuration

* **Default Model**: `gemini-flash-lite-latest` via Google Generative Language API.
* **OpenAI / Groq Compatibility**: Supports any OpenAI-compatible API by setting `LLM_PROVIDER=openai` and specifying `OPENAI_API_KEY` and optional `OPENAI_BASE_URL`.
* **Zero-Downtime Deterministic Fallback**: If no API key is provided, or if an external provider experiences network failure/timeout, the system automatically uses `app/interpreter/fallback.py` to ensure 100% test reliability and zero downtime.

---

## 11. API Endpoints & Examples

### A. `GET /health`
Verifies readiness for the judge harness.

**Command**:
```bash
curl -X GET http://127.0.0.1:8000/health
```

**Expected Response** (`HTTP 200 OK`):
```json
{
  "status": "ok"
}
```

---

### B. `POST /optimize-energy`
Processes a 24-hour campus scenario with operator notes and returns the optimized schedule.

**Command**:
```bash
curl -X POST http://127.0.0.1:8000/optimize-energy \
  -H "Content-Type: application/json" \
  -d '{
    "scenario_id": "SAMPLE-01",
    "operator_notes": [
      "Facilities will wash the rooftop solar panels from noon until 2 PM. During cleaning, usable solar should be treated as roughly 25% of the forecast.",
      "The sports office moved next month'\''s registration deadline."
    ],
    "hours": [
      {"hour": 0, "demand_kwh": 90, "solar_kwh": 0, "tariff_bdt_per_kwh": 6},
      {"hour": 1, "demand_kwh": 85, "solar_kwh": 0, "tariff_bdt_per_kwh": 6},
      {"hour": 2, "demand_kwh": 80, "solar_kwh": 0, "tariff_bdt_per_kwh": 5},
      {"hour": 3, "demand_kwh": 80, "solar_kwh": 0, "tariff_bdt_per_kwh": 5},
      {"hour": 4, "demand_kwh": 85, "solar_kwh": 0, "tariff_bdt_per_kwh": 5},
      {"hour": 5, "demand_kwh": 95, "solar_kwh": 0, "tariff_bdt_per_kwh": 6},
      {"hour": 6, "demand_kwh": 110, "solar_kwh": 5, "tariff_bdt_per_kwh": 8},
      {"hour": 7, "demand_kwh": 130, "solar_kwh": 20, "tariff_bdt_per_kwh": 10},
      {"hour": 8, "demand_kwh": 150, "solar_kwh": 50, "tariff_bdt_per_kwh": 12},
      {"hour": 9, "demand_kwh": 165, "solar_kwh": 90, "tariff_bdt_per_kwh": 14},
      {"hour": 10, "demand_kwh": 175, "solar_kwh": 130, "tariff_bdt_per_kwh": 16},
      {"hour": 11, "demand_kwh": 180, "solar_kwh": 160, "tariff_bdt_per_kwh": 16},
      {"hour": 12, "demand_kwh": 185, "solar_kwh": 180, "tariff_bdt_per_kwh": 15},
      {"hour": 13, "demand_kwh": 180, "solar_kwh": 170, "tariff_bdt_per_kwh": 14},
      {"hour": 14, "demand_kwh": 170, "solar_kwh": 140, "tariff_bdt_per_kwh": 13},
      {"hour": 15, "demand_kwh": 165, "solar_kwh": 90, "tariff_bdt_per_kwh": 14},
      {"hour": 16, "demand_kwh": 170, "solar_kwh": 45, "tariff_bdt_per_kwh": 18},
      {"hour": 17, "demand_kwh": 185, "solar_kwh": 10, "tariff_bdt_per_kwh": 22},
      {"hour": 18, "demand_kwh": 205, "solar_kwh": 0, "tariff_bdt_per_kwh": 28},
      {"hour": 19, "demand_kwh": 215, "solar_kwh": 0, "tariff_bdt_per_kwh": 30},
      {"hour": 20, "demand_kwh": 205, "solar_kwh": 0, "tariff_bdt_per_kwh": 26},
      {"hour": 21, "demand_kwh": 175, "solar_kwh": 0, "tariff_bdt_per_kwh": 18},
      {"hour": 22, "demand_kwh": 135, "solar_kwh": 0, "tariff_bdt_per_kwh": 10},
      {"hour": 23, "demand_kwh": 105, "solar_kwh": 0, "tariff_bdt_per_kwh": 7}
    ],
    "battery": {
      "capacity_kwh": 220,
      "initial_energy_kwh": 110,
      "minimum_energy_kwh": 40,
      "max_charge_kwh_per_hour": 50,
      "max_discharge_kwh_per_hour": 50
    }
  }'
```

**Expected Response** (`HTTP 200 OK`):
```json
{
  "scenario_id": "SAMPLE-01",
  "directive_interpretation": [
    {
      "note_index": 0,
      "applies": true,
      "directive_type": "solar_reduction",
      "structured_adjustment": {
        "hours": [12, 13],
        "factor": 0.25
      },
      "explanation": "Solar reduction to 25% usable factor from 12:00 to 14:00."
    },
    {
      "note_index": 1,
      "applies": false,
      "directive_type": "no_op",
      "structured_adjustment": null,
      "explanation": "Sports office registration deadline has no energy scheduling impact."
    }
  ],
  "hourly_plan": [
    {
      "hour": 0,
      "grid_kwh": 90.0,
      "solar_used_kwh": 0.0,
      "battery_action": "idle",
      "battery_kwh": 0.0,
      "battery_energy_after_kwh": 110.0
    },
    "... (24 hourly items) ..."
  ],
  "total_grid_kwh": 2692.5,
  "total_cost_bdt": 38365.0,
  "peak_grid_kwh": 175.0,
  "plan_summary": "Optimized 24-hour campus energy schedule applying 1 active operator directive(s). Scheduled 8 charging and 8 discharging cycles to shift load away from peak tariff hours while maintaining all reserve margins and end-of-day battery neutrality. Total grid cost: 38365.0 BDT with peak import of 175.0 kWh."
}
```

---

## 12. Public Sample Test Command & Expected Result

### Automated Pytest Suite Command:
```bash
pytest tests/ -v
```

### Expected Test Result:
```
============================= test session starts ==============================
platform linux -- Python 3.11+, pytest-8.0+
rootdir: /path/to/BUP_CSE_FEST_2026_Participant_Docs

tests/test_api.py::test_health_check PASSED                              [  7%]
tests/test_api.py::test_malformed_request_missing_field PASSED           [ 15%]
tests/test_api.py::test_invalid_hours_length PASSED                      [ 23%]
tests/test_sample_cases.py::test_public_sample_case[SAMPLE-01] PASSED    [ 30%]
tests/test_sample_cases.py::test_public_sample_case[SAMPLE-02] PASSED    [ 38%]
tests/test_sample_cases.py::test_public_sample_case[SAMPLE-03] PASSED    [ 46%]
tests/test_sample_cases.py::test_public_sample_case[SAMPLE-04] PASSED    [ 53%]
tests/test_sample_cases.py::test_public_sample_case[SAMPLE-05] PASSED    [ 61%]
tests/test_sample_cases.py::test_public_sample_case[SAMPLE-06] PASSED    [ 69%]
tests/test_sample_cases.py::test_public_sample_case[SAMPLE-07] PASSED    [ 76%]
tests/test_sample_cases.py::test_public_sample_case[SAMPLE-08] PASSED    [ 84%]
tests/test_sample_cases.py::test_public_sample_case[SAMPLE-09] PASSED    [ 92%]
tests/test_sample_cases.py::test_public_sample_case[SAMPLE-10] PASSED    [100%]

======================== 13 passed in ~0.9s ========================
```

---

## 13. Docker Instructions (Fallback Execution Path)

A tested Docker container image is provided as an independent fallback execution path.

* **Registry Reference**: `docker.io/<your-username>/gridwise:latest` (or `ghcr.io/<your-org>/gridwise:latest`)
* **Service Port**: Exposes port `8000`
* **Bind Address**: Binds to `0.0.0.0`
* **No Baked-in Secrets**: The image contains zero credentials.

### Step 1: Pull Image
```bash
docker pull docker.io/<your-username>/gridwise:latest
```

### Step 2: Run Container
```bash
docker run -d \
  -p 8000:8000 \
  -e GEMINI_API_KEY="your_api_key_here" \
  -e LLM_PROVIDER="gemini" \
  --name gridwise-instance \
  docker.io/<your-username>/gridwise:latest
```
*(If running offline or without an API key, omit the `GEMINI_API_KEY` variable; the container will automatically operate in deterministic fallback mode).*

### Step 3: Verify Container Readiness
```bash
curl http://127.0.0.1:8000/health
# Returns: {"status":"ok"}
```

### Step 4: Run Tests Inside Container
```bash
docker exec -it gridwise-instance pytest tests/ -v
```

---

## 14. Known Limitations

1. **Continuous Energy Flow**: The optimizer models energy import and storage as continuous linear variables ($0.01\text{ kWh}$ precision). Discrete mechanical switching latency is not modeled.
2. **Zero Grid Export**: The system assumes no feed-in tariff exists; excess solar is curtailed and cannot be exported to the grid.
3. **Synthetic Horizon**: Assumes fixed 24-hour deterministic forecasts for demand, solar, and grid tariffs as defined by the challenge contract.

---

## 15. Secret-Handling Information

* **No Committed Secrets**: `.env`, `*.key`, `*.pem`, and `*.token` files are excluded from Git via `.gitignore`.
* **Zero Baked-in Credentials**: The Docker image contains no hardcoded API keys. Keys must be supplied at runtime via environment variables (`GEMINI_API_KEY` or `OPENAI_API_KEY`).
* **Safe Error Handling**: Server errors return controlled HTTP 400 or HTTP 500 messages without exposing raw prompts, keys, or stack traces.
