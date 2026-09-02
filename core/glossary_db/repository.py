"""Repository for the Business Glossary v2 Postgres store.

All glossary SQL lives here. The public methods speak the **flat v1 dict shape**
(``GlossaryTerm.to_dict()``) so ``GlossaryAgent`` can delegate without changing its
interface, and no ORM object escapes to the routes. The flat term is assembled from
``term`` + its current ``term_version`` + ``linkage`` rows (catalog refs) + ``term_relation``
rows (free-text concepts); writes decompose it back.

Phase-2 semantics notes (interface preserved, mechanism narrowed):
  * term identity is the v1 slug string (``id``); the BIGINT PK is internal.
  * an upsert updates the single current version IN PLACE (v1 "edits are immediate");
    the versioning machinery exists but the old interface never creates a 2nd version.
  * ``related_objects`` round-trips exactly via ``linkage.raw_ref`` / ``term_relation.to_label``
    (ordering may change; contents are preserved).
  * search replicates v1 ``GlossaryTerm.matches`` in Python for exact parity; the FTS/trigram
    indexes back the v2 faceted UI (Phase 4), not this legacy path.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import and_, delete, func, select, text
from sqlalchemy.orm import Session

from core.shared.models import (
    Glossary, LifecycleTransition, Linkage, ReviewSubject, Term, TermRelation, TermVersion,
)
from core.lifecycle_vocab import derive_saved_state

_ATTR_CRR = "crr3_context"
_ATTR_DPM = "dpm2_context"


# ── ref parsing (mirrors agents.glossary_agent._parse_related_object) ─────────

def _parse_ref(ref: str) -> tuple[str, str, list[str]] | None:
    parts = [p.strip() for p in ref.split("|", 2)]
    if len(parts) != 3:
        return None
    kind, dataset, path = parts
    segs = [s.strip() for s in path.split(".") if s.strip()]
    if not segs:
        return None
    return kind, dataset, segs


def _granularity(segs: list[str]) -> str:
    n = len(segs)
    return "column" if n >= 3 else ("table" if n == 2 else "dataset")


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── v1 search parity (mirrors GlossaryTerm.matches) ───────────────────────────

def _matches(d: dict, query: str) -> bool:
    q = (query or "").strip().lower()
    if not q:
        return True
    haystack = " ".join([
        d.get("title", ""),
        d.get("business_description", ""),
        d.get("detailed_description", ""),
        " ".join(d.get("synonyms") or []),
        " ".join(d.get("tags") or []),
        d.get("domain", ""),
        d.get("category", ""),
    ]).lower()
    return all(tok in haystack for tok in q.split())


class GlossaryRepository:
    """Session-scoped repository. One instance per unit of work."""

    def __init__(self, session: Session):
        self.s = session

    # ── glossary container ────────────────────────────────────────────────────
    def _glossary_id(self) -> int:
        # Concurrency-safe get-or-create: two simultaneous first-writers must not collide
        # on glossary.key. ON CONFLICT DO NOTHING makes the insert idempotent under races.
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        self.s.execute(
            pg_insert(Glossary)
            .values(key="business", name="Business Glossary")
            .on_conflict_do_nothing(index_elements=["key"])
        )
        self.s.flush()
        return self.s.execute(select(Glossary.id).where(Glossary.key == "business")).scalar_one()

    # ── assembly (relational → flat dict) ─────────────────────────────────────
    @staticmethod
    def _pick_current(versions: list[TermVersion]) -> TermVersion | None:
        cur = None
        for v in versions:
            if cur is None:
                cur = v
            elif (v.is_current_approved and not cur.is_current_approved) or (
                v.is_current_approved == cur.is_current_approved and v.version_no > cur.version_no
            ):
                cur = v
        return cur

    def _assemble_many(self, terms: list[Term]) -> list[dict]:
        if not terms:
            return []
        ids = [t.id for t in terms]
        versions = self.s.execute(select(TermVersion).where(TermVersion.term_id.in_(ids))).scalars().all()
        vers_by_term: dict[int, list[TermVersion]] = defaultdict(list)
        for v in versions:
            vers_by_term[v.term_id].append(v)
        linkages = self.s.execute(select(Linkage).where(Linkage.term_id.in_(ids))).scalars().all()
        links_by_term: dict[int, list[Linkage]] = defaultdict(list)
        for lk in linkages:
            links_by_term[lk.term_id].append(lk)
        relations = self.s.execute(
            select(TermRelation).where(TermRelation.from_term_id.in_(ids))).scalars().all()
        rels_by_term: dict[int, list[TermRelation]] = defaultdict(list)
        for r in relations:
            rels_by_term[r.from_term_id].append(r)
        # resolve any to_term_id relations back to their slug (none in Phase 2, future-proof)
        to_ids = {r.to_term_id for rs in rels_by_term.values() for r in rs if r.to_term_id}
        slug_by_id: dict[int, str] = {}
        if to_ids:
            for tid, slug in self.s.execute(
                    select(Term.id, Term.slug).where(Term.id.in_(to_ids))).all():
                slug_by_id[tid] = slug
        return [
            self._to_flat(t, self._pick_current(vers_by_term.get(t.id, [])),
                          links_by_term.get(t.id, []), rels_by_term.get(t.id, []), slug_by_id)
            for t in terms
        ]

    @staticmethod
    def _to_flat(term: Term, ver: TermVersion | None, links: list[Linkage],
                 rels: list[TermRelation], slug_by_id: dict[int, str]) -> dict:
        related = [lk.raw_ref for lk in links]
        related += [(r.to_label or slug_by_id.get(r.to_term_id, "")) for r in rels]
        attrs = (ver.attributes if ver and ver.attributes else {}) or {}
        return {
            "id": term.slug,
            "domain": term.domain or "",
            "category": term.category or "",
            "title": (ver.title if ver else "") or "",
            "business_description": (ver.business_description if ver else "") or "",
            "detailed_description": (ver.detailed_description if ver else "") or "",
            "synonyms": list(ver.synonyms) if ver and ver.synonyms else [],
            "related_objects": [r for r in related if r],
            "steward": term.steward or "",
            "tags": list(ver.tags) if ver and ver.tags else [],
            "status": term.status or "draft",
            "CRR_context": attrs.get(_ATTR_CRR, "") or "",
            "DPM_context": attrs.get(_ATTR_DPM, "") or "",
            "ai_generated_fields": list(ver.ai_generated_fields) if ver and ver.ai_generated_fields else [],
            "ai_provenance": (ver.ai_provenance if ver and ver.ai_provenance else {}) or {},
            "is_cde": term.is_cde,
            "last_updated": term.updated_at.isoformat() if term.updated_at else None,
            "last_reviewed": term.last_reviewed.isoformat() if term.last_reviewed else None,
        }

    # ── reads ──────────────────────────────────────────────────────────────────
    def list_terms(self) -> list[dict]:
        terms = self.s.execute(select(Term)).scalars().all()
        return self._assemble_many(list(terms))

    def get_term(self, slug: str) -> dict | None:
        term = self.s.execute(select(Term).where(Term.slug == slug)).scalar_one_or_none()
        if term is None:
            return None
        return self._assemble_many([term])[0]

    def exists(self, slug: str) -> bool:
        return self.s.execute(select(Term.id).where(Term.slug == slug)).scalar_one_or_none() is not None

    def search(self, query: str) -> list[dict]:
        return [d for d in self.list_terms() if _matches(d, query)]

    def by_domain_category(self) -> dict[str, dict[str, list[dict]]]:
        tree: dict[str, dict[str, list[dict]]] = {}
        for d in self.list_terms():
            tree.setdefault(d.get("domain", ""), {}).setdefault(d.get("category", ""), []).append(d)
        return tree

    def cross_references(self, ref: str) -> list[dict]:
        tids = set(self.s.execute(select(Linkage.term_id).where(Linkage.raw_ref == ref)).scalars().all())
        tids |= set(self.s.execute(
            select(TermRelation.from_term_id).where(TermRelation.to_label == ref)).scalars().all())
        if not tids:
            return []
        terms = self.s.execute(select(Term).where(Term.id.in_(tids))).scalars().all()
        return self._assemble_many(list(terms))

    # ── writes ─────────────────────────────────────────────────────────────────
    def insert_term(self, data: dict) -> dict:
        slug = data.get("id") or ""
        if self.exists(slug):
            raise ValueError(f"Term with id '{slug}' already exists.")
        return self._upsert(data, creating=True)

    def update_term(self, data: dict) -> dict:
        slug = data.get("id") or ""
        # Row-lock the target so two concurrent updaters serialise instead of clobbering.
        term = self.s.execute(
            select(Term).where(Term.slug == slug).with_for_update()).scalar_one_or_none()
        if term is None:
            raise KeyError(f"Term '{slug}' not found.")
        return self._upsert(data, creating=False, term=term)

    def delete_term(self, slug: str) -> None:
        term = self.s.execute(select(Term).where(Term.slug == slug)).scalar_one_or_none()
        if term is None:
            raise KeyError(f"Term '{slug}' not found.")
        self.s.delete(term)  # cascades to versions / linkages / relations
        self.s.flush()

    def _upsert(self, data: dict, *, creating: bool, term: Term | None = None) -> dict:
        slug = data.get("id") or ""
        gid = self._glossary_id()
        if term is None:
            term = self.s.execute(
                select(Term).where(Term.glossary_id == gid, Term.slug == slug)
                .with_for_update()).scalar_one_or_none()
        if creating and term is not None:
            raise ValueError(f"Term with id '{slug}' already exists.")
        if term is None:
            term = Term(glossary_id=gid, slug=slug)
            self.s.add(term)

        term.domain = data.get("domain") or None
        term.category = data.get("category") or None
        term.steward = data.get("steward") or None
        # D4 empty-vs-draft: a caller-supplied status wins (edits send the full term); a
        # fresh term with only a title and no other content rests at 'empty', else 'draft'.
        _content = (data.get("business_description"), data.get("detailed_description"),
                    data.get("CRR_context"), data.get("DPM_context"))
        _has_content = (any((c or "").strip() for c in _content)
                        or bool(data.get("synonyms")) or bool(data.get("tags")))
        term.status = data.get("status") or derive_saved_state(_has_content)
        if "is_cde" in data:
            term.is_cde = data.get("is_cde")
        term.last_reviewed = _parse_dt(data.get("last_reviewed"))
        term.updated_at = _now()
        self.s.flush()  # assign term.id

        approved = term.status == "approved"
        ver = self.s.execute(
            select(TermVersion).where(TermVersion.term_id == term.id, TermVersion.version_no == 1)
        ).scalar_one_or_none()
        if ver is None:
            ver = TermVersion(term_id=term.id, version_no=1)
            self.s.add(ver)
        ver.title = data.get("title") or ""
        ver.business_description = data.get("business_description") or None
        ver.detailed_description = data.get("detailed_description") or None
        ver.synonyms = list(data.get("synonyms") or [])
        ver.tags = list(data.get("tags") or [])
        ver.ai_generated_fields = list(data.get("ai_generated_fields") or [])
        ver.attributes = {
            _ATTR_CRR: data.get("CRR_context") or "",
            _ATTR_DPM: data.get("DPM_context") or "",
        }
        ver.status = "approved" if approved else "draft"
        ver.is_current_approved = approved
        if "ai_provenance" in data:
            ver.ai_provenance = data.get("ai_provenance") or {}

        # Children are fully replaced on every upsert (matches v1 whole-object write),
        # safely inside this transaction.
        self.s.execute(delete(Linkage).where(Linkage.term_id == term.id))
        self.s.execute(delete(TermRelation).where(TermRelation.from_term_id == term.id))
        for ref in data.get("related_objects") or []:
            parsed = _parse_ref(ref)
            if parsed and parsed[0] in ("source", "target"):
                kind, dataset, segs = parsed
                gran = _granularity(segs)
                schema = segs[0] if segs else None
                table = segs[1] if len(segs) >= 2 else None
                column = ".".join(segs[2:]) if len(segs) >= 3 else None
                self.s.add(Linkage(
                    term_id=term.id, kind=kind, granularity=gran, dataset=dataset,
                    schema_name=schema, table_name=table, column_name=column,
                    raw_ref=ref, status="active", origin="migrated", resolved=True,
                ))
            else:
                self.s.add(TermRelation(from_term_id=term.id, relation_type="related", to_label=ref))
        self.s.flush()
        return self._assemble_many([term])[0]

    # ── v2 API: lightweight summaries, tree, faceted search, history, queue ────
    def _current_versions_map(self, term_ids: list[int]) -> dict[int, TermVersion]:
        rows = self.s.execute(select(TermVersion).where(TermVersion.term_id.in_(term_ids))).scalars().all()
        by_term: dict[int, list[TermVersion]] = defaultdict(list)
        for v in rows:
            by_term[v.term_id].append(v)
        return {tid: self._pick_current(vs) for tid, vs in by_term.items()}

    def _summaries(self, terms: list[Term]) -> list[dict]:
        if not terms:
            return []
        ids = [t.id for t in terms]
        cur = self._current_versions_map(ids)
        linked = set(self.s.execute(
            select(Linkage.term_id).where(Linkage.term_id.in_(ids)).distinct()).scalars().all())
        parents_with_children = set(self.s.execute(
            select(Term.parent_term_id).where(Term.parent_term_id.in_(ids)).distinct()).scalars().all())
        parent_ids = {t.parent_term_id for t in terms if t.parent_term_id}
        pslug: dict[int, str] = {}
        if parent_ids:
            for tid, slug in self.s.execute(
                    select(Term.id, Term.slug).where(Term.id.in_(parent_ids))).all():
                pslug[tid] = slug
        out = []
        for t in terms:
            v = cur.get(t.id)
            out.append({
                "id": t.slug,
                "parent": pslug.get(t.parent_term_id),
                "title": (v.title if v else t.slug) or t.slug,
                "domain": t.domain or "",
                "category": t.category or "",
                "status": t.status,
                "is_cde": t.is_cde,
                "has_linkage": t.id in linked,
                "ai_generated": bool(v and v.ai_generated_fields),
                "has_children": t.id in parents_with_children,
            })
        return out

    def tree(self) -> list[dict]:
        terms = self.s.execute(select(Term)).scalars().all()
        return self._summaries(list(terms))

    def facets(self) -> dict[str, dict[str, int]]:
        def counts(col):
            return {k: n for k, n in self.s.execute(
                select(col, func.count()).where(col.isnot(None)).group_by(col)).all()}
        return {
            "domain": counts(Term.domain),
            "category": counts(Term.category),
            "status": counts(Term.status),
            "steward": counts(Term.steward),
        }

    def faceted_search(self, q: str | None = None, *, domain: str | None = None, category: str | None = None,
               status: str | None = None, steward: str | None = None,
               has_linkage: bool | None = None, ai_generated: bool | None = None) -> list[dict]:
        """Faceted search served by Postgres FTS (GIN index), not in-memory filtering.

        Distinct from the v1-parity ``search(query)`` above (which the legacy GlossaryAgent
        interface uses): this powers the v2 faceted UI and returns lightweight summaries."""
        cur = (
            select(TermVersion.term_id, TermVersion.search_tsv, TermVersion.ai_generated_fields)
            .distinct(TermVersion.term_id)
            .order_by(TermVersion.term_id, TermVersion.is_current_approved.desc(),
                      TermVersion.version_no.desc())
        ).subquery()
        stmt = select(Term.id).join(cur, cur.c.term_id == Term.id)
        conds = []
        if q:
            conds.append(cur.c.search_tsv.op("@@")(func.websearch_to_tsquery("english", q)))
        if domain:
            conds.append(Term.domain == domain)
        if category:
            conds.append(Term.category == category)
        if status:
            conds.append(Term.status == status)
        if steward:
            conds.append(Term.steward == steward)
        if ai_generated:
            conds.append(func.coalesce(func.array_length(cur.c.ai_generated_fields, 1), 0) > 0)
        if has_linkage:
            conds.append(Term.id.in_(select(Linkage.term_id)))
        if conds:
            stmt = stmt.where(and_(*conds))
        ids = self.s.execute(stmt).scalars().all()
        if not ids:
            return []
        terms = self.s.execute(select(Term).where(Term.id.in_(ids))).scalars().all()
        return self._summaries(list(terms))

    def history(self, slug: str) -> dict | None:
        term = self.s.execute(select(Term).where(Term.slug == slug)).scalar_one_or_none()
        if term is None:
            return None
        versions = self.s.execute(
            select(TermVersion).where(TermVersion.term_id == term.id)
            .order_by(TermVersion.version_no)).scalars().all()
        transitions = self.s.execute(
            select(LifecycleTransition)
            .where(LifecycleTransition.subject_type == "glossary_term",
                   LifecycleTransition.subject_ref == slug)
            .order_by(LifecycleTransition.occurred_at)).scalars().all()
        return {
            "term": slug,
            "versions": [{
                "version_no": v.version_no,
                "title": v.title,
                "status": v.status,
                # "serving DQ scoring" concept present even with a single version (Phase 5-ready)
                "serving": bool(v.is_current_approved) or (v.status == "draft" and len(versions) == 1),
                "authored_by": v.authored_by,
                "authored_at": v.authored_at.isoformat() if v.authored_at else None,
                "ai_provenance": v.ai_provenance or {},
            } for v in versions],
            "transitions": [{
                "from_status": tr.from_status,
                "to_status": tr.to_status,
                "actor": tr.actor,
                "actor_role": tr.actor_role,
                "reason": tr.reason,
                "occurred_at": tr.occurred_at.isoformat() if tr.occurred_at else None,
            } for tr in transitions],
        }

    def review_queue(self) -> list[dict]:
        """Draft terms carrying AI-generated content — the bulk-review work list."""
        terms = self.s.execute(select(Term).where(Term.status == "draft")).scalars().all()
        summaries = self._summaries(list(terms))
        summaries = [s for s in summaries if s["ai_generated"]]
        # attach assignment from review_subject, if any
        assigned = {
            ref: who for ref, who in self.s.execute(
                select(ReviewSubject.subject_ref, ReviewSubject.assigned_to)
                .where(ReviewSubject.subject_type == "glossary_term")).all()
        }
        for s in summaries:
            s["assigned_to"] = assigned.get(s["id"])
        return summaries

    def assign_review(self, slug: str, assignee: str | None) -> None:
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        term = self.s.execute(select(Term).where(Term.slug == slug)).scalar_one_or_none()
        if term is None:
            raise KeyError(f"Term '{slug}' not found.")
        stmt = pg_insert(ReviewSubject).values(
            subject_type="glossary_term", subject_ref=slug,
            current_state=term.status, assigned_to=assignee,
        ).on_conflict_do_update(
            index_elements=["subject_type", "subject_ref"],
            set_={"assigned_to": assignee, "current_state": term.status, "updated_at": _now()},
        )
        self.s.execute(stmt)
        self.s.flush()

    def set_status(self, slug: str, new_status: str, *, actor: str | None = None,
                   actor_role: str | None = None, reason: str | None = None) -> dict:
        """Transition a term's lifecycle status (v2 review confirm/reject).

        Writes a ``lifecycle_transition`` row so the History tab shows the decision trail,
        and syncs the current version's approved flag. Single-version model — Phase 5 adds
        versioning-on-edit and the revalidation coupling; here the status change is in place.
        """
        term = self.s.execute(
            select(Term).where(Term.slug == slug).with_for_update()).scalar_one_or_none()
        if term is None:
            raise KeyError(f"Term '{slug}' not found.")
        from_status = term.status
        approved = new_status == "approved"
        term.status = new_status
        term.updated_at = _now()
        if approved and term.last_reviewed is None:
            term.last_reviewed = _now()
        versions = self.s.execute(
            select(TermVersion).where(TermVersion.term_id == term.id)).scalars().all()
        cur = self._pick_current(list(versions))
        if cur is not None:
            cur.status = "approved" if approved else "draft"
            cur.is_current_approved = approved
        self.s.add(LifecycleTransition(
            subject_type="glossary_term", subject_ref=slug,
            from_status=from_status, to_status=new_status,
            actor=actor, actor_role=actor_role, reason=reason,
        ))
        rs = self.s.execute(
            select(ReviewSubject).where(ReviewSubject.subject_type == "glossary_term",
                                        ReviewSubject.subject_ref == slug)).scalar_one_or_none()
        if rs is not None:
            rs.current_state = new_status
            rs.updated_at = _now()
        self.s.flush()
        return self._assemble_many([term])[0]

    # ── hierarchy (reparent, ≤3 levels, no cycles) ─────────────────────────────
    def _depth_up(self, term: Term) -> int:
        depth, node, seen = 1, term, set()
        while node.parent_term_id and node.parent_term_id not in seen:
            seen.add(node.id)
            node = self.s.execute(select(Term).where(Term.id == node.parent_term_id)).scalar_one()
            depth += 1
        return depth

    def _subtree_ids(self, term_id: int) -> set[int]:
        found, frontier = set(), [term_id]
        while frontier:
            children = self.s.execute(
                select(Term.id).where(Term.parent_term_id.in_(frontier))).scalars().all()
            children = [c for c in children if c not in found]
            found.update(children)
            frontier = children
        return found

    def _subtree_height(self, term_id: int) -> int:
        levels, frontier = 1, [term_id]
        while frontier:
            children = self.s.execute(
                select(Term.id).where(Term.parent_term_id.in_(frontier))).scalars().all()
            if not children:
                break
            levels += 1
            frontier = children
        return levels

    def reparent(self, slug: str, parent_slug: str | None) -> dict:
        term = self.s.execute(select(Term).where(Term.slug == slug)).scalar_one_or_none()
        if term is None:
            raise KeyError(f"Term '{slug}' not found.")
        if parent_slug is None:
            term.parent_term_id = None
            self.s.flush()
            return self.get_term(slug)
        parent = self.s.execute(select(Term).where(Term.slug == parent_slug)).scalar_one_or_none()
        if parent is None:
            raise KeyError(f"Parent term '{parent_slug}' not found.")
        if parent.id == term.id:
            raise ValueError("A term cannot be its own parent.")
        if parent.id in self._subtree_ids(term.id):
            raise ValueError("Cannot reparent under a descendant (would create a cycle).")
        if self._depth_up(parent) + self._subtree_height(term.id) > 3:
            raise ValueError("Reparenting would exceed the 3-level hierarchy cap.")
        term.parent_term_id = parent.id
        self.s.flush()
        return self.get_term(slug)

    def set_parent_by_id(self, slug: str, parent_id: int | None) -> None:
        """Direct parent set for seeding demos (skips depth/cycle checks — caller's responsibility)."""
        term = self.s.execute(select(Term).where(Term.slug == slug)).scalar_one()
        term.parent_term_id = parent_id
        self.s.flush()

    def record_provenance(self, slug: str, provenance: dict) -> None:
        """Merge per-field AI provenance into the current version (activated by the v2 write path)."""
        term = self.s.execute(select(Term).where(Term.slug == slug)).scalar_one_or_none()
        if term is None:
            raise KeyError(f"Term '{slug}' not found.")
        versions = self.s.execute(
            select(TermVersion).where(TermVersion.term_id == term.id)).scalars().all()
        cur = self._pick_current(list(versions))
        if cur is not None:
            cur.ai_provenance = {**(cur.ai_provenance or {}), **provenance}
            self.s.flush()

    def multi_term_column_count(self) -> int:
        """Diagnostic (decision E): columns linked by >1 term — gauges the element.py contract risk."""
        sub = (
            select(Linkage.kind, Linkage.dataset, Linkage.schema_name,
                   Linkage.table_name, Linkage.column_name)
            .where(Linkage.granularity == "column")
            .group_by(Linkage.kind, Linkage.dataset, Linkage.schema_name,
                      Linkage.table_name, Linkage.column_name)
            .having(func.count(func.distinct(Linkage.term_id)) > 1)
        ).subquery()
        return self.s.execute(select(func.count()).select_from(sub)).scalar_one()

    def coverage(self) -> dict:
        """Real coverage/health facts from Postgres (the numbers the v2 Coverage view shows)."""
        from core.shared.models import LinkageTriage

        by_status = {k: n for k, n in self.s.execute(
            select(Term.status, func.count()).group_by(Term.status)).all()}
        by_gran = {k: n for k, n in self.s.execute(
            select(Linkage.granularity, func.count()).group_by(Linkage.granularity)).all()}
        distinct_cols = self.s.execute(
            select(func.count(func.distinct(func.concat(
                Linkage.dataset, "|", Linkage.schema_name, "|",
                Linkage.table_name, "|", Linkage.column_name))))
            .where(Linkage.kind == "source", Linkage.granularity == "column",
                   Linkage.resolved.is_(True))
        ).scalar_one()
        return {
            "terms_total": self.s.execute(select(func.count()).select_from(Term)).scalar_one(),
            "by_status": by_status,
            "approved": by_status.get("approved", 0),
            "linkages_total": self.s.execute(select(func.count()).select_from(Linkage)).scalar_one(),
            "by_granularity": by_gran,
            "distinct_linked_source_columns": distinct_cols,
            "triage_total": self.s.execute(select(func.count()).select_from(LinkageTriage)).scalar_one(),
            "needs_revalidation": self.s.execute(
                select(func.count()).select_from(Linkage)
                .where(Linkage.status == "needs_revalidation")).scalar_one(),
        }
