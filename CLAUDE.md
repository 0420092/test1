# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Steps 1–4 are done, and the issues from the step 4 review are fixed and re-verified. Remaining work: P2 (quantity input UI) and deployment to Streamlit Community Cloud. Planning documents:
- `PRD.md` — product requirements (Korean). It is the source of truth for features, the data model, and acceptance criteria (section 9).
- `PROMPTS.md` — the four-step build plan (1 skeleton → 2 features → 3 UI → 4 Playwright review).

The user writes in Korean. Reply and write UI text in Korean.

## Commands

A Streamlit app in one file (`app.py`), deployed to Streamlit Community Cloud. It needs `streamlit>=1.58` because it uses `width="stretch"`, `st.container(key=)`, and `[theme.light]`/`[theme.dark]`.

```bash
pip install -r requirements.txt
streamlit run app.py                                              # local dev
streamlit run app.py --server.headless true --server.port 8501    # for Playwright testing
```

No test framework or linter. Verification means driving the app with `streamlit.testing.v1.AppTest` (no browser) and with Playwright against PRD section 9. On this Windows console, set `PYTHONIOENCODING=utf-8` so Korean output doesn't crash on cp949.

## Architecture

- **Shared file, re-read every run:** all sessions (tabs and users) share `data/shopping_list.json`. `init_state()` re-reads it on every script run into `st.session_state["items"]`, so changes from other tabs show up on the next interaction.
- **All writes go through `_mutate(change)`:** it takes a process-wide lock (`_file_lock()`, via `st.cache_resource` so it survives reruns), re-reads the file, applies `change(items)`, and saves only if something changed. Never write the session's copy of the list back to the file. That was the step 4 data-loss bug, where one tab overwrote another tab's additions.
- **Layers:** the data functions (`add_item`, `update_item`, `delete_item`, `toggle_item`, `clear_checked`, `clear_all`) wrap `_mutate` and return results or messages. The `on_*` callbacks call them and turn the results into UI feedback. `render_*` functions only draw.
- **Callback feedback:** anything a callback renders ends up at the top of the page. So callbacks queue messages in `session_state` (`flash_warning`, `flash_toast`), and `show_flash_messages()` displays them on the next run.
- **Item shape:** `{id: uuid4 str, name: 1–50 chars, quantity: int = 1, checked: bool, created_at: ISO 8601}`. Display order: unchecked items first, then checked items. Inside each group, sort by `created_at`.

## Rules that are easy to get wrong

- **`st.session_state["items"]`:** always use bracket access. `st.session_state.items` resolves to the dict-like `.items()` method.
- **Checkbox state:** `_render_row` sets `st.session_state[f"check_{id}"]` from the file before creating the checkbox, with no `value=` argument. `on_toggle` sets the checkbox's new value instead of flipping it. Both keep a stale tab from toggling an item the wrong way.
- **Validation (`validate_name`):** strip whitespace, reject empty input and input over 50 characters, and reject a case-insensitive duplicate of an *unchecked* item. The same check runs when unchecking an item. The add input has no `max_chars`; a limit there would silently truncate pastes. Only clear the add input when an add succeeds.
- **Edit row:** it's an `st.form`, so Enter saves. 저장 and 취소 are both `form_submit_button`s.
- **Mobile CSS (`CUSTOM_CSS`):** at widths of 640px or less, Streamlit stacks `st.columns` vertically. The CSS forces `nowrap` and uses `:has()` selectors to give the checkbox and button columns a fixed width (44px touch targets) while the name and input columns take the rest. Ratio-based columns clip the [추가] button at 320px. Check any layout change at 320px.
- **Icon buttons:** the label is "수정" or "삭제" with `icon=`. CSS hides the label visually but screen readers still read it.
- **Displaying names:** markdown escapes don't work inside HTML tags, so `_display_text` HTML-escapes names and converts markdown special characters to numeric entities.
- **Theme:** colors go in `[theme.light]` and `[theme.dark]` in `.streamlit/config.toml`. A color directly under `[theme]` locks the app to light mode. Theme changes need a server restart.
- **Playwright:** select elements with `.st-key-<widget key>` (e.g. `[class*="st-key-del_"]`). Buttons with `help` render a hidden duplicate, so use `button:visible`. Wait for `[data-testid="stStatusWidget"]` to disappear between actions. Typing during a rerun can be wiped.
- **Step 4 review:** report only, with no code changes, using the table format in `PROMPTS.md`. Back up `data/shopping_list.json` before testing and restore it afterward.
