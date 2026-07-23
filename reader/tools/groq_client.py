"""
LLM Client Module for EMAIL READER.
Configured for GROQ API using groq SDK with single API key and model fallback.
"""

from typing import Dict, Any, List, Optional
import json
from groq import Groq
from config import Config
from tools.utils import setup_logger
from tools.token_tracker import check_preflight_quota, record_successful_usage, update_usage_from_429_error

logger = setup_logger("groq_client")


class GroqClient:
    """Wrapper class around the Groq API client configured for a single GROQ_API_KEY."""

    def __init__(self) -> None:
        import os
        from dotenv import load_dotenv
        # Dynamic reload of .env to pick up any changes
        load_dotenv(override=True)

        self.api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not self.api_key or self.api_key == "gsk_your_groq_api_key_here":
            self.api_key = Config.GROQ_API_KEY

        self._init_client()

    def _init_client(self) -> None:
        if not self.api_key or self.api_key == "gsk_your_groq_api_key_here":
            logger.warning("No GROQ API key is configured.")
            self.client = None
        else:
            prefix = self.api_key[:15] if self.api_key else "none"
            logger.info(f"Initializing Groq client (prefix: {prefix})")
            self.client = Groq(api_key=self.api_key)

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
        Includes automatic model fallbacks.
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

                # Check for rate limit / 429 error
                if "429" in err_msg or "rate" in err_msg.lower() or "limit" in err_msg.lower():
                    update_usage_from_429_error(err_msg)
                
                # If it's a JSON validation error or other 400 error, switch to next model immediately
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
