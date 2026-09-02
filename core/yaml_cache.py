"""
yaml_cache.py  –  Mtime-based cached YAML loading.

Wraps yaml.safe_load with an lru_cache keyed on file path + modification time.
Files are only re-parsed when they change on disk.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml


@lru_cache(maxsize=64)
def _load_yaml_cached(path: str, _mtime: float) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_yaml_cached(path: str | Path) -> dict:
    """Load a YAML file with mtime-based caching.

    Returns cached result if the file has not been modified since last parse.
    """
    p = str(path)
    return _load_yaml_cached(p, os.path.getmtime(p))
