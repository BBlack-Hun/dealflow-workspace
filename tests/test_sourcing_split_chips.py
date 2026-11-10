"""딜 소싱 시리즈 A 탭 나눠 보기(i128 · i129) · 딜 발송 요청 이름.

  ① 시리즈 A 탭 위 칩 두 줄 — 검토가능(= 참여 안내 대상: 제안 대기중 + 물어보는 중) ·
     참여 · 불참여 수, 담당별 수와 그 담당의 검토가능 · 참여. 칩은 머리글 필터
     (`participation` · `assignee_name`)를 주소로 건 링크다(`filters.js` 가 읽는 꼴).
  ② 다른 갈래 탭 · 전체 탭에는 안 선다.
  ③ `월간 리마인드` 는 화면에서 `딜 발송 요청` — 종류 키(`sourcing_remind`)는 그대로.

칸을 고친 뒤 칩 수를 다시 세는 것은 `tests/js/sourcing_split_chips_test.js`.
이름은 전부 가상값이다(공개 저장소).
"""
from __future__ import annotations

import html
import re
from urllib.parse import quote

import pytest

from .conftest import DEMO_PASSWORD

SERIES_A = "시리즈 A 이상 딜 소싱 참여 심사역"
MNA = "M&A 찾는 투자사"
OFFER = "딜 소싱 참여 제안 대기중"
ASKING = "참여 의사를 물어보는 중"


@pytest.fixture()
def tab(client, db, users):
    from app.models import SourcingContact

    rows = [("가심사", "참여", "가담당"), ("나심사", OFFER, "가담당"),
            ("다심사", ASKING, "가담당"), ("라심사", "참여", "나담당 > 11/01 다담당"),
            ("마심사", "불참여", "다담당"), ("바심사", OFFER, "다담당")]
    db.add_all([SourcingContact(bucket=SERIES_A, position=i, name=n, participation=p,
                                assignee_name=a) for i, (n, p, a) in enumerate(rows)]
               + [SourcingContact(bucket=MNA, position=1000, name="사투자", participation=OFFER,
                                  assignee_name="가담당")])
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})


def _links(body):
    """`#sourcing-split` 안의 링크 → [(글자, 주소)]. 주소는 HTML 풀이를 한 것."""
    start = body.index('id="sourcing-split"')
    part = body[start:body.index('data-filter-chips', start)]
    return [(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text)).strip(), html.unescape(href))
            for href, text in re.findall(r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>', part, re.S)]


def test_series_a_tab_splits_by_participation_and_assignee(tab, client):
    body = client.get("/sourcing?tab=" + quote(SERIES_A)).text
    base = "/sourcing?tab=" + quote(SERIES_A, safe="")
    invite = "participation=" + quote(OFFER, safe="") + "," + quote(ASKING, safe="")
    joined = "participation=" + quote("참여", safe="")
    who = lambda name: "assignee_name=" + quote(name, safe="")    # noqa: E731
    assert _links(body) == [
        ("검토가능 3", f"{base}&{invite}"),
        ("참여 2", f"{base}&{joined}"),
        ("불참여 1", f"{base}&participation=" + quote("불참여", safe="")),
        # 담당은 **지금 맡은 사람**(`가 > 날짜 나` 의 뒤) — 많은 순, 같으면 이름순.
        ("가담당 3", f"{base}&{who('가담당')}"),
        ("검토가능 2", f"{base}&{invite}&{who('가담당')}"),
        ("참여 1", f"{base}&{joined}&{who('가담당')}"),
        ("다담당 3", f"{base}&{who('다담당')}"),
        ("검토가능 1", f"{base}&{invite}&{who('다담당')}"),
        ("참여 1", f"{base}&{joined}&{who('다담당')}"),
    ]
    # 칩이 거는 값 = 행이 싣는 필터 값(그래야 누르면 그 수만큼 뜬다).
    assert body.count(f'data-f-participation="{OFFER}"') == 2
    assert body.count('data-f-assignee_name="다담당"') == 3


@pytest.mark.parametrize("query", ["?tab=" + quote(MNA), "?tab=all"])
def test_other_tabs_have_no_split_chips(tab, client, query):
    assert 'id="sourcing-split"' not in client.get("/sourcing" + query).text


def test_remind_is_shown_as_deal_request(tab, client):
    from app.routers.deals import MODE_TOPIC_KINDS
    from app.services import sourcing_msg

    assert sourcing_msg.REMIND_KIND == "sourcing_remind"
    assert (sourcing_msg.REMIND_KIND, "딜 발송 요청") in MODE_TOPIC_KINDS["sourcing"]
    bar = client.get("/deals").text
    bar = bar[bar.index('id="sourcing-topic"'):]
    bar = bar[:bar.index("</div>")]
    assert 'data-value="sourcing_remind">딜 발송 요청</button>' in bar
    assert "월간 리마인드" not in bar


def _deals_split(body):
    """딜 제안 관리 › [갈래] 줄의 시리즈 A 두 칩 → {묶음: (글자, data-topic, data-value)}."""
    out = {}
    for attrs, text in re.findall(r'<button ([^>]*data-split="[^"]+"[^>]*)>(.*?)</button>', body, re.S):
        kind = re.search(r'data-split="([^"]+)"', attrs).group(1)
        out[kind] = (re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text)).strip(),
                     re.search(r'data-topic="([^"]+)"', attrs).group(1),
                     html.unescape(re.search(r'data-value="([^"]+)"', attrs).group(1)))
    return out


def test_deals_page_splits_series_a_into_the_same_two_counts(tab, client, db):
    """#210 — 딜 제안 관리 › [딜 소싱 제안]의 시리즈 A 갈래가 `검토가능 심사역` · `참여 심사역`
    칩 둘로 서고, 수가 딜 소싱 화면의 그 탭 칩(`검토가능` · `참여`)과 같다. 사람이 적은 문구 ·
    불참여는 어느 쪽에도 안 든다. 검토가능은 참여 안내 (처음), 참여는 딜 발송 요청을 고른다."""
    from app.models import SourcingContact

    db.add(SourcingContact(bucket=SERIES_A, position=99, name="사심사", participation="11월 재연락",
                           assignee_name="가담당"))
    db.commit()
    split = [text for text, _href in _links(client.get("/sourcing?tab=" + quote(SERIES_A)).text)[:2]]
    assert split == ["검토가능 3", "참여 2"]
    body = client.get("/deals").text
    assert _deals_split(body) == {
        "invite": ("검토가능 심사역 3", "sourcing_intro", SERIES_A),
        "joined": ("참여 심사역 2", "sourcing_remind", SERIES_A),
    }
    bar = body[body.index('id="bucket-filter"'):]
    bar = bar[:bar.index("</div>")]
    # 시리즈 A 의 옛 한 칩은 두 칩으로 갈렸고, 다른 갈래 칩은 그대로다.
    assert bar.count(f'data-value="{html.escape(SERIES_A)}"') == 2
    assert f'data-value="{html.escape(MNA)}"' in bar
