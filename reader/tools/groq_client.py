"""
Groq Client Utility Module for EMAIL READER.
Manages the instantiation and chat completions from the Groq API.
"""

from typing import Dict, Any, List, Optional
import json
from groq import Groq
from config import Config
from tools.utils import setup_logger

logger = setup_logger("groq_client")


class GroqClient:
    """Wrapper class around the Groq API client."""

    def __init__(self) -> None:
        if not Config.GROQ_API_KEY or Config.GROQ_API_KEY == "gsk_your_groq_api_key_here":
            logger.warning("GROQ_API_KEY is not configured. AI functions will fall back to rule-based mock responses.")
            self.client = None
        else:
            self.client = Groq(api_key=Config.GROQ_API_KEY)

    def is_available(self) -> bool:
        """Returns True if the Groq client is configured and available."""
        return self.client is not None

    def get_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = "llama-3.3-70b-versatile",
        temperature: float = 0.2,
        response_json: bool = False
    ) -> str:
        """
        Requests a completion from the Groq API.
        
        Args:
            system_prompt: Context instruction for the model.
            user_prompt: User instruction or input data.
            model: Model name.
            temperature: LLM temperature parameter.
            response_json: Whether to enforce JSON output format.
            
        Returns:
            The string content of the response.
        """
        if not self.is_available():
            raise ValueError("Groq client is not initialized. Please configure GROQ_API_KEY.")

        logger.debug(f"Calling Groq model={model} with JSON mode={response_json}")
        
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": temperature
        }
        
        if response_json:
            kwargs["response_format"] = {"type": "json_object"}
            
        try:
            response = self.client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content.strip()
            return content
        except Exception as e:
            error_msg = str(e).lower()
            if "rate limit reached" in error_msg or "rate_limit_exceeded" in error_msg or "413" in error_msg or "429" in error_msg:
                import time
                logger.warning(f"Rate limit / token limit hit ({e}). Waiting 2s before fallback...")
                time.sleep(2)
                
                # Truncate user prompt to safe size (12,000 characters max ~ 3,000 tokens)
                truncated_user_prompt = user_prompt
                if len(user_prompt) > 12000:
                    half = 6000
                    truncated_user_prompt = user_prompt[:half] + "\n\n...[TRUNCATED FOR FALLBACK MODEL]...\n\n" + user_prompt[-half:]

                for fallback_model in ["llama-3.1-8b-instant", "mixtral-8x7b-32768", "llama3-70b-8192"]:
                    if fallback_model == model:
                        continue
                    try:
                        logger.info(f"Retrying with fallback model {fallback_model}...")
                        kwargs["model"] = fallback_model
                        kwargs["messages"] = [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": truncated_user_prompt}
                        ]
                        response = self.client.chat.completions.create(**kwargs)
                        content = response.choices[0].message.content.strip()
                        return content
                    except Exception as fallback_e:
                        logger.warning(f"Fallback {fallback_model} failed: {fallback_e}")
                        time.sleep(1)
                        
            logger.error(f"Groq API call failed: {e}")
            raise
