from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Folders that are not source code for this repo's runtime logic.
SKIP_PARTS = {".venv", "node_modules", ".git", "dist", "build", "__pycache__", "tests"}


def _iter_python_files():
    for path in ROOT.rglob("*.py"):
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        yield path


def test_no_legacy_azure_openai_client_usage():
    offenders: list[str] = []
    for path in _iter_python_files():
        text = path.read_text(encoding="utf-8")
        if "AzureOpenAI" in text:
            offenders.append(str(path.relative_to(ROOT)))

    assert not offenders, (
        "Legacy AzureOpenAI usage found. Use foundry_client.create_foundry_client instead:\n"
        + "\n".join(offenders)
    )


def test_no_hardcoded_api_version_in_openai_calls():
    offenders: list[str] = []
    for path in _iter_python_files():
        text = path.read_text(encoding="utf-8")
        if "api_version=" in text:
            offenders.append(str(path.relative_to(ROOT)))

    assert not offenders, (
        "Hardcoded api_version detected. Use foundry_client.create_foundry_client instead:\n"
        + "\n".join(offenders)
    )
