"""Base declarative class shared by every feature's ORM models (S0 models split).

All feature model modules (glossary, governance, audit, catalog) import this single ``Base``
so every table lands on one shared metadata object — required for Alembic's ``target_metadata``
autogenerate support to see every table via one import (see db/migrations/env.py).
"""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
