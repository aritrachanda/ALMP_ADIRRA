# Tasks â€” add-chat-and-glossary-ui

## 1. Service modules (Streamlit-free)

- [x] 1.1 Create `core/glossary.py` with: `load_glossary()`, `save_glossary(data)`, `iter_terms()`, `find_term(category, subcategory, title)`, `upsert_term(...)`, `delete_term(...)`. No Streamlit imports.
- [x] 1.2 Create `core/chat_history.py` with: `new_conversation(first_message=None)`, `list_conversations()`, `load_conversation(id)`, `append_message(id, role, content)`, `delete_conversation(id)`. Stores JSON files under `chat_history/`. No Streamlit imports.
- [x] 1.3 Add a constant for the `chat_history/` directory; create the directory lazily on first write.

## 2. Seed data

- [x] 2.1 Create `glossary/` directory.
- [x] 2.2 Create `glossary/glossary.yaml` with ~5â€“10 seed terms across at least two categories and one subcategory level (matching the mockup: Financial â†’ Banking â†’ Accounts payable turnover, Debt equity ratio, Loan-to-deposit ratio, Loans type, Net charge-off ratio, plus Operational â†’ Member, etc.).

## 3. Theming and assets

- [x] 3.1 Create `.streamlit/config.toml` with the ALM Partners palette (deep navy sidebar, white content, accent color).
- [x] 3.2 Create `ui/assets/styles.css` with sidebar spacing, section-header styling, and 3-pane glossary helper classes.
- [x] 3.3 In `ui/app.py`, load `styles.css` once on startup and inject via `st.markdown(..., unsafe_allow_html=True)`.

## 4. Navigation restructure

- [x] 4.1 In `ui/app.py`, replace the flat `st.navigation([mapping, discovery, catalog])` with the grouped dict form matching the agreed IA.
- [x] 4.2 Confirm sub-items render with section headers: Dashboard, Data, Active reports, Reporting history, Chat, Settings.
- [x] 4.3 Verify the existing `pages/mapping.py`, `pages/catalog.py`, `pages/discovery.py` are reachable under the Chat section.

## 5. Stub pages

- [x] 5.1 Create `pages/dashboard.py` â€” title + "Coming soon".
- [x] 5.2 Create `pages/data_input.py` â€” title + "Coming soon".
- [x] 5.3 Create `pages/data_model.py` â€” title + "Coming soon".
- [x] 5.4 Create `pages/corrections.py` â€” title + "Coming soon".
- [x] 5.5 Create `pages/active_reports.py` â€” title + "Coming soon".
- [x] 5.6 Create `pages/reporting_history.py` â€” title + "Coming soon".
- [x] 5.7 Create `pages/settings.py` â€” title + "Coming soon".

## 6. Chat page

- [x] 6.1 Create `pages/chat.py` with a centered hero greeting and `st.chat_input`.
- [x] 6.2 Render conversation turns with `st.chat_message`, sourced from `chat_history.load_conversation(current_id)`.
- [x] 6.3 On user submit: append user turn via `append_message`, append a stub assistant turn ("Orchestrator not connected yet â€” your message was: â€¦"), rerun.
- [x] 6.4 Add a "Previous conversations" section listing entries from `list_conversations()` sorted by `updated_at` desc; clicking loads that conversation into the active surface.
- [x] 6.5 Add a "New chat" button that calls `new_conversation()` and resets the active surface.
- [x] 6.6 Persist active conversation ID in `st.session_state`.

## 7. Business glossary page

- [x] 7.1 Create `pages/glossary.py` with a 3-column layout (`st.columns([1, 2, 4])` or CSS-assisted equivalent) â€” actually a 2-column inside the page since Streamlit's sidebar is the outer column.
- [x] 7.2 Left panel: search box, "Add new +" button, expandable tree of categories â†’ subcategories â†’ terms. Selected term stored in `st.session_state`.
- [x] 7.3 Right panel: read-mode display of `Title`, `Business description`, `Detailed description`, `Related objects`, each with a pencil icon button.
- [x] 7.4 Per-section edit: clicking a pencil sets a session-state flag for that section; the section renders an inline editor with Save / Cancel.
- [x] 7.5 Save: call `glossary.upsert_term(...)` then `save_glossary(...)`, clear the section's edit flag, rerun.
- [x] 7.6 "Add new +" opens an empty term form on the right with category/subcategory pickers.
- [x] 7.7 Search filters the tree by case-insensitive substring match on term titles.

## 8. Housekeeping

- [x] 8.1 Add `chat_history/` to `.gitignore`.
- [x] 8.2 Update `README.md` with a short note on the new navigation and where the glossary lives.
- [x] 8.3 Smoke test: launch `streamlit run ui/app.py`, click every nav item, create a chat turn, edit a glossary section, restart the app, confirm both persisted.
