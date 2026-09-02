# Polish Streamlit UI toward Figma DPMM mockups

## Status (revised 2026-05-13)

This change is **scoped down** to what is realistically achievable in Streamlit before the 25 May demo. After implementing the original two passes we hit Streamlit's ceiling: pixel parity with the Figma frames is not achievable, and many structural items (true app top bar, sidebar group expand/collapse, card-as-button cards, custom serif headlines, sticky panels) require fighting the framework with brittle CSS hacks.

Decision: stop investing in fidelity here. The production UI will be a separate Quasar (Vue 3 + TS) frontend talking to a FastAPI backend; see openspec changes `add-fastapi-backend` and `migrate-ui-to-quasar`.

This change retains the items that genuinely help the engineering preview:
- Polished mapping result views (Visualization / Table / Raw with toolbar and SQL preview)
- Three-suggestion-chip chat hero + custom message bubbles
- Glossary tree search, AI assist toggle, top-right Save/Cancel on the New term form
- DPMM token wiring and a navy sidebar with Material icons
- Forced light theme via CSS

The following items are explicitly **deferred to the Quasar port** and removed from scope here:
- Custom navy top app bar (the in-page fake top bar was awkward; reverted to a no-op)
- Sidebar collapsible groups
- Card-as-button suggestion cards (used chip-row instead)
- Pixel-aligned spacing and typography
- Bell/avatar interactivity, breadcrumb, multi-user

## Why

The 25 May demo needs to land close to the agreed ALM Partners DPMM-Ideation Figma mockups (Desktop frames 111–124, plus glossary frames 2887/2914/2922/2939/3202 and CRDM mapping frames 3095/3148/3156). The first pass shipped the right information architecture but kept generic Streamlit chrome; reviewing the live build against the Figma reveals that the chrome itself (top bar, sidebar IA, three-pane layouts) and the structural composition of each page (cards vs. chips, side conversation list, card-graph vs. plain graph) are the dominant gap. This revision targets that gap to the extent Streamlit allows.

## What Changes

### App shell (new)
- Hide the default Streamlit header and render a **navy top app bar** inside the main content area (logo · breadcrumb/page title · bell · avatar+name).
- Restyle `st.navigation` sidebar to the **DPMM navy IA**: Dashboard / Data (with Input data, Data model (CRDM), Corrections under it) / Active reports / Reporting history / Chat / Mapping / Business glossary / Data Catalog / Discovery / Settings, plus Audit log + About the product pinned to the bottom. Group headers are static labels (no animated collapse).
- Provide a reusable **three-pane page layout** (`sidebar | secondary list/tree | main detail`) used by the Glossary and Mapping pages.

### Chat page (Desktop 122/124)
- Replace the 4-pill suggestion row with **3 suggestion cards** (title + one-line subtitle).
- Move the **conversations list to a left side panel** with a search input above it; remove the timestamps and "▸" markers from list items.
- Show the active conversation **title** at the top of the main column.
- Render **user messages** as right-aligned light-blue pill bubbles and **assistant messages** as plain left-aligned text (no avatars).
- Keep `st.chat_input` bottom-pinned (Streamlit-native; floating layout deferred).

### Mapping / Data model (CRDM) page (Desktop 3095/3148/3156)
- Restyle the Visualization tab as a **card-graph**: each table is a card showing table name, "X cols, Y rows", and a confidence pill; edges between cards are colored by confidence; selecting a card highlights its edges.
- Add a **left dataset panel** (single hard-coded entry pointing at the active mapping for the demo).
- Add a **table toolbar** (View columns multiselect, Filter by pipeline, Search) above the Table tab dataframe.
- Wrap the SQL preview in `st.expander("SQL query")`.

### Business Glossary page (Desktop 2887/2914/2922/2939/3202)
- Add a **search input** above the term tree.
- Make the **AI chat panel** visible on both the term-detail view and the New-term form (currently only on Add-new), behind a toggle button "AI assist" so it can be hidden.
- Place **Save / Cancel** at the **top right** of the New-term form (matches Desktop 2939).
- Keep the existing pencil-per-section editor; current behavior already matches Desktop 2914/2922 closely.

### Tokens / CSS
- DPMM tokens are already wired (Section 0 of original tasks). Add a small block of additive classes for: top bar, card-graph node, message bubbles, search input, suggestion cards. Keep additions under ~80 lines total.

### Out of scope (explicit)
- Animated/collapsible sidebar group expansion (`st.navigation` limitation; render as static headers + indented children).
- Floating non-pinned chat input (loses `st.chat_input` UX; deferred).
- Bell / avatar interactivity, Undo/Redo, and any other top-bar action wiring.
- Time-partitioned dataset tree on the Mapping page (use one hard-coded entry).
- Drag-to-rearrange cards in the mapping canvas.
- Real LLM wiring on the glossary AI-assist panel; Desktop 123's streaming-skeleton effect.

## Capabilities

### New Capabilities
- `app-shell`: Navy top bar, restyled sidebar IA, reusable three-pane layout, and the CSS that hides Streamlit's default chrome.
- `mapping-visualization`: Card-graph and tabular views of mapping results (replacing the original generic-graph requirement) including a left dataset panel, confidence-pill nodes, table toolbar, and a collapsed SQL preview.

### Modified Capabilities
- `chat-ui`: Centered hero + 3 suggestion cards on a fresh conversation, conversations list in a left side panel with search, conversation title header, custom message bubble styling.
- `business-glossary`: AI-assist chat panel available on both view and Add-new (toggleable), search above the term tree, Save/Cancel pinned top-right on the New-term form, save-confirmation toast.

## Impact

- **Dependencies**: no additional deps beyond the previously approved `streamlit-agraph`.
- **Affected code**: [ui/app.py](ui/app.py) (top bar, hide default header, navigation IA), [ui/pages/mapping.py](ui/pages/mapping.py), [ui/pages/chat.py](ui/pages/chat.py), [ui/pages/glossary.py](ui/pages/glossary.py), [ui/assets/styles.css](ui/assets/styles.css). No `core/`, agent, or data files touched.
- **Demo target**: 25 May. Scope is bounded to the structural and chrome changes that close the largest visual gap; pixel-perfect parity is explicitly deferred to the future Django/JS port.
