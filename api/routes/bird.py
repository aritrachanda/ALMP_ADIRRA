"""BIRD Knowledge Base — read-only API endpoints (Phase 1)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from core.bird_kb import BIRD_KB_FRAMEWORKS, bird_conn as _conn

router = APIRouter(prefix="/bird", tags=["bird-kb"])

ROLE_LABEL: dict[str, str] = {"D": "Dimension", "O": "Observation", "A": "Attribute"}

# Maps layer tab name → (column, value) filter on cube table
_LAYER_FILTER: dict[str, tuple[str, str]] = {
    "LDM":  ("cube_type",    "LDM"),
    "ELDM": ("cube_type",    "ELDM"),
    "IL":   ("cube_type",    "IL"),
    "EIL":  ("cube_type",    "EIL"),
    "ROL":  ("framework_id", "ANCRDT"),   # AnaCredit output cubes
}


def _layer_filter(layer: str) -> tuple[str, str]:
    col, val = _LAYER_FILTER.get(layer.upper(), ("cube_type", layer.upper()))
    return col, val


# Maps the UI framework filter tab → cube.framework_id value. "All" → BIRD KB scope (below),
# not the full 9-framework export — the other frameworks are Regulatory KB seed data (Decision
# Point 21) and are not exposed on this page.
_FRAMEWORK_FILTER: dict[str, str] = {
    "BIRD": "BIRD",
    "ANACREDIT": "ANCRDT",
    "ANCRDT": "ANCRDT",
}


def _framework_clause(framework: str | None) -> tuple[str, list]:
    """Return an extra SQL WHERE clause + params for the cube framework filter."""
    fw = _FRAMEWORK_FILTER.get((framework or "").upper())
    if fw:
        return " AND c.framework_id = ?", [fw]
    placeholders = ",".join("?" for _ in BIRD_KB_FRAMEWORKS)
    return f" AND c.framework_id IN ({placeholders})", list(BIRD_KB_FRAMEWORKS)


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/groups")
def get_groups(layer: str = "LDM", framework: str | None = None):
    """Entity group list for a layer with entity count badge."""
    col, val = _layer_filter(layer)
    fw_clause, fw_params = _framework_clause(framework)
    with _conn() as conn:
        rows = conn.execute(
            f"""
            SELECT cg.cube_group_id, cg.name, cg.code, cg.description,
                   COUNT(DISTINCT c.cube_id) AS entity_count
            FROM cube_group cg
            JOIN cube_group_enumeration_current cge ON cge.cube_group_id = cg.cube_group_id
            JOIN cube_current c ON c.cube_id = cge.cube_id AND c.{col} = ?{fw_clause}
            GROUP BY cg.cube_group_id, cg.name, cg.code, cg.description
            HAVING COUNT(DISTINCT c.cube_id) > 0
            ORDER BY cg.name
            """,
            [val, *fw_params],
        ).fetchall()
    return [
        dict(zip(["cube_group_id", "name", "code", "description", "entity_count"], r))
        for r in rows
    ]


@router.get("/entities")
def get_entities(group: str, layer: str = "LDM", framework: str | None = None):
    """Cubes within a group for the selected layer, ordered by name."""
    col, val = _layer_filter(layer)
    fw_clause, fw_params = _framework_clause(framework)
    with _conn() as conn:
        rows = conn.execute(
            f"""
            SELECT c.cube_id, c.code, c.name, c.cube_type, c.framework_id, c.description
            FROM cube_current c
            JOIN cube_group_enumeration_current cge ON cge.cube_id = c.cube_id
            WHERE cge.cube_group_id = ? AND c.{col} = ?{fw_clause}
            ORDER BY c.name
            """,
            [group, val, *fw_params],
        ).fetchall()
    return [
        dict(zip(["cube_id", "code", "name", "cube_type", "framework_id", "description"], r))
        for r in rows
    ]


@router.get("/entity/{cube_id}")
def get_entity(cube_id: str):
    """Full entity detail: metadata + attributes grouped D → O → A + legal references."""
    with _conn() as conn:
        cube_row = conn.execute(
            "SELECT cube_id, code, name, cube_type, framework_id, description "
            "FROM cube WHERE cube_id = ?",
            [cube_id],
        ).fetchone()
        if not cube_row:
            raise HTTPException(status_code=404, detail=f"Entity '{cube_id}' not found")
        cube = dict(zip(["cube_id", "code", "name", "cube_type", "framework_id", "description"], cube_row))

        attr_rows = conn.execute(
            """
            SELECT csi.cube_structure_item_id, csi.role, csi.is_mandatory, csi.subdomain_id,
                   csi."order", csi.attribute_associated_variable,
                   v.variable_id, v.code AS variable_code, v.name AS variable_name,
                   v.description AS variable_description,
                   d.domain_id, d.name AS domain_name, d.data_type, d.is_enumerated
            FROM cube_structure_item csi
            JOIN variable v ON v.variable_id = csi.variable_id
            JOIN domain d   ON d.domain_id   = v.domain_id
            WHERE csi.cube_structure_id = (SELECT cube_structure_id FROM cube WHERE cube_id = ?)
            ORDER BY
                CASE csi.role WHEN 'D' THEN 1 WHEN 'O' THEN 2 WHEN 'A' THEN 3 ELSE 4 END,
                csi."order"
            """,
            [cube_id],
        ).fetchall()

        attr_cols = [
            "csi_id", "role", "is_mandatory", "subdomain_id", "order_num",
            "attribute_associated_variable",
            "variable_id", "variable_code", "variable_name", "variable_description",
            "domain_id", "domain_name", "data_type", "is_enumerated",
        ]
        attributes = []
        for row in attr_rows:
            attr = dict(zip(attr_cols, row))
            attr["role_label"] = ROLE_LABEL.get(str(attr["role"]), str(attr["role"]))
            # NEVS = Null Explanatory Values: A-role variables named NEVS on AnaCredit/ROL
            # output cubes. Match against either variable code or name (the SMCube export
            # uses both forms, often suffixed e.g. "<concept>_NEVS").
            _code = str(attr.get("variable_code") or "").upper()
            _name = str(attr.get("variable_name") or "").upper()
            attr["is_nevs"] = bool(
                attr["role"] == "A" and ("NEVS" in _code or "NEVS" in _name)
            )
            attributes.append(attr)

        legal_rows = conn.execute(
            """
            SELECT lr.object_id, lr.legal_text_id, lt.legal_code, lt.legal_description,
                   lt.business_description, lr.article
            FROM legal_reference_current lr
            JOIN legal_text lt ON lt.legal_text_id = lr.legal_text_id
            WHERE lr.object_id = ? AND lr.object_type = 'CUBE'
            """,
            [cube_id],
        ).fetchall()
        legal = [
            {
                # legal_reference has no published id (Decision Point 19) — (object_id,
                # legal_text_id) is the real key; derive a stable list key from it at read time.
                "legal_reference_id": f"{r[0]}__{r[1]}",
                "legal_code": r[2],
                "legal_description": r[3],
                "business_description": r[4],
                "article": r[5],
            }
            for r in legal_rows
        ]

        cube["attributes"] = attributes
        cube["legal_references"] = legal
        return cube


@router.get("/graph")
def get_graph(layer: str = "LDM", group: str | None = None, framework: str | None = None):
    """
    vis-network {nodes, edges} payload.
    No group → level-1 cluster nodes (entity groups, max 20).
    With group → level-2 entity nodes + cube_relationship edges (max 20 nodes).
    """
    col, val = _layer_filter(layer)
    fw_clause, fw_params = _framework_clause(framework)
    with _conn() as conn:
        if not group:
            rows = conn.execute(
                f"""
                SELECT cg.cube_group_id, cg.name,
                       COUNT(DISTINCT c.cube_id) AS entity_count
                FROM cube_group cg
                JOIN cube_group_enumeration_current cge ON cge.cube_group_id = cg.cube_group_id
                JOIN cube_current c ON c.cube_id = cge.cube_id AND c.{col} = ?{fw_clause}
                GROUP BY cg.cube_group_id, cg.name
                HAVING COUNT(DISTINCT c.cube_id) > 0
                ORDER BY entity_count DESC
                LIMIT 20
                """,
                [val, *fw_params],
            ).fetchall()
            nodes = [
                {
                    "id": r[0],
                    "label": r[1],
                    "title": f"{r[1]}\n{r[2]} entities",
                    "value": int(r[2]) if r[2] else 1,
                    "group": "cluster",
                }
                for r in rows
            ]
            return {"nodes": nodes, "edges": [], "level": 1}

        entity_rows = conn.execute(
            f"""
            SELECT c.cube_id, c.name, c.framework_id
            FROM cube_current c
            JOIN cube_group_enumeration_current cge ON cge.cube_id = c.cube_id
            WHERE cge.cube_group_id = ? AND c.{col} = ?{fw_clause}
            ORDER BY c.name
            LIMIT 20
            """,
            [group, val, *fw_params],
        ).fetchall()
        cube_ids = [r[0] for r in entity_rows]
        nodes_out = [
            {"id": r[0], "label": r[1], "title": r[1], "group": "entity", "framework_id": r[2]}
            for r in entity_rows
        ]

        edges_out: list[dict[str, Any]] = []
        if cube_ids:
            ph = ",".join("?" for _ in cube_ids)
            edge_rows = conn.execute(
                f"""
                SELECT cube_relationship_id, primary_cube_id, foreign_cube_id,
                       type_of_relationship, primary_cube_cardinality, foreign_cube_cardinality
                FROM cube_relationship_current
                WHERE primary_cube_id IN ({ph}) AND foreign_cube_id IN ({ph})
                """,
                cube_ids + cube_ids,
            ).fetchall()
            edges_out = [
                {
                    "id": r[0],
                    "from": r[1],
                    "to": r[2],
                    "label": f"{r[4] or ''}:{r[5] or ''}",
                    "title": r[3] or "",
                }
                for r in edge_rows
            ]

        return {"nodes": nodes_out, "edges": edges_out, "level": 2}


@router.get("/mapping-candidates")
def get_mapping_candidates(type: str = "", subject: str = ""):
    """Primary mapping lookup: LDM candidate attributes for a given entity subject + data type."""
    with _conn() as conn:
        q = """
            SELECT c.cube_id, c.name AS entity_name, c.cube_type,
                   csi.role, csi.is_mandatory,
                   v.variable_id, v.code AS variable_code, v.name AS variable_name, v.description,
                   d.name AS domain_name, d.data_type, d.is_enumerated
            FROM cube_current c
            JOIN cube_structure_item csi ON csi.cube_structure_id = c.cube_structure_id
            JOIN variable v ON v.variable_id = csi.variable_id
            JOIN domain d   ON d.domain_id   = v.domain_id
            WHERE c.cube_type = 'LDM' AND c.framework_id = 'BIRD'
        """
        params: list[Any] = []
        if subject:
            q += " AND c.name ILIKE ?"
            params.append(f"%{subject}%")
        if type:
            q += " AND d.data_type ILIKE ?"
            params.append(f"%{type}%")
        q += (
            " ORDER BY CASE csi.role WHEN 'D' THEN 1 WHEN 'O' THEN 2 WHEN 'A' THEN 3 ELSE 4 END,"
            " v.name LIMIT 200"
        )
        rows = conn.execute(q, params).fetchall()

    cols = [
        "cube_id", "entity_name", "cube_type", "role", "is_mandatory",
        "variable_id", "variable_code", "variable_name", "description",
        "domain_name", "data_type", "is_enumerated",
    ]
    result = []
    for row in rows:
        item = dict(zip(cols, row))
        item["role_label"] = ROLE_LABEL.get(str(item["role"]), str(item["role"]))
        result.append(item)
    return result


@router.get("/chain/{cube_id}")
def get_chain(cube_id: str):
    """
    Forward transformation chain: follow cube_link + logical_transformation_rule
    from the given entity through WUDEN → DER → GEN hops.
    Display-only in Phase 1 — does not execute rules.
    """
    with _conn() as conn:
        if not conn.execute("SELECT 1 FROM cube WHERE cube_id = ?", [cube_id]).fetchone():
            raise HTTPException(status_code=404, detail=f"Entity '{cube_id}' not found")

        chain: list[dict[str, Any]] = []
        visited_ltrs: set[str] = set()
        visited_cubes: set[str] = {cube_id}
        current_ids = [cube_id]

        for _ in range(4):
            if not current_ids:
                break
            ph = ",".join("?" for _ in current_ids)
            rules = conn.execute(
                f"""
                SELECT ltr.logical_transformation_rule_id,
                       ltr.transformation_type, ltr.source_layer, ltr.destination_layer,
                       ltr.algorithm,
                       cl.primary_cube_id, cl.foreign_cube_id,
                       src.name AS source_name, dst.name AS destination_name
                FROM cube_link_current cl
                JOIN logical_transformation_rule_current ltr
                    ON ltr.logical_transformation_rule_id = cl.logical_transformation_rule_id
                JOIN cube src ON src.cube_id = cl.primary_cube_id
                JOIN cube dst ON dst.cube_id = cl.foreign_cube_id
                WHERE cl.primary_cube_id IN ({ph})
                ORDER BY CASE ltr.transformation_type
                    WHEN 'WUDEN' THEN 1 WHEN 'DER' THEN 2 WHEN 'GEN' THEN 3 ELSE 4 END
                """,
                current_ids,
            ).fetchall()

            next_ids: list[str] = []
            for r in rules:
                ltr_id = r[0]
                if ltr_id in visited_ltrs:
                    continue
                visited_ltrs.add(ltr_id)
                chain.append({
                    "ltr_id": r[0],
                    "transformation_type": r[1],
                    "source_layer": r[2],
                    "destination_layer": r[3],
                    "algorithm": r[4],
                    "source_cube_id": r[5],
                    "destination_cube_id": r[6],
                    "source_name": r[7],
                    "destination_name": r[8],
                })
                dest_cube_id = r[6]
                if dest_cube_id not in visited_cubes:
                    visited_cubes.add(dest_cube_id)
                    next_ids.append(dest_cube_id)
            current_ids = list(dict.fromkeys(next_ids))  # deduplicate preserving order

        return {"cube_id": cube_id, "chain": chain}


@router.get("/members/{domain_id}")
def get_members(domain_id: str):
    """Code list entries for an enumerated domain."""
    with _conn() as conn:
        domain_row = conn.execute(
            "SELECT domain_id, name, data_type, is_enumerated, description FROM domain WHERE domain_id = ?",
            [domain_id],
        ).fetchone()
        if not domain_row:
            raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")
        domain = dict(zip(["domain_id", "name", "data_type", "is_enumerated", "description"], domain_row))

        member_rows = conn.execute(
            "SELECT member_id, code, name, description FROM member WHERE domain_id = ? ORDER BY code",
            [domain_id],
        ).fetchall()
    members = [dict(zip(["member_id", "code", "name", "description"], r)) for r in member_rows]
    return {"domain": domain, "members": members}


@router.get("/table")
def get_table(
    layer: str = "LDM",
    group: str | None = None,
    framework: str | None = None,
    limit: int = 500,
):
    """
    Cross-entity flat table: all variables for all entities in the selected layer/group.
    Fetches limit+1 rows to detect capping; returns {rows, total, capped}.
    """
    col, val = _layer_filter(layer)
    fw_clause, fw_params = _framework_clause(framework)

    # NOTE: the DuckDB-era version of this query computed fw_clause but never spliced it into
    # `where` (only fw_params rode along in the params list, silently mismatched against the
    # placeholder count) — a pre-existing bug, harmless only because the default "All" framework
    # used to add no clause at all. Fixed here since "All" now always adds a BIRD KB scope clause.
    conditions = [f"c.{col} = ?"]
    params: list[Any] = [val]
    if group:
        conditions.append("cge.cube_group_id = ?")
        params.append(group)
    where = " AND ".join(conditions) + fw_clause
    params += fw_params

    with _conn() as conn:
        rows = conn.execute(
            f"""
            SELECT
                csi.cube_structure_item_id AS csi_id,
                cg.cube_group_id, cg.name AS group_name,
                c.cube_id, c.name AS entity_name, c.code AS entity_code,
                c.framework_id,
                csi.role, csi.is_mandatory,
                v.variable_id, v.code AS variable_code, v.name AS variable_name,
                d.domain_id, d.name AS domain_name, d.data_type, d.is_enumerated
            FROM cube_current c
            JOIN cube_group_enumeration_current cge ON cge.cube_id = c.cube_id
            JOIN cube_group cg ON cg.cube_group_id = cge.cube_group_id
            JOIN cube_structure_item csi ON csi.cube_structure_id = c.cube_structure_id
            JOIN variable v ON v.variable_id = csi.variable_id
            JOIN domain d ON d.domain_id = v.domain_id
            WHERE {where}
            ORDER BY cg.name, c.name,
                CASE csi.role WHEN 'D' THEN 1 WHEN 'O' THEN 2 WHEN 'A' THEN 3 ELSE 4 END,
                v.name
            LIMIT ?
            """,
            params + [limit + 1],
        ).fetchall()

    capped = len(rows) > limit
    rows = rows[:limit]

    cols_out = [
        "csi_id", "cube_group_id", "group_name",
        "cube_id", "entity_name", "entity_code", "framework_id",
        "role", "is_mandatory",
        "variable_id", "variable_code", "variable_name",
        "domain_id", "domain_name", "data_type", "is_enumerated",
    ]
    result = []
    for row in rows:
        item = dict(zip(cols_out, row))
        item["role_label"] = ROLE_LABEL.get(str(item["role"]), str(item["role"]))
        _code = str(item.get("variable_code") or "").upper()
        _name = str(item.get("variable_name") or "").upper()
        item["is_nevs"] = bool(item["role"] == "A" and ("NEVS" in _code or "NEVS" in _name))
        result.append(item)
    return {"rows": result, "total": len(result), "capped": capped}


@router.get("/suggest")
def get_suggestions(q: str, layer: str = "LDM", scope: str = "All", exact: bool = False):
    """
    Live search suggestions scoped to a BIRD object type (min 2 chars).
    exact=true  → case-insensitive exact match (ILIKE without wildcards)
    exact=false → case-insensitive contains  (ILIKE with %…% wildcards)
    """
    if not q or len(q) < 2:
        return []
    col, val = _layer_filter(layer)
    # exact=True → match whole value; exact=False → match substring
    s = q if exact else f"%{q}%"
    with _conn() as conn:
        def rows(sql: str, params: list) -> list[dict[str, str]]:
            return [{"text": str(r[0]), "type": str(r[1])} for r in conn.execute(sql, params).fetchall() if r[0]]

        scope_key = scope.strip()

        if scope_key == "All":
            result = (
                rows(
                    f"""SELECT DISTINCT v.name, 'variable'
                        FROM variable v
                        JOIN cube_structure_item csi ON csi.variable_id = v.variable_id
                        JOIN cube_current c ON c.cube_structure_id = csi.cube_structure_id
                        WHERE c.{col} = ? AND (v.name ILIKE ? OR v.code ILIKE ?)
                        ORDER BY v.name LIMIT 7""",
                    [val, s, s],
                )
                + rows(
                    f"SELECT DISTINCT c.name, 'entity' FROM cube_current c WHERE c.{col} = ? AND c.name ILIKE ? ORDER BY c.name LIMIT 5",
                    [val, s],
                )
            )

        elif scope_key in ("Entity", "Cube"):
            result = rows(
                f"SELECT DISTINCT c.name, 'entity' FROM cube_current c WHERE c.{col} = ? AND c.name ILIKE ? ORDER BY c.name LIMIT 12",
                [val, s],
            )

        elif scope_key == "Entity Group":
            result = rows(
                f"""SELECT DISTINCT cg.name, 'entity_group'
                    FROM cube_group cg
                    JOIN cube_group_enumeration_current cge ON cge.cube_group_id = cg.cube_group_id
                    JOIN cube_current c ON c.cube_id = cge.cube_id AND c.{col} = ?
                    WHERE cg.name ILIKE ?
                    ORDER BY cg.name LIMIT 12""",
                [val, s],
            )

        elif scope_key == "Variable":
            result = rows(
                f"""SELECT DISTINCT v.name, 'variable'
                    FROM variable v
                    JOIN cube_structure_item csi ON csi.variable_id = v.variable_id
                    JOIN cube_current c ON c.cube_structure_id = csi.cube_structure_id
                    WHERE c.{col} = ? AND (v.name ILIKE ? OR v.code ILIKE ?)
                    ORDER BY v.name LIMIT 12""",
                [val, s, s],
            )

        elif scope_key == "Domain":
            result = rows(
                f"""SELECT DISTINCT d.name, 'domain'
                    FROM domain d
                    JOIN variable v ON v.domain_id = d.domain_id
                    JOIN cube_structure_item csi ON csi.variable_id = v.variable_id
                    JOIN cube_current c ON c.cube_structure_id = csi.cube_structure_id
                    WHERE c.{col} = ? AND d.name ILIKE ?
                    ORDER BY d.name LIMIT 12""",
                [val, s],
            )

        elif scope_key == "Sub-Domain":
            result = rows(
                f"""SELECT DISTINCT sd.name, 'subdomain'
                    FROM subdomain sd
                    JOIN domain d ON d.domain_id = sd.domain_id
                    JOIN variable v ON v.domain_id = d.domain_id
                    JOIN cube_structure_item csi ON csi.variable_id = v.variable_id
                    JOIN cube_current c ON c.cube_structure_id = csi.cube_structure_id
                    WHERE c.{col} = ? AND (sd.name ILIKE ? OR sd.code ILIKE ?)
                    ORDER BY sd.name LIMIT 12""",
                [val, s, s],
            )

        elif scope_key == "Cube Link":
            result = rows(
                f"""SELECT DISTINCT COALESCE(cl.name, cl.code), 'cube_link'
                    FROM cube_link_current cl
                    JOIN cube_current c ON c.cube_id = cl.primary_cube_id
                    WHERE c.{col} = ? AND (cl.name ILIKE ? OR cl.code ILIKE ?)
                    ORDER BY 1 LIMIT 12""",
                [val, s, s],
            )

        elif scope_key == "Cube Structure Item":
            result = rows(
                f"""SELECT DISTINCT csi.cube_variable_code, 'csi'
                    FROM cube_structure_item csi
                    JOIN cube_current c ON c.cube_structure_id = csi.cube_structure_id
                    WHERE c.{col} = ? AND csi.cube_variable_code ILIKE ?
                    ORDER BY csi.cube_variable_code LIMIT 12""",
                [val, s],
            )

        elif scope_key == "Member":
            result = rows(
                f"""SELECT DISTINCT m.name, 'member'
                    FROM member m
                    JOIN domain d ON d.domain_id = m.domain_id
                    JOIN variable v ON v.domain_id = d.domain_id
                    JOIN cube_structure_item csi ON csi.variable_id = v.variable_id
                    JOIN cube_current c ON c.cube_structure_id = csi.cube_structure_id
                    WHERE c.{col} = ? AND (m.name ILIKE ? OR m.code ILIKE ?)
                    ORDER BY m.name LIMIT 12""",
                [val, s, s],
            )

        elif scope_key == "Transformation Rule":
            result = rows(
                """SELECT DISTINCT ltr.transformation_type, 'transformation_rule'
                   FROM logical_transformation_rule_current ltr
                   WHERE ltr.transformation_type ILIKE ?
                   ORDER BY ltr.transformation_type LIMIT 12""",
                [s],
            )

        else:
            result = []

    return result[:12]
