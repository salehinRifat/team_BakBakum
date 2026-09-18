# GridWise — Smart Campus Energy Optimization Service
**BUP CSE Fest 2026 Hackathon · Online Preliminary Round**

GridWise is an end-to-end intelligent microgrid energy scheduling service for the Bangladesh University of Professionals (BUP) smart campus. It combines a **Large Language Model (LLM)** for unstructured operator directive interpretation, **deterministic guardrails** for validation, and a **high-performance Linear Programming (LP) solver** to schedule campus grid electricity, solar generation, and battery storage across a 24-hour horizon.

---

## 1. System Architecture

The service implements a strict 4-stage pipeline that ensures safety, deterministic validation, and cost optimality:

```
[ POST /optimize-energy ]
           │
           ▼
┌──────────────────────────────────────┐
│  Stage 1: LLM Directive Interpreter  │ ──► Interprets 1-3 operator notes into structured JSON
└──────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────┐
│  Stage 2: Deterministic Guardrails   │ ──► Validates directive types, hour bounds [0..23],
└──────────────────────────────────────┘     fractions [0..1], capacity, and applies semantics
           │
           ▼
┌──────────────────────────────────────┐
│  Stage 3: LP Mathematical Optimizer  │ ──► SciPy HiGHS LP Solver minimizes total grid cost
└──────────────────────────────────────┘     subject to energy balance, battery dynamics & rules
           │
           ▼
┌──────────────────────────────────────┐
│  Stage 4: Replay Audit & Recalc      │ ──► Verifies physical feasibility, battery neutrality,
└──────────────────────────────────────┘     and recalculates exact totals and metrics
           │
           ▼
[ Verified JSON Response (HTTP 200) ]
```

### Core Components
* **API Service (`app/main.py`)**: Built with FastAPI and Uvicorn for asynchronous, high-throughput, low-latency API serving ($p95 \le 60\text{ms}$).
* **Schemas (`app/schemas.py`)**: Strict Pydantic v2 schemas validating request structures, hour ordering, and response integrity.
* **LLM Interpreter (`app/interpreter/`)**:
  * Multi-provider client supporting **Google Gemini** (`gemini-1.5-flash` / `gemini-2.0-flash`) and **OpenAI/Groq** (`gpt-4o-mini` / `llama-3.3-70b`).
  * Structured prompt templates with canonical few-shot examples and time window parsing.
  * Deterministic rule-based fallback parser ensuring zero downtime, safe error handling, and 100% test pass rates under provider network issues or offline evaluation.
* **Deterministic Guardrails (`app/guardrails/validator.py`)**: Enforces Section 08 rules:
  * Only supported directive types (`solar_reduction`, `minimum_battery_reserve`, `no_charge_window`, `no_discharge_window`, `max_grid_window`, `no_op`).
  * Consecutive `note_index` ordering (`0..N-1`).
  * `applies = false` solely for `no_op`.
  * Hour array validation: unique, strictly ascending integers within `0..23`.
* **Optimizer (`app/optimizer/solver.py`)**: Formulates the 24-hour cost minimization Linear Program (120 variables, 49 linear equality/inequality constraints) and solves it using the HiGHS dual-simplex solver in $<10\text{ms}$.
* **Replay Engine (`app/optimizer/replay.py`)**: Independently audits each hour for balance, solar limits, battery state transitions, and end-of-day neutrality.

---

## 2. Supported Directives & Conventions

| Directive Type | Meaning | `applies` | `structured_adjustment` |
|---|---|---|---|
| `solar_reduction` | Usable solar reduced | `true` | `{"hours": [int, ...], "factor": float}` ($0 \le \text{factor} \le 1$, remaining fraction) |
| `minimum_battery_reserve` | Minimum battery level | `true` | `{"hours": [int, ...], "minimum_energy_kwh": float}` |
| `no_charge_window` | Charging prohibited | `true` | `{"hours": [int, ...]}` |
| `no_discharge_window` | Discharging prohibited | `true` | `{"hours": [int, ...]}` |
| `max_grid_window` | Grid import capped | `true` | `{"hours": [int, ...], "max_grid_kwh": float}` |
| `no_op` | Realistic distractor note | `false` | `null` |

* **Time Window Rule**: Start-inclusive, end-exclusive (e.g., "1 PM to 3 PM" $\rightarrow$ `[13, 14]`).
* **End-of-Day Neutrality**: Battery state of charge after hour 23 must equal initial battery energy.

---

## 3. Local Quickstart (From Fresh Environment)

### Prerequisites
* Python 3.10+ (tested on Python 3.11, 3.12, 3.14)
* `git` and `pip`

### Step-by-Step Setup
```bash
# 1. Clone repository
git clone <YOUR_REPO_URL>
cd BUP_CSE_FEST_2026_Participant_Docs

# 2. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables (optional, defaults to fallback mode)
cp .env.example .env
# Edit .env to add your GEMINI_API_KEY or OPENAI_API_KEY if desired

# 5. Start the API service
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The service will start and bind to `http://0.0.0.0:8000`.

---

## 4. API Verification & Testing

### A. Health Check
```bash
curl -X GET http://127.0.0.1:8000/health
```
**Expected Response**:
```json
{"status": "ok"}
```

### B. Sample Request to `/optimize-energy`
Run a sample optimization request using `curl`:
```bash
curl -X POST http://127.0.0.1:8000/optimize-energy \
  -H "Content-Type: application/json" \
  -d '{
    "scenario_id": "TEST-01",
    "operator_notes": [
      "Solar output will drop to about 20% from 1 PM to 3 PM.",
      "The cafeteria menu changes tomorrow."
    ],
    "hours": [
      {"hour": 0, "demand_kwh": 100, "solar_kwh": 0, "tariff_bdt_per_kwh": 6},
      {"hour": 1, "demand_kwh": 95, "solar_kwh": 0, "tariff_bdt_per_kwh": 6},
      {"hour": 2, "demand_kwh": 90, "solar_kwh": 0, "tariff_bdt_per_kwh": 5},
      {"hour": 3, "demand_kwh": 90, "solar_kwh": 0, "tariff_bdt_per_kwh": 5},
      {"hour": 4, "demand_kwh": 95, "solar_kwh": 0, "tariff_bdt_per_kwh": 5},
      {"hour": 5, "demand_kwh": 105, "solar_kwh": 0, "tariff_bdt_per_kwh": 6},
      {"hour": 6, "demand_kwh": 120, "solar_kwh": 10, "tariff_bdt_per_kwh": 8},
      {"hour": 7, "demand_kwh": 140, "solar_kwh": 30, "tariff_bdt_per_kwh": 10},
      {"hour": 8, "demand_kwh": 160, "solar_kwh": 60, "tariff_bdt_per_kwh": 12},
      {"hour": 9, "demand_kwh": 175, "solar_kwh": 100, "tariff_bdt_per_kwh": 14},
      {"hour": 10, "demand_kwh": 185, "solar_kwh": 140, "tariff_bdt_per_kwh": 16},
      {"hour": 11, "demand_kwh": 190, "solar_kwh": 170, "tariff_bdt_per_kwh": 16},
      {"hour": 12, "demand_kwh": 195, "solar_kwh": 190, "tariff_bdt_per_kwh": 15},
      {"hour": 13, "demand_kwh": 190, "solar_kwh": 180, "tariff_bdt_per_kwh": 14},
      {"hour": 14, "demand_kwh": 180, "solar_kwh": 150, "tariff_bdt_per_kwh": 13},
      {"hour": 15, "demand_kwh": 175, "solar_kwh": 100, "tariff_bdt_per_kwh": 14},
      {"hour": 16, "demand_kwh": 180, "solar_kwh": 50, "tariff_bdt_per_kwh": 18},
      {"hour": 17, "demand_kwh": 195, "solar_kwh": 15, "tariff_bdt_per_kwh": 22},
      {"hour": 18, "demand_kwh": 215, "solar_kwh": 0, "tariff_bdt_per_kwh": 28},
      {"hour": 19, "demand_kwh": 225, "solar_kwh": 0, "tariff_bdt_per_kwh": 30},
      {"hour": 20, "demand_kwh": 215, "solar_kwh": 0, "tariff_bdt_per_kwh": 26},
      {"hour": 21, "demand_kwh": 185, "solar_kwh": 0, "tariff_bdt_per_kwh": 18},
      {"hour": 22, "demand_kwh": 145, "solar_kwh": 0, "tariff_bdt_per_kwh": 10},
      {"hour": 23, "demand_kwh": 115, "solar_kwh": 0, "tariff_bdt_per_kwh": 7}
    ],
    "battery": {
      "capacity_kwh": 500,
      "initial_energy_kwh": 200,
      "minimum_energy_kwh": 50,
      "max_charge_kwh_per_hour": 100,
      "max_discharge_kwh_per_hour": 100
    }
  }'
```

### C. Run Full Test Suite Against 10 Public Sample Cases
```bash
pytest tests/ -v
```
**Expected Result**:
```
tests/test_api.py::test_health_check PASSED
tests/test_api.py::test_malformed_request_missing_field PASSED
tests/test_api.py::test_invalid_hours_length PASSED
tests/test_sample_cases.py::test_public_sample_case[SAMPLE-01] PASSED
tests/test_sample_cases.py::test_public_sample_case[SAMPLE-02] PASSED
tests/test_sample_cases.py::test_public_sample_case[SAMPLE-03] PASSED
tests/test_sample_cases.py::test_public_sample_case[SAMPLE-04] PASSED
tests/test_sample_cases.py::test_public_sample_case[SAMPLE-05] PASSED
tests/test_sample_cases.py::test_public_sample_case[SAMPLE-06] PASSED
tests/test_sample_cases.py::test_public_sample_case[SAMPLE-07] PASSED
tests/test_sample_cases.py::test_public_sample_case[SAMPLE-08] PASSED
tests/test_sample_cases.py::test_public_sample_case[SAMPLE-09] PASSED
tests/test_sample_cases.py::test_public_sample_case[SAMPLE-10] PASSED
======================== 13 passed in ~0.85s ========================
```

---

## 5. Docker Fallback Instructions

A self-contained Docker container is provided as a fallback execution path for evaluation:

### Build Container
```bash
docker build -t gridwise-service:latest .
```

### Run Container
```bash
docker run -d \
  -p 8000:8000 \
  --name gridwise-instance \
  gridwise-service:latest
```

### Test Container Health
```bash
curl http://127.0.0.1:8000/health
```

### Run with Custom API Keys
```bash
docker run -d \
  -p 8000:8000 \
  -e GEMINI_API_KEY="your_api_key" \
  -e LLM_PROVIDER="gemini" \
  --name gridwise-instance \
  gridwise-service:latest
```

---

## 6. Configuration & Environment Variables

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `fallback` | LLM service: `gemini`, `openai`, `groq`, or `fallback` |
| `GEMINI_API_KEY` | *(None)* | Google Gemini API Key |
| `OPENAI_API_KEY` | *(None)* | OpenAI / Groq API Key |
| `OPENAI_BASE_URL` | *(None)* | Optional custom base URL (e.g. `https://api.groq.com/openai/v1`) |
| `MODEL_NAME` | `gemini-1.5-flash` | Language model identifier |
| `HOST` | `0.0.0.0` | Service bind address |
| `PORT` | `8000` | Service port |
| `TIMEOUT_SECONDS` | `25.0` | Per-request timeout safeguard |

---

## 7. Security, Secrets & Limitations

* **No Baked-in Secrets**: The repository, Docker image, and logs contain zero hardcoded API keys, tokens, or credentials.
* **Controlled Failures**: Malformed requests return HTTP 400 with descriptive error structures. Unhandled errors return HTTP 500 without leaking stack traces or internal environment details.
* **Synthetic Data Only**: All processing is strictly designed for synthetic smart campus microgrid scheduling as specified in the problem statement.
* **Known Limitations**: The linear programming solver models continuous energy flows. Integer constraints (e.g. strict discrete on/off inverter states) are mapped to continuous charging and discharging variables; mutually exclusive actions are ensured by positive tariffs and arbitrage economics.

---

## 8. Authors & Credits
* Developed for **BUP CSE Fest 2026 Hackathon (Online Preliminary Round)**.
* Optimization powered by **SciPy HiGHS LP Solver**.
* Web service built with **FastAPI** and **Uvicorn**.
