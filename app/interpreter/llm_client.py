"""
LLM Client for GridWise operator notes interpretation.
Supports Google Gemini, OpenAI/Groq, and robust deterministic fallback.
"""

import json
import logging
from typing import Any, Dict, List, Optional
import httpx

from app.config import settings
from app.interpreter.prompts import SYSTEM_PROMPT, FEW_SHOT_EXAMPLES
from app.interpreter.fallback import interpret_note_fallback
from app.schemas import DirectiveInterpretation

logger = logging.getLogger(__name__)


def build_user_prompt(operator_notes: List[str], capacity_kwh: float) -> str:
    prompt = f"Battery Capacity: {capacity_kwh} kWh\n"
    prompt += "Operator Notes to Interpret:\n"
    for idx, note in enumerate(operator_notes):
        prompt += f'Note {idx}: "{note}"\n'
    prompt += "\nReturn a JSON array with one object per note in sequential note_index order (0, 1, ...)."
    return prompt


def parse_llm_json(content: str) -> Optional[List[Dict[str, Any]]]:
    """Cleans code blocks and parses JSON output from LLM."""
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()
    try:
        data = json.loads(content)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "directives" in data:
            return data["directives"]
        if isinstance(data, dict) and "directive_interpretation" in data:
            return data["directive_interpretation"]
        return None
    except Exception as e:
        logger.warning(f"Failed to parse LLM JSON: {e}")
        return None


async def call_gemini(user_prompt: str) -> Optional[str]:
    """Calls Google Gemini API using REST."""
    if not settings.GEMINI_API_KEY:
        return None
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.MODEL_NAME}:generateContent?key={settings.GEMINI_API_KEY}"
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": f"{SYSTEM_PROMPT}\n\n{FEW_SHOT_EXAMPLES}\n\n{user_prompt}"}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json"
        }
    }
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code == 200:
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        else:
            logger.warning(f"Gemini API returned status {resp.status_code}: {resp.text}")
            return None


async def call_openai(user_prompt: str) -> Optional[str]:
    """Calls OpenAI-compatible API (OpenAI, Groq, Ollama, OpenRouter)."""
    if not settings.OPENAI_API_KEY:
        return None
        
    base_url = settings.OPENAI_BASE_URL or "https://api.openai.com/v1"
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": settings.MODEL_NAME,
        "messages": [
            {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{FEW_SHOT_EXAMPLES}"},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"} if "gpt-4" in settings.MODEL_NAME else None
    }
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code == 200:
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        else:
            logger.warning(f"OpenAI API returned status {resp.status_code}: {resp.text}")
            return None


async def interpret_operator_notes(operator_notes: List[str], capacity_kwh: float) -> List[DirectiveInterpretation]:
    """
    Interprets 1-3 operator notes using configured LLM provider,
    with automatic fallback to deterministic interpreter if unavailable or invalid.
    """
    user_prompt = build_user_prompt(operator_notes, capacity_kwh)
    parsed_items: Optional[List[Dict[str, Any]]] = None

    if settings.LLM_PROVIDER == "gemini":
        try:
            content = await call_gemini(user_prompt)
            if content:
                parsed_items = parse_llm_json(content)
        except Exception as e:
            logger.warning(f"Gemini LLM call failed: {e}")

    elif settings.LLM_PROVIDER in ("openai", "groq"):
        try:
            content = await call_openai(user_prompt)
            if content:
                parsed_items = parse_llm_json(content)
        except Exception as e:
            logger.warning(f"OpenAI LLM call failed: {e}")

    # Fallback to rule-based parser if LLM failed, returned invalid structure, or LLM_PROVIDER is fallback
    results: List[DirectiveInterpretation] = []
    
    if parsed_items and len(parsed_items) == len(operator_notes):
        try:
            for idx, item in enumerate(parsed_items):
                # Ensure note_index matches
                item["note_index"] = idx
                entry = DirectiveInterpretation(**item)
                results.append(entry)
            return results
        except Exception as e:
            logger.warning(f"LLM items failed schema validation: {e}. Using deterministic fallback.")
            results = []

    # Deterministic fallback per note
    for idx, note in enumerate(operator_notes):
        entry = interpret_note_fallback(note, idx, capacity_kwh)
        results.append(entry)

    return results
