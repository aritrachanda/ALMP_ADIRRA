"""Lifecycle state store for data elements (source columns).

States: draft → defined → approved
Persisted as a YAML file at <repo_root>/element_states.yaml.
Thread-safe writes; the file is small (one entry per governed column).

Schema:
  descriptions:
    source|schema|table|column: "Description text..."
  business_names:
    source|schema|table|column: "Business Name"
  states:
    source|schema|table|column: draft/defined/approved
  metadata:
    source|schema|table|column:
      created_by: null or "AI"
      created_at: ISO timestamp
      updated_at: ISO timestamp
      updated_by: null (for future use)
      is_ai_generated: boolean
      business_name_is_ai: boolean
      mapping_instructions: null (placeholder for BIRD)
  submission_overlay:
    source|schema|table|column:
      submitted_at: ISO timestamp or null
      submitted_by: actor name or null
      decided_at: ISO timestamp or null
      decided_by: actor name or null
      decision: "approved" | "rejected" | null
      reject_reason: advisory text or null
"""
from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml

STATE_VALUES = ("draft", "defined", "approved")
LifecycleState = Literal["draft", "defined", "approved"]
_DEFAULT_STATE: LifecycleState = "draft"

_STATES_KEY = "states"
_DESCRIPTIONS_KEY = "descriptions"
_BUSINESS_NAMES_KEY = "business_names"
_METADATA_KEY = "metadata"
_DATA_STORIES_KEY = "data_stories"
_SUBMISSION_OVERLAY_KEY = "submission_overlay"
_ASSESSMENT_SCOPE_KEY = "assessment_scope"

ASSESSMENT_SCOPE_VALUES = ("in_scope", "out_of_scope")
_DEFAULT_ASSESSMENT_SCOPE = "in_scope"


class ElementStateStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._data: dict = self._load()
        self._lifecycle_repo = None  # lazily built when element_backend() == 'postgres'
        self._content_repo = None
        self._refset_repo_instance = None

    # ── backend switch — LIFECYCLE only (Phase 5a: status + submission overlay) ──
    # CONTENT (definitions, business names, data stories, assessment scope, metadata) and
    # REFSET (which shared reference set a column is bound to) are Postgres-only since Slice F;
    # only the lifecycle half still flips independently, hence it keeps its own flag/branch.
    def _use_pg(self) -> bool:
        from core.element_lifecycle_repo import element_backend
        return element_backend() == "postgres"

    def _repo(self):
        if self._lifecycle_repo is None:
            from core.element_lifecycle_repo import ElementLifecycleRepo
            self._lifecycle_repo = ElementLifecycleRepo()
        return self._lifecycle_repo

    def _content(self):
        if self._content_repo is None:
            from core.element_content_repo import ElementContentRepo
            self._content_repo = ElementContentRepo()
        return self._content_repo

    def _refset_repo(self):
        if self._refset_repo_instance is None:
            from core.reference_set_repo import ReferenceSetRepo
            self._refset_repo_instance = ReferenceSetRepo()
        return self._refset_repo_instance

    def _pg_content_map(self) -> dict[str, dict]:
        """Every element's content record from Postgres (bulk, cached). Collection-query
        methods (``find_in_source``/``get_pending_review``/``search_multi_filter``/etc.) use
        this instead of reading ``self._data`` directly.
        """
        return self._content().all_definitions()

    def _content_row(self, k: str, defs: dict[str, dict]) -> tuple[str | None, dict]:
        """(description, metadata) for one key from the bulk Postgres map. Shares the exact
        metadata shape used by ``ElementContentRepo.get_metadata``.
        """
        record = defs.get(k)
        if record is None:
            return None, {}
        from core.element_content_repo import ElementContentRepo
        return record["definition"], ElementContentRepo._record_to_metadata(record)

    def _load(self) -> dict:
        if self._path.exists():
            with self._path.open(encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}
            # Migrate flat format (old: {key: state}) to nested format
            if raw and not isinstance(next(iter(raw.values()), dict) if raw else None, dict) and \
               _STATES_KEY not in raw and _DESCRIPTIONS_KEY not in raw:
                return {_STATES_KEY: raw, _DESCRIPTIONS_KEY: {}, _METADATA_KEY: {}}
            if _STATES_KEY not in raw:
                raw[_STATES_KEY] = {}
            if _DESCRIPTIONS_KEY not in raw:
                raw[_DESCRIPTIONS_KEY] = {}
            if _BUSINESS_NAMES_KEY not in raw:
                raw[_BUSINESS_NAMES_KEY] = {}
            if _METADATA_KEY not in raw:
                raw[_METADATA_KEY] = {}
            if _DATA_STORIES_KEY not in raw:
                raw[_DATA_STORIES_KEY] = {}
            if _SUBMISSION_OVERLAY_KEY not in raw:
                raw[_SUBMISSION_OVERLAY_KEY] = {}
            if _ASSESSMENT_SCOPE_KEY not in raw:
                raw[_ASSESSMENT_SCOPE_KEY] = {}
            return raw
        return {_STATES_KEY: {}, _DESCRIPTIONS_KEY: {}, _BUSINESS_NAMES_KEY: {}, _METADATA_KEY: {}, _DATA_STORIES_KEY: {}, _SUBMISSION_OVERLAY_KEY: {}, _ASSESSMENT_SCOPE_KEY: {}}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as fh:
            yaml.dump(self._data, fh, default_flow_style=False, sort_keys=True, allow_unicode=True)

    @staticmethod
    def key(source: str, schema: str | None, table: str, column: str) -> str:
        return f"{source}|{schema or ''}|{table}|{column}"

    def get(self, source: str, schema: str | None, table: str, column: str) -> LifecycleState:
        if self._use_pg():
            return self._repo().get_status(self.key(source, schema, table, column))  # type: ignore[return-value]
        k = self.key(source, schema, table, column)
        return self._data[_STATES_KEY].get(k, _DEFAULT_STATE)  # type: ignore[return-value]

    def set(self, source: str, schema: str | None, table: str, column: str, state: LifecycleState) -> None:
        if self._use_pg():
            # In postgres mode the status vocabulary is the canonical Phase-5 set
            # (core.lifecycle); the repo validates it is a resting status.
            self._repo().set_status(self.key(source, schema, table, column), state)
            return
        if state not in STATE_VALUES:
            raise ValueError(f"Invalid lifecycle state: {state!r}")
        k = self.key(source, schema, table, column)
        with self._lock:
            self._data[_STATES_KEY][k] = state
            # Update metadata timestamp
            if k not in self._data[_METADATA_KEY]:
                self._data[_METADATA_KEY][k] = {}
            self._data[_METADATA_KEY][k]['updated_at'] = datetime.now().isoformat()
            self._save()

    def get_description(self, source: str, schema: str | None, table: str, column: str) -> str | None:
        return self._content().get_description(source, schema, table, column)

    def set_description(self, source: str, schema: str | None, table: str, column: str,
                       description: str, is_ai_generated: bool = False) -> None:
        self._content().set_description(source, schema, table, column, description,
                                        is_ai_generated=is_ai_generated)

    def get_business_name(self, source: str, schema: str | None, table: str, column: str) -> str | None:
        return self._content().get_business_name(source, schema, table, column)

    def set_business_name(self, source: str, schema: str | None, table: str, column: str,
                          name: str, is_ai_generated: bool = False) -> None:
        self._content().set_business_name(source, schema, table, column, name,
                                          is_ai_generated=is_ai_generated)

    def get_metadata(self, source: str, schema: str | None, table: str, column: str) -> dict:
        return self._content().get_metadata(source, schema, table, column)

    def set_metadata(self, source: str, schema: str | None, table: str, column: str,
                    metadata: dict) -> None:
        self._content().set_metadata(source, schema, table, column, metadata)

    def get_reference_binding(self, source: str, schema: str | None, table: str, column: str) -> str | None:
        """Return the reference-set id a field is bound to, or ``None``."""
        return self._refset_repo().get_binding(self.key(source, schema, table, column))

    def set_reference_binding(self, source: str, schema: str | None, table: str, column: str,
                              set_id: str) -> None:
        """Bind a field to a reference set."""
        self._refset_repo().set_binding(self.key(source, schema, table, column), set_id)

    def clear_reference_binding(self, source: str, schema: str | None, table: str, column: str) -> None:
        """Remove a field's reference-set binding, restoring its own inline meanings."""
        self._refset_repo().clear_binding(self.key(source, schema, table, column))

    @staticmethod
    def dataset_key(source: str, schema: str | None, table: str) -> str:
        return f"{source}|{schema or ''}|{table}"

    def get_assessment_scope(self, source: str, schema: str | None, table: str, column: str) -> str:
        """Return 'in_scope' | 'out_of_scope' (default 'in_scope') for a column (D1)."""
        return self._content().get_assessment_scope(source, schema, table, column)

    def get_assessment_scope_record(self, source: str, schema: str | None, table: str, column: str) -> dict:
        return self._content().get_assessment_scope_record(source, schema, table, column)

    def set_assessment_scope(
        self,
        source: str,
        schema: str | None,
        table: str,
        column: str,
        scope: str,
        *,
        scope_reason: str | None = None,
        scoped_by: str | None = None,
    ) -> dict:
        """Set the assessment scope for a column (D1). Audited by the caller."""
        if scope not in ASSESSMENT_SCOPE_VALUES:
            raise ValueError(f"Invalid assessment scope: {scope!r}")
        return self._content().set_assessment_scope(
            source, schema, table, column, scope,
            scope_reason=scope_reason, scoped_by=scoped_by,
        )

    def record_content_submission(self, source: str, schema: str | None, table: str, column: str,
                                  *, submitted_by: str | None = None) -> dict | None:
        """Open a history window for this column's definition/business name at submission time.

        Mirrors ``SemanticTypeStore.record_submission()`` so both halves of one Interpretation
        Set are versioned by the same action.
        """
        return self._content().record_submission(source, schema, table, column,
                                                 submitted_by=submitted_by)

    def content_history(self, source: str, schema: str | None, table: str,
                        column: str) -> list[dict]:
        """Every recorded wording for this column, oldest first."""
        return self._content().history(source, schema, table, column)

    def get_data_story(self, source: str, schema: str | None, table: str) -> dict | None:
        return self._content().get_data_story(source, schema, table)

    def set_data_story(
        self,
        source: str,
        schema: str | None,
        table: str,
        tagline: str,
        narrative: str,
        is_ai_generated: bool = False,
    ) -> None:
        self._content().set_data_story(source, schema, table, tagline, narrative,
                                       is_ai_generated=is_ai_generated)

    def get_all(self) -> dict[str, str]:
        if self._use_pg():
            return self._repo().all_states()
        return dict(self._data[_STATES_KEY])

    def submit_for_review(self, source: str, schema: str | None, table: str, column: str,
                         submitted_by: str | None = None, submitted_by_role: str | None = None) -> None:
        """Mark an aspect as submitted for steward review.
        
        Sets submitted_at and submitted_by in the overlay. The aspect state
        should already be 'defined' before calling this.
        """
        if self._use_pg():
            self._repo().submit(self.key(source, schema, table, column),
                                actor=submitted_by, actor_role=submitted_by_role)
            return
        k = self.key(source, schema, table, column)
        with self._lock:
            if k not in self._data[_SUBMISSION_OVERLAY_KEY]:
                self._data[_SUBMISSION_OVERLAY_KEY][k] = {}
            self._data[_SUBMISSION_OVERLAY_KEY][k]["submitted_at"] = datetime.now().isoformat()
            self._data[_SUBMISSION_OVERLAY_KEY][k]["submitted_by"] = submitted_by
            self._data[_SUBMISSION_OVERLAY_KEY][k]["submitted_by_role"] = submitted_by_role
            # Update metadata timestamp
            if k not in self._data[_METADATA_KEY]:
                self._data[_METADATA_KEY][k] = {}
            self._data[_METADATA_KEY][k]["updated_at"] = datetime.now().isoformat()
            self._save()

    def approve(self, source: str, schema: str | None, table: str, column: str,
               decided_by: str | None = None, decided_by_role: str | None = None) -> None:
        """Approve a submitted aspect.
        
        Sets decided_at, decided_by, and decision='approved' in the overlay.
        Also sets the state to 'approved'.
        """
        if self._use_pg():
            self._repo().approve(self.key(source, schema, table, column),
                                 decided_by=decided_by, decided_by_role=decided_by_role)
            return
        k = self.key(source, schema, table, column)
        with self._lock:
            # Set state to approved
            self._data[_STATES_KEY][k] = "approved"
            # Set decision overlay
            if k not in self._data[_SUBMISSION_OVERLAY_KEY]:
                self._data[_SUBMISSION_OVERLAY_KEY][k] = {}
            now = datetime.now().isoformat()
            self._data[_SUBMISSION_OVERLAY_KEY][k]["decided_at"] = now
            self._data[_SUBMISSION_OVERLAY_KEY][k]["decided_by"] = decided_by
            self._data[_SUBMISSION_OVERLAY_KEY][k]["decided_by_role"] = decided_by_role
            self._data[_SUBMISSION_OVERLAY_KEY][k]["decision"] = "approved"
            # Clear reject reason on approval
            self._data[_SUBMISSION_OVERLAY_KEY][k]["reject_reason"] = None
            # Update metadata
            if k not in self._data[_METADATA_KEY]:
                self._data[_METADATA_KEY][k] = {}
            self._data[_METADATA_KEY][k]["updated_at"] = now
            self._save()

    def reject(self, source: str, schema: str | None, table: str, column: str,
              decided_by: str | None = None, reason: str | None = None,
              decided_by_role: str | None = None) -> None:
        """Reject a submitted aspect.
        
        Sets decided_at, decided_by, and decision='rejected' in the overlay.
        Reverts the state back to 'defined' so the author can re-edit.
        """
        if self._use_pg():
            # Phase-5 mapping (locked): the legacy 'reject' (bounce back to editable)
            # maps to the new 'Returned' status, NOT the new outright 'Rejected'.
            self._repo().send_back(self.key(source, schema, table, column),
                                   decided_by=decided_by, decided_by_role=decided_by_role,
                                   reason=reason)
            return
        k = self.key(source, schema, table, column)
        with self._lock:
            # Revert state to defined (author can edit again)
            self._data[_STATES_KEY][k] = "defined"
            # Set decision overlay
            if k not in self._data[_SUBMISSION_OVERLAY_KEY]:
                self._data[_SUBMISSION_OVERLAY_KEY][k] = {}
            now = datetime.now().isoformat()
            self._data[_SUBMISSION_OVERLAY_KEY][k]["decided_at"] = now
            self._data[_SUBMISSION_OVERLAY_KEY][k]["decided_by"] = decided_by
            self._data[_SUBMISSION_OVERLAY_KEY][k]["decided_by_role"] = decided_by_role
            self._data[_SUBMISSION_OVERLAY_KEY][k]["decision"] = "rejected"
            self._data[_SUBMISSION_OVERLAY_KEY][k]["reject_reason"] = reason
            # Update metadata
            if k not in self._data[_METADATA_KEY]:
                self._data[_METADATA_KEY][k] = {}
            self._data[_METADATA_KEY][k]["updated_at"] = now
            self._save()

    # ── Phase 5b.1 canonical set-level actions ──────────────────────────────
    # These branch to the canonical Postgres lifecycle (core.lifecycle vocabulary)
    # when element_backend() == 'postgres'; the YAML branch maps onto the legacy
    # draft/defined/approved model so the pre-flip app keeps working.

    def save(self, source: str, schema: str | None, table: str, column: str,
             actor: str | None = None, actor_role: str | None = None) -> None:
        """Holistic Save of the interpretation set: advance to Draft — or Empty when the
        set is still title-only (no definition and no business name yet, D4).

        Content (definition, business name) is persisted via the dedicated setters before
        this is called; this only moves the set lifecycle. When Draft is reached via a prior
        withdraw/revoke the copy simply becomes editable again — nothing is rewritten.
        """
        has_content = bool(
            (self.get_description(source, schema, table, column) or "").strip()
            or (self.get_business_name(source, schema, table, column) or "").strip()
        )
        if self._use_pg():
            self._repo().save(self.key(source, schema, table, column),
                              has_content=has_content, actor=actor, actor_role=actor_role)
            return
        k = self.key(source, schema, table, column)
        with self._lock:
            # 'defined' is the legacy equivalent of canonical 'draft' (content present); a
            # title-only set stays at 'draft' (the legacy empty-equivalent shell). Never
            # downgrade an approved item (Save is not offered on frozen items).
            if self._data[_STATES_KEY].get(k) != "approved":
                self._data[_STATES_KEY][k] = "defined" if has_content else "draft"
            meta = self._data[_METADATA_KEY].setdefault(k, {})
            meta["updated_at"] = datetime.now().isoformat()
            self._save()

    def withdraw(self, source: str, schema: str | None, table: str, column: str,
                 actor: str | None = None, actor_role: str | None = None) -> None:
        """Analyst pulls an In-Review submission back → rests in Draft (spontaneous)."""
        if self._use_pg():
            self._repo().withdraw(self.key(source, schema, table, column),
                                  actor=actor, actor_role=actor_role)
            return
        k = self.key(source, schema, table, column)
        with self._lock:
            # Clear the submission overlay so it is no longer pending; stay 'defined'.
            overlay = self._data[_SUBMISSION_OVERLAY_KEY].setdefault(k, {})
            overlay["submitted_at"] = None
            overlay["submitted_by"] = None
            overlay["decided_at"] = None
            overlay["decided_by"] = None
            overlay["decision"] = None
            if self._data[_STATES_KEY].get(k) == "approved":
                self._data[_STATES_KEY][k] = "defined"
            meta = self._data[_METADATA_KEY].setdefault(k, {})
            meta["updated_at"] = datetime.now().isoformat()
            self._save()

    def revoke(self, source: str, schema: str | None, table: str, column: str,
               actor: str | None = None, actor_role: str | None = None) -> None:
        """Analyst pulls a prior approval back → rests in Draft (editable again)."""
        if self._use_pg():
            self._repo().revoke(self.key(source, schema, table, column),
                                actor=actor, actor_role=actor_role)
            return
        k = self.key(source, schema, table, column)
        with self._lock:
            # Re-open an approved set for editing; clear the decision overlay.
            self._data[_STATES_KEY][k] = "defined"
            overlay = self._data[_SUBMISSION_OVERLAY_KEY].setdefault(k, {})
            overlay["submitted_at"] = None
            overlay["submitted_by"] = None
            overlay["decided_at"] = None
            overlay["decided_by"] = None
            overlay["decision"] = None
            meta = self._data[_METADATA_KEY].setdefault(k, {})
            meta["updated_at"] = datetime.now().isoformat()
            self._save()

    def decline(self, source: str, schema: str | None, table: str, column: str,
                decided_by: str | None = None, decided_by_role: str | None = None,
                reason: str | None = None) -> None:
        """Steward outright-rejects a submission → canonical 'rejected'.

        Distinct from ``reject`` (which is the fix-and-resubmit 'Return' / 'returned').
        In YAML mode both bounce the item back to an editable 'defined'.
        """
        if self._use_pg():
            self._repo().reject(self.key(source, schema, table, column),
                                decided_by=decided_by, decided_by_role=decided_by_role,
                                reason=reason)
            return
        k = self.key(source, schema, table, column)
        with self._lock:
            self._data[_STATES_KEY][k] = "defined"
            overlay = self._data[_SUBMISSION_OVERLAY_KEY].setdefault(k, {})
            now = datetime.now().isoformat()
            overlay["decided_at"] = now
            overlay["decided_by"] = decided_by
            overlay["decided_by_role"] = decided_by_role
            overlay["decision"] = "rejected"
            overlay["reject_reason"] = reason
            meta = self._data[_METADATA_KEY].setdefault(k, {})
            meta["updated_at"] = now
            self._save()

    def get_submission_status(self, source: str, schema: str | None, table: str, column: str) -> dict:
        """Get the submission overlay for an aspect.
        
        Returns dict with keys: submitted_at, submitted_by, decided_at, decided_by,
        decision, reject_reason. Values are None if not set.
        """
        if self._use_pg():
            return self._repo().get_review(self.key(source, schema, table, column))
        k = self.key(source, schema, table, column)
        overlay = self._data[_SUBMISSION_OVERLAY_KEY].get(k, {})
        return {
            "submitted_at": overlay.get("submitted_at"),
            "submitted_by": overlay.get("submitted_by"),
            "decided_at": overlay.get("decided_at"),
            "decided_by": overlay.get("decided_by"),
            "decision": overlay.get("decision"),
            "reject_reason": overlay.get("reject_reason"),
        }

    def get_last_status(self, source: str, schema: str | None, table: str, column: str) -> dict:
        """Latest lifecycle status update for the interpretation: {action, at}.

        Postgres backend reads the newest lifecycle_transition; the YAML fallback derives it
        from the stored state + updated_at. Returns ``{action: None, at: None}`` when unknown.
        """
        k = self.key(source, schema, table, column)
        if self._use_pg():
            tr = self._repo().last_transition(k)
            return tr or {"action": None, "at": None}
        meta = self._data[_METADATA_KEY].get(k, {})
        return {"action": self.get(source, schema, table, column), "at": meta.get("updated_at")}

    # ── Indexing for fast queries ──────────────────────────────────────────

    def find_all_in_state(self, state: str) -> list[dict]:
        """Find all elements in a given lifecycle state"""
        defs = self._pg_content_map()
        if self._use_pg():
            states = self._repo().all_states()
            results = []
            for k, s in states.items():
                if s != state:
                    continue
                desc, meta = self._content_row(k, defs)
                results.append({"key": k, "state": s, "description": desc, "metadata": meta})
            return results
        keys = [k for k, s in self._data[_STATES_KEY].items() if s == state]
        results = []
        for k in keys:
            desc, meta = self._content_row(k, defs)
            results.append({'key': k, 'state': self._data[_STATES_KEY][k],
                            'description': desc, 'metadata': meta})
        return results

    def all_states(self, source: str) -> dict[str, str]:
        """Bulk ``{key: state}`` map for a source (sparse — only columns with an explicit
        saved state record appear; a column never touched by any governance action has no
        entry here and should be treated as its true default, 'empty', by the caller).
        """
        if self._use_pg():
            return self._repo().all_states(source)
        return {k: v for k, v in self._data[_STATES_KEY].items() if k.startswith(f"{source}|")}

    def find_in_source(self, source: str) -> list[dict]:
        """Find all elements in a given source"""
        defs = self._pg_content_map()
        if self._use_pg():
            states = self._repo().all_states(source)
            results = []
            for k, s in states.items():
                desc, meta = self._content_row(k, defs)
                results.append({'key': k, 'state': s, 'description': desc, 'metadata': meta})
            return results
        keys = [k for k in self._data[_STATES_KEY].keys() if k.startswith(f"{source}|")]
        results = []
        for k in keys:
            desc, meta = self._content_row(k, defs)
            results.append({'key': k, 'state': self._data[_STATES_KEY][k],
                            'description': desc, 'metadata': meta})
        return results

    def search_description(self, text: str) -> list[dict]:
        """Full-text search in descriptions"""
        query = text.lower()
        defs = self._pg_content_map()
        results = []
        if defs is not None:
            for k, record in defs.items():
                desc = record["definition"] or ""
                if query in desc.lower():
                    state = self._repo().get_status(k) if self._use_pg() else self._data[_STATES_KEY].get(k)
                    _, meta = self._content_row(k, defs)
                    results.append({'key': k, 'state': state, 'description': desc, 'metadata': meta})
            return results
        for k, desc in self._data[_DESCRIPTIONS_KEY].items():
            if query in desc.lower():
                results.append({
                    'key': k,
                    'state': self._data[_STATES_KEY].get(k),
                    'description': desc,
                    'metadata': self._data[_METADATA_KEY].get(k, {})
                })
        return results

    def get_pending_review(self, source: str | None = None) -> list[dict]:
        """Return all elements submitted for review that have not yet received a decision.

        An item is pending when its submission_overlay has ``submitted_at`` set
        and ``decision`` is null.  Optionally filter to a single source.
        """
        defs = self._pg_content_map()
        if self._use_pg():
            out: list[dict] = []
            for it in self._repo().pending_review(source):
                k = it["key"]
                review = self._repo().get_review(k)
                desc, meta = self._content_row(k, defs)
                out.append({
                    "key": k, "source": it["source"], "schema": it["schema"],
                    "table": it["table"], "column": it["column"],
                    "aspect_type": "definition", "state": it["state"],
                    "description": desc,
                    "submitted_at": review.get("submitted_at"),
                    "submitted_by": review.get("submitted_by"),
                    "provenance": "ai_detected" if meta.get("is_ai_generated") else "human_authored",
                })
            return out
        results = []
        overlay_data = self._data[_SUBMISSION_OVERLAY_KEY]
        for k, ov in overlay_data.items():
            if not ov.get("submitted_at"):
                continue
            if ov.get("decision") is not None:
                continue
            if source and not k.startswith(f"{source}|"):
                continue
            parts = k.split("|", 3)
            desc, meta = self._content_row(k, defs)
            results.append({
                "key": k,
                "source": parts[0] if len(parts) > 0 else "",
                "schema": parts[1] if len(parts) > 1 else "",
                "table": parts[2] if len(parts) > 2 else "",
                "column": parts[3] if len(parts) > 3 else "",
                "aspect_type": "definition",
                "state": self._data[_STATES_KEY].get(k, _DEFAULT_STATE),
                "description": desc,
                "submitted_at": ov.get("submitted_at"),
                "submitted_by": ov.get("submitted_by"),
                "provenance": "ai_detected" if meta.get("is_ai_generated") else "human_authored",
            })
        return results

    def search_multi_filter(self, source: str | None = None, state: str | None = None,
                           description_text: str | None = None) -> list[dict]:
        """Combined multi-filter queries.

        Reads live state from Postgres when ``element_backend`` is postgres, and live
        description/metadata from Postgres when ``element_content_backend`` is postgres —
        each flag checked independently, since they flip on their own schedule.
        """
        defs = self._pg_content_map()
        if self._use_pg():
            states = dict(self._repo().all_states(source))
        else:
            states = {k: s for k, s in self._data[_STATES_KEY].items()
                     if not source or k.startswith(f"{source}|")}

        candidates = set(states.keys())

        # Filter by state
        if state:
            candidates = {k for k in candidates if states.get(k) == state}

        # Filter by description text
        if description_text:
            query = description_text.lower()
            candidates = {
                k for k in candidates
                if query in (self._content_row(k, defs)[0] or '').lower()
            }

        # Build results
        results = []
        for k in sorted(candidates):
            desc, meta = self._content_row(k, defs)
            results.append({'key': k, 'state': states[k], 'description': desc, 'metadata': meta})
        return results

