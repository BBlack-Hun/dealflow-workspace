"""「투자사 현황 관리 → 전체 딜소개현황」 [수정] 창의 **이름과 구성**.

이 창은 배치(`contact_columns.Layout`)가 세우지 않는다. `contacts.html` 의
`{% if layout.key != 'investor' %} … {% else %}` 에서 **else 쪽에 손으로 적혀
있다.** 그래서 배치를 고쳐도 이 화면은 안 움직이고, 이름이 어긋나도 반복문
검사에 안 걸린다 — 여기서 글자를 직접 잰다.

뜻이 불명확하다고 지적된 아홉 칸을 전수 검토해 **지운 칸은 하나도 없고**
다섯 군데만 손봤다. 이 파일은 그 다섯을 각각 지킨다.

    ① `담당자`            → `연결 담당`      (우리 팀원 ↔ 옆 `부서`·`직함` 은 투자사 쪽)
    ② `단계 태그`         → `선호 투자단계`  (라운드의 단계가 아니라 선호 투자 단계)
    ③ `관심도 (월말기준)` → `관심도`         (`(월말기준)` 은 앱이 안 지키는 약속)
    ④ `카톡방 참여여부`   → `연결 상태` 아래로 자리 이동 (이름은 그대로)
    ⑤ `초대 완료 여부`    → 수정창에서만 뺌   (모델 칸·값·이주는 그대로)

**바꾼 것은 화면 이름과 창 구성뿐이다.** 모델 칸 이름(`assignee_name` ·
`stages` · `interest_level` · `kakao_joined` · `invited_status`)과 필터 키
(`assignee` · `interest` · `joined`)는 하나도 안 바뀌었다 — 대시보드 링크와
사람들이 저장해 둔 주소가 그 키로 들어온다. 이름과 키를 **따로** 잰다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CONTACTS_HTML = ROOT / "app" / "templates" / "contacts.html"


def _markup(text: str) -> str:
    """Jinja 주석(`{# … #}`)을 뺀 실제 마크업.

    이 판에서 뺀 칸(`초대 완료 여부`)의 **되돌릴 한 줄**이 주석 안에 그대로
    적혀 있다. 지우지 않고 세면 "아직 창에 서 있다" 고 잘못 읽는다.
    """
    return re.sub(r"\{#.*?#\}", "", text, flags=re.S)


#: 손으로 적은 [수정] 창을 감싼 조건. 배치가 세우는 창이 `if` 쪽이고,
#: 투자사 명함 배치의 창이 `else` 쪽에 **글자로 적혀 있다**.
_PANEL_IF = "{% if layout.key != 'investor' %}"


@pytest.fixture(scope="module")
def panel() -> str:
    """손으로 적은 [수정] 창 부분(= `{% else %}` 쪽)의 마크업만.

    **가장 가까운 `{% else %}` 를 잡으면 안 된다** — `if` 쪽 안에도 `{% if %}`
    가 여럿 있어서, 그중 하나의 `else` 를 창의 시작으로 잘못 짚는다(그러면
    창이 한 줄로 보이고 이 파일의 검사가 통째로 헛돈다).  같은 깊이의
    `{% else %}` 를 찾을 때까지 `{% if %}`/`{% endif %}` 를 센다.
    """
    text = _markup(CONTACTS_HTML.read_text(encoding="utf-8"))
    at = text.index(_PANEL_IF) + len(_PANEL_IF)
    depth, start, end = 1, None, None
    for tag in re.finditer(r"\{%-?\s*(if|else|elif|endif)\b", text[at:]):
        word = tag.group(1)
        if word == "if":
            depth += 1
        elif word == "endif":
            depth -= 1
            if depth == 0:
                end = at + tag.start()
                break
        elif word == "else" and depth == 1:
            start = at + tag.end()
    assert start is not None and end is not None, "수정 창의 `else` 쪽을 못 찾았습니다"
    return text[start:end]


@pytest.fixture(scope="module")
def head() -> str:
    """투자사 표의 머리글 마크업만."""
    text = _markup(CONTACTS_HTML.read_text(encoding="utf-8"))
    m = re.search(r'id="contacts-table".*?<thead>(.*?)</thead>', text, re.S)
    assert m, "투자사 표의 머리글을 못 찾았습니다"
    return m.group(1)


def _label_of(panel_html: str, field: str) -> str:
    """수정창에서 `id="f-<field>"` 를 담은 `<label>` 의 이름."""
    for open_tag in re.finditer(r'<label class="field[^"]*"[^>]*>', panel_html):
        depth, end = 1, len(panel_html)
        for tag in re.finditer(r"<(/?)label\b", panel_html[open_tag.end():]):
            depth += -1 if tag.group(1) else 1
            if depth == 0:
                end = open_tag.end() + tag.start()
                break
        block = panel_html[open_tag.end():end]
        if f'id="f-{field}"' not in block:
            continue
        span = re.search(r"<span[^>]*>(.*?)</span>", block, re.S)
        return re.sub(r"\s+", " ", span.group(1).split("<")[0]).strip() if span else ""
    return ""


def _th(head_html: str, key: str):
    """필터 키가 `key` 인 머리글 → (이름, 필터 라벨, 폭 px)."""
    for attrs, cell in re.findall(r"<th\b([^>]*)>(.*?)</th>", head_html, re.S):
        m = re.search(r'data-filters="([^"]*)"', attrs)
        if not m or not m.group(1).startswith(key + ":"):
            continue
        name = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cell)).strip()
        px = re.search(r"width:\s*(\d+)px", attrs)
        return name, m.group(1).split(":", 1)[1], int(px.group(1)) if px else None
    return None


# ── ① 담당자 → 연결 담당 ────────────────────────────────────────────────────

def test_담당자는_투자사_쪽_사람이_아니라_우리_팀원이라_연결_담당이다(head, panel):
    """옆 칸 `부서`·`직함` 은 **투자사 쪽 사람**의 것이다.

    `담당자` 라고만 적혀 있으면 둘 중 누구를 가리키는지 화면만 보고는 가릴
    수가 없었다 — 그것이 지적의 핵심이었다. 대시보드는 이 값을 이미 `연결
    담당` 이라고 부른다(`services/dashboard.py` · `templates/dashboard.html`).
    그쪽에 맞춘다.
    """
    got = _th(head, "assignee")
    assert got, "표에 `assignee` 필터를 단 칸이 없습니다"
    name, label, _px = got
    assert name == label == "연결 담당", f"표 머리글이 `연결 담당` 이 아닙니다: {got}"
    assert _label_of(panel, "assignee_name") == "연결 담당", \
        "수정창 라벨이 표 머리글과 다릅니다"


def test_대시보드가_부르는_이름과_같은_말이어야_한다():
    """이름을 맞추는 상대는 **이미 그렇게 부르고 있던 쪽**이다."""
    dash_py = (ROOT / "app" / "services" / "dashboard.py").read_text(encoding="utf-8")
    dash_html = (ROOT / "app" / "templates" / "dashboard.html").read_text(encoding="utf-8")
    assert "연결 담당" in dash_py and "연결 담당" in dash_html


# ── ② 단계 태그 → 선호 투자단계 ─────────────────────────────────────────────

def test_단계_태그는_라운드의_단계가_아니라_투자사가_선호하는_단계다(panel):
    """`라운드 사이즈` 옆에 `단계 태그` 라고만 적혀 있어 **"라운드의 단계"**
    로 읽혔다. 실제로는 투자사가 선호하는 투자 단계(Seed·SeriesA…)다.

    `matcher.evaluate_company` 가 이 값을 기업의 `series` 와 견주어 `단계
    불일치` 를 내고, `라운드 사이즈` 는 **금액 축**으로 따로 본다 — 두 축이
    다르다는 것이 이름에 드러나야 한다.
    """
    assert _label_of(panel, "stages") == "선호 투자단계"
    assert "단계 태그" not in panel, "옛 이름이 창에 남아 있습니다"


def test_선호_투자단계와_라운드_사이즈는_서로_다른_축이다():
    """이름을 그렇게 지은 근거가 코드에 실제로 있는가."""
    src = (ROOT / "app" / "services" / "matcher.py").read_text(encoding="utf-8")
    assert "단계 불일치" in src and "stages" in src
    assert "round_size" in src, "금액 축이 따로 없으면 이름을 가를 이유도 없다"


# ── ③ 관심도 (월말기준) → 관심도 ────────────────────────────────────────────

def test_월말기준은_앱이_지키지_않는_약속이라_이름에서_뺀다(head, panel):
    """어느 달 기준인지 적는 칸이 없고, 달이 바뀔 때 이 값을 비우거나 달
    이름을 붙이는 코드도 없다. 안 지키는 약속을 이름에 달아 두니 `상태` 와
    같은 뜻으로 오해받았다.
    """
    got = _th(head, "interest")
    assert got, "표에 `interest` 필터를 단 칸이 없습니다"
    name, label, _px = got
    assert name == label == "관심도", f"표 머리글이 `관심도` 가 아닙니다: {got}"
    assert _label_of(panel, "interest_level") == "관심도"

    whole = CONTACTS_HTML.read_text(encoding="utf-8")
    assert "관심도 (월말기준)" not in _markup(whole), \
        "옛 이름이 화면에 남아 있습니다"


def test_월말기준은_엑셀_머리글에도_없다():
    """엑셀은 이미 `관심도` 로 적고 있었다 — 이름이 갈려 있던 자리다."""
    from app.routers import data_io

    assert "관심도" in data_io.CONTACT_HEADERS
    assert "관심도 (월말기준)" not in data_io.CONTACT_HEADERS


def test_배치가_세우는_수정창의_같은_칸도_같이_고친다():
    """`투자사 딜공유` 배치의 수정창에도 같은 이름이 적혀 있었다.

    한쪽만 고치면 같은 값이 화면에 따라 다른 이름으로 선다.
    """
    from app.services import contact_columns as cc

    labels = {c.key: c.label
              for c in cc.INVESTOR_MONTHLY_LAYOUT.extra}
    assert labels.get("interest_level") == "관심도"


def test_관심도는_표에서_고르는_칸인데_창만_빈_글자칸이면_값이_갈린다(head, panel):
    """표 칸은 `data-type="pick"`(`높음,중간,낮음`)인데 창만 자유 글자칸이라
    **같은 칸을 어디서 고치느냐에 따라 값이 갈렸다.** 이 저장소가 `O`·`o`·
    `완료` 로 이미 데인 자리다.

    다른 칸들이 쓰는 `list=` 로 묶는다 — `<select>` 가 아닌 이유도 같다:
    목록에 없는 옛 값이 창을 여는 것만으로 사라지면 안 된다.
    """
    whole = _markup(CONTACTS_HTML.read_text(encoding="utf-8"))
    cell = re.search(r'<td[^>]*data-field="interest_level"[^>]*>', whole) or \
        re.search(r'data-field="interest_level"[^>]*data-choices="([^"]*)"', whole)
    choices = re.search(r'data-field="interest_level"(?:[^>]*?)data-choices="([^"]*)"',
                        whole, re.S)
    assert choices, "표 칸에 `data-choices` 가 없습니다"
    want = [v.strip() for v in choices.group(1).split(",")]

    block = re.search(r'id="f-interest_level"(.*?)</label>', panel, re.S)
    assert block, "수정창에 `interest_level` 칸이 없습니다"
    assert 'list="opts-panel-interest_level"' in panel, \
        "수정창이 아직 자유 글자칸입니다 — `list=` 로 묶어야 합니다"
    got = re.findall(r'<option value="([^"]*)"></option>',
                     re.search(r'<datalist id="opts-panel-interest_level">(.*?)</datalist>',
                               panel, re.S).group(1))
    assert got == want, f"창의 보기가 표 칸과 다릅니다: {got} ≠ {want}"


# ── ④ 카톡방 참여여부 — 자리를 `연결 상태` 아래로 ───────────────────────────

def test_부서는_회사_옆이지_연결_담당_옆이_아니다(panel):
    """둘이 가리키는 사람이 아예 다르다 (사용자 지적).

    `연결 담당`(`assignee_name`)은 **우리 팀원**이고 `부서`(`department`)는
    **투자사 쪽 사람**의 부서다. 한동안 나란히 서 있어서 같은 사람의 두 값으로
    읽혔다 — 이름을 `연결 담당` 으로 고쳐도 옆에 `부서` 가 붙어 있으면 그
    오해가 그대로 남는다.

    `이름 · 직함 · 회사 · 부서` 는 **명함 한 장을 읽는 차례**라, 여기 서면
    누구의 부서인지가 자리로 드러난다.
    """
    at_firm = panel.index('id="f-firm"')
    at_dept = panel.index('id="f-department"')
    at_assignee = panel.index('id="f-assignee_name"')

    assert at_firm < at_dept, "`부서` 가 `회사` 위에 있습니다"
    assert at_dept < at_assignee, \
        "`부서` 가 아직 `연결 담당` 뒤에 있습니다 — 옮기다 만 것입니다"

    # `회사` 가 닫힌 자리부터 `부서` 가 **열리는** 자리까지 다른 칸이 없어야
    # 한다(위 `카톡방 참여여부` 검사와 같은 자다).
    between = panel[panel.index("</label>", at_firm):
                    panel.rindex('<label class="field', 0, at_dept)]
    assert '<label class="field' not in between, \
        "`회사` 와 `부서` 사이에 다른 칸이 끼었습니다"


def test_카톡방_참여여부는_연결_상태_바로_아래에_선다(panel):
    """한 창에 카톡방을 적는 자리가 넷이라(`카톡방 이름`+`채널` · 이 칸 ·
    `연결 상태`) 이름만으로는 **어느 것이 발송을 가르는지** 알 수 없었다.

    가르는 것은 `연결 상태`(`connect_stage`)다 — `sheet_owner.can_send_to` 가
    읽는다. 이 칸은 **스위치가 아니라 시트에서 온 기록**이고 그 기록은 `연결
    상태` 를 만드는 재료다. 이름에 `(시트 원문)` 을 붙이는 대신 자리를 옮겼다
    — 이 칸은 표에도 서서 이름이 표 머리글과 한 글자도 달라지면 안 된다
    (`tests/test_ui_layout.py`).
    """
    at_stage = panel.index('id="f-connect_stage"')
    at_joined = panel.index('id="f-kakao_joined"')
    assert at_stage < at_joined, "`카톡방 참여여부` 가 `연결 상태` 위에 있습니다"

    # `연결 상태` 가 닫힌 자리부터 `카톡방 참여여부` 가 **열리는** 자리까지.
    # (`id=` 위치까지 재면 그 칸 자신의 여는 태그가 사이에 낀 것으로 세어진다)
    between = panel[panel.index("</label>", at_stage):
                    panel.rindex('<label class="field', 0, at_joined)]
    assert '<label class="field' not in between, \
        "`연결 상태` 와 `카톡방 참여여부` 사이에 다른 칸이 끼었습니다"


def test_스타트업_화면의_카톡_연결_여부는_그대로_둔다():
    """같은 모델 칸을 보여 주지만 **화면이 다르면 이름도 그 화면의 것**이다."""
    from app.services import contact_columns as cc

    labels = [c.label for c in cc.STARTUP_LAYOUT.tail if c.key == "kakao_joined"]
    assert labels == ["카톡 연결 여부"], labels


# ── ⑤ 초대 완료 여부 — 창에서만 뺀다 ────────────────────────────────────────

def test_초대_완료_여부는_창에서만_빠지고_모델_칸은_그대로다(panel):
    """고쳐도 아무 데도 안 걸리는 칸이었다 — `PATCH` 가 값을 대입만 하고
    `connect_stage` 를 다시 계산하지 않는다. 표·필터·대시보드·`llm_brief`
    어디도 안 읽는다.

    **칸을 지운 것이 아니다.** 값 125줄은 그대로 있고, 읽는 두 곳(시트
    임포트 · 엑셀)은 지금까지처럼 읽는다.
    """
    from app.models import VcContact

    assert 'id="f-invited_status"' not in panel, "아직 창에 서 있습니다"
    assert hasattr(VcContact, "invited_status"), "모델 칸을 지우면 안 됩니다"


def test_초대_완료_여부를_읽는_두_곳은_그대로다():
    """읽는 곳은 **시트 임포트**(연결 상태를 만드는 재료)와 **엑셀** 둘뿐이다."""
    from app.routers import data_io
    from app.services import sheet_import

    assert "초대" in data_io.CONTACT_HEADERS
    assert sheet_import.is_invited("완료") and sheet_import.is_invited("O")


def test_되돌리기가_한_줄이어야_다음_사람이_도로_붙이지_않는다():
    """왜 뺐는지를 **그 자리에** 적어 두지 않으면 다음 사람이 "빠졌네" 하고
    도로 붙인다. 뺀 자리를 주석으로 남겨 두면 되돌리기도 한 줄이다.

    같은 물음을 시트별로 다르게 부른 것이라는 사실(`sheet_import` 의
    `connect_stage` 주석 — 명단 시트는 `카톡방 참여여부(O/X)`, 딜소개현황
    시트는 `초대 완료여부(완료)`, **둘 다 본다**)도 그 자리에 적는다.
    """
    text = CONTACTS_HTML.read_text(encoding="utf-8")
    notes = re.findall(r"\{#.*?#\}", text, re.S)
    hit = [n for n in notes if "invited_status" in n]
    assert hit, "뺀 자리에 주석이 없습니다"
    note = hit[0]

    # 되돌릴 한 줄이 주석 안에 통째로 들어 있다 — 꺼내면 그대로 산다.
    line = [ln.strip() for ln in note.splitlines()
            if 'id="f-invited_status"' in ln]
    assert len(line) == 1, f"되돌릴 한 줄이 주석에 없습니다: {line}"
    assert line[0].startswith('<label class="field"') and line[0].endswith("</label>")

    for word in ("카톡방 참여여부", "초대 완료여부", "connect_stage", "둘 다 본다"):
        assert word in note, f"주석에 `{word}` 가 없습니다"

    # 그 한 줄이 살아나려면 `contacts.js` 의 목록에 이름이 남아 있어야 한다.
    js = (ROOT / "app" / "static" / "js" / "contacts.js").read_text(encoding="utf-8")
    assert '"invited_status"' in js, \
        "`FIELDS` 에서 빠지면 주석을 꺼내도 값이 안 채워진다 — 한 줄이 아니게 된다"


# ── 바꾸지 않은 것 ──────────────────────────────────────────────────────────

def test_필터_키는_하나도_안_바뀐다(head):
    """대시보드 링크와 저장해 둔 주소가 이 키로 들어온다. 이름은 바뀌어도
    키는 안 바뀐다 — 바뀌면 눌러도 아무 일이 안 일어난다(`filters.js` 는
    선언되지 않은 키를 통째로 버린다).
    """
    keys = set()
    for attrs, _cell in re.findall(r"<th\b([^>]*)>(.*?)</th>", head, re.S):
        m = re.search(r'data-filters="([^"]*)"', attrs)
        if m:
            keys |= {spec.split(":", 1)[0] for spec in m.group(1).split("|")}
    for key in ("assignee", "interest", "joined", "round", "sector",
                "firm", "group", "channel", "room", "connect", "dealstage"):
        assert key in keys, f"필터 키 `{key}` 가 사라졌습니다"


def test_발송을_가르는_두_스위치의_이름은_안_건드린다(panel):
    """`상태`(`status`)와 `연결 상태`(`connect_stage`)는 `sheet_owner.can_send_to`
    가 직접 읽는 값이다. 이름도 값도 그대로 둔다.
    """
    assert _label_of(panel, "status") == "상태"
    assert _label_of(panel, "connect_stage") == "연결 상태"
    assert _label_of(panel, "department") == "부서"
    assert _label_of(panel, "round_size") == "라운드 사이즈(투자운영금액)"


def test_모델_칸_이름은_하나도_안_바뀐다():
    """이 판은 **화면 이름**과 **수정창 구성**만 바꾼다. 이주는 없다."""
    from app.models import VcContact

    for field in ("assignee_name", "stages", "interest_level",
                  "kakao_joined", "invited_status"):
        assert hasattr(VcContact, field), f"모델 칸 `{field}` 이 사라졌습니다"


# ── 화면으로도 한 번 ────────────────────────────────────────────────────────

def test_그린_화면에도_새_이름으로_선다(logged_in):
    """템플릿 글자만 재면 `{% if %}` 안에 갇힌 칸을 놓친다 — 그려서도 본다."""
    html = logged_in.get("/contacts").text
    for word in ("연결 담당", "선호 투자단계", "관심도"):
        assert word in html, f"화면에 `{word}` 가 없습니다"
    for word in ("단계 태그", "관심도 (월말기준)", 'id="f-invited_status"'):
        assert word not in html, f"화면에 `{word}` 가 아직 있습니다"
    assert 'data-filters="assignee:연결 담당"' in html
    assert 'data-filters="interest:관심도"' in html
