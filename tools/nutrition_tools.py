from ibm_watsonx_orchestrate.agent_builder.tools import tool
import httpx
import os
import time
from typing import Optional

WATSONX_URL   = "https://us-south.ml.cloud.ibm.com/ml/v1/text/chat?version=2023-05-29"
IAM_TOKEN_URL = "https://iam.cloud.ibm.com/identity/token"
PROJECT_ID    = "dd6cb8ce-c2cd-48ea-ba0d-068062af2b13"
WATSONX_APIKEY = os.getenv("WATSONX_APIKEY", "iEcAYr__w_EdxG7RTUOM2fZ-uPSaaL-d3_8GLRyUrG63")

MODELS = [
    "meta-llama/llama-3-3-70b-instruct",
    "meta-llama/llama-3-1-8b-instruct",
    "ibm/granite-3-3-8b-instruct",
]

# In-memory token cache
_token_cache: dict = {"token": "", "expires_at": 0}


def _get_iam_token_sync() -> str:
    """Fetch or return cached IBM Cloud IAM Bearer token."""
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"] - 60:
        return _token_cache["token"]
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            IAM_TOKEN_URL,
            data={"grant_type": "urn:ibm:params:oauth:grant-type:apikey", "apikey": WATSONX_APIKEY},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    resp.raise_for_status()
    data = resp.json()
    _token_cache["token"]      = data["access_token"]
    _token_cache["expires_at"] = now + int(data.get("expires_in", 3600))
    return _token_cache["token"]

NUTRITION_SYSTEM_PROMPT = """You are an expert Nutrition Agent and Dietitian AI assistant.
Your role is to provide personalized nutritional advice to humans based on their health profile.
For every response:
1. Analyze the user's health profile carefully.
2. Recommend specific nutrients, vitamins, and minerals they SHOULD prioritize.
3. List foods they SHOULD eat with nutritional reasoning.
4. List foods or substances they SHOULD AVOID with health-based reasoning.
5. Suggest a simple meal plan if requested.
6. Provide healthy food alternatives when advising against something.
7. Always remind users to consult a licensed doctor or dietitian for clinical decisions.
Be empathetic, clear, science-backed, and concise. Use bullet points for readability."""


def _call_watsonx_sync(messages: list) -> str:
    """Call watsonx with auto token refresh and model fallback on 429."""
    token = _get_iam_token_sync()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    params  = {"max_new_tokens": 1200, "temperature": 0.7, "top_p": 0.9}

    for model in MODELS:
        for attempt in range(3):
            payload = {"model_id": model, "project_id": PROJECT_ID,
                       "messages": messages, "parameters": params}
            with httpx.Client(timeout=90.0) as client:
                resp = client.post(WATSONX_URL, json=payload, headers=headers)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            if resp.status_code == 401:
                _token_cache["expires_at"] = 0
                token = _get_iam_token_sync()
                headers["Authorization"] = f"Bearer {token}"
                continue
            if resp.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
    raise RuntimeError("watsonx rate limit reached on all models. Please retry later.")


@tool
def get_nutrition_advice(
    message: str,
    age: Optional[int] = None,
    gender: Optional[str] = None,
    weight_kg: Optional[float] = None,
    height_cm: Optional[float] = None,
    health_conditions: Optional[str] = None,
    dietary_preferences: Optional[str] = None,
    health_goal: Optional[str] = None,
) -> str:
    """
    Get personalized nutrition advice based on the user's health profile.

    Args:
        message: The user's nutrition-related question or concern.
        age: User's age in years.
        gender: User's gender (male/female/other).
        weight_kg: User's weight in kilograms.
        height_cm: User's height in centimetres.
        health_conditions: Any existing health conditions (e.g. diabetes, hypertension).
        dietary_preferences: Dietary restrictions or preferences (e.g. vegan, gluten-free).
        health_goal: The user's health goal (e.g. weight loss, muscle gain, manage diabetes).

    Returns:
        Personalised nutritional advice from the AI dietitian.
    """
    profile_parts = []
    if age:              profile_parts.append(f"Age: {age}")
    if gender:           profile_parts.append(f"Gender: {gender}")
    if weight_kg:        profile_parts.append(f"Weight: {weight_kg} kg")
    if height_cm:        profile_parts.append(f"Height: {height_cm} cm")
    if health_conditions: profile_parts.append(f"Health Conditions: {health_conditions}")
    if dietary_preferences: profile_parts.append(f"Dietary Preferences: {dietary_preferences}")
    if health_goal:      profile_parts.append(f"Health Goal: {health_goal}")

    profile_ctx = "\n".join(profile_parts)
    user_content = f"{profile_ctx}\n\nQuestion: {message}" if profile_ctx else message

    messages = [
        {"role": "system", "content": NUTRITION_SYSTEM_PROMPT},
        {"role": "user",   "content": user_content},
    ]
    return _call_watsonx_sync(messages)


@tool
def analyze_food_nutrition(
    food_item: str,
    health_condition: Optional[str] = None,
) -> str:
    """
    Analyze the nutritional profile of a specific food item.

    Args:
        food_item: The name of the food to analyze (e.g. 'spinach', 'brown rice', 'banana').
        health_condition: Optional health condition to evaluate food suitability (e.g. diabetes).

    Returns:
        Detailed nutritional analysis of the food item.
    """
    prompt = f"Analyze the nutritional profile of '{food_item}'."
    if health_condition:
        prompt += (
            f" Is it suitable for someone with {health_condition}? "
            "Explain benefits and risks in detail."
        )
    else:
        prompt += " Include macronutrients, micronutrients, health benefits, and any cautions."

    messages = [
        {"role": "system", "content": NUTRITION_SYSTEM_PROMPT},
        {"role": "user",   "content": prompt},
    ]
    return _call_watsonx_sync(messages)


@tool
def generate_meal_plan(
    health_goal: str,
    health_conditions: Optional[str] = "none",
    dietary_preferences: Optional[str] = "no restrictions",
    days: Optional[int] = 3,
) -> str:
    """
    Generate a personalized multi-day meal plan for the user.

    Args:
        health_goal: The user's primary health goal (e.g. 'weight loss', 'muscle gain', 'manage diabetes').
        health_conditions: Existing health conditions to account for.
        dietary_preferences: Dietary restrictions or preferences.
        days: Number of days the meal plan should cover (default 3, max 7).

    Returns:
        A detailed day-by-day meal plan with nutritional notes.
    """
    days = min(max(days, 1), 7)
    prompt = (
        f"Create a {days}-day detailed meal plan:\n"
        f"Health Goal: {health_goal}\n"
        f"Health Conditions: {health_conditions}\n"
        f"Dietary Preferences: {dietary_preferences}\n\n"
        "Include breakfast, lunch, dinner, and two snacks per day with portion sizes and nutritional notes."
    )
    messages = [
        {"role": "system", "content": NUTRITION_SYSTEM_PROMPT},
        {"role": "user",   "content": prompt},
    ]
    return _call_watsonx_sync(messages)


@tool
def check_nutrient_deficiency(
    symptoms: str,
    age: Optional[int] = None,
    gender: Optional[str] = None,
) -> str:
    """
    Identify potential nutrient deficiencies based on reported symptoms.

    Args:
        symptoms: Description of physical symptoms (e.g. 'fatigue, hair loss, brittle nails').
        age: User's age in years.
        gender: User's gender.

    Returns:
        Likely nutrient deficiencies and recommended dietary interventions.
    """
    profile = ""
    if age:    profile += f"Age: {age}\n"
    if gender: profile += f"Gender: {gender}\n"

    prompt = (
        f"{profile}"
        f"The user is experiencing the following symptoms: {symptoms}\n\n"
        "Identify the most likely nutrient deficiencies causing these symptoms. "
        "For each deficiency explain: the nutrient, its role in the body, food sources rich in it, "
        "and whether a supplement might help. Also note any serious conditions to rule out with a doctor."
    )
    messages = [
        {"role": "system", "content": NUTRITION_SYSTEM_PROMPT},
        {"role": "user",   "content": prompt},
    ]
    return _call_watsonx_sync(messages)
