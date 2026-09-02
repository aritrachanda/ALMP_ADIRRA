# Design — polish-ui-to-figma

## Context

The product currently runs on Streamlit with the IA delivered by `add-chat-and-glossary-ui` (now archived). The 25 May demo needs to feel like the ALM Partners DPMM-Ideation Figma design (Desktop frames 111–124) without leaving Streamlit. The Figma file uses generic kits (Material 3 / Simple Design System) lightly skinned — there is no proprietary component library to clone, only a small set of patterns to approximate.

The team has agreed: one new Python dependency is acceptable; emoji is acceptable in lieu of bespoke pill components; clickable parent nav items and a custom top bar are deferred. The future Django/JS port will own pixel-perfect parity.

## Goals / Non-Goals

**Goals:**
- Demo-ready by 25 May. Scope fits inside one week.
- Visual fidelity ~85% on the three highest-impact screens: Mapping (Desktop 119–121), Chat (Desktop 122/124), Business Glossary (Desktop 111–114).
- One new dependency only: `streamlit-agraph`.
- All polish lives in `ui/`; no `core/` or agent code touched.
- CSS additions stay small and additive — easy to remove or restyle.

**Non-Goals:**
- Replacing `st.navigation` with a custom sidebar.
- Building a real top bar / breadcrumb / user chip.
- Wiring an actual LLM into the glossary AI-assist panel.
- Reproducing Desktop 123's streaming-skeleton text effect.
- Pixel-perfect parity with Figma.
- Multi-user, auth, sharing.

## Decisions

### D1. Graph library: `streamlit-agraph`

Picked over `pyvis` and `streamlit-flow`:
- Native Streamlit component — declarative `Node`/`Edge`/`Config`, ~5 lines to render, ~10 to wire click events.
- `pyvis` renders as an iframe via `st.components.v1.html`; click events don't return to Python without glue.
- `streamlit-flow` is newer/nicer but smaller community and more API surface.
- License MIT. Last release 2023 — stable enough for a demo.

Adds `streamlit-agraph` to `requirements.txt`. No version pin beyond `>=0.0.45` to avoid surprise breakage.

### D2. Mapping page layout: tabs

Keep the existing Mapping page header (source/target selector, run button, status). Below, replace the per-candidate expander wall with a `st.tabs(["Visualization", "Table", "Raw"])`:
- **Visualization** — `streamlit-agraph` graph. Source tables on the left, target tables on the right; edges colored by confidence (🟢/🟡/🔴 → green/yellow/red).
- **Table** — single `st.dataframe` aggregating *all accepted/pending* column mappings across candidates: source schema/table/column, target schema/table/column, confidence (emoji + value), rationale, status. Sortable, filterable.
- **Raw** — the existing expander/data-editor flow, kept intact for accept/discard workflow. Demo-safe fallback.

This avoids ripping out the working accept/discard editor while delivering the Figma look on the default tab.

### D3. Confidence pills via emoji

Three buckets, mapped from the agent's float `confidence`:
- `>= 0.7` → 🟢 high
- `0.4–0.69` → 🟡 medium
- `< 0.4` → 🔴 low

Used in the table column, in graph edge colors, and in the glossary if needed. No HTML pill components — keeps CSS surface small.

### D4. SQL preview

Below the Table tab, add a `st.code(..., language="sql")` block showing a generated `SELECT` that joins source columns into target column names (one row per accepted mapping). Mirrors Desktop 121's lower-right panel. It's a *preview*, not executed — purely visual / copy-paste aid.

### D5. Chat hero state

Detect "fresh conversation" as: no messages yet in the active conversation. When fresh:
- Render a centered hero (`# Hello! What can I help you with?`).
- Render a row of 3–5 suggestion chips as `st.button`s in a horizontal `st.columns` layout. Clicking a chip stuffs the chip text into `st.session_state["chat_input_prefill"]` and reruns; the chat input reads and clears that key on next render.

Once the conversation has at least one turn, the hero collapses and `st.chat_input` behaves as today.

Suggestion chip texts (initial set, easy to change):
- "Map banking source to BIRD"
- "Show me unmapped columns"
- "Explain the CRDM model"
- "Find tables with low confidence"

### D6. Glossary AI-assist side panel (stub)

On the New term form (today's "Add new +"), wrap the form in `st.columns([3, 2])`:
- Left = the existing form fields.
- Right = a small chat surface labeled "AI assist", reusing `st.chat_input` and `st.chat_message`. Submitting a prompt appends a user turn and a stubbed assistant turn ("AI assist not connected yet — your message was: …") to a *separate* in-memory list (not persisted, not in `chat_history/`). State scoped per-page-session.

This is purely visual. The wiring contract for a future agent: assistant text replaces the form field values when the user clicks an "Apply" button (out of scope; tracked in tasks as a comment, not built).

### D7. CSS additions

`ui/assets/styles.css` gains a small additive block. Targets:
- `.dpmm-chip-row` — flex row used by chat suggestion chips.
- `.dpmm-section-divider` — slimmer hr for glossary sections.
- `.dpmm-hero` — center-aligned hero block on the chat page.

No rewrites of existing styles, no `!important` chains. If a Streamlit upgrade nukes one of these, the page degrades gracefully (just visual, nothing functional breaks).

### D8. Save toasts

Glossary save and mapping accept/discard already write back to disk silently. Add `st.toast("Saved.")` on each. Cheap; matches the design's snappy feedback feel.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| `streamlit-agraph` last released 2023 — could break with newer Streamlit | Keep the Visualization tab as one of three; users can fall back to Table or Raw. Pin only loose `>=`. |
| Emoji pills look less polished than HTML pills | Accepted; team OK'd it. Trivial to swap later. |
| Chat suggestion chips need `st.session_state` plumbing to prefill input | Use a single key (`chat_input_prefill`) read-and-clear pattern. Well-understood Streamlit idiom. |
| AI-assist stub could mislead a viewer into thinking it works | Label the assistant bubble explicitly: "AI assist not connected yet". |
| Tabs change muscle memory for anyone who's used the Raw editor | Keep "Raw" as the third tab; default is Visualization but Raw is one click away. |
| New dep slows `pip install` | Negligible; `streamlit-agraph` is small. |
| CSS drift on Streamlit upgrade | Already accepted in prior change; this change adds <30 lines of additive CSS. |

## Migration

- Add `streamlit-agraph` to `requirements.txt`; users re-run `pip install -r requirements.txt`.
- No data migration. Mappings, glossary, chat history files unchanged.
- No breaking changes to `core/` or `agents/` APIs.
- Rollback: revert the change branch; the archived `add-chat-and-glossary-ui` UI continues to work.

## Open Questions

- Suggestion chip texts are placeholder — confirm with stakeholders before demo day or accept current set.
- Should the SQL preview reflect *only accepted* mappings or *accepted + pending*? Default: accepted only; revisit during smoke test.
