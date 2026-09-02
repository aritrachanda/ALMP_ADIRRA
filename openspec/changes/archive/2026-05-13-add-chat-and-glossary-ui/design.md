# Design — add-chat-and-glossary-ui

## Context

The team is building the chat-orchestrator backend in parallel branches. To avoid blocking the UI track, this change delivers the **UI shell only**. The chat page accepts input and displays a stubbed reply; the glossary page is a fully functional CRUD-over-YAML view that doesn't need any LLM.

Two longer-term constraints shape the design:

1. **Future Django + JS port.** Existing ALM Partners products use Django + plain JS. We should not write business logic inside Streamlit pages — the glossary and chat-history modules must be importable from a non-Streamlit context.
2. **Minimize dependencies.** The team explicitly does not want LangChain / LlamaIndex / heavy frameworks. Streamlit, PyYAML, and stdlib only for this change.

## Goals / Non-Goals

**Goals**
- Restructured left navigation matching the agreed IA.
- Working chat UI shell with persisted conversations (JSON on disk).
- Working business glossary with per-section editing, persisted to YAML.
- Visual fidelity ~90% of the ALM Partners mockups.
- Service modules (`core/glossary.py`, `core/chat_history.py`) free of Streamlit imports.

**Non-Goals**
- Wire up an actual LLM. The reply is a placeholder string.
- Build a real tool/function-calling layer.
- Build content for Dashboard / Active reports / Reporting history / Settings beyond stubs.
- Pixel-perfect parity with the mockups.
- Multi-user or auth concerns.

## Decisions

### D1. Navigation: `st.navigation` dict form

Use `st.navigation({"section": [pages...]})` for grouped section labels. Pros: native, low effort, good enough visually. Cons: section labels aren't clickable parents — clicking "Chat" can't *itself* open the chat page out-of-the-box.

**Workaround:** make the chat page the **first sub-item** under the Chat section and label it `Chat` (or `New chat`). The Mapping / Glossary / Data Catalog / Discovery sub-items follow it. Functionally this matches the agreed Pattern A: opening the Chat section's first item lands you on the chat. We accept that the section header itself isn't clickable.

If a future visual pass wants true expand/collapse parents, we replace `st.navigation` with a custom sidebar — out of scope here.

### D2. Chat persistence: JSON files, write-on-turn

Each conversation is a JSON file in `chat_history/<conversation_id>.json`:

```json
{
  "id": "2026-05-12T08-14-22_a1b2c3",
  "title": "Mapping banking to BIRD",
  "created_at": "2026-05-12T08:14:22Z",
  "updated_at": "2026-05-12T08:16:01Z",
  "messages": [
    {"role": "user", "content": "...", "ts": "..."},
    {"role": "assistant", "content": "...", "ts": "..."}
  ]
}
```

- Each turn is appended and the file is rewritten immediately (write-on-turn, no explicit "save" button).
- The conversation `id` doubles as the filename (filesystem-safe timestamp + short suffix).
- The conversation `title` is auto-derived from the first user message (first ~40 chars) and can be left as-is for v1.
- "Previous conversations" reads the directory, sorts by `updated_at` desc, shows a list. Clicking one loads it into the chat surface.
- Directory `chat_history/` is gitignored.

**Alternative considered:** SQLite. Rejected for v1 — JSON is human-readable, trivial to inspect during demo, zero schema concerns, easier to migrate later.

### D3. Glossary YAML shape: 2–3 levels

```yaml
version: 1
categories:
  - name: Financial
    subcategories:
      - name: Banking
        terms:
          - title: Accounts payable turnover
            business_description: >
              Measures how quickly a company pays off its suppliers.
            detailed_description: >
              ...
            related_objects:
              - Accounts payable
              - Total supplier purchases
          - title: Debt equity ratio
            business_description: ...
            detailed_description: ...
            related_objects: []
  - name: Operational
    # no subcategories — terms hang directly off the category
    terms:
      - title: Member
        business_description: ...
        detailed_description: ...
        related_objects: []
```

Rules:
- A category may have either `subcategories` or `terms` (not both, for clarity in v1).
- A subcategory always has `terms`.
- Term fields: `title` (required), `business_description`, `detailed_description`, `related_objects` (list of strings).
- `related_objects` is free-form strings in v1 (mockup shows them as links, but we don't have a link target yet).

### D4. Glossary editing: per-section

Each of `Title`, `Business description`, `Detailed description`, `Related objects` has its own pencil icon. Clicking a pencil expands that section into an inline editor with `Save` and `Cancel` buttons. Other sections remain in read mode. Save writes the whole `glossary.yaml` back to disk (the file is small enough that whole-file rewrite is fine).

**Why per-section** (vs. whole-pane form mode like the second mockup): user picked it. It also reduces accidental edits and makes the diff in `glossary.yaml` smaller per save.

### D5. Service modules are Streamlit-free

```
core/
  glossary.py        # load_glossary(), save_glossary(), add_term(), update_term(), delete_term(), find_term()
  chat_history.py    # list_conversations(), load_conversation(id), append_message(id, role, content), new_conversation(title)
```

These modules import only stdlib + `yaml`. They take and return plain dicts / dataclasses. Streamlit pages call them; a future Django view can also call them.

### D6. Theming approach

- `.streamlit/config.toml` for primary colors, background, text — Streamlit's first-class theming.
- `ui/assets/styles.css` for sidebar tweaks (deep-navy background, item spacing, icon alignment) and the 3-pane glossary layout. Loaded once in `ui/app.py` via `st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)`.
- Accept that Streamlit version updates may break the CSS; treat it as best-effort polish for the demo.

### D7. Page file layout

```
ui/
  app.py                      # navigation + CSS injection
  assets/
    logo.png                  # existing
    styles.css                # NEW
  pages/
    chat.py                   # NEW — chat shell page
    glossary.py               # NEW — business glossary
    mapping.py                # existing, untouched
    catalog.py                # existing, untouched
    discovery.py              # existing, untouched
    dashboard.py              # NEW stub
    data_input.py             # NEW stub
    data_model.py             # NEW stub
    corrections.py            # NEW stub
    active_reports.py         # NEW stub
    reporting_history.py      # NEW stub
    settings.py               # NEW stub
```

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| `st.navigation` doesn't support clickable parent headers | Accept; first sub-item under Chat acts as the chat page. |
| CSS in Streamlit can break on version upgrades | Keep CSS minimal; only structural / color polish, not layout-critical. |
| JSON conversation files could grow large | Acceptable for demo scale; revisit if a single user has thousands of conversations. |
| Per-section editing means many state flags in the glossary page | Use a single `st.session_state` dict keyed by section name. |
| Whole-file YAML rewrite on every glossary save | File is small (<100KB); fine. Add file lock only if multi-user becomes real. |
| Mockup fidelity gap | Explicit non-goal; demo aims for ~90%. |

## Migration

- Existing users of the Mapping / Discovery / Data Catalog pages will find them under the new Chat section. No data migration required — those pages still read the same catalog YAMLs.
- Existing `pages/*.py` files are kept as-is; only `ui/app.py` changes how they're registered.
- New gitignored directory `chat_history/` is created on first chat use.
