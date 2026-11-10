"""쇼핑 리스트 앱 (Streamlit).

PRD.md 기준. 추가/수정/삭제/체크 + 진행 현황 + 일괄 정리 + JSON 저장.

데이터 흐름
- 모든 세션(탭·사용자)이 data/shopping_list.json 하나를 공유한다.
- 화면을 그릴 때마다 파일을 새로 읽어 st.session_state["items"]에 둔다.
- 변경은 _mutate()로만 한다. 프로세스 공용 락을 잡은 채 파일을 다시 읽고 →
  바꾸고 → 저장하므로, 다른 탭의 변경을 덮어쓰지 않는다.

버튼과 체크박스는 on_click / on_change 콜백으로 처리해 클릭 한 번에 반영된다.
콜백에서 보여줄 경고/알림은 session_state에 넣어 두었다가 main()에서 표시한다.
"""

import html
import json
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

import streamlit as st

DATA_FILE = Path(__file__).parent / "data" / "shopping_list.json"
MAX_NAME_LENGTH = 50

# 주의: st.session_state.items 는 dict의 .items() 메서드로 해석되므로
# 반드시 st.session_state["items"] 로 접근한다.
ITEMS = "items"


# ---------------------------------------------------------------------------
# 파일 저장소
# ---------------------------------------------------------------------------

@st.cache_resource
def _file_lock() -> threading.Lock:
    """모든 세션이 공유하는 파일 락. 스크립트가 다시 실행돼도 같은 객체를 쓴다."""
    return threading.Lock()


def _normalize_item(raw) -> dict | None:
    """파일에서 읽은 아이템 하나를 검사해 올바른 형태로 맞춘다. 쓸 수 없으면 None."""
    if not isinstance(raw, dict):
        return None
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    quantity = raw.get("quantity", 1)
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
        quantity = 1
    return {
        "id": str(raw.get("id") or uuid.uuid4()),
        "name": name.strip()[:MAX_NAME_LENGTH],
        "quantity": quantity,
        "checked": bool(raw.get("checked", False)),
        "created_at": str(raw.get("created_at") or datetime.now().isoformat(timespec="seconds")),
    }


def load_items() -> list[dict]:
    """data/shopping_list.json에서 아이템 목록을 읽는다. 락을 잡은 상태에서 호출한다.

    파일이 없거나 손상된 경우(빈 파일, 잘못된 JSON, 리스트가 아님) 빈 리스트를 반환한다.
    형식이 잘못된 아이템은 건너뛰고, id가 겹치면 뒤의 것을 버린다.
    """
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except ValueError:  # 손상된 JSON
        return []
    if not isinstance(data, list):
        return []

    items, seen_ids = [], set()
    for raw in data:
        item = _normalize_item(raw)
        if item and item["id"] not in seen_ids:
            seen_ids.add(item["id"])
            items.append(item)
    return items


def save_items(items: list[dict]) -> None:
    """아이템 목록을 data/shopping_list.json에 UTF-8로 저장한다. 락을 잡은 상태에서 호출한다.

    임시 파일에 먼저 쓴 뒤 교체해서, 저장 도중 앱이 멈춰도 파일이 깨지지 않게 한다.
    """
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = DATA_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(DATA_FILE)


def _read_latest() -> list[dict]:
    """락을 잡고 파일의 최신 목록을 읽는다."""
    with _file_lock():
        return load_items()


def _mutate(change: Callable[[list[dict]], tuple[bool, object]]):
    """파일의 최신 목록에 change를 적용하고, 바뀐 경우에만 저장한다.

    change(items)는 리스트를 직접 고치고 (변경 여부, 돌려줄 값)을 반환한다.
    읽기·변경·저장 전체를 락 안에서 하므로 다른 세션의 변경을 덮어쓰지 않는다.
    """
    with _file_lock():
        items = load_items()
        changed, result = change(items)
        if changed:
            try:
                save_items(items)
            except OSError:
                _flash_warning("저장에 실패했어요. 잠시 후 다시 시도해 주세요.")
                return result
    st.session_state[ITEMS] = items
    return result


# ---------------------------------------------------------------------------
# 데이터 처리 (모두 _mutate를 통해 파일 최신 내용 기준으로 동작)
# ---------------------------------------------------------------------------

def validate_name(
    name: str, items: list[dict], exclude_id: str | None = None
) -> tuple[bool, str]:
    """아이템 이름을 검증한다.

    Args:
        name: 앞뒤 공백이 제거된 이름.
        items: 중복 검사 대상 목록 (파일의 최신 목록).
        exclude_id: 중복 검사에서 제외할 아이템 id (수정·체크 해제 시 자기 자신).

    Returns:
        (통과 여부, 실패 시 사용자에게 보여줄 메시지)
    """
    if not name:
        return False, "아이템 이름을 입력해 주세요."
    if len(name) > MAX_NAME_LENGTH:
        return False, f"아이템 이름은 {MAX_NAME_LENGTH}자까지 입력할 수 있어요. (현재 {len(name)}자)"

    key = name.casefold()
    for item in items:
        if item["id"] != exclude_id and not item["checked"] and item["name"].casefold() == key:
            return False, f"'{item['name']}'은(는) 이미 살 것 목록에 있어요."
    return True, ""


def _find(items: list[dict], item_id: str) -> dict | None:
    return next((i for i in items if i["id"] == item_id), None)


MISSING = "다른 화면에서 이미 삭제된 아이템이에요."


def add_item(name: str, quantity: int = 1) -> tuple[bool, str]:
    """새 아이템을 목록 끝에 추가한다. (성공 여부, 실패 메시지)를 반환한다."""
    def change(items):
        ok, message = validate_name(name, items)
        if ok:
            items.append({
                "id": str(uuid.uuid4()),
                "name": name,
                "quantity": quantity,
                "checked": False,
                "created_at": datetime.now().isoformat(timespec="microseconds"),
            })
        return ok, (ok, message)
    return _mutate(change)


def update_item(item_id: str, new_name: str) -> tuple[bool, str]:
    """아이템 이름을 수정한다. (성공 여부, 실패 메시지)를 반환한다."""
    def change(items):
        item = _find(items, item_id)
        if not item:
            return False, (False, MISSING)
        ok, message = validate_name(new_name, items, exclude_id=item_id)
        if ok:
            item["name"] = new_name
        return ok, (ok, message)
    return _mutate(change)


def delete_item(item_id: str) -> str | None:
    """아이템을 삭제한다. 삭제한 아이템 이름을 반환한다 (없으면 None)."""
    def change(items):
        item = _find(items, item_id)
        if not item:
            return False, None
        items.remove(item)
        return True, item["name"]
    return _mutate(change)


def toggle_item(item_id: str, checked: bool) -> str | None:
    """아이템의 구매 완료 상태를 checked로 맞춘다. 실패 시 메시지를 반환한다.

    체크를 해제할 때 같은 이름의 미완료 아이템이 이미 있으면 중복이 되므로 막는다.
    """
    def change(items):
        item = _find(items, item_id)
        if not item:
            return False, MISSING
        if item["checked"] == checked:
            return False, None
        if not checked:
            ok, message = validate_name(item["name"], items, exclude_id=item_id)
            if not ok:
                return False, message
        item["checked"] = checked
        return True, None
    return _mutate(change)


def clear_checked() -> int:
    """체크된 아이템을 모두 삭제하고 삭제한 개수를 반환한다."""
    def change(items):
        before = len(items)
        items[:] = [i for i in items if not i["checked"]]
        removed = before - len(items)
        return removed > 0, removed
    return _mutate(change)


def clear_all() -> int:
    """모든 아이템을 삭제하고 삭제한 개수를 반환한다."""
    def change(items):
        removed = len(items)
        items.clear()
        return removed > 0, removed
    return _mutate(change)


# ---------------------------------------------------------------------------
# 상태 도우미
# ---------------------------------------------------------------------------

def _flash_warning(message: str) -> None:
    """다음 화면 그리기에서 한 번 보여줄 경고를 등록한다."""
    st.session_state["flash_warning"] = message


def _flash_toast(message: str, icon: str) -> None:
    """다음 화면 그리기에서 한 번 보여줄 알림을 등록한다."""
    st.session_state["flash_toast"] = (message, icon)


def _display_text(text: str) -> str:
    """사용자 입력을 st.markdown(unsafe_allow_html=True)에 안전하게 넣도록 이스케이프한다.

    HTML 태그 안에서는 마크다운의 백슬래시 이스케이프가 처리되지 않아 '\\!'처럼
    그대로 보이므로, 마크다운 특수문자도 HTML 숫자 엔티티(&#33; 등)로 바꾼다.
    """
    escaped = html.escape(text)
    return re.sub(r"[\\`*_{}\[\]()#+\-.!|~>$]", lambda m: f"&#{ord(m.group())};", escaped)


# ---------------------------------------------------------------------------
# 콜백
# ---------------------------------------------------------------------------

def on_add() -> None:
    name = st.session_state.get("new_name", "").strip()
    ok, message = add_item(name)
    if ok:
        st.session_state["new_name"] = ""  # 성공했을 때만 비운다 (실패 시 고쳐 쓸 수 있게)
    else:
        _flash_warning(message)


def on_toggle(item_id: str) -> None:
    # 뒤집지 않고 체크박스의 새 값으로 맞춘다. 다른 탭에서 상태가 바뀌었어도
    # 사용자가 화면에서 의도한 상태가 저장된다.
    message = toggle_item(item_id, st.session_state[f"check_{item_id}"])
    if message:
        _flash_warning(message)


def on_delete(item_id: str) -> None:
    name = delete_item(item_id)
    if name is not None:
        _flash_toast(f"'{name}'을(를) 삭제했습니다", "🗑️")
    if st.session_state.get("editing_id") == item_id:
        on_cancel_edit(item_id)


def on_start_edit(item_id: str) -> None:
    previous = st.session_state.get("editing_id")
    if previous:
        st.session_state.pop(f"edit_{previous}", None)
    item = _find(st.session_state[ITEMS], item_id)
    if item:
        st.session_state["editing_id"] = item_id
        st.session_state[f"edit_{item_id}"] = item["name"]


def on_save_edit(item_id: str) -> None:
    new_name = st.session_state.get(f"edit_{item_id}", "").strip()
    ok, message = update_item(item_id, new_name)
    if ok or message == MISSING:
        on_cancel_edit(item_id)
    if not ok:
        _flash_warning(message)  # 검증 실패 시 수정 모드를 유지해서 다시 고칠 수 있게 한다


def on_cancel_edit(item_id: str) -> None:
    st.session_state["editing_id"] = None
    st.session_state.pop(f"edit_{item_id}", None)


def on_clear_checked() -> None:
    removed = clear_checked()
    if removed:
        _flash_toast(f"완료 항목 {removed}개를 삭제했습니다", "🧹")


def on_ask_clear_all() -> None:
    st.session_state["confirm_clear"] = True


def on_confirm_clear_all() -> None:
    clear_all()
    st.session_state["confirm_clear"] = False
    st.session_state["editing_id"] = None
    _flash_toast("리스트를 모두 비웠습니다", "🧹")


def on_cancel_clear_all() -> None:
    st.session_state["confirm_clear"] = False


# ---------------------------------------------------------------------------
# 화면 그리기
# ---------------------------------------------------------------------------

# 1) Streamlit은 폭 640px 이하에서 st.columns를 세로로 쌓는다. 그러면 모바일에서
#    한 행의 체크박스·이름·버튼이 흩어지므로 가로 배치를 강제한다.
# 2) 아이템 행은 체크박스·버튼 칸을 고정 폭으로 두고 이름 칸이 나머지를 쓴다.
#    버튼은 모바일에서도 누르기 쉬운 44px(2.75rem) 이상을 유지한다.
# 3) 아이콘 버튼의 글자("수정"/"삭제")는 화면에서 숨기되 스크린리더에는 읽힌다.
CUSTOM_CSS = """
<style>
h1 { word-break: keep-all; }
[data-testid="stHorizontalBlock"] {
    flex-wrap: nowrap !important;
    gap: 0.5rem !important;
}
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    min-width: 0 !important;
}
button[data-testid^="stBaseButton"] p {
    white-space: nowrap;
}
/* 폼(추가·수정) 안에서는 입력창이 남는 폭을 쓰고, 버튼은 글자 폭만큼 고정한다.
   비율로 나누면 320px 화면에서 [추가] 글자가 잘린다. */
[data-testid="stForm"] [data-testid="stColumn"]:has(input) {
    flex: 1 1 0 !important;
    width: auto !important;
}
[data-testid="stForm"] [data-testid="stColumn"]:has(button) {
    flex: 0 0 auto !important;
    width: auto !important;
}
[data-testid="stForm"] button {
    min-width: 3.5rem;
}
/* 하단 일괄 버튼은 좁은 화면에서 글자가 넘치지 않도록 줄바꿈을 허용한다. */
.st-key-clear_checked button p,
.st-key-clear_all button p,
.st-key-confirm_clear_yes button p,
.st-key-confirm_clear_no button p {
    white-space: normal;
    word-break: keep-all;
}
.st-key-item_list [data-testid="stVerticalBlock"] {
    gap: 0.4rem;
}
.st-key-item_list [data-testid="stColumn"]:has([data-testid="stCheckbox"]) {
    flex: 0 0 1.5rem !important;
    width: 1.5rem !important;
}
.st-key-item_list [data-testid="stColumn"]:has([data-testid="stCheckbox"]) label {
    margin-top: 0.6rem;
}
.st-key-item_list [data-testid="stColumn"]:has(.item-name),
.st-key-item_list [data-testid="stColumn"]:has(input[type="text"]) {
    flex: 1 1 0 !important;
    width: auto !important;
}
.st-key-item_list [data-testid="stColumn"]:has([class*="st-key-edit_btn_"]),
.st-key-item_list [data-testid="stColumn"]:has([class*="st-key-del_"]) {
    flex: 0 0 2.75rem !important;
    width: 2.75rem !important;
}
.st-key-item_list [data-testid="stColumn"]:has([class*="st-key-save_"]),
.st-key-item_list [data-testid="stColumn"]:has([class*="st-key-cancel_"]) {
    flex: 0 0 auto !important;
    width: auto !important;
}
.st-key-item_list button {
    min-height: 2.75rem;
    min-width: 2.75rem;
    padding: 0.25rem 0.6rem;
}
.st-key-item_list [class*="st-key-edit_btn_"] button p,
.st-key-item_list [class*="st-key-del_"] button p {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
}
.item-name {
    margin: 0;
    overflow-wrap: anywhere;
    line-height: 1.4;
}
.item-done {
    text-decoration: line-through;
    opacity: 0.5;
}
.section-title {
    margin: 0.25rem 0 0;
    font-size: 0.9rem;
    font-weight: 600;
    opacity: 0.75;
}
</style>
"""


def inject_css() -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def render_input_form() -> None:
    """아이템 이름 입력창과 [추가] 버튼을 한 줄로 그린다. Enter로도 제출된다.

    길이 제한(max_chars)을 걸지 않는다. 걸면 50자 초과 붙여넣기가 조용히 잘리므로
    validate_name()에서 경고로 알려 준다.
    """
    with st.form("add_form", border=False):
        input_col, button_col = st.columns([5, 1], vertical_alignment="bottom")
        with input_col:
            st.text_input(
                "아이템 이름",
                key="new_name",
                placeholder="살 물건을 입력하세요 (예: 우유)",
                label_visibility="collapsed",
            )
        with button_col:
            st.form_submit_button("추가", type="primary", on_click=on_add, width="stretch")


def render_summary() -> None:
    """전체/완료 개수와 진행률을 표시한다."""
    items = st.session_state[ITEMS]
    if not items:
        st.info("쇼핑 리스트가 비어 있어요. 아이템을 추가해 보세요!", icon="📝")
        return
    total = len(items)
    done = sum(i["checked"] for i in items)
    st.progress(done / total, text=f"전체 {total}개 · 완료 {done}개")
    if done == total:
        st.success("🎉 쇼핑 완료!")


def _render_edit_row(item: dict) -> None:
    """수정 중인 행. 폼이라서 입력창에서 Enter를 누르면 [저장]과 같다."""
    item_id = item["id"]
    with st.form(f"edit_form_{item_id}", border=False):
        input_col, save_col, cancel_col = st.columns([5, 1, 1], vertical_alignment="center")
        with input_col:
            st.text_input(
                f"{item['name']} 이름 수정",
                key=f"edit_{item_id}",
                label_visibility="collapsed",
            )
        with save_col:
            st.form_submit_button(
                "저장", key=f"save_{item_id}", type="primary",
                on_click=on_save_edit, args=(item_id,),
            )
        with cancel_col:
            st.form_submit_button(
                "취소", key=f"cancel_{item_id}",
                on_click=on_cancel_edit, args=(item_id,),
            )


def _render_row(item: dict) -> None:
    item_id = item["id"]
    if st.session_state.get("editing_id") == item_id:
        _render_edit_row(item)
        return

    check_col, name_col, edit_col, del_col = st.columns(
        [1, 6, 1, 1], vertical_alignment="center"
    )
    with check_col:
        # 매번 파일의 최신 상태로 체크박스를 맞춘다 (다른 탭에서 바뀐 경우 포함).
        st.session_state[f"check_{item_id}"] = item["checked"]
        st.checkbox(
            f"{item['name']} 구매 완료",
            key=f"check_{item_id}",
            label_visibility="collapsed",
            on_change=on_toggle,
            args=(item_id,),
        )
    with name_col:
        text = _display_text(item["name"])
        if item["quantity"] > 1:
            text += f" × {item['quantity']}"
        css_class = "item-name item-done" if item["checked"] else "item-name"
        st.markdown(f'<p class="{css_class}">{text}</p>', unsafe_allow_html=True)
    with edit_col:
        st.button(
            "수정", icon="✏️", key=f"edit_btn_{item_id}", help="수정",
            on_click=on_start_edit, args=(item_id,),
        )
    with del_col:
        st.button(
            "삭제", icon="🗑️", key=f"del_{item_id}", help="삭제",
            on_click=on_delete, args=(item_id,),
        )


def _section_title(text: str) -> None:
    st.markdown(f'<p class="section-title">{text}</p>', unsafe_allow_html=True)


def render_item_list() -> None:
    """아이템 목록을 미완료 → 완료 순으로 표시한다. 각 그룹 안에서는 추가한 순서."""
    items = sorted(st.session_state[ITEMS], key=lambda i: (i["checked"], i["created_at"]))
    todo = [i for i in items if not i["checked"]]
    done = [i for i in items if i["checked"]]

    with st.container(key="item_list"):
        if todo:
            _section_title(f"🛍️ 살 것 ({len(todo)})")
            for item in todo:
                _render_row(item)
        if todo and done:
            st.divider()
        if done:
            _section_title(f"✅ 구매 완료 ({len(done)})")
            for item in done:
                _render_row(item)


def render_bulk_actions() -> None:
    """[완료 항목 모두 삭제], [전체 초기화] 버튼을 그린다. 초기화는 확인을 한 번 더 받는다."""
    items = st.session_state[ITEMS]
    if not items:
        st.session_state["confirm_clear"] = False
        return

    st.divider()
    if st.session_state.get("confirm_clear"):
        st.warning(f"아이템 {len(items)}개를 모두 삭제할까요? 되돌릴 수 없어요.")
        yes_col, no_col = st.columns(2)
        yes_col.button(
            "네, 모두 삭제", key="confirm_clear_yes", type="primary", width="stretch",
            on_click=on_confirm_clear_all,
        )
        no_col.button("취소", key="confirm_clear_no", width="stretch", on_click=on_cancel_clear_all)
        return

    left, right = st.columns(2)
    left.button(
        "🧹 완료 항목 모두 삭제",
        key="clear_checked",
        width="stretch",
        on_click=on_clear_checked,
        disabled=not any(i["checked"] for i in items),
    )
    right.button(
        "전체 초기화", key="clear_all", type="tertiary", width="stretch",
        on_click=on_ask_clear_all,
    )


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------

def init_state() -> None:
    """매 실행마다 파일의 최신 목록을 읽어 다른 탭·사용자의 변경을 반영한다."""
    st.session_state[ITEMS] = _read_latest()
    st.session_state.setdefault("editing_id", None)
    st.session_state.setdefault("confirm_clear", False)
    # 수정 중이던 아이템이 다른 곳에서 삭제됐으면 수정 모드를 끝낸다.
    editing = st.session_state["editing_id"]
    if editing and not _find(st.session_state[ITEMS], editing):
        on_cancel_edit(editing)


def show_flash_messages() -> None:
    """콜백에서 등록한 경고/알림을 한 번만 표시한다."""
    if message := st.session_state.pop("flash_warning", None):
        st.warning(message)
    if toast := st.session_state.pop("flash_toast", None):
        st.toast(toast[0], icon=toast[1])


def main() -> None:
    st.set_page_config(page_title="쇼핑 리스트", page_icon="🛒", layout="centered")
    inject_css()
    init_state()

    st.title("🛒 쇼핑 리스트")
    render_input_form()
    show_flash_messages()
    render_summary()
    render_item_list()
    render_bulk_actions()


if __name__ == "__main__":
    main()
