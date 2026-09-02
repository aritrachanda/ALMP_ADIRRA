"""Glossary lookup caching in api.routes.element.

Scoring a whole source used to re-open and re-parse glossary.yaml once per
column. The lookup now uses an mtime-cached index; these tests pin that the
index is parsed once (identity-stable) and refreshes when the file changes.
"""
from __future__ import annotations

from api.routes import element


def _write_glossary(path, related):
    path.write_text(
        "terms:\n"
        "  - name: Country Code\n"
        f"    related_objects: ['{related}']\n"
        "    status: approved\n",
        encoding="utf-8",
    )


def test_glossary_index_is_parsed_once_and_reused(tmp_path, monkeypatch):
    monkeypatch.setenv("ADIRRA_GLOSSARY_BACKEND", "yaml")  # pin: this test is yaml-cache-specific
    gpath = tmp_path / "glossary.yaml"
    _write_glossary(gpath, "source|banking|src.accounts.country")
    monkeypatch.setattr(element, "_GLOSSARY_PATH", gpath)
    monkeypatch.setattr(element, "_GLOSSARY_INDEX_CACHE", None)
    monkeypatch.setattr(element, "_GLOSSARY_CACHE_MTIME", None)

    first = element._glossary_related_index()
    second = element._glossary_related_index()

    assert first is second  # same cached object — not re-parsed per call
    term = element._find_glossary_term("banking", "src", "accounts", "country")
    assert term is not None and term["name"] == "Country Code"


def test_glossary_cache_refreshes_when_file_changes(tmp_path, monkeypatch):
    import os

    monkeypatch.setenv("ADIRRA_GLOSSARY_BACKEND", "yaml")  # pin: this test is yaml-cache-specific
    gpath = tmp_path / "glossary.yaml"
    _write_glossary(gpath, "source|banking|src.accounts.country")
    monkeypatch.setattr(element, "_GLOSSARY_PATH", gpath)
    monkeypatch.setattr(element, "_GLOSSARY_INDEX_CACHE", None)
    monkeypatch.setattr(element, "_GLOSSARY_CACHE_MTIME", None)

    assert element._find_glossary_term("banking", "src", "accounts", "country") is not None

    # Rewrite pointing at a different column, with a newer mtime.
    _write_glossary(gpath, "source|banking|src.accounts.currency")
    os.utime(gpath, (gpath.stat().st_atime, gpath.stat().st_mtime + 5))

    assert element._find_glossary_term("banking", "src", "accounts", "country") is None
    assert element._find_glossary_term("banking", "src", "accounts", "currency") is not None
