"""DQScoringConfig — config loader for the DQ Scoring Model.

Modelled on ``core.semantic_resolver.ResolverConfig``: a frozen dataclass
loaded once from YAML, with fail-fast load-time invariants so a malformed
config never silently produces wrong scores.

U0 scope: config loading and validation only — no scorer reads this yet
(the scorer itself lands in U2). See ``governance/dq_scoring_config.yaml``
and docs/architecture/DQ-Scoring-Model-Design-v1.md §8.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_PATH = _ROOT / "governance" / "dq_scoring_config.yaml"


class DQConfigError(ValueError):
    """Raised when the DQ scoring config fails a load-time invariant."""


@dataclass(frozen=True)
class DQScoringConfig:
    model_version: str
    component_weights: dict[str, float]
    component_applicability: dict[str, str]
    archetype_detection: dict[str, Any]
    semantic_type_archetype_map: dict[str, str]
    validator_backed_semantic_types: list[str]
    column_intent_defaults: dict[str, Any]
    profile_dimensions: dict[str, dict[str, float]]
    tolerances: dict[str, Any]
    consistency_deductions: dict[str, float]
    finding_routing: dict[str, Any]
    persistence: dict[str, Any]
    definition_scales: dict[str, Any]
    reference_data_scales: dict[str, Any]
    dataset_scoring: dict[str, Any]
    grade_bands: list[dict[str, Any]]
    semantic_line_item: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @classmethod
    def from_project(
        cls,
        project: dict[str, Any] | None = None,
        *,
        path: Path | None = None,
    ) -> "DQScoringConfig":
        """Load and validate the DQ scoring config.

        *project* is accepted (parity with ``ResolverConfig.from_project`` and
        to allow a future ``paths.dq_scoring_config`` override) but is not
        currently consulted — the config path defaults to
        ``governance/dq_scoring_config.yaml``, overridable via the
        ``AI_TIMO_DQ_SCORING_CONFIG`` environment variable or the *path* kwarg.
        """
        resolved_path = path or Path(os.getenv("AI_TIMO_DQ_SCORING_CONFIG", str(_DEFAULT_PATH)))
        if not resolved_path.exists():
            raise DQConfigError(f"DQ scoring config not found at {resolved_path}")
        with resolved_path.open(encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}

        config = cls(
            model_version=raw.get("model_version", "dq-1"),
            component_weights=raw.get("component_weights", {}) or {},
            component_applicability=raw.get("component_applicability", {}) or {},
            archetype_detection=raw.get("archetype_detection", {}) or {},
            semantic_type_archetype_map=raw.get("semantic_type_archetype_map", {}) or {},
            validator_backed_semantic_types=list(raw.get("validator_backed_semantic_types", []) or []),
            column_intent_defaults=raw.get("column_intent_defaults", {}) or {},
            profile_dimensions=raw.get("profile_dimensions", {}) or {},
            tolerances=raw.get("tolerances", {}) or {},
            consistency_deductions=raw.get("consistency_deductions", {}) or {},
            finding_routing=raw.get("finding_routing", {}) or {},
            persistence=raw.get("persistence", {}) or {},
            definition_scales=raw.get("definition_scales", {}) or {},
            reference_data_scales=raw.get("reference_data_scales", {}) or {},
            dataset_scoring=raw.get("dataset_scoring", {}) or {},
            grade_bands=raw.get("grade_bands", []) or [],
            semantic_line_item=raw.get("semantic_line_item", {}) or {},
            raw=raw,
        )
        config._validate()
        return config

    def _validate(self) -> None:
        # Invariant 1: every component weight is > 0.
        for name, weight in self.component_weights.items():
            if not (isinstance(weight, (int, float)) and weight > 0):
                raise DQConfigError(f"component_weights.{name} must be > 0, got {weight!r}")

        # Invariant 2 (SD-R3c): universal line-item↔weight closure. For EVERY component,
        # the maxima of its line-items sum exactly to its configured weight, and the
        # component weights themselves sum to 100. This generalises the old
        # profile_dimensions-only check to the whole model, so a component can never again
        # hold line-items that don't sum to its block (the exact bug the retired 4th
        # 'semantic' component re-weighting introduced — line-items at raw scale under a
        # re-weighted block). Interpretation and Reference Data derive their line-item
        # maxes from the same scale literals the scorer reads (one source of truth).
        weights_total = sum(float(v) for v in self.component_weights.values())
        if abs(weights_total - 100.0) > 1e-9:
            raise DQConfigError(
                f"component_weights sum to {weights_total}, expected 100"
            )

        # Profile is validated per-archetype: each archetype row is a full set of the
        # Profile component's line-items and must sum to the Profile weight.
        profile_max = self.component_weights.get("profile")
        for archetype, dims in self.profile_dimensions.items():
            total = sum(float(v) for v in (dims or {}).values())
            if profile_max is not None and abs(total - float(profile_max)) > 1e-9:
                raise DQConfigError(
                    f"profile_dimensions.{archetype} line-items sum to {total}, "
                    f"expected component_weights.profile={profile_max}"
                )

        for comp_name, items in (
            ("interpretation", self._interpretation_line_item_maxes()),
            ("reference_data", self._reference_data_line_item_maxes()),
        ):
            weight = self.component_weights.get(comp_name)
            if weight is None:
                continue
            total = sum(float(v) for v in items.values())
            if abs(total - float(weight)) > 1e-9:
                raise DQConfigError(
                    f"{comp_name} line-items {items} sum to {total}, "
                    f"expected component_weights.{comp_name}={weight}"
                )

        # Invariant 3: grade bands cover 0-100 descending, without gap or overlap.
        if not self.grade_bands:
            raise DQConfigError("grade_bands must not be empty")
        mins = [band["min"] for band in self.grade_bands]
        sorted_desc = sorted(mins, reverse=True)
        if mins != sorted_desc:
            raise DQConfigError("grade_bands must be declared in descending 'min' order")
        if len(set(mins)) != len(mins):
            raise DQConfigError("grade_bands must have distinct 'min' thresholds (overlap detected)")
        if sorted_desc[-1] != 0:
            raise DQConfigError("grade_bands must cover down to 0 (gap at the bottom)")
        if sorted_desc[0] > 100:
            raise DQConfigError("grade_bands top band must start at or below 100")

    # ── SD-R3c: Interpretation line-item accessors ────────────────────────────
    # Semantic Type is now a line-item inside Interpretation (the retired 4th
    # 'semantic' component). These derive the same line-item maxima the scorer
    # uses, and back the universal Invariant 2 closure check above.

    def _interpretation_line_item_maxes(self) -> dict[str, float]:
        """Best-case (max) points for each Interpretation line-item.

        Derived from the same ``definition_scales`` + ``semantic_line_item``
        literals the scorer reads, so config validation and scoring share one
        source of truth. Definition = present + best authorship + best
        lifecycle; Business Name / Glossary = best step; Semantic Type = its max.
        """
        scales = self.definition_scales or {}
        desc = scales.get("description", {}) or {}
        lifecycle = desc.get("lifecycle", {}) or {}
        definition_max = (
            float(desc.get("present", 0))
            + max(float(desc.get("authorship_human", 0)), float(desc.get("authorship_ai", 0)))
            + (max(float(v) for v in lifecycle.values()) if lifecycle else 0.0)
        )
        bn = scales.get("business_name", {}) or {}
        business_name_max = max((float(v) for v in bn.values()), default=0.0)
        gl = scales.get("glossary", {}) or {}
        term_status = gl.get("term_status", {}) or {}
        glossary_max = float(gl.get("linked", 0)) + (
            max(float(v) for v in term_status.values()) if term_status else 0.0
        )
        return {
            "Definition": definition_max,
            "Business Name": business_name_max,
            "Glossary Linkage": glossary_max,
            "Semantic Type": self.semantic_line_item_max,
        }

    def _reference_data_line_item_maxes(self) -> dict[str, float]:
        """Best-case (max) points for each Reference Data line-item."""
        scales = self.reference_data_scales or {}
        status = scales.get("status", {}) or {}
        return {
            "Codes documented": float(scales.get("codes_documented_max", 0)),
            "Code set approved": max((float(v) for v in status.values()), default=0.0),
        }

    @property
    def semantic_line_item_max(self) -> float:
        """Max points for the Semantic Type line-item inside Interpretation."""
        return float((self.semantic_line_item or {}).get("max", 0.0) or 0.0)

    @property
    def semantic_line_item_scale(self) -> dict[str, Any]:
        """Stepped earned-fraction-of-max scale, keyed by semantic state."""
        return (self.semantic_line_item or {}).get("scale", {}) or {}

    @property
    def semantic_type_conflict_deduction(self) -> float:
        """Fraction of the Semantic Type max deducted on a type/value conflict."""
        return float((self.semantic_line_item or {}).get("type_value_conflict_deduction", 0.0) or 0.0)
