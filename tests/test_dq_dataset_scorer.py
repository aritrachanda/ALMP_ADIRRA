"""Tests for core.dq_dataset_scorer — dataset roll-up (§15).

The §15.3 worked example is the headless proof: three columns (81/73/96) roll
up, plus an ``fk_only`` integrity line, to exactly **85 · Good**. Under the
consistent ROUND_HALF_UP law the FK line-item is 14.3 (the doc's 14.2 is a
recorded §15.3 erratum) — but the dataset TOTAL still re-derives to 85, so the
erratum does not cascade.
"""
from __future__ import annotations

from core.dq_config import DQScoringConfig
from core.dq_dataset_scorer import DATASET_BREAKDOWN_VERSION, score_dataset

CONFIG = DQScoringConfig.from_project()


def _component(breakdown, name):
    return next(c for c in breakdown["components"] if c["name"] == name)


# ── Worked example — dataset `exposures` → 85 · Good (§15.3) ──────────────────

def _exposures_columns():
    return [
        {"column": "counterparty_country", "state": "scored", "dq_score": 81,
         "archetype": "coded", "in_scope": True},
        {"column": "exposure_amount", "state": "scored", "dq_score": 73,
         "archetype": "numeric", "in_scope": True},
        {"column": "exposure_id", "state": "scored", "dq_score": 96,
         "archetype": "key_like", "in_scope": True},
    ]


def test_worked_example_dataset_exposures_totals_85():
    breakdown = score_dataset(
        columns=_exposures_columns(),
        table_signals={
            "row_count": 10000, "duplicate_count": 0, "orphan_fk_count": 25,
            "primary_key": ["exposure_id"], "has_fk": True,
        },
        config=CONFIG,
    )

    assert breakdown["state"] == "scored"

    rollup = _component(breakdown, "column_rollup")
    assert rollup["earned"] == 70.8          # 85 × mean(81,73,96)/100 = 85 × 0.8333

    integrity = _component(breakdown, "dataset_integrity")
    assert integrity["profile"] == "fk_only"  # single-col PK on key_like column → PK line N/A
    fk = next(li for li in integrity["line_items"] if li["label"] == "Referential integrity")
    assert fk["earned"] == 14.3               # 15 × (1 − 0.0025/0.05) = 14.25 → HALF_UP 14.3
    assert integrity["earned"] == 14.3

    # The line-item erratum (14.3 vs doc's 14.2) does NOT move the total: 85.
    assert breakdown["dq_score"] == 85
    assert breakdown["grade_label"] == "Good"


def test_contribution_breakdown_lowest_first():
    breakdown = score_dataset(
        columns=_exposures_columns(),
        table_signals={"row_count": 10000, "orphan_fk_count": 25,
                       "primary_key": ["exposure_id"], "has_fk": True},
        config=CONFIG,
    )
    rollup = _component(breakdown, "column_rollup")
    items = rollup["line_items"]
    # Sorted so the columns that dragged the roll-up down come first.
    assert [li["key"] for li in items] == ["exposure_amount", "counterparty_country", "exposure_id"]
    assert [li["contribution"] for li in items] == [24.33, 27.0, 32.0]
    assert sum(li["contribution"] for li in items) == 83.33  # == the 0–100 mean


# ── Integrity profiles ───────────────────────────────────────────────────────

def test_pk_only_profile_composite_key():
    breakdown = score_dataset(
        columns=[{"column": "a", "state": "scored", "dq_score": 90, "archetype": "text",
                  "in_scope": True}],
        table_signals={"row_count": 1000, "duplicate_count": 0,
                       "primary_key": ["a", "b"], "has_fk": False},
        config=CONFIG,
    )
    integrity = _component(breakdown, "dataset_integrity")
    assert integrity["profile"] == "pk_only"
    assert integrity["earned"] == 15.0        # no duplicate PK rows → full marks


def test_pk_and_fk_profile():
    breakdown = score_dataset(
        columns=[{"column": "a", "state": "scored", "dq_score": 80, "archetype": "text",
                  "in_scope": True}],
        table_signals={"row_count": 1000, "duplicate_count": 0, "orphan_fk_count": 0,
                       "primary_key": ["a", "b"], "has_fk": True},
        config=CONFIG,
    )
    integrity = _component(breakdown, "dataset_integrity")
    assert integrity["profile"] == "pk_and_fk"
    labels = {li["label"] for li in integrity["line_items"]}
    assert labels == {"PK uniqueness", "Referential integrity"}


def test_no_integrity_reallocates_to_column_rollup():
    """No keys to check → integrity N/A → §6 reallocation, no penalty."""
    breakdown = score_dataset(
        columns=[{"column": "a", "state": "scored", "dq_score": 80, "archetype": "text",
                  "in_scope": True}],
        table_signals={"row_count": 1000, "primary_key": [], "has_fk": False},
        config=CONFIG,
    )
    assert breakdown["applicable_components"] == ["column_rollup"]
    assert breakdown["integrity_profile"] is None
    # 85 × 80/100 = 68.0 earned, reallocated ×(100/85) → 80.
    assert _component(breakdown, "column_rollup")["earned"] == 68.0
    assert breakdown["dq_score"] == 80


def test_single_column_pk_on_keylike_column_is_na():
    """A single-column PK carried by a key_like column prices its duplicates in
    that column's Uniqueness → dataset PK line N/A (no double counting)."""
    breakdown = score_dataset(
        columns=[{"column": "id", "state": "scored", "dq_score": 95,
                  "archetype": "key_like", "in_scope": True}],
        table_signals={"row_count": 1000, "duplicate_count": 0,
                       "primary_key": ["id"], "has_fk": False},
        config=CONFIG,
    )
    assert breakdown["integrity_profile"] is None
    assert breakdown["applicable_components"] == ["column_rollup"]


# ── Scope-aware edge cases (D1 / §16.6) ──────────────────────────────────────

def test_fully_descoped_table_is_unscored():
    breakdown = score_dataset(
        columns=[
            {"column": "batch_id", "state": "unscored", "dq_score": None,
             "archetype": None, "in_scope": False},
            {"column": "load_ts", "state": "unscored", "dq_score": None,
             "archetype": None, "in_scope": False},
        ],
        table_signals={"row_count": 1000},
        config=CONFIG,
    )
    assert breakdown["state"] == "unscored"
    assert breakdown["reason"] == "fully_descoped"
    assert breakdown["breakdown_version"] == DATASET_BREAKDOWN_VERSION


def test_out_of_scope_columns_excluded_from_rollup():
    """A descoped column does not drag the dataset score."""
    breakdown = score_dataset(
        columns=[
            {"column": "good", "state": "scored", "dq_score": 90, "archetype": "text",
             "in_scope": True},
            {"column": "junk", "state": "scored", "dq_score": 10, "archetype": "text",
             "in_scope": False},
        ],
        table_signals={"row_count": 1000, "primary_key": [], "has_fk": False},
        config=CONFIG,
    )
    rollup = _component(breakdown, "column_rollup")
    assert rollup["column_count"] == 1          # only the in-scope column
    assert [li["key"] for li in rollup["line_items"]] == ["good"]


def test_in_scope_but_no_scored_columns_is_unscored():
    breakdown = score_dataset(
        columns=[{"column": "empty", "state": "unscored", "dq_score": None,
                  "archetype": None, "in_scope": True}],
        table_signals={"row_count": 0},
        config=CONFIG,
    )
    assert breakdown["state"] == "unscored"
    assert breakdown["reason"] == "no_scored_columns"


def test_grade_band_lookup_matches_score():
    """A weak dataset lands in the Weak band on the same 0–100 scale."""
    breakdown = score_dataset(
        columns=[{"column": "a", "state": "scored", "dq_score": 50, "archetype": "text",
                  "in_scope": True}],
        table_signals={"row_count": 1000, "primary_key": [], "has_fk": False},
        config=CONFIG,
    )
    assert breakdown["dq_score"] == 50
    assert breakdown["grade_label"] == "Weak"
