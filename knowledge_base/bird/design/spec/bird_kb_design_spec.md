# BIRD Knowledge Base — Design Spec & Copilot Build Prompt
**ADIRRA Project · ALM Partners · v1.0 · June 2026**
**BIRD version:** 6.7 · **Framework priority:** AnaCredit-first

---

## 1. What the BIRD KB is

A **read-only reference store** holding BIRD structural metadata across all data-model layers (LDM, ELDM, IL, EIL, ROL). It serves two consumers:

1. **BIRD Mapping module** — mapping lookup: given a source field's Mapping Type + Entity Subject, return candidate BIRD LDM target attributes
2. **Data pipeline module** — forward chain reference: show/execute BIRD's own transformation rules (WUDEN → DER → GEN) from LDM → IL/EIL → ROL (AnaCredit output)

The KB stores and displays. It does **not** execute the pipeline. Rule execution happens in the pipeline module, which reads the KB as its config/reference.

---

## 2. Menu placement

The BIRD KB lives under the **Knowledge Base** sidebar group (new group, see Navigation spec):

```
KNOWLEDGE BASE
  BIRD              ← this module
  Regulatory        ← separate module, AnaCredit-first, built later
```

---

## 3. BIRD KB page structure

### 3.1 Top-level layout

The BIRD KB page has **three panels**:

```
┌─────────────────────────────────────────────────────────────┐
│  Layer selector    [LDM] [ELDM] [IL] [EIL] [ROL]            │
│  Framework filter  [All] [BIRD] [AnaCredit]                  │
├──────────────────┬──────────────────────────────────────────┤
│  LEFT PANEL      │  RIGHT PANEL                             │
│  Entity Group    │  ┌─────────────────────────────────────┐ │
│  browser         │  │  [Graph View]  [Table View]          │ │
│  (tree/list)     │  │                                      │ │
│                  │  │  Entity detail / relationship graph  │ │
│                  │  │  or entity browser table             │ │
│                  │  └─────────────────────────────────────┘ │
│                  │  ┌─────────────────────────────────────┐ │
│                  │  │  Attribute detail panel              │ │
│                  │  │  (opens when entity selected)        │ │
│                  │  └─────────────────────────────────────┘ │
└──────────────────┴──────────────────────────────────────────┘
```

### 3.2 Layer selector

Five tabs at the top: **LDM · ELDM · IL · EIL · ROL**

- Default: LDM selected
- LDM and ELDM are the mapping target layers — highlight these visually
- IL / EIL / ROL are the forward-chain layers — secondary visual weight
- Switching layer refreshes both left panel and graph/table view

### 3.3 Left panel — Entity Group browser

Three-level progressive disclosure:

```
Layer (selected above)
  └── Entity Group  [PRTY_RLTD · Party-related]
        └── Entity  [BIRD_PRTY_LDM · Party]
              └── (click → opens attribute panel on right)
```

- Groups sourced from `CUBE_GROUP` table, filtered by selected layer
- Entities within group sourced from `CUBE_GROUP_ENUMERATION` → `CUBE`
- Entity count badge per group
- Search box above the tree (searches entity name + code)
- AnaCredit-relevant groups highlighted when AnaCredit filter active

### 3.4 Right panel — Graph View (default)

Rendered using **vis-network** (already in stack). Progressive disclosure:

**Level 1 (layer selected, no group selected):** show 18 entity group nodes as cluster bubbles, sized by entity count. Clicking a group expands it.

**Level 2 (group selected):** show entities within that group as nodes. Edges sourced from `CUBE_RELATIONSHIP` filtered to these entities. Node colour = entity group colour. Edge label = relationship type + cardinality.

**Level 3 (entity selected):** entity detail panel slides in below the graph showing:
- Entity name, code, description
- Dimension variables (D role — the PK set), listed first
- Observation variables (O role — the reportable facts)
- Attribute variables (A role — qualifiers, shown paired with their O variable by name proximity)
- Each variable row shows: name · domain name · data type · enumerated badge (if coded)
- For enumerated domains: expand to show member code list inline
- Legal references (if any) shown as collapsible footnote

**Never render all 550+ entities at once.** Max nodes on screen: 18 groups or ~20 entities within one group.

### 3.5 Right panel — Table View (toggle)

When user switches to Table View, shows a filterable grid:

| Entity Group | Entity Name | Entity Code | Variable Name | Role | Domain | Data Type | Enumerated |
|---|---|---|---|---|---|---|---|
| Party-related | Party | BIRD_PRTY_LDM | counterparty_identifier | D | String | string | No |

Filter controls: Role (D/O/A), Enumerated (yes/no), search by variable name.

### 3.6 Forward chain panel

Accessible from any entity detail panel via **"Show transformation chain"** button.

Shows the path for the selected entity:

```
[LDM Entity]  →WUDEN→  [IL Table]  →DER→  [EIL Table]  →GEN→  [ROL / AnaCredit Output]
```

Each hop shows:
- Source cube name + code
- Destination cube name + code
- Transformation type (WUDEN / DER / GEN)
- Algorithm text (collapsed by default, expandable)
- Layer tag

Source: `LOGICAL_TRANSFORMATION_RULE` filtered by `SOURCE_CUBE_ID` matching selected entity, traversed through the chain.

### 3.7 SMCube vocabulary explainer

A collapsible **"What does this mean?"** panel available on every view, explaining SMCube terminology in plain language:

| SMCube term | Plain meaning |
|---|---|
| Cube | An entity (a business concept like Party, Instrument, Collateral) |
| Variable | A reusable attribute definition |
| Cube Structure Item | This variable as used in this specific entity, with its role |
| Domain | The data type + allowed values for a variable |
| Member | One allowed value in an enumerated domain (a code list entry) |
| Subdomain | A restricted subset of a domain's allowed values for a specific context |
| Cube Link | A connection between entities across layers |
| Transformation Rule | The logic that moves/derives data from one layer to the next |
| WUDEN | Wrap-Up / DENormalise — LDM → IL structural reshaping |
| DER | Derivation — computing enriched attributes on the EIL |
| GEN | Generation — producing the final regulatory output (AnaCredit) |

---

## 4. Navigation spec (sidebar — full revised structure)

### 4.1 Complete sidebar layout

```
─── pinned above all groups ───────────────────────────────────
Home                           ← app landing page + AI assistant chat interface
                                 NOT a workspace item; sits above all group structure

─── WORKSPACE ─────────────────────────────────────────────────
  Asset Workspace              ← multi-layer: source → table → field
                                 includes profiling, FK stats, SQL bar, bulk grid-edit
                                 (Discovery + Data Catalog functionality absorbed here)

─── DATA GOVERNANCE  (existing — frozen, untouched) ───────────
  Chat
  Discovery                    ← KEEP as-is; not worked on for now
  Data Catalog                 ← KEEP as-is; not worked on for now
  Business Glossary            ← KEEP as-is; old linkage to Discovery/Catalog unchanged
  Mapping                      ← KEEP as-is
  Dashboard                    ← KEEP as-is

─── DATA STANDARDS  (new group) ───────────────────────────────
  Business Glossary  ✦         ← NEW: same underlying data as old Glossary;
                                 re-skinned for new UI; linkage to Asset Workspace
                                 instead of old Discovery/Catalog; old Glossary untouched
  Reference Data     ✦         ← NEW: governed code lists (BIRD domains/members,
                                 AnaCredit enumerations, internal code lists);
                                 curated with lifecycle (draft → approved)

─── REGULATORY WORKSPACE  (new group) ─────────────────────────
  BIRD Mapping       ✦         ← Phase-2 destination: map source fields to BIRD LDM;
                                 consumes BIRD KB; steward review + approval workflow
                                 [future: pipeline module, COREP/FINREP mapping,
                                  output generation land here as well]

─── KNOWLEDGE BASE  (new group) ───────────────────────────────
  BIRD               ✦         ← structural reference model (this spec)
  Regulatory         ✦         ← regulatory interpretation layer;
                                 AnaCredit first when built

─── SYSTEM ────────────────────────────────────────────────────
  (unchanged)
```

### 4.2 Key decisions per item

**Home** — the application landing page hosting the AI assistant chat interface. Pinned above all navigation groups. Not nested inside any group. Users land here first on every session.

**DATA GOVERNANCE (existing)** — completely frozen. Every item (Chat, Discovery, Data Catalog, Business Glossary, Mapping, Dashboard) stays exactly as-is. No link changes, no redirects, no UI modifications. Discovery and Data Catalog are kept even though their functionality is absorbed by the Asset Workspace — they are not removed, just not actively worked on.

**DATA STANDARDS (new group name)** — chosen to distinguish cleanly from the existing "Data Governance" group without renaming anything frozen. "Data Standards" accurately describes the group's function (defining what data means and what values it is allowed to have) and is recognisable in a regulatory reporting context.

- **Business Glossary (new)** — same underlying glossary data as the existing one; new UI layout; Related Items links point to the Asset Workspace (source → table → field) instead of the old Discovery/Catalog screens. The old Business Glossary is untouched — this is a new projection, not a migration.
- **Reference Data** — governed code lists. Covers BIRD enumerated domains (CRRNCY, member hierarchies etc.), AnaCredit enumerations, and any internal bank code lists. Stewards curate entries with a governance lifecycle (draft → approved). This is a *governance asset*, not infrastructure — hence placement in Data Standards rather than Knowledge Base.

**REGULATORY WORKSPACE (new group)** — where regulatory work happens *on your data*. BIRD Mapping is the first item. The group is the long-term container for all regulatory processing: mapping, validation, forward engineering, output generation. When the pipeline module arrives, it lands here. When COREP/FINREP mapping comes, same group.

- **BIRD Mapping** — renamed from the existing "Mapping" item (which stays frozen in the old group). This is the new Phase-2 mapping surface: source field → BIRD LDM attribute, with Mapping Type + Entity Subject deduction, steward review, and approval.

**KNOWLEDGE BASE (new group)** — reference models you *consult*, not workspaces you *operate in*. Read-only. Distinct from Data Standards (which you author) and Regulatory Workspace (where you act).

- **BIRD** — the structural KB (this spec). All BIRD layers, entities, variables, domains, transformation rules.
- **Regulatory** — the interpretive KB. AnaCredit regulation and guidance first; COREP/FINREP/IReF when built. Source: ECB regulation PDFs and guidance documents, not the SMCube export.

### 4.3 AI assistant connectivity rule

Every ✦ new item exposes a **page-context payload** to the AI assistant — both the Home-page chat and the per-page floater chat instance. The payload includes at minimum: active module name, active entity/record/view, and relevant IDs. This allows the assistant to respond to "explain this" or "what does this mean" without the user re-stating where they are. All new modules built under this spec must implement this context hook.

The Home page AI assistant chat is the primary entry point and must be aware of all new modules so users can navigate or query them directly from the landing page ("show me the BIRD Collateral entity", "what code lists are available for currency?").

---

## 5. DuckDB schema

Thirty tables in seven groups. Every table from the SMCube multi-framework export is loaded — nothing omitted. This ensures the full LDM → IL → EIL → ROL transformation journey has all its reference material available. Load from the two SMCube workbook exports. Mirror SMCube language in the store; translate to plain English only in the presentation layer.

### 5.1 Core entity / attribute tables (purple group)

```sql
-- Entity groups (18 groups per layer)
CREATE TABLE cube_group (
    cube_group_id   TEXT PRIMARY KEY,
    name            TEXT,
    layer           TEXT,   -- LDM / ELDM / IL / EIL
    framework_id    TEXT,
    description     TEXT
);

-- Entities / cubes
CREATE TABLE cube (
    cube_id             TEXT PRIMARY KEY,
    cube_group_id       TEXT REFERENCES cube_group(cube_group_id),
    code                TEXT,
    name                TEXT,
    cube_type           TEXT,   -- LDM / ELDM / IL / EIL / C
    framework_id        TEXT,   -- BIRD / ANCRDT / SDD
    cube_structure_id   TEXT,
    description         TEXT
);

-- Attribute-in-use (variable as used in a specific cube, with its role)
CREATE TABLE cube_structure_item (
    csi_id              TEXT PRIMARY KEY,
    cube_structure_id   TEXT,                   -- joins to cube.cube_structure_id
    variable_id         TEXT REFERENCES variable(variable_id),
    role                TEXT,                   -- D (Dimension/PK) / O (Observation) / A (Attribute/qualifier)
    is_mandatory        BOOLEAN,
    subdomain_id        TEXT,                   -- nullable; overrides variable's full domain for this context
    order_num           INTEGER
);
CREATE INDEX idx_csi_structure ON cube_structure_item(cube_structure_id);
CREATE INDEX idx_csi_role ON cube_structure_item(role);

-- Reusable attribute definitions
CREATE TABLE variable (
    variable_id     TEXT PRIMARY KEY,
    code            TEXT,
    name            TEXT,
    domain_id       TEXT REFERENCES domain(domain_id),
    description     TEXT
);
CREATE INDEX idx_var_domain ON variable(domain_id);
```

### 5.2 Domain / value tables (teal group)

```sql
-- Datatype + allowed-value container
CREATE TABLE domain (
    domain_id       TEXT PRIMARY KEY,
    name            TEXT,
    data_type       TEXT,           -- number / string / date / integer(6) etc.
    is_enumerated   BOOLEAN,        -- true = has a member code list
    description     TEXT
);

-- Code list entries (only for enumerated domains)
CREATE TABLE member (
    member_id       TEXT PRIMARY KEY,
    domain_id       TEXT REFERENCES domain(domain_id),
    code            TEXT,
    name            TEXT,
    description     TEXT
);
CREATE INDEX idx_member_domain ON member(domain_id);
```

### 5.3 Transformation chain tables (amber group)

```sql
-- Entity-to-entity FK relationships (for graph view edges)
CREATE TABLE cube_relationship (
    cube_relationship_id    TEXT PRIMARY KEY,
    primary_cube_id         TEXT REFERENCES cube(cube_id),
    foreign_cube_id         TEXT REFERENCES cube(cube_id),
    type_of_relationship    TEXT,
    primary_cardinality     TEXT,
    foreign_cardinality     TEXT
);
CREATE INDEX idx_cr_primary ON cube_relationship(primary_cube_id);
CREATE INDEX idx_cr_foreign  ON cube_relationship(foreign_cube_id);

-- Layer-hop transformation rules (WUDEN / DER / GEN)
CREATE TABLE logical_transformation_rule (
    ltr_id                  TEXT PRIMARY KEY,
    source_cube_id          TEXT REFERENCES cube(cube_id),
    destination_cube_id     TEXT REFERENCES cube(cube_id),
    source_layer            TEXT,
    destination_layer       TEXT,
    transformation_type     TEXT,   -- WUDEN / DER / GEN
    algorithm               TEXT
);
CREATE INDEX idx_ltr_source ON logical_transformation_rule(source_cube_id);
CREATE INDEX idx_ltr_dest   ON logical_transformation_rule(destination_cube_id);
```

### 5.4 Legal reference table (gray group)

```sql
-- Regulatory legal basis for BIRD objects (polymorphic: cube or variable)
CREATE TABLE legal_reference (
    legal_text_id   TEXT PRIMARY KEY,
    object_id       TEXT,       -- soft FK: CUBE_ID or VARIABLE_ID (no hard constraint)
    object_type     TEXT,       -- 'CUBE' or 'VARIABLE'
    legal_code      TEXT,
    article         TEXT,
    description     TEXT
);
CREATE INDEX idx_lr_object ON legal_reference(object_id);
```

### 5.5 Primary mapping lookup query

The central query the mapping module calls:

```sql
-- Given Entity Subject (cube name) + Mapping Type (domain data_type), return candidates
SELECT
    c.cube_id,
    c.name          AS entity_name,
    c.cube_type,
    csi.role,
    csi.is_mandatory,
    v.variable_id,
    v.code          AS variable_code,
    v.name          AS variable_name,
    v.description,
    d.name          AS domain_name,
    d.data_type,
    d.is_enumerated
FROM cube c
JOIN cube_structure_item csi ON csi.cube_structure_id = c.cube_structure_id
JOIN variable            v   ON v.variable_id         = csi.variable_id
JOIN domain              d   ON d.domain_id           = v.domain_id
WHERE c.cube_type    = 'LDM'
  AND c.name         ILIKE :entity_subject          -- from Entity Subject deduction
  AND d.data_type    ILIKE :mapping_type_domain      -- from Mapping Type deduction
ORDER BY csi.role, v.name;
-- Role order: D first (context), then O (facts), then A (qualifiers)
-- Returns the full entity context so steward sees PK set + the candidate variable together
```

---

## 6. Interactive data model diagram (additional requirement)

The BIRD KB UI also needs an **interactive expandable data model diagram**, separate from the graph view, showing:

1. **BIRD infrastructure / metadata model** — the SMCube meta-model (Cube → CubeStructureItem → Variable → Domain → Member relationships as an ERD-style diagram)
2. **BIRD Logical Data Model** — the actual LDM entity diagram (entities, relationships, cardinality) rendered as an interactive graph

Both use **vis-network** (already in stack):
- Nodes = entities / tables
- Edges = relationships (labelled with cardinality)
- Click node → detail panel (attributes, description)
- Progressive disclosure: groups first, expand to entities
- Filter by layer using the layer selector tabs

Implementation note: the infrastructure diagram is static (SMCube meta-model doesn't change per BIRD version). The LDM diagram is dynamic (data-driven from `cube` + `cube_relationship` tables).

---

## 7. Loader implementation

**File location:** `knowledge_base/bird/loader/bird_kb_loader.py`

> **Run once after clone, and re-run when a new BIRD release is available and explicitly prompted to do so. Do not run automatically on app start.**

**Source file location:** `knowledge_base/bird/source/BIRDv6.7_DM_Reg_ANC.xlsx`
**Output DB location:** `knowledge_base/bird/data/bird_kb.duckdb` (gitignored)

Example invocation from repo root:
```bash
python knowledge_base/bird/loader/bird_kb_loader.py \
  --multi-framework knowledge_base/bird/source/BIRDv6.7_DM_Reg_ANC.xlsx \
  --db knowledge_base/bird/data/bird_kb.duckdb
```

When AnaCredit Regulatory KB loader is built, it follows the same pattern:
`knowledge_base/anacredit/loader/anacredit_kb_loader.py`

BIRD version: latest-only. Full replace on new release (drop + reload).

---

## 8. Key implementation rules for Copilot

1. **Mirror SMCube language in the store** — table and column names match the source. Translation to plain English happens in the presentation layer (UI labels), not on load.
2. **ROLE codes are D / O / A** — always display in this order: Dimension (PK set) first, then Observation, then Attribute (qualifier). Never display raw codes to the user — translate: D = "Key field", O = "Reported value", A = "Qualifier".
3. **Enumerated flag drives the UI** — if `domain.is_enumerated = true`, show the member code list as expandable. If false, show only the data type.
4. **AnaCredit filter = `framework_id = 'ANCRDT'`** for ROL cubes; `framework_id = 'BIRD'` for LDM/IL input model.
5. **Graph view is vis-network** (already in stack) — `GET /bird/graph?layer=LDM` returns `{nodes: [], edges: []}` JSON shaped for vis-network. Never render all 550+ entities. Max nodes per render: 20.
6. **Transformation chain traversal** — follow `logical_transformation_rule` by `source_cube_id` → `destination_cube_id`, grouping by `transformation_type` (WUDEN then DER then GEN). Display as a linear chain, not a table.
7. **No overclaims** — the KB displays BIRD's rules as reference knowledge. It does not execute them. Pipeline execution is a separate module.
8. **Soft FK on legal_reference** — `object_id` is a TEXT column pointing at either a cube or variable. Do not add a hard FK constraint. Query by joining on `object_id = cube_id` or `object_id = variable_id` with `object_type` discriminating.
9. **NEVS (Null Explanatory Values)** — A-role variables on ROL cubes named NEVS are AnaCredit output-layer reporting conventions (null-value codes). Display them with a "NEV" badge, not as regular attribute qualifiers.
10. **Version column** — the SMCube export carries `VALID_FROM`/`VALID_TO`. Load them to the tables for future versioning support, but filter to latest-only for now (`WHERE valid_to IS NULL OR valid_to > CURRENT_DATE`).

