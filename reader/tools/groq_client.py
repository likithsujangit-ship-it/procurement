"""
LLM Client Module for EMAIL READER.
Configured for GROQ API using groq SDK with automatic model fallback and preflight token quota tracking.
"""

from typing import Dict, Any, List, Optional
import json
from groq import Groq
from config import Config
from tools.utils import setup_logger
from tools.token_tracker import check_preflight_quota, record_successful_usage, update_usage_from_429_error

logger = setup_logger("groq_client")


class GroqClient:
    """Wrapper class around the Groq API client."""

    def __init__(self) -> None:
        if not Config.GROQ_API_KEY or Config.GROQ_API_KEY == "gsk_your_groq_api_key_here":
            logger.warning("GROQ_API_KEY is not configured.")
            self.client = None
        else:
            self.client = Groq(api_key=Config.GROQ_API_KEY)

    def is_available(self) -> bool:
        """Returns True if the LLM client is configured and available."""
        return self.client is not None

    def get_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "llama-3.3-70b-versatile",
        temperature: float = 0.2,
        response_json: bool = False,
        json_schema: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Requests a multi-turn or single-turn chat completion using Groq API.
        Includes preflight quota checks and cumulative token usage tracking.
        """
        if not self.is_available():
            raise ValueError("LLM client is not initialized. Please configure GROQ_API_KEY.")

        # Estimate request token cost (rough ~4 chars/token)
        total_prompt_chars = sum(len(m.get("content", "")) for m in messages)
        estimated_tokens = max(100, total_prompt_chars // 4)

        if not check_preflight_quota(estimated_tokens):
            raise Exception("Preflight token quota check failed: Daily token limit reached")

        # Map Gemini or obsolete model names to Groq models if passed
        if "gemini" in model.lower() or "qwen" in model.lower() or "mixtral" in model.lower() or "gpt-oss" in model.lower():
            model = "llama-3.3-70b-versatile"

        models_to_try = [model]
        for alt in ("llama-3.3-70b-versatile", "llama-3.1-8b-instant", "qwen/qwen3.6-27b", "openai/gpt-oss-20b"):
            if alt not in models_to_try:
                models_to_try.append(alt)

        kwargs: Dict[str, Any] = {
            "messages": messages,
            "temperature": temperature
        }
        
        if response_json or json_schema:
            kwargs["response_format"] = {"type": "json_object"}

        last_error = None
        for current_model in models_to_try:
            try:
                logger.debug(f"Calling Groq model={current_model} with JSON mode={response_json}")
                response = self.client.chat.completions.create(
                    model=current_model,
                    **kwargs
                )
                
                # Record token usage from response object
                actual_tokens = estimated_tokens
                if hasattr(response, "usage") and response.usage:
                    actual_tokens = getattr(response.usage, "total_tokens", estimated_tokens)
                record_successful_usage(actual_tokens)
                
                return response.choices[0].message.content.strip()

            except Exception as e:
                err_msg = str(e)
                last_error = e
                logger.warning(f"Groq API call failed for model '{current_model}': {e}")

                if "429" in err_msg or "rate" in err_msg.lower() or "limit" in err_msg.lower():
                    update_usage_from_429_error(err_msg)
                    continue

                if "400" in err_msg:
                    continue

        logger.error(f"All Groq model attempts failed. Last error: {last_error}")
        raise last_error

    def get_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = "llama-3.3-70b-versatile",
        temperature: float = 0.2,
        response_json: bool = False,
        json_schema: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Requests a single-turn completion using Groq API.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        return self.get_chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            response_json=response_json,
            json_schema=json_schema
        )
