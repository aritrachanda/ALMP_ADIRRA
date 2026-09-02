# Add Chat shell and Business Glossary UI

## Why

The product is moving toward a **chat-as-orchestrator** experience: users will eventually drive everything (mappings, discovery, reporting) through a single conversational entry point. The conversational backend is being built in parallel branches and will be merged later.

To unblock that work and align the product with the agreed information architecture (mockups in `business_glossary_UI_layout.png`, `business_glossary_UI_layout_edit.png`, `bark_reference.png`), we need to:

1. Restructure the left navigation to match the target IA (Dashboard, Data ▾, Active reports, Reporting history, Chat ▾, Settings).
2. Add a **Chat** page as the parent of the Chat section — a clean, BARK-inspired shell that captures user prompts, displays a running conversation, and lists previous conversations. The bot reply is stubbed for now; the orchestrator will be wired in later via merge.
3. Add a **Business Glossary** page — a 3-pane (sidebar + tree + detail) view backed by `glossary/glossary.yaml` with per-section editing (Save/Cancel per field group).
4. Move the existing Mapping, Data Catalog, and Discovery pages under the Chat section as "state of things" sub-pages.
5. Add lightweight stub pages for Dashboard, Data ▾ (Input data, Data model, Corrections), Active reports, Reporting history, and Settings so the navigation feels complete.

This is a **UI-only** change. No LLM wiring, no orchestrator tools, no new Python dependencies. Visual target is roughly 90% fidelity to the ALM Partners mockups; pixel-perfect parity is deferred to the eventual Django/JS rewrite.

## What Changes

### Navigation (breaking change for end users)

Replaces the current flat `Mapping / Discovery / Data Catalog` navigation with a grouped sidebar:

```
📊 Dashboard                    [stub]
📁 Data                  ▾
   Input data                   [stub]
   Data model (CRDM)            [stub]
   Corrections                  [stub]
📋 Active reports               [stub]
🕐 Reporting history            [stub]
💬 Chat                  ▾      ← parent opens chat page
   Mapping                      ← existing pages/mapping.py
   Business glossary            ← NEW
   Data Catalog                 ← existing pages/catalog.py
   Discovery                    ← existing pages/discovery.py
⚙  Settings                     [stub]
```

### New capabilities

- **Chat shell page** — centered hero greeting, single chat input, conversation history rendered with `st.chat_message`, "previous conversations" list. Conversations persisted to a JSON file (one entry per turn, written immediately). Bot replies are placeholders ("Orchestrator not connected yet…").
- **Business Glossary page** — 3-pane layout: search/tree on the left (categories → optional subcategories → terms), term detail on the right. Per-section pencil icons for Title, Business description, Detailed description, Related objects; each section edits independently with its own Save/Cancel. "Add new +" creates an empty term in the currently selected category. Edits persist to `glossary/glossary.yaml`.
- **`core/glossary.py`** — UI-agnostic Python service for loading, querying, mutating, and saving the glossary. No Streamlit imports — written so a future Django port can call the same module.
- **`core/chat_history.py`** — UI-agnostic Python service for reading/writing chat conversations to a JSON file under `chat_history/`.
- **Theming** — `.streamlit/config.toml` themed to ALM Partners palette (deep navy sidebar, white content); a small `ui/assets/styles.css` injected at app start for sidebar polish, icons, and spacing.
- **Seed data** — `glossary/glossary.yaml` populated with ~5–10 example terms matching the mockup (Financial → Banking → Accounts payable turnover, Debt equity ratio, Loan-to-deposit ratio, etc.).

### Stub pages

Each stub is ~5 lines: a title, one-line description, and an `st.info("Coming soon")`.

### Out of scope

- LLM / orchestrator wiring (separate branches, merge later).
- Tool layer / function calling.
- Real content for Dashboard, Active reports, Reporting history, Settings.
- Migration off Streamlit.
- Auth, multi-user, conversation sharing.

## Impact

**Affected specs**

- `ui-navigation` (NEW) — describes the sidebar structure and routing.
- `chat-ui` (NEW) — describes the chat shell page and conversation persistence.
- `business-glossary` (NEW) — describes the glossary data model, page layout, and editing semantics.

**Affected code**

- `ui/app.py` — replace flat navigation with grouped `st.navigation`, inject CSS.
- `ui/pages/` — add `chat.py`, `glossary.py`, plus stub pages (`dashboard.py`, `data_input.py`, `data_model.py`, `corrections.py`, `active_reports.py`, `reporting_history.py`, `settings.py`). Existing `mapping.py`, `catalog.py`, `discovery.py` remain untouched.
- `core/glossary.py` (NEW) — glossary load/save service.
- `core/chat_history.py` (NEW) — chat persistence service.
- `glossary/glossary.yaml` (NEW) — seed glossary.
- `chat_history/` (NEW directory, gitignored) — conversation JSON files.
- `.streamlit/config.toml` (NEW) — theme.
- `ui/assets/styles.css` (NEW) — small CSS polish.
- `.gitignore` — add `chat_history/`.

**No new Python dependencies.** Uses only Streamlit, PyYAML, and stdlib (`json`, `pathlib`, `uuid`, `datetime`).
