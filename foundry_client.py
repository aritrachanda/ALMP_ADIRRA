"""File Overview
This module is the single place that builds AI clients for Foundry/OpenAI calls.

Purpose
- Keep endpoint and API key handling consistent across the app.
- Prevent each feature from implementing its own client setup logic.
- Make future key/endpoint changes work app-wide from one place.

Structure
- `_load_env_if_needed(...)`: loads `.env` only when required variables are missing.
- `normalize_foundry_base_url(...)`: normalizes endpoint values to `/openai/v1` format.
- `create_foundry_client(...)`: validates config and returns a ready-to-use client.

Guarantee
Any module using `create_foundry_client(...)` follows the same configuration rules.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

_ROOT = Path(__file__).resolve().parent


def _load_env_if_needed(api_key_env: str, endpoint_env: str) -> None:
    """Load project .env if required Foundry variables are missing."""
    if os.environ.get(api_key_env) and os.environ.get(endpoint_env):
        return
    load_dotenv(_ROOT / ".env")


def normalize_foundry_base_url(endpoint: str) -> str:
    """Normalize Foundry endpoint to OpenAI v1 base URL format."""
    base_url = endpoint.strip().rstrip("/")
    if not base_url:
        return ""
    if not base_url.endswith("/openai/v1"):
        base_url = f"{base_url}/openai/v1"
    return base_url


def create_foundry_client(
    *,
    api_key: str | None = None,
    api_key_env: str = "AZURE_FOUNDRY_KEY",
    endpoint_env: str = "AZURE_FOUNDRY_ENDPOINT",
) -> OpenAI:
    """Create OpenAI client configured for Foundry endpoints."""
    _load_env_if_needed(api_key_env, endpoint_env)

    resolved_api_key = api_key if api_key is not None else os.environ.get(api_key_env, "")
    endpoint = os.environ.get(endpoint_env, "")
    base_url = normalize_foundry_base_url(endpoint)

    if not resolved_api_key or not base_url:
        raise ValueError(
            "Azure Foundry configuration is missing. "
            f"Set {api_key_env} and {endpoint_env}."
        )

    return OpenAI(api_key=resolved_api_key, base_url=base_url)
