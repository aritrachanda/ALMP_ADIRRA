# Tasks — polish-ui-to-figma

## 0. Design tokens (from DPMM Component library)

- [x] 0.1 Replace placeholder palette in [.streamlit/config.toml](.streamlit/config.toml) with DPMM tokens: `primaryColor = "#0d4da1"` (Primary/Main), `backgroundColor = "#fdfdfd"` (White/Background), `secondaryBackgroundColor = "#f7f7f7"` (White/Light grey), `textColor = "#2b2a31"` (Black/Text).
- [x] 0.2 Expose tokens as CSS variables (`--dpmm-primary`, `--dpmm-primary-hover`, `--dpmm-primary-light`, `--dpmm-text`, `--dpmm-grey`, `--dpmm-dark-grey`, `--dpmm-shadow`) at the top of [ui/assets/styles.css](ui/assets/styles.css) and re-use them in existing rules where they apply.

## 1. Dependency

- [x] 1.1 Add `streamlit-agraph>=0.0.45` to [requirements.txt](requirements.txt).
- [x] 1.2 Run `pip install -r requirements.txt` in the project venv and confirm import works (`python -c "import streamlit_agraph"`).

## 2. Mapping page — visualization tab

- [x] 2.1 In [ui/pages/mapping.py](ui/pages/mapping.py), wrap the existing results section in `st.tabs(["Visualization", "Table", "Raw"])`. Keep the source/target selector, dataset context, and Run button above the tabs.
- [x] 2.2 Implement a helper `build_graph(mapping)` that returns `(nodes, edges)` for `streamlit-agraph`: source tables on one side, target tables on the other; one edge per non-discarded column mapping.
- [x] 2.3 Bucket confidence into 🟢 (≥0.7) / 🟡 (0.4–0.69) / 🔴 (<0.4); use these as edge colors (`#22c55e`, `#eab308`, `#ef4444`).
- [x] 2.4 Render the graph with `streamlit_agraph.agraph(nodes, edges, Config(width=..., height=550, directed=True, physics=True, hierarchical=False))`.
- [x] 2.5 Show an empty-state message ("Run the agent to see a graph.") if no mapping is loaded.

## 3. Mapping page — table tab

- [x] 3.1 Implement `flatten_mapping(mapping)` returning a list of dicts (one per non-discarded column mapping) with: source schema/table/column, target schema/table/column, confidence, status, rationale.
- [x] 3.2 Render as `st.dataframe` with sorting enabled. Add a `confidence_label` column combining numeric value and the bucket emoji.
- [x] 3.3 Below the table, render an SQL preview block using `st.code(sql, language="sql")`. Generate `SELECT <src_col> AS <tgt_col>, ... FROM <src_table>` per accepted source table; show `-- Accept mappings to generate SQL` when no rows are accepted.

## 4. Mapping page — raw tab

- [x] 4.1 Move the existing per-candidate expander/data-editor block into the "Raw" tab without behavior changes.
- [x] 4.2 Verify accept/discard/reset buttons and inline column edits still write to `mappings/<source>_to_<target>.yaml`.
- [x] 4.3 Add `st.toast("Saved.")` after each successful save in this tab.

## 5. Chat page — hero + suggestion chips

- [x] 5.1 In [ui/pages/chat.py](ui/pages/chat.py), detect "fresh conversation" as no messages in the active conversation.
- [x] 5.2 When fresh, render a centered hero (`# Hello! What can I help you with?`) using a `dpmm-hero` CSS class.
- [x] 5.3 Render a row of 4 suggestion chips below the hero using `st.columns(4)` with `st.button` per chip. Initial chip texts: "Map banking source to BIRD", "Show me unmapped columns", "Explain the CRDM model", "Find tables with low confidence".
- [x] 5.4 On chip click, set `st.session_state["chat_input_prefill"] = chip_text` and `st.rerun()`.
- [x] 5.5 Read-and-clear the prefill key when rendering `st.chat_input`. Confirm the prefilled text appears as a default value the user can edit. _(Implemented as a textarea + Send button, since `st.chat_input` has no `value=` parameter; the user can edit the chip text before sending.)_
- [x] 5.6 Once the conversation has ≥1 message, hide the hero and chip row but keep the input.

## 6. Glossary page — AI-assist stub

- [x] 6.1 In [ui/pages/glossary.py](ui/pages/glossary.py), in the "Add new +" branch, wrap the form in `st.columns([3, 2])`.
- [x] 6.2 In the right column, render a header "AI assist", an `st.chat_input(key="glossary_ai_assist_input")`, and a list of turns from `st.session_state["glossary_ai_assist_turns"]` (initialize to `[]`).
- [x] 6.3 On submit, append a user turn and a stubbed assistant turn ("AI assist not connected yet — your message was: …") to that session-state list. Do NOT call `core/chat_history.py`.
- [x] 6.4 Confirm the panel does not render outside the New term form (i.e. when a term is selected for view/edit).

## 7. Glossary page — save toasts

- [x] 7.1 After every successful section save and successful "Add new +" save in [ui/pages/glossary.py](ui/pages/glossary.py), call `st.toast("Saved.")`.
- [x] 7.2 On `Exception` from `save_glossary(...)`, render `st.error(...)` and keep the section in edit mode with the user's input preserved.

## 8. CSS additions

- [x] 8.1 In [ui/assets/styles.css](ui/assets/styles.css), add `.dpmm-hero` (centered, top margin), `.dpmm-chip-row` (flex/gap), `.dpmm-section-divider` (thinner hr) classes. Keep additions under ~30 lines.
- [x] 8.2 Verify [ui/app.py](ui/app.py) still injects the CSS at startup and the new classes are reachable on the chat and glossary pages.

## 9. Smoke test (manual) — first pass

- [x] 9.1 Launch `streamlit run ui/app.py`; click every nav item, no errors.
- [x] 9.2 On Mapping with an existing `mappings/banking_to_bird.yaml`: switch through Visualization / Table / Raw; confirm graph renders, table sorts, SQL preview appears for accepted rows, Raw tab still accepts/discards.
- [x] 9.3 On Chat: confirm hero + 4 chips appear on a new conversation; click a chip, edit, submit; confirm hero collapses and the conversation persists across restart.
- [x] 9.4 On Glossary: open "Add new +"; confirm AI-assist panel renders, accepts input, shows stub reply; confirm `chat_history/` is NOT modified by AI-assist activity. Edit a section on an existing term; confirm save toast appears and `glossary/glossary.yaml` updates.
- [x] 9.5 Restart the app; confirm chat history and glossary edits persist; AI-assist turns reset (expected — session-scoped).

## 10. App shell — top bar + sidebar IA + hide default chrome

- [x] 10.1 In [ui/assets/styles.css](ui/assets/styles.css) add rules to hide `[data-testid="stHeader"]` and zero out the top padding on `[data-testid="stAppViewContainer"] > .main`.
- [x] 10.2 In [ui/app.py](ui/app.py) add a `render_top_bar(page_title: str)` helper that injects an HTML block: navy background, ALMPARTNERS logo on the left, page title in the center-left, bell + avatar+name on the right. Call it at the top of every page render.  _(Helper lives in `ui/chrome.py`; called from every page.)_
- [x] 10.3 Restyle the sidebar via existing `section[data-testid="stSidebar"]` rules to ensure group captions ("Data", "Reports", "Chat", "Settings") render as small uppercase labels and active items use `--dpmm-navy-active`.
- [x] 10.4 In [ui/app.py](ui/app.py) reorganize `st.navigation` into the IA: Dashboard / Data {Input data, Data model (CRDM), Corrections} / Reports {Active reports, Reporting history} / Chat {Chat, Mapping, Business glossary, Data Catalog, Discovery} / Settings {Settings} / pinned bottom {Audit log, About the product}. Use `Page` titles to convey hierarchy (e.g. indent child names with leading "└ " or simply group via dict keys).
- [x] 10.5 Add CSS rules to push the "Audit log" and "About the product" links to the bottom of the sidebar (`margin-top: auto` on a wrapper; or absolute-position via a pinned div).  _(Implemented as a separate " " group at the end of `st.navigation`; ordered last.)_
- [x] 10.6 Add `.dpmm-three-pane` helper (display: grid; grid-template-columns: 1fr 3fr) used by glossary and mapping pages, OR simply use `st.columns([1, 3])` consistently — pick whichever survives Streamlit reruns better.  _(Used `st.columns` per page.)_

## 11. Chat page — structural redesign (Desktop 122/124)

- [x] 11.1 In [ui/pages/chat.py](ui/pages/chat.py) split the page into `left, main = st.columns([1, 3], gap="medium")`.  _(Used `gap="large"`.)_
- [x] 11.2 In `left`: render `st.text_input("Search", placeholder="Search…", key="chat_search")`, then `st.button("+ New conversation", use_container_width=True, on_click=_start_new)`, then a flat list of previous conversations as link-styled buttons (no timestamps, no "▸").
- [x] 11.3 Filter the conversations list by the search input (case-insensitive substring match against `convo.title`).
- [x] 11.4 In `main`: when fresh, render the centered hero (existing) and **3 suggestion cards** in `st.columns(3)`. Replace `_SUGGESTION_CHIPS` with a list of 3 `(title, subtitle)` tuples: `("Map banking source to BIRD", "Suggested action")`, `("Show me unmapped columns for CRDM", "Suggested action")`, `("Explain the BIRD model", "Suggested conversation")`.
- [x] 11.5 Style each card as a CSS `.dpmm-suggestion-card` with title (bold) and subtitle (muted). Implement card-as-button via `st.button` with help text or a labeled HTML+button hack; clicking sets the prefill (existing flow).  _(HTML card + a small "Use" button under each card.)_
- [x] 11.6 When a conversation is active, render the conversation title at the top of `main` (`st.subheader(convo.title)`).
- [x] 11.7 Replace `st.chat_message` rendering with a custom HTML block: user turns → right-aligned light-blue rounded pill (`.dpmm-msg-user`); assistant turns → plain left-aligned text (`.dpmm-msg-assistant`).
- [x] 11.8 Keep `st.chat_input` bottom-pinned. Confirm chip-prefill still works (existing textarea fallback OK).

## 12. Glossary page — search, AI toggle, top-right Save/Cancel

- [x] 12.1 In [ui/pages/glossary.py](ui/pages/glossary.py) add an `st.text_input("Search", key="glossary_search")` above the term tree in the secondary panel.  _(Already shipped earlier; verified.)_
- [x] 12.2 Filter the tree items by the search text (case-insensitive substring on title).  _(Already shipped earlier; verified.)_
- [x] 12.3 Add a session state key `glossary_ai_assist_open: False` and an "AI assist" toggle button visible on **both** the term-detail view and the New-term form. When True, render the AI-assist panel as the rightmost column.
- [x] 12.4 Refactor the page to a 3-column layout when the AI panel is open: `[1, 2, 2]` (tree | detail | AI panel); when closed: `[1, 4]` (tree | detail).
- [x] 12.5 On the New-term form, move Save and Cancel buttons to the top-right of the detail column using `st.columns([6, 1, 1])` and rendering them in the right two cells.

## 13. Mapping page — card-graph, dataset panel, table toolbar, collapsed SQL

- [x] 13.1 In [ui/pages/mapping.py](ui/pages/mapping.py) split the page: `dataset_col, main_col = st.columns([1, 4])`. In `dataset_col` render a header "Datasets" and a single button labeled e.g. "banking → BIRD" (hard-coded for the demo) that activates the current mapping.  _(Used `[1, 5]` for breathing room; dataset button reflects active source→target.)_
- [x] 13.2 Update `_build_graph` to set node labels combining table name + a "X cols, Y rows" caption (use the loaded source/target catalog if available; fall back to mapping data). Keep node colors as per current design.
- [x] 13.3 Pass `Config(..., nodeHighlightBehavior=True, highlightColor="#0c56b7")` so card selection highlights incident edges (already partly configured; verify on smoke test).
- [x] 13.4 Above the Table tab dataframe add a 3-column toolbar: `view_cols = st.multiselect("View columns", ALL_COLS, default=DEFAULT_COLS)`; `pipeline = st.selectbox("Filter by pipeline", ["All"] + unique_source_tables)`; `search = st.text_input("Search", placeholder="Search…")`. Apply all three before rendering the dataframe.
- [x] 13.5 Wrap the SQL preview in `with st.expander("SQL query", expanded=False):` and keep the existing `st.code(..., language="sql")` inside.

## 14. Smoke test — second pass

- [ ] 14.1 Restart the app. Confirm the navy top bar is visible on every page and the default Streamlit header is hidden.
- [ ] 14.2 Confirm sidebar shows grouped IA, navy palette, "About the product" pinned bottom.
- [ ] 14.3 Chat: left conversations panel + search + "+ New conversation" + 3 cards on fresh; user/assistant bubbles render distinctly; conversation title appears once a turn exists.
- [ ] 14.4 Glossary: search filters tree; AI assist toggle shows/hides panel on both view and New term; Save/Cancel are top-right on New term form.
- [ ] 14.5 Mapping: left dataset panel renders; card-graph shows captions and confidence pills; selecting a card highlights edges; Table tab toolbar (View columns / Filter by pipeline / Search) filters correctly; SQL preview lives inside a collapsed expander.
