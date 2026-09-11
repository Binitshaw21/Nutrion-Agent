# 🥗 NutriAI — Personal Nutrition Agent

A complete full-stack AI-powered Nutrition Agent built with **IBM watsonx AI** (llama-3-3-70b-instruct), a **FastAPI** backend, and a pure HTML/CSS/JS frontend — also deployable as a native agent on **IBM watsonx Orchestrate**.

---

## 📁 Project Structure

```
NUTRION AGENT/
├── backend/
│   ├── main.py              ← FastAPI server — 7 API endpoints, watsonx integration
│   └── requirements.txt     ← Python dependencies
│
├── frontend/
│   └── index.html           ← Full SPA frontend — 8 tabs, no build step needed
│
├── tools/
│   ├── nutrition_tools.py   ← 4 watsonx Orchestrate native tools
│   └── requirements.txt
│
├── agent/
│   └── nutrition_agent.yaml ← watsonx Orchestrate agent definition
│
├── start.bat                ← One-click backend launcher (Windows)
├── deploy_wxo.bat           ← One-click watsonx Orchestrate deploy (Windows)
└── README.md
```

---

## 🚀 Quick Start

### 1 — Start the Backend

```bat
start.bat
```

Or manually:
```powershell
cd backend
$env:WATSONX_APIKEY = "iEcAYr__w_EdxG7RTUOM2fZ-uPSaaL-d3_8GLRyUrG63"
..\venv\Scripts\uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The backend starts at **http://localhost:8000**
Interactive API docs at **http://localhost:8000/docs**

### 2 — Open the Frontend

**Option A** — Served by the backend (recommended):
Open **http://localhost:8000** in your browser.

**Option B** — Open directly:
Open `frontend/index.html` in any browser.

---

## 🌐 Frontend Tabs

| Tab | Feature |
|---|---|
| 🏠 Home | Overview, tips, feature cards |
| 🩺 Advisor | Full health profile → personalized nutrition advice |
| 💬 Chat | Multi-turn AI dietitian conversation |
| 🔬 Food Lab | Deep nutritional analysis of any food |
| 📅 Meal Plan | 1–7 day custom meal plans |
| ⚖️ BMI | Live BMI calculator + AI dietary recommendations |
| 💊 Deficiency | Identify nutrient gaps from symptoms |
| 🔎 Nutrients | Vitamin/mineral/macronutrient encyclopedia |

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Liveness check |
| POST | `/api/nutrition-advice` | Personalised advice from full health profile |
| POST | `/api/chat` | Multi-turn conversation |
| POST | `/api/analyze-food` | Food nutritional analysis |
| POST | `/api/meal-plan` | Generate meal plan |
| POST | `/api/bmi` | BMI calculation + AI tips |
| POST | `/api/check-deficiency` | Nutrient deficiency from symptoms |
| POST | `/api/nutrient-search` | Vitamin/mineral encyclopedia lookup |

---

## 🤖 Deploy to watsonx Orchestrate

```bat
deploy_wxo.bat
```

Or manually:
```bash
# Activate environment first
orchestrate env activate <your-env>

# Import tools
orchestrate tools import -k python -f tools/nutrition_tools.py \
  --requirements tools/requirements.txt

# Import agent
orchestrate agents import -f agent/nutrition_agent.yaml
```

The agent will appear as **nutrition-agent** in your watsonx Orchestrate workspace.

---

## ⚙️ watsonx Configuration

| Parameter | Value |
|---|---|
| API URL | `https://us-south.ml.cloud.ibm.com/ml/v1/text/chat?version=2023-05-29` |
| Model | `meta-llama/llama-3-3-70b-instruct` |
| Project ID | `dd6cb8ce-c2cd-48ea-ba0d-068062af2b13` |
| Token env var | `WATSONX_TOKEN` |

---

## 🛡️ Disclaimer

NutriAI provides general dietary guidance only. Always consult a licensed doctor or registered dietitian for clinical decisions.
