"""
LLM Client Module for EMAIL READER.
Configured for GROQ API using groq SDK with automatic API key rotation and model fallback.
"""

from typing import Dict, Any, List, Optional
import json
from groq import Groq
from config import Config
from tools.utils import setup_logger
from tools.token_tracker import check_preflight_quota, record_successful_usage, update_usage_from_429_error

logger = setup_logger("groq_client")


class GroqClient:
    """Wrapper class around the Groq API client with auto key-rotation on rate limits."""

    def __init__(self) -> None:
        import os
        from dotenv import load_dotenv
        # Dynamic reload of .env to pick up any changes
        load_dotenv(override=True)

        self.api_keys = []
        # Populate all configured keys from env
        for key_name in ["GROQ_API_KEY", "GROQ_API_KEY_2", "GROQ_API_KEY_3", "GROQ_API_KEY_4", "GROQ_API_KEY_5"]:
            k = os.getenv(key_name, "").strip()
            if k and k != "gsk_your_groq_api_key_here":
                if k not in self.api_keys:
                    self.api_keys.append(k)

        # Fallback to Config.GROQ_API_KEY if not in list
        if Config.GROQ_API_KEY and Config.GROQ_API_KEY != "gsk_your_groq_api_key_here":
            if Config.GROQ_API_KEY not in self.api_keys:
                self.api_keys.insert(0, Config.GROQ_API_KEY)

        self.current_key_idx = 0
        self._init_client()

    def _init_client(self) -> None:
        if not self.api_keys:
            logger.warning("No GROQ API keys are configured.")
            self.client = None
        else:
            current_key = self.api_keys[self.current_key_idx]
            prefix = current_key[:15] if current_key else "none"
            logger.info(f"Initializing Groq client with key index {self.current_key_idx} (prefix: {prefix})")
            self.client = Groq(api_key=current_key)

    def rotate_key(self) -> bool:
        """Rotates to the next available API key. Returns True if rotated, False if only 1 key configured."""
        if len(self.api_keys) <= 1:
            return False
        self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys)
        self._init_client()
        return True

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
        Includes automatic model fallbacks and multi-key rotation on 429 errors.
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
            # We allow up to len(self.api_keys) attempts per model if rate limits occur
            key_attempts = max(1, len(self.api_keys))
            for attempt in range(key_attempts):
                try:
                    logger.debug(f"Calling Groq model={current_model} with JSON mode={response_json} (key index={self.current_key_idx})")
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
                    logger.warning(f"Groq API call failed for model '{current_model}' (key index={self.current_key_idx}): {e}")

                    # Check for rate limit / 429 error
                    if "429" in err_msg or "rate" in err_msg.lower() or "limit" in err_msg.lower():
                        update_usage_from_429_error(err_msg)
                        if self.rotate_key():
                            logger.warning(f"Rate limit hit! Rotated to key index {self.current_key_idx}. Retrying same model...")
                            continue  # Retry key loop on current model
                    
                    # If it's a JSON validation error or other 400 error, switch to next model immediately
                    if "400" in err_msg:
                        break  # Break key_attempts loop to go to next model fallback

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
