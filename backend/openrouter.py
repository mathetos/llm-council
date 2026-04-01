"""OpenRouter API client for making LLM requests."""

import httpx
from typing import List, Dict, Any, Optional, Tuple
from .config import OPENROUTER_API_KEY, OPENROUTER_API_URL
MODELS_USER_URL = "https://openrouter.ai/api/v1/models/user"
MODELS_URL = "https://openrouter.ai/api/v1/models"


async def query_model_with_error(
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = 120.0,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Query OpenRouter; returns (result, None) on success or (None, error_message) on failure.
    """
    if not OPENROUTER_API_KEY or not OPENROUTER_API_KEY.strip():
        err = "OPENROUTER_API_KEY is missing or empty in .env"
        print(f"Error querying model {model}: {err}")
        return None, err

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload
            )
            response.raise_for_status()

            data = response.json()
            message = data["choices"][0]["message"]

            return {
                "content": message.get("content"),
                "reasoning_details": message.get("reasoning_details"),
                # Routers (e.g., openrouter/free) may resolve to a different underlying model.
                "model_used": data.get("model"),
            }, None

    except httpx.HTTPStatusError as e:
        detail = (e.response.text or str(e))[:800]
        err = f"HTTP {e.response.status_code}: {detail}"
        print(f"Error querying model {model}: {err}")
        return None, err
    except httpx.RequestError as e:
        err = f"Network error: {e}"
        print(f"Error querying model {model}: {err}")
        return None, err
    except (KeyError, IndexError, ValueError) as e:
        err = f"Unexpected API response: {e}"
        print(f"Error querying model {model}: {err}")
        return None, err


async def query_model(
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = 120.0
) -> Optional[Dict[str, Any]]:
    """
    Query a single model via OpenRouter API.

    Args:
        model: OpenRouter model identifier (e.g., "openai/gpt-4o")
        messages: List of message dicts with 'role' and 'content'
        timeout: Request timeout in seconds

    Returns:
        Response dict with 'content' and optional 'reasoning_details', or None if failed
    """
    result, _ = await query_model_with_error(model, messages, timeout=timeout)
    return result


async def query_models_parallel(
    models: List[str],
    messages: List[Dict[str, str]]
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Query multiple models in parallel.

    Args:
        models: List of OpenRouter model identifiers
        messages: List of message dicts to send to each model

    Returns:
        Dict mapping model identifier to response dict (or None if failed)
    """
    import asyncio

    # Create tasks for all models
    tasks = [query_model(model, messages) for model in models]

    # Wait for all to complete
    responses = await asyncio.gather(*tasks)

    # Map models to their responses
    return {model: response for model, response in zip(models, responses)}


async def list_user_visible_models_with_error(
    timeout: float = 30.0,
) -> Tuple[Optional[List[str]], Optional[str]]:
    """
    List model ids visible to the current API key after user preference filtering.

    Returns:
        (model_ids, None) on success, (None, error_message) on failure.
    """
    if not OPENROUTER_API_KEY or not OPENROUTER_API_KEY.strip():
        err = "OPENROUTER_API_KEY is missing or empty in .env"
        return None, err

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(MODELS_USER_URL, headers=headers)
            response.raise_for_status()
            data = response.json()
            model_ids = [
                item.get("id")
                for item in (data.get("data") or [])
                if isinstance(item, dict) and item.get("id")
            ]
            return model_ids, None
    except httpx.HTTPStatusError as e:
        detail = (e.response.text or str(e))[:800]
        return None, f"HTTP {e.response.status_code}: {detail}"
    except httpx.RequestError as e:
        return None, f"Network error: {e}"
    except (KeyError, IndexError, ValueError, TypeError) as e:
        return None, f"Unexpected API response: {e}"


async def list_models_with_error(
    timeout: float = 30.0,
) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    """
    List all OpenRouter models and basic metadata.

    Returns:
        (models, None) on success, (None, error_message) on failure.
    """
    if not OPENROUTER_API_KEY or not OPENROUTER_API_KEY.strip():
        err = "OPENROUTER_API_KEY is missing or empty in .env"
        return None, err

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(MODELS_URL, headers=headers)
            response.raise_for_status()
            data = response.json()
            models = [item for item in (data.get("data") or []) if isinstance(item, dict)]
            return models, None
    except httpx.HTTPStatusError as e:
        detail = (e.response.text or str(e))[:800]
        return None, f"HTTP {e.response.status_code}: {detail}"
    except httpx.RequestError as e:
        return None, f"Network error: {e}"
    except (KeyError, IndexError, ValueError, TypeError) as e:
        return None, f"Unexpected API response: {e}"
