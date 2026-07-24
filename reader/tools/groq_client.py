"""
LLM Client Module for EMAIL READER.
Configured for GROQ API and OpenRouter API dynamically, bypassing token tracking.
"""

from typing import Dict, Any, List, Optional
import os
import json
import time
import requests
from groq import Groq
from config import Config
from tools.utils import setup_logger

logger = setup_logger("groq_client")


class GroqClient:
    """Wrapper class around LLM clients configured for Groq and OpenRouter."""

    def __init__(self) -> None:
        from dotenv import load_dotenv
        # Dynamic reload of .env to pick up any changes
        load_dotenv(override=True)

        self.openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not self.openrouter_key:
            self.openrouter_key = getattr(Config, "OPENROUTER_API_KEY", "").strip()

        self.api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not self.api_key or self.api_key == "gsk_your_groq_api_key_here":
            self.api_key = Config.GROQ_API_KEY

        self.is_openrouter = bool(self.openrouter_key)
        self.client = None
        self._init_client()

    def _init_client(self) -> None:
        if self.is_openrouter:
            logger.info("Initializing OpenRouter API client")
        else:
            if not self.api_key or self.api_key == "gsk_your_groq_api_key_here":
                logger.warning("No GROQ API key is configured.")
                self.client = None
            else:
                prefix = self.api_key[:15] if self.api_key else "none"
                logger.info(f"Initializing Groq client (prefix: {prefix})")
                try:
                    self.client = Groq(api_key=self.api_key)
                except Exception as e:
                    logger.error(f"Failed to initialize Groq SDK client: {e}")
                    self.client = None

    def is_available(self) -> bool:
        """Returns True if at least one LLM client is configured and available."""
        if self.is_openrouter:
            return True
        return self.client is not None

    def get_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "llama-3.3-70b-versatile",
        temperature: float = 0.2,
        response_json: bool = False,
        json_schema: Optional[Dict[str, Any]] = None,
        task: str = "generic"
    ) -> str:
        """
        Requests a multi-turn or single-turn chat completion using either OpenRouter or Groq.
        Includes model routing based on task and api client type.
        """
        if not self.is_available():
            raise ValueError("LLM client is not initialized. Please configure GROQ_API_KEY or OPENROUTER_API_KEY.")

        # Map models if using OpenRouter
        if self.is_openrouter:
            # Route to Nous Hermes 3 Llama 3.1 405b for sub-5-second speed and perfect JSON compliance
            model = "nousresearch/hermes-3-llama-3.1-405b"
        else:
            # Map Gemini or obsolete model names to Groq models if passed
            if "gemini" in model.lower() or "qwen" in model.lower() or "mixtral" in model.lower() or "gpt-oss" in model.lower() or "claude" in model.lower():
                model = "llama-3.3-70b-versatile"

        models_to_try = [
            model,
            "meta-llama/llama-3.3-70b-instruct",     # Frontier 70B model
            "openai/gpt-oss-120b",                    # 120B model fallback
            "meta-llama/llama-3.3-70b-instruct:free" # 100% Free backup
        ]
        last_error = None

        for current_model in models_to_try:
            for attempt in range(3):
                try:
                    if self.is_openrouter:
                        logger.debug(f"Calling OpenRouter model={current_model} with JSON mode={response_json} (attempt {attempt+1}/3)")
                        headers = {
                            "Authorization": f"Bearer {self.openrouter_key}",
                            "Content-Type": "application/json",
                            "HTTP-Referer": "https://github.com/likithsujangit-ship-it/procurement",
                            "X-Title": "Procurement Reader"
                        }
                        payload = {
                            "model": current_model,
                            "messages": messages,
                            "temperature": temperature
                        }
                        if response_json or json_schema:
                            payload["response_format"] = {"type": "json_object"}

                        response = requests.post(
                            "https://openrouter.ai/api/v1/chat/completions",
                            headers=headers,
                            json=payload,
                            timeout=60
                        )
                        response.raise_for_status()
                        resp_data = response.json()
                        if "choices" not in resp_data or not resp_data["choices"]:
                            raise ValueError(f"Invalid OpenRouter response structure: {resp_data}")
                        content = resp_data["choices"][0]["message"]["content"].strip()
                    else:
                        logger.debug(f"Calling Groq model={current_model} with JSON mode={response_json} (attempt {attempt+1}/3)")
                        kwargs: Dict[str, Any] = {
                            "messages": messages,
                            "temperature": temperature
                        }
                        if response_json or json_schema:
                            kwargs["response_format"] = {"type": "json_object"}

                        response = self.client.chat.completions.create(
                            model=current_model,
                            **kwargs
                        )
                        content = response.choices[0].message.content.strip()

                    # Clean JSON response if markdown formatting is present
                    if response_json or json_schema:
                        content_cleaned = content.strip()
                        if "```" in content_cleaned:
                            parts = content_cleaned.split("```")
                            for part in parts:
                                part_cleaned = part.strip()
                                if part_cleaned.startswith("json"):
                                    part_cleaned = part_cleaned[4:].strip()
                                if (part_cleaned.startswith("{") and part_cleaned.endswith("}")) or (part_cleaned.startswith("[") and part_cleaned.endswith("]")):
                                    content_cleaned = part_cleaned
                                    break
                        else:
                            # Fallback: Extract from the first '{' to the last '}' or '[' to ']'
                            import json
                            try:
                                json.loads(content_cleaned)
                            except Exception:
                                # Try to find bounds of the first dict/list
                                first_curly = content_cleaned.find('{')
                                last_curly = content_cleaned.rfind('}')
                                if first_curly != -1 and last_curly != -1 and last_curly > first_curly:
                                    candidate = content_cleaned[first_curly:last_curly+1]
                                    try:
                                        json.loads(candidate)
                                        content_cleaned = candidate
                                    except Exception:
                                        pass
                                else:
                                    first_bracket = content_cleaned.find('[')
                                    last_bracket = content_cleaned.rfind(']')
                                    if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
                                        candidate = content_cleaned[first_bracket:last_bracket+1]
                                        try:
                                            json.loads(candidate)
                                            content_cleaned = candidate
                                        except Exception:
                                            pass
                        content = content_cleaned
                    return content

                except Exception as e:
                    err_msg = str(e)
                    last_error = e
                    logger.warning(f"LLM API call failed for model '{current_model}' (attempt {attempt+1}/3): {e}")

                    # Sleep on rate limit / 429 error
                    if "429" in err_msg or "rate" in err_msg.lower() or "limit" in err_msg.lower():
                        import re
                        wait_sec = 5.0
                        cleaned_msg = err_msg.replace("ms", "")
                        if "h" in cleaned_msg or "m" in cleaned_msg:
                            logger.warning("Rate limit wait time is too long. Switching/failing model.")
                            break
                            
                        match = re.search(r'try again in ([\d\.]+)s', err_msg)
                        if match:
                            wait_sec = float(match.group(1)) + 0.5
                            
                        if wait_sec <= 10.0:
                            logger.warning(f"Rate limit hit. Sleeping for {wait_sec} seconds before retry...")
                            time.sleep(wait_sec)
                            continue
                        else:
                            logger.warning(f"Rate limit wait time ({wait_sec}s) > 10s. Swapping/failing.")
                            break
                    break

        logger.error(f"All LLM model attempts failed. Last error: {last_error}")
        raise last_error

    def get_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = "llama-3.3-70b-versatile",
        temperature: float = 0.2,
        response_json: bool = False,
        json_schema: Optional[Dict[str, Any]] = None,
        task: str = "generic"
    ) -> str:
        """
        Requests a single-turn completion using LLM API.
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
            json_schema=json_schema,
            task=task
        )
