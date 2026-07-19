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
            logger.error(f"Groq API call failed: {e}")
            raise
