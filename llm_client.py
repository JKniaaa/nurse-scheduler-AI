import os
import json
import re
from typing import Dict
from prompts import build_prompt
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

load_dotenv()

# Read environment variables
provider = os.getenv("PROVIDER", "openai")
openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
openrouter_model = os.getenv("OPENROUTER_MODEL", "mistralai/mistral-7b-instruct")
openai_api_key = os.getenv("OPENAI_API_KEY")
openai_model = os.getenv("OPENAI_MODEL", "gpt-4-turbo")
anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
anthropic_model = os.getenv("ANTHROPIC_MODEL", "claude-3-sonnet-20240229")

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
            temperature=0.0,
            max_tokens=1024
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
        }

        url = "https://openrouter.ai/api/v1/chat/completions"
        resp = requests.post(url, headers=headers, json=payload)
        try:
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            print(f"HTTP error: {e}")
            print("Response:", resp.text)
            raise

        content = resp.json()["choices"][0]["message"]["content"]

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

            # Final fallback: raise with full content
            raise RuntimeError(f"LLM response was not valid JSON. Raw content:\n{content}")

    else:
        raise RuntimeError(f"Unsupported provider: {provider}")
