from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional, List
import httpx
import os
import time
import asyncio
from pathlib import Path

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="NutriAI — Nutrition Agent API",
    version="2.0.0",
    description="Personalized AI nutrition advice powered by IBM watsonx llama-3-3-70b",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── watsonx config ─────────────────────────────────────────────────────────────
WATSONX_URL   = "https://us-south.ml.cloud.ibm.com/ml/v1/text/chat?version=2023-05-29"
IAM_TOKEN_URL = "https://iam.cloud.ibm.com/identity/token"
PROJECT_ID    = "dd6cb8ce-c2cd-48ea-ba0d-068062af2b13"

# Model priority list — tried in order when 429 is hit on the primary
MODELS = [
    "meta-llama/llama-3-3-70b-instruct",   # primary (free tier, 10 concurrent)
    "meta-llama/llama-3-1-8b-instruct",     # smaller/faster fallback
    "ibm/granite-3-3-8b-instruct",          # IBM granite fallback
]

# IBM Cloud API key — used to auto-refresh the Bearer token (never expires)
WATSONX_APIKEY = os.getenv("WATSONX_APIKEY", "iEcAYr__w_EdxG7RTUOM2fZ-uPSaaL-d3_8GLRyUrG63")

# Token cache — refreshed automatically when it expires
_token_cache: dict = {"token": "", "expires_at": 0}

# Semaphore: allow max 5 concurrent watsonx calls to stay under the 10-request limit
_watsonx_sem = asyncio.Semaphore(5)


async def _get_iam_token() -> str:
    """Return a valid IBM Cloud IAM Bearer token, refreshing it if expired."""
    now = time.time()
    # Refresh 60 s before real expiry to avoid edge-case rejections
    if _token_cache["token"] and now < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            IAM_TOKEN_URL,
            data={
                "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                "apikey":     WATSONX_APIKEY,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=401,
            detail=f"IBM IAM token fetch failed ({resp.status_code}): {resp.text}",
        )

    data = resp.json()
    _token_cache["token"]      = data["access_token"]
    _token_cache["expires_at"] = now + int(data.get("expires_in", 3600))
    return _token_cache["token"]

SYSTEM_PROMPT = """You are NutriAI — an expert AI Nutrition Agent and Virtual Dietitian.
Your role is to provide personalized, science-backed nutritional advice based on the user's health profile.

For every response:
1. Analyse the user's health profile carefully before responding.
2. Recommend specific nutrients, vitamins, and minerals they SHOULD prioritise, with reasoning.
3. List foods they SHOULD EAT with portion guidance and why each food helps.
4. List foods or substances they SHOULD AVOID with clear health-based reasoning.
5. Suggest healthy alternatives for anything you advise against.
6. If a meal plan is requested, structure it clearly by day and meal.
7. Always end with: "⚠️ Please consult a licensed doctor or registered dietitian for clinical decisions."

Format responses with clear sections using markdown-style headers (## Section) and bullet points.
Be empathetic, encouraging, precise, and concise."""

# ── Pydantic models ────────────────────────────────────────────────────────────
class HealthProfile(BaseModel):
    age:                  Optional[int]   = None
    gender:               Optional[str]   = None
    weight_kg:            Optional[float] = None
    height_cm:            Optional[float] = None
    health_conditions:    Optional[str]   = None
    dietary_preferences:  Optional[str]   = None
    health_goal:          Optional[str]   = None
    message:              str

class ChatMessage(BaseModel):
    message:              str
    conversation_history: Optional[List[dict]] = Field(default_factory=list)

class FoodAnalyzeRequest(BaseModel):
    food:             str
    health_condition: Optional[str] = None

class MealPlanRequest(BaseModel):
    goal:                Optional[str] = "general health"
    days:                Optional[int] = 3
    health_conditions:   Optional[str] = "none"
    dietary_preferences: Optional[str] = "no restrictions"

class NutrientSearchRequest(BaseModel):
    query: str

class BMIRequest(BaseModel):
    weight_kg: float
    height_cm: float
    age:       Optional[int] = None
    gender:    Optional[str] = None

class DeficiencyRequest(BaseModel):
    symptoms: str
    age:      Optional[int] = None
    gender:   Optional[str] = None

# ── Helpers ────────────────────────────────────────────────────────────────────
def _build_profile_context(profile: HealthProfile) -> str:
    parts = []
    if profile.age:               parts.append(f"Age: {profile.age}")
    if profile.gender:            parts.append(f"Gender: {profile.gender}")
    if profile.weight_kg:         parts.append(f"Weight: {profile.weight_kg} kg")
    if profile.height_cm:         parts.append(f"Height: {profile.height_cm} cm")
    if profile.health_conditions: parts.append(f"Health Conditions: {profile.health_conditions}")
    if profile.dietary_preferences: parts.append(f"Dietary Preferences: {profile.dietary_preferences}")
    if profile.health_goal:       parts.append(f"Health Goal: {profile.health_goal}")
    return "\n".join(parts)


async def _call_watsonx(messages: list) -> str:
    """
    Call watsonx chat endpoint.
    - Respects a semaphore (max 5 concurrent) to avoid 429 from the free tier.
    - Retries with exponential backoff on 429.
    - Falls back to smaller models if primary is rate-limited on all retries.
    """
    async with _watsonx_sem:
        token = await _get_iam_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        base_params = {
            "max_new_tokens":     1200,
            "temperature":        0.7,
            "top_p":              0.9,
            "repetition_penalty": 1.05,
        }

        last_error = None
        for model in MODELS:
            # Retry this model up to 3 times with backoff on 429
            for attempt in range(3):
                payload = {
                    "model_id":   model,
                    "project_id": PROJECT_ID,
                    "messages":   messages,
                    "parameters": base_params,
                }
                try:
                    async with httpx.AsyncClient(timeout=90.0) as client:
                        resp = await client.post(WATSONX_URL, json=payload, headers=headers)
                except httpx.TimeoutException:
                    raise HTTPException(status_code=504, detail="watsonx API timed out. Please retry.")
                except httpx.RequestError as exc:
                    raise HTTPException(status_code=502, detail=f"Network error: {exc}")

                if resp.status_code == 200:
                    try:
                        return resp.json()["choices"][0]["message"]["content"]
                    except (KeyError, IndexError):
                        raise HTTPException(status_code=500,
                                            detail=f"Unexpected watsonx response: {resp.text}")

                if resp.status_code == 401:
                    # Token expired mid-flight — force refresh and retry once
                    _token_cache["expires_at"] = 0
                    token = await _get_iam_token()
                    headers["Authorization"] = f"Bearer {token}"
                    continue

                if resp.status_code == 429:
                    wait = 2 ** attempt          # 1 s, 2 s, 4 s
                    last_error = resp.text
                    await asyncio.sleep(wait)
                    continue                      # retry same model

                # Any other error — don't retry, fail immediately
                raise HTTPException(status_code=resp.status_code,
                                    detail=f"watsonx error {resp.status_code}: {resp.text}")

            # All retries exhausted for this model — try the next one

        # All models exhausted
        raise HTTPException(
            status_code=429,
            detail=(
                "The IBM watsonx free-tier rate limit is currently reached across all available models. "
                "Please wait 30–60 seconds and try again. "
                f"Last error: {last_error}"
            ),
        )


def _bmi_category(bmi: float) -> str:
    if bmi < 18.5: return "Underweight"
    if bmi < 25.0: return "Normal weight"
    if bmi < 30.0: return "Overweight"
    return "Obese"

# ── Static files — serve frontend ──────────────────────────────────────────────
_frontend_dir = Path(__file__).parent.parent / "frontend"
if _frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_frontend_dir)), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_index():
        return FileResponse(str(_frontend_dir / "index.html"))

# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health_check():
    """Liveness probe."""
    return {
        "status": "ok",
        "agent":  "NutriAI v2.0",
        "model":  MODEL_ID,
        "project": PROJECT_ID,
    }


@app.post("/api/nutrition-advice", tags=["Nutrition"])
async def get_nutrition_advice(profile: HealthProfile):
    """
    Get personalised nutrition advice based on the user's full health profile.
    All profile fields are optional — provide as many as available for better advice.
    """
    ctx = _build_profile_context(profile)
    user_content = f"## My Health Profile\n{ctx}\n\n## My Question\n{profile.message}" if ctx else profile.message
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_content},
    ]
    advice = await _call_watsonx(messages)
    return {"advice": advice, "status": "success"}


@app.post("/api/chat", tags=["Chat"])
async def chat(chat_msg: ChatMessage):
    """
    Multi-turn conversation endpoint.
    Pass the full conversation_history array from previous turns to maintain context.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    # Include last 10 turns max to avoid token overflow
    for turn in chat_msg.conversation_history[-10:]:
        if turn.get("role") in ("user", "assistant"):
            messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": chat_msg.message})
    reply = await _call_watsonx(messages)
    return {"reply": reply, "status": "success"}


@app.post("/api/analyze-food", tags=["Nutrition"])
async def analyze_food(req: FoodAnalyzeRequest):
    """
    Analyse the full nutritional profile of a specific food item.
    Optionally evaluate its suitability for a health condition.
    """
    prompt = f"Analyse the complete nutritional profile of '{req.food}'."
    if req.health_condition:
        prompt += (
            f"\n\nAlso assess: Is it suitable for someone with {req.health_condition}? "
            "List specific benefits, risks, recommended portions, and any preparation tips."
        )
    else:
        prompt += (
            "\n\nCover: macronutrients (protein/carbs/fat/fibre), key micronutrients, "
            "glycaemic index, health benefits, cautions, and best preparation methods."
        )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": prompt},
    ]
    analysis = await _call_watsonx(messages)
    return {"analysis": analysis, "food": req.food, "status": "success"}


@app.post("/api/meal-plan", tags=["Nutrition"])
async def generate_meal_plan(req: MealPlanRequest):
    """
    Generate a personalised multi-day meal plan.
    """
    days = min(max(req.days or 3, 1), 7)
    prompt = (
        f"Create a detailed {days}-day meal plan for the following profile:\n\n"
        f"- Health Goal: {req.goal}\n"
        f"- Health Conditions: {req.health_conditions}\n"
        f"- Dietary Preferences: {req.dietary_preferences}\n\n"
        "Format each day as:\n"
        "**Day N**\n"
        "- Breakfast: [meal] | ~[calories] kcal | [key nutrients]\n"
        "- Morning Snack: ...\n"
        "- Lunch: ...\n"
        "- Afternoon Snack: ...\n"
        "- Dinner: ...\n"
        "- Daily Total: ~X kcal\n\n"
        "End with a brief summary of why this plan supports the stated health goal."
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": prompt},
    ]
    plan = await _call_watsonx(messages)
    return {"meal_plan": plan, "days": days, "status": "success"}


@app.post("/api/check-deficiency", tags=["Nutrition"])
async def check_deficiency(req: DeficiencyRequest):
    """
    Identify potential nutrient deficiencies from reported symptoms.
    """
    profile = ""
    if req.age:    profile += f"Age: {req.age}\n"
    if req.gender: profile += f"Gender: {req.gender}\n"

    prompt = (
        f"{profile}"
        f"Reported symptoms: {req.symptoms}\n\n"
        "For each likely nutrient deficiency:\n"
        "1. Name the nutrient and its essential role\n"
        "2. Explain why the deficiency causes these symptoms\n"
        "3. List the top 5 food sources\n"
        "4. Recommend daily intake target\n"
        "5. State whether supplementation is appropriate\n"
        "6. Flag any symptoms that need urgent medical evaluation"
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": prompt},
    ]
    result = await _call_watsonx(messages)
    return {"result": result, "status": "success"}


@app.post("/api/bmi", tags=["Calculators"])
async def calculate_bmi(req: BMIRequest):
    """
    Calculate BMI, categorise it, and get AI-driven nutritional recommendations.
    """
    if req.height_cm <= 0 or req.weight_kg <= 0:
        raise HTTPException(status_code=400, detail="Weight and height must be positive numbers.")

    height_m = req.height_cm / 100
    bmi      = round(req.weight_kg / (height_m ** 2), 1)
    category = _bmi_category(bmi)

    # Ideal weight range (BMI 18.5–24.9)
    ideal_low  = round(18.5 * height_m ** 2, 1)
    ideal_high = round(24.9 * height_m ** 2, 1)

    # AI nutrition tips for this BMI
    profile_parts = [f"BMI: {bmi} ({category})"]
    if req.age:    profile_parts.append(f"Age: {req.age}")
    if req.gender: profile_parts.append(f"Gender: {req.gender}")

    prompt = (
        f"My health profile:\n" + "\n".join(profile_parts) + "\n\n"
        f"Based on my BMI of {bmi} ({category}), give me:\n"
        "1. What this BMI means for my health\n"
        "2. Top 5 dietary changes I should make\n"
        "3. Foods to prioritise and foods to reduce\n"
        "4. A daily calorie range target\n"
        "5. A brief motivational note"
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": prompt},
    ]
    tips = await _call_watsonx(messages)
    return {
        "bmi":        bmi,
        "category":   category,
        "ideal_low":  ideal_low,
        "ideal_high": ideal_high,
        "tips":       tips,
        "status":     "success",
    }


@app.post("/api/nutrient-search", tags=["Nutrition"])
async def nutrient_search(req: NutrientSearchRequest):
    """
    Search for information about a specific nutrient, vitamin, or mineral.
    """
    prompt = (
        f"Provide a comprehensive guide on: {req.query}\n\n"
        "Cover:\n"
        "## What it is\n"
        "## Why it matters (health benefits)\n"
        "## Daily recommended intake (by age/gender)\n"
        "## Top 10 food sources with approximate amounts\n"
        "## Signs of deficiency\n"
        "## Signs of excess / toxicity\n"
        "## Interactions with medications or conditions to be aware of"
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": prompt},
    ]
    info = await _call_watsonx(messages)
    return {"info": info, "query": req.query, "status": "success"}


# ── Global error handler ───────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}", "status": "error"},
    )
