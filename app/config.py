"""
Configuration settings for the GridWise application.
Loads from environment variables and .env file.
"""

import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


class Settings:
    GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    OPENAI_BASE_URL: Optional[str] = os.getenv("OPENAI_BASE_URL")
    
    # Provider: gemini, openai, groq, or fallback
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "").lower()
    if not LLM_PROVIDER:
        if GEMINI_API_KEY:
            LLM_PROVIDER = "gemini"
        elif OPENAI_API_KEY:
            LLM_PROVIDER = "openai"
        else:
            LLM_PROVIDER = "fallback"

    MODEL_NAME: str = os.getenv("MODEL_NAME", "")
    if not MODEL_NAME:
        if LLM_PROVIDER == "gemini":
            MODEL_NAME = "gemini-1.5-flash"
        elif LLM_PROVIDER in ("openai", "groq"):
            MODEL_NAME = "gpt-4o-mini"
        else:
            MODEL_NAME = "rule-based-fallback"

    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    TIMEOUT_SECONDS: float = float(os.getenv("TIMEOUT_SECONDS", "25.0"))


settings = Settings()
