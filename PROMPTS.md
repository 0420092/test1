# 쇼핑 리스트 앱 — 단계별 개발 프롬프트

> `PRD.md`를 기준으로 Claude Code에 단계마다 하나씩 붙여 넣어 사용합니다.
> 각 단계를 끝내면 `streamlit run app.py`로 직접 확인한 뒤 다음 단계로 넘어가세요.

---

## 1단계: 기본 뼈대 작성

```
PRD.md를 읽고 쇼핑 리스트 앱의 기본 뼈대를 만들어줘.

[만들 파일]
- app.py: Streamlit 메인 앱
- requirements.txt: streamlit
- .gitignore: data/, __pycache__/, .venv/, .streamlit/secrets.toml
- README.md: 설치·실행 방법 (pip install -r requirements.txt → streamlit run app.py)

[app.py 요구사항]
1. st.set_page_config(page_title="쇼핑 리스트", page_icon="🛒")와 제목 "🛒 쇼핑 리스트"
2. PRD 5장의 데이터 모델 그대로 사용: id(uuid4), name, quantity(기본 1), checked, created_at(ISO 8601)
3. st.session_state 초기화: items(리스트), editing_id(None)
4. 아래 함수들의 시그니처와 docstring만 작성하고, 본문은 TODO 또는 최소 구현으로 둬:
   - load_items() -> list[dict]       # data/shopping_list.json 읽기
   - save_items(items) -> None        # JSON 저장
   - validate_name(name, exclude_id=None) -> tuple[bool, str]
   - add_item(name, quantity=1)
   - update_item(item_id, new_name)
   - delete_item(item_id)
   - toggle_item(item_id)
   - clear_checked()
   - clear_all()
   - render_input_form()
   - render_summary()
   - render_item_list()
   - render_bulk_actions()
   - main()
5. main()에서 render_* 함수를 순서대로 호출하는 구조만 잡아줘.
6. 이 단계에서는 "추가"와 "목록 표시"만 실제로 동작하게 해줘 (st.form + st.text_input + 제출 버튼).

[주의]
- 파일은 app.py 하나로 유지하고, 함수는 데이터 처리와 화면 그리기로 나눠줘.
- 마지막에 streamlit run app.py로 오류 없이 실행되는지 확인하고 결과를 알려줘.
```

---

## 2단계: 기능 추가

```
PRD.md의 4장 기능 요구사항을 기준으로 app.py에 나머지 기능을 모두 구현해줘.

[P0 - 필수]
1. 추가 (4.1)
   - st.form(clear_on_submit=True)로 Enter 제출 지원
   - 앞뒤 공백 제거, 빈 값/공백만 입력 시 경고, 최대 50자
   - 같은 이름의 "미완료" 아이템이 있으면 경고 (대소문자 무시)
2. 수정 (4.2)
   - ✏️ 버튼 → 해당 행이 text_input + [저장]/[취소]로 바뀜
   - editing_id로 한 번에 하나만 수정 모드
   - 저장 시 추가와 같은 검증 적용 (자기 자신은 중복 검사에서 제외)
3. 삭제 (4.3)
   - 🗑️ 버튼 → 즉시 삭제, st.toast("'우유'를 삭제했습니다")
4. 체크 (4.4)
   - 체크박스로 checked 토글
   - 정렬: 미완료 위, 완료 아래, 각 그룹 안에서는 created_at 순

[P1 - 권장]
5. 진행 현황 (4.5): "전체 N개 · 완료 M개" + st.progress, 빈 리스트 안내 문구
6. 일괄 정리 (4.6): [완료 항목 모두 삭제], [전체 초기화] (초기화는 확인 단계 필수)
7. 데이터 저장 (4.7)
   - 추가/수정/삭제/체크/일괄 정리 후마다 data/shopping_list.json 저장
   - data/ 폴더가 없으면 생성, 파일이 없거나 JSON이 손상되면 빈 리스트로 시작
   - 저장은 UTF-8, ensure_ascii=False

[구현 주의사항]
- 모든 위젯 key는 아이템 id 기반으로 고유하게 (예: f"check_{id}", f"del_{id}")
- 버튼 동작은 on_click 콜백으로 처리해서 클릭 한 번에 바로 반영되게 해줘 (두 번 눌러야 반영되는 문제 방지)
- 리스트를 순회하면서 삭제하지 말 것
- 경고/성공 메시지는 st.warning / st.toast 사용

구현 후 PRD 9장 인수 기준 체크리스트를 하나씩 보고, 코드상 어느 부분이 각 항목을 만족하는지 표로 정리해줘.
```

---

## 3단계: UI 디자인

```
기능은 그대로 두고 app.py의 UI를 다듬어줘. PRD 6장의 화면 구성을 기준으로 해.

[레이아웃]
1. 입력 영역: st.columns로 [입력창(넓게) | 추가 버튼] 한 줄 배치, placeholder "살 물건을 입력하세요 (예: 우유)"
2. 아이템 행: st.columns([0.5, 6, 1, 1]) 비율로 [체크박스 | 이름 | ✏️ | 🗑️]
   - 버튼은 아이콘만 표시하고 help 툴팁("수정", "삭제") 추가
   - 체크된 아이템은 이름에 취소선 + 회색 (st.markdown 사용, 사용자 입력은 HTML 이스케이프 처리)
3. 진행 현황: 요약 문구 + 진행률 바, 모두 완료되면 "🎉 쇼핑 완료!" 표시
4. 미완료 / 완료 구역 사이에 구분선, 완료 구역 제목 "✅ 구매 완료 (M)"
5. 하단 일괄 정리 버튼 2개를 나란히 배치, 전체 초기화는 type="secondary"로 덜 눈에 띄게

[스타일]
- .streamlit/config.toml에 테마 설정 (primaryColor는 초록 계열, 라이트/다크 모두 읽기 편하게)
- 필요한 경우에만 st.markdown(unsafe_allow_html=True)로 최소한의 CSS 추가
  (행 간격 줄이기, 버튼 크기 통일 정도)
- 페이지 최대 폭은 layout="centered" 유지

[모바일]
- 폭 375px 화면에서 버튼이 겹치거나 줄바꿈으로 깨지지 않게 해줘
- 긴 아이템 이름(50자)도 레이아웃이 깨지지 않는지 확인

[주의]
- 2단계 기능 동작이 바뀌면 안 돼. 수정 후 추가/수정/삭제/체크가 그대로 동작하는지 다시 확인해줘.
- 바꾼 내용을 전/후로 간단히 정리해줘.
```

---

## 4단계: 검토 및 테스트 (Playwright 활용)

```
PRD.md를 기준으로 완성된 앱을 꼼꼼하게 검토해줘. 코드 리뷰와 Playwright 브라우저 테스트를 모두 해야 해.

[준비]
1. 백그라운드로 streamlit run app.py --server.headless true --server.port 8501 실행
2. 테스트 전에 data/shopping_list.json을 백업하고, 깨끗한 상태에서 시작
3. Playwright로 http://localhost:8501 접속

[A. 코드 리뷰]
- PRD 4장(기능), 5장(데이터 모델), 8장(비기능) 요구사항과 코드를 한 항목씩 대조
- 버그 가능성 점검:
  - 위젯 key 중복, 콜백에서 st.rerun 오용, 버튼을 두 번 눌러야 반영되는 문제
  - 수정 모드 중 다른 아이템 삭제/체크 시 상태 꼬임
  - JSON 파일 손상/없음/빈 파일 처리
  - 사용자 입력을 HTML로 출력할 때 이스케이프 누락 (예: <b>test</b>, <script>)
  - 중복 검사 시 대소문자·공백 처리

[B. Playwright 기능 테스트 — PRD 9장 인수 기준 전부]
각 항목마다 실제로 조작하고, 결과를 snapshot이나 screenshot으로 확인해줘.
1. "우유" 추가 → 리스트에 표시
2. 빈 값, 공백만 입력 → 추가 안 되고 경고
3. 51자 입력 → 막히는지
4. "우유" 중복 추가, "우유 " / "우유"(대소문자 다른 영문 예: "Milk"/"milk") → 경고
5. Enter 키로 추가되는지
6. "우유" → "저지방 우유" 수정 후 저장 / 수정 중 취소 시 원래 이름 유지
7. 삭제 → 사라지고 toast 표시
8. 체크 → 취소선 + 아래로 이동 / 해제 → 원상복구
9. 진행 현황 숫자와 진행률이 매 동작마다 정확한지
10. 완료 항목 모두 삭제, 전체 초기화(확인 단계 포함)
11. 새로고침 후 데이터 유지
12. 특수문자/이모지/HTML 태그가 들어간 이름 표시
13. 아이템 30개 이상 추가 시 동작 속도와 표시

[C. UI / 반응형]
- 데스크톱(1280x800)과 모바일(375x812)에서 각각 스크린샷
- 버튼 겹침, 텍스트 넘침, 정렬 깨짐 확인
- 브라우저 콘솔 에러 확인

[결과 보고]
아래 형식의 표로 정리해줘.
| # | 구분(버그/PRD 불일치/개선) | 심각도(높음/중간/낮음) | 재현 방법 | 기대 결과 | 실제 결과 | 수정 제안 |

- 마지막에 PRD 9장 인수 기준 체크리스트를 통과/실패로 표시
- 이 단계에서는 코드를 수정하지 말고 보고만 해줘. 수정은 내가 확인한 다음에 진행할게.
- 테스트가 끝나면 백업해 둔 data/shopping_list.json을 복원하고 streamlit 서버를 종료해줘.
```

---

## 진행 팁

- 각 단계가 끝날 때마다 직접 `streamlit run app.py`로 확인한 뒤 다음 단계로 넘어가세요.
- 4단계에서 문제가 나오면 "4단계 보고서의 1, 3, 5번 수정해줘"처럼 번호로 수정을 요청하고, 다시 4단계를 실행해 재검증하세요.
- 모두 통과하면 GitHub에 올리고 Streamlit Community Cloud에 배포합니다 (PRD 7.3).
