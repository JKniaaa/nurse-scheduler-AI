import os
import json
import re
from typing import Dict
from prompts import build_prompt
import logging
from dotenv import load_dotenv

# Lazy imports for providers
try:
    import openai
except ImportError:
    openai = None
try:
    import anthropic
except ImportError:
    anthropic = None

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(
    filename="scheduler.log",
    filemode="a",
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s"
)

load_dotenv()

# Read environment variables
provider = os.getenv("PROVIDER", "openai")
openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
openrouter_model = os.getenv("OPENROUTER_MODEL", "mistralai/mistral-7b-instruct")
openai_api_key = os.getenv("OPENAI_API_KEY")
openai_model = os.getenv("OPENAI_MODEL", "gpt-4-turbo")
anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
anthropic_model = os.getenv("ANTHROPIC_MODEL", "claude-3-sonnet-20240229")
deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

def call_llm(prompt: str) -> Dict:
    """Calls the configured AI provider and returns parsed JSON schedule."""
    
    if provider == "openai":
        if openai is None:
            raise RuntimeError("openai package not installed")
        openai.api_key = openai_api_key
        resp = openai.ChatCompletion.create(
            model=openai_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            functions=[{
                "name": "return_schedule",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "schedule": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "nurse": {"type": "string"},
                                    "date": {"type": "string", "format": "date"},
                                    "shift": {"type": "string", "enum": ["AM", "PM", "Night"]}
                                },
                                "required": ["nurse", "date", "shift"]
                            }
                        }
                    },
                    "required": ["schedule"]
                }
            }],
            function_call={"name": "return_schedule"}
        )
        args = resp.choices[0].message.function_call.arguments
        return json.loads(args)

    elif provider == "anthropic":
        if anthropic is None:
            raise RuntimeError("anthropic package not installed")
        client = anthropic.Client(api_key=anthropic_api_key)
        resp = client.completions.create(
            prompt=prompt,
            model=anthropic_model,
            temperature=0.2,
            max_tokens=2000
        )
        return json.loads(resp.completion)

    elif provider == "openrouter":
        headers = {
            "Authorization": f"Bearer {openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost"
        }

        payload = {
            "model": openrouter_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 25000
        }

        url = "https://openrouter.ai/api/v1/chat/completions"
        resp = requests.post(url, headers=headers, json=payload)
        logging.info(f"[LLM FULL RESPONSE] {resp.text}")
        try:
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if resp.status_code == 429:
                # Print rate limit reset time if available
                reset_timestamp = resp.headers.get("X-RateLimit-Reset")
                if reset_timestamp:
                    from datetime import datetime
                    reset_dt = datetime.fromtimestamp(int(reset_timestamp) / 1000)
                    logging.error(f"Rate limit exceeded. Try again at {reset_dt} (X-RateLimit-Reset)")
                else:
                    logging.error("Rate limit exceeded (429). No reset time provided.")
                raise RuntimeError("Rate limit exceeded (429). Please wait before retrying.")
            
            logging.error(f"HTTP error: {e}")
            logging.error(f"Response: {resp.text}")
            raise
        except requests.exceptions.HTTPError as e:
            logging.info(f"HTTP error: {e}")
            logging.info(f"Response: {resp.text}")
            raise

        content = resp.json()["choices"][0]["message"]["content"]
        logging.info(f"[LLM RAW OUTPUT] {content}")
        if not content.strip():
            raise RuntimeError("LLM response was empty.")

        # Robust JSON extraction
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Try JSON-looking object anywhere in text
            match = re.search(r'\{[\s\S]*\}', content)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass

            # Try fenced code block
            fenced = re.search(r"```json\s*([\s\S]*?)\s*```", content)
            if fenced:
                try:
                    return json.loads(fenced.group(1).strip())
                except json.JSONDecodeError:
                    pass

            first = content.find("{")
            last  = content.rfind("}")
            if first != -1 and last != -1:
                json_str = content[first:last+1]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    pass

            # Final fallback: raise with full content
            raise RuntimeError(f"LLM response was not valid JSON. Raw content:\n{content}")
        
    if provider == "deepseek":
        headers = {
            "Authorization": f"Bearer {deepseek_api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": deepseek_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            # "max_tokens": 7000,
            "stream": False
        }

        url = "https://api.deepseek.com/chat/completions"
        
        try:
            # Create session with retry mechanism
            session = requests.Session()
            retry_strategy = Retry(
                total=3,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["POST"]
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            session.mount("https://", adapter)
            
            # Increase timeout to 120 seconds
            resp = session.post(url, headers=headers, json=payload, timeout=120)
            resp.raise_for_status()
            logging.info(f"[DEEPSEEK FULL RESPONSE] {resp.text}")  # <-- Add this line
            response_data = resp.json()

            # Extract token usage
            usage = response_data.get('usage', {})
            prompt_tokens = usage.get('prompt_tokens', 0)
            completion_tokens = usage.get('completion_tokens', 0)
            total_tokens = usage.get('total_tokens', 0)
            
            logging.info(
                f"Token usage: Prompt={prompt_tokens}, "
                f"Completion={completion_tokens}, "
                f"Total={total_tokens}"
            )
            
            # Extract content from correct response structure
            content = response_data["choices"][0]["message"]["content"]
            logging.info(f"[DEEPSEEK RESPONSE] {content}")

            if content.strip().startswith("```"):
                content = re.sub(r"^```(?:json)?\s*|```$", "", content.strip(), flags=re.MULTILINE).strip()
            
            # Robust JSON extraction (same as before)
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                # Try JSON-looking object anywhere in text
                match = re.search(r'\{[\s\S]*\}', content)
                if match:
                    try:
                        return json.loads(match.group())
                    except json.JSONDecodeError:
                        pass

                # Try fenced code block
                fenced = re.search(r"```json\s*([\s\S]*?)\s*```", content)
                if fenced:
                    try:
                        return json.loads(fenced.group(1).strip())
                    except json.JSONDecodeError:
                        pass

                first = content.find("{")
                last  = content.rfind("}")
                if first != -1 and last != -1:
                    json_str = content[first:last+1]
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError:
                        pass

                # Final fallback: raise with full content
                raise RuntimeError(f"DeepSeek response was not valid JSON. Raw content:\n{content}")
                
        except requests.exceptions.RequestException as e:
            logging.error(f"DeepSeek API request failed: {str(e)}")
            if e.response is not None:
                logging.error(f"Response status: {e.response.status_code}")
                logging.error(f"Response body: {e.response.text}")
            raise RuntimeError("Failed to communicate with DeepSeek API")


    else:
        raise RuntimeError(f"Unsupported provider: {provider}")
