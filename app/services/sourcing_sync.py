"""딜 소싱 ↔ 투자사 관리 현황 — **한 사람을 한쪽에서 고치면 다른 쪽도 따라온다.**

같은 심사역이 두 표에 산다. 투자사 관리 현황(`vc_contacts` — 딜소개를 보내는
명단)과 딜 소싱(`sourcing_contacts` — 우리 딜을 같이 볼 사람). 지금까지는 두
메뉴에서 따로 적었다 — 투자사 관리 현황에서 "이 분 시리즈 A 딜 소싱 참여하신대"
를 듣고 딜 소싱 메뉴로 가서 이름 · 회사 · 번호를 다시 쳐 넣었다.

## 무엇을 잇나 — 세 갈래(`BRANCHES`)

잇는 것은 **세 갈래의 줄뿐**이다 — `Series A`(`시리즈 A 이상 딜 소싱 참여 심사역`
· `SYNC_BUCKET`) · `M&A`(`M&A 찾는 투자사`) · `구주·후속`(`구주매각 / 후속투자사
…`). 사용자가 정했다(2026-10-21 — 처음에는 시리즈 A 하나였다). `딜 소싱  참여
투자사 대표` · `딜 소싱  개인참여 심사역` 갈래는 예전 그대로 잇지 않는다.

한 투자사 줄은 **갈래마다 한 줄**과 이어진다(유일 색인 `(vc_contact_id, bucket)`
— 이주 `0114`). 같은 분이 Series A 와 M&A 에 다 있으면 두 줄이 그 투자사 줄을
가리킨다. 시리즈 A 에만 있는 일(Series A 딜 공유 · A1 자동 리마인드의 기본
갈래 · 투자사 방을 이어받지 않는 것)은 그대로 시리즈 A 에만 있다.

## 칸은 하나다 — 따로 저장하지 않는다

투자사 관리 현황의 `딜 소싱` 칸은 **값이 없다.** 그 투자사 줄에 이어진 소싱
줄들(`SourcingContact.vc_contact_id`)의 갈래와 `participation` 을 읽어 갈래마다
딱지 하나로 그린다(`chips`) — `Series A·참여` · `M&A·제안 대기중`. `불참여` 인
줄은 흐린 딱지로 남긴다(지우지 않았고 이력이 그 줄에 있다 — 숨기면 빠진 것과
처음부터 없던 것이 같아 보인다). **고른 갈래 = 이어진 줄이 있고 `불참여` 가
아닌 갈래**다. 갈래 하나만 보면 예전 O/X 그대로다.

    이어진 줄 있음 · 불참여        →  X   (흐린 딱지)
    이어진 줄 있음 · 그 밖의 값    →  O   (참여 · 제안 대기중 · 물어보는 중 · 사람이 적은 문구)
    이어진 줄 없음                 →  빈칸

O 는 **"이 갈래에 들어 있다"** 이지 "딜을 받겠다고 했다" 가 아니다. 받는지는
아래 `참여` 칸이 정한다.

그래서 딜 소싱 화면에서 `참여` 를 `불참여` 로 바꾸면 투자사 관리 현황의 그 칸이
그대로 X 가 된다 — 두 화면이 **같은 칸 하나**를 본다. O/X 를 투자사 쪽에
따로 적어 두는 길을 고르지 않은 이유가 그것이다: 두 벌을 맞추는 코드는 반드시
한쪽이 빠지고, 이 저장소가 반복해 당한 사고가 정확히 그 모양이다.

## `참여` 칸 — 딜을 받는 것은 **정확히 `참여`** 인 분뿐이다

    참여                     월간 리마인드 · Series A 딜 공유를 받는다(참여 안내는 안 받는다 — 이미 들어왔다)
    불참여                   안 받는다 — 투자사 관리 현황 칸은 X
    딜 소싱 참여 제안 대기중 참여 안내(처음)만 받는다 — O 로 막 넣은 분. 나가면 `물어보는 중` 으로
    참여 의사를 물어보는 중  참여 안내(처음)만 받는다(다시 보내기) — 동의하시면 `참여` 로 바꾼다
    그 밖의 글(사람이 적음)  참여 안내도 안 받는다 — 뜻을 모른다(`11월에 다시 연락` 같은 메모)

참여 안내(처음)만 `can_get_invite` 를 본다 — 아직 참여하지 않은 분께 참여를 청하는
글이라서다. 그 안내가 `제안 대기중` 인 분께 나가면 그 줄은 저절로 `물어보는 중` 이
된다(`mark_invited`). 나머지 글은 모두 `takes_part` 다.

`takes_part` 가 그 한 자리다. 예전에는 "불참여가 아니면 받는다" 였는데, 그러면
값을 하나 더 들이는 순간 그 값이 `참여` 와 똑같이 딜을 받는다 — 아직 동의하지
않은 분께 딜이 나간다. 그래서 **허용 목록**으로 뒤집었다: 받는 값은 하나다.
발송 화면 · 발송 목록 · A1 소싱 리마인드(자동) · 메일 채널이 모두 이 함수를 지난다.

사람이 적는 문구는 막지 않는다(`normalize_participation` — 앞뒤 공백을 떼고 40자 ·
제어문자 금지). 보기를 따로 저장하지 않는다 — 표의 고르는 창이 같은 칸의 다른 줄
값을 보기로 모아 준다(`inline_edit.js` 의 pick).

## 칸을 고치면 (`set_mark` — 갈래 하나씩, `apply_branches` — 여럿)

칸의 고르는 창은 갈래 셋에 체크 상자 하나씩이다. 체크하면 그 갈래에 O, 풀면 X 다.
`(딜 소개 X)` 가 이름에 붙었거나 그룹이 `딜 소개 보류` 인 분은 **넣지 않는다**
(`intro_blocked` — O 만 막고 X 는 막지 않는다).

    O  이어진 줄이 있으면 — `불참여` 면 `딜 소싱 참여 제안 대기중` 으로(다시 묻는
       것으로 본다). 그 밖의 값(참여 · 제안 대기중 · 물어보는 중 · 문구)은 **덮지 않는다** —
       O 는 갈래에 넣는 것이지 동의를 받았다는 뜻이 아니다.
       없으면 그 갈래에서 **같은 사람**을 찾아 잇고(이름 + 번호가 둘 다 같을 때만 —
       아래 `auto_link` 와 같은 규칙. 이은 줄에도 위 규칙을 그대로 적용한다),
       같은 사람일 수도 있는 줄(번호만 · 이름+회사만 같다)이 있으면 **잇지도
       만들지도 않고 막는다** — 딜 소싱 화면의 후보로 넘긴다. 아무도 없으면
       **새 줄을 `딜 소싱 참여 제안 대기중` 으로 만든다** — 제안도 동의도 아직이다.
    X  이어진 줄을 `불참여` 로. **지우지 않는다** — 리마인드 · `딜 받음` 이력이
       그 줄에 달려 있고, 다시 참여하시면 그대로 돌아온다.
    빈칸  이어진 줄이 없으면 그대로. 이어진 줄이 있으면 **막는다** — 빠지는
       것은 X 다(지우는 것은 딜 소싱 화면의 [삭제]).

## 딜 소싱에서 사람을 넣거나 이름 · 번호를 고치면 (`auto_link`)

그 갈래 줄이고 아직 안 이어졌으면 투자사 관리 현황에서 **이름과 번호가 둘 다
같은** 줄을 찾아 잇는다 — 그 번호가 투자사 쪽에 딱 한 줄이고, 그 줄의 이름도
같을 때만. 그러면 투자사 쪽 칸이 곧바로 O 다. 사용자가 정했다(#28) — "이름+
번호일 때만 저절로, 아니면 사람이 확정". 번호만으로 잇던 때는 번호를 한 자리
잘못 적은 줄이 남의 투자사 줄과 조용히 이어질 수 있었다. 이름만으로는 원래
잇지 않는다 — 같은 이름이 여럿이다(`sourcing_link` 머리말).

잇기가 생기기 전부터 있던 M&A · 구주·후속 줄은 이 길을 지난 적이 없다 — 딜 소싱
화면의 그 탭 [저절로 잇기]가 같은 규칙으로 한꺼번에 잇는다(`auto_link_all`).

이름은 `_key` 로 맞춘다(띄어쓰기를 빼고 소문자로) — 투자사 쪽에서 O 를 넣을 때
같은 분을 찾는 규칙(`find_row` 의 이름+회사)과 **같은 잣대**다. 두 길이 이름을
다르게 읽으면 한쪽에서는 같은 분인데 다른 쪽에서는 남이 된다.

## 저절로 못 이은 줄 — 사람이 확정한다 (`link_candidates` · `confirm_link`)

이름만 같거나(번호가 다르거나 없다), 번호만 같거나, 번호가 투자사 쪽 여러 줄에
맞으면 **잇지 않고 후보로 띄운다** — 딜 소싱 표의 그 줄 이름 아래에 후보와
[이 분으로 확정]. 사람이 고른 줄만 잇는다. 후보는 서버가 다시 세어 보고 그 안에
있을 때만 잇는다(화면이 보낸 번호를 그대로 믿지 않는다). 이을 때의 규칙은 저절로
이을 때와 같다(`link` — 소싱 줄의 빈 칸만 채운다).

이미 이어 둔 줄은 **저절로 풀지 않는다** — 번호로만 이어진 옛 줄(이주 `0093` · #28
전의 `auto_link`)도 그대로다. 규칙이 바뀐 것은 앞으로 저절로 잇는 일뿐이다. 잘못
이은 줄은 사람이 [연결 풀기]로 푼다(`unlink` — 관리자 · 이어진 투자사 줄의 담당,
두 줄 다 지우지 않는다).

사람이 확정한 잇기는 표시해 둔다(`vc_link_confirmed`) — 시트를 다시 가져와 갈래를
갈아 끼워도 그 잇기는 되살린다(`confirmed_links` · `restore_confirmed`). 그 표시가
생기기 전부터 이어져 있던 줄(번호로만 이어진 옛 줄 포함)도 확정으로 친다(이주
`0104`) — 위의 '저절로 풀지 않는다' 가 시트를 다시 가져올 때도 지켜지게.

## 이어진 두 줄의 같은 칸 — **고치면 따라 고친다** (`before_flush`)

이름 · 직함 · 회사 · 휴대폰 · 메일 · 투자분야 · 라운드 사이즈(`SHARED_FIELDS`)는
두 표에 다 있다. 이어진 뒤에 한쪽에서 고치면 다른 쪽에도 같은 값을 적는다.

투자분야는 딜 소싱 표의 `투자분야` 와 투자사 관리 현황의 `선호 투자분야` 가
**같은 칸**이다(둘 다 `sectors`). 라운드 사이즈도 두 표에서 같은 이름이다(#17 —
"두 메뉴의 컬럼이 같으면 어느 쪽에 넣어도 다른 쪽에 자동으로"). 값은 적힌
**글자 그대로** 옮긴다 — 투자사 쪽은 쉼표로 나눠 읽고 딜 소싱 쪽은 글 칸이라,
여기서 고쳐 쓰면 사람이 적은 글이 다른 표에서 바뀌어 보인다.

**메모는 잇지 않는다.** 두 표에 다 `memo` 가 있지만 담는 것이 다르다 — 투자사
쪽은 그 담당의 통화 · 카톡 내용, 딜 소싱 쪽은 딜 소싱 방의 이야기다(사용자가
정했다). 메모를 따라 고치면 한쪽에 적은 이야기가 남의 표 칸을 덮는다.

**왜 '쓸 때 따라 고친다' 인가 — '읽을 때 한쪽에서 가져온다' 가 아니라.**
소싱 줄의 이름 · 회사 · 메일을 읽는 곳이 많다 — 딜 소싱 제안 문구
(`routers/deals.py`), 메일 확인이 보낸 주소를 맞추는 곳(`sourcing_receipts.
addresses_of`), 딜 소싱 표 · 엑셀. 읽는 쪽을 다 고치면 하나는 반드시 빠지고,
빠진 곳만 옛 값을 쓴다. 쓰는 쪽은 **ORM 세션의 flush 한 자리**라(수정 로그
`edit_log` 가 같은 이유로 거기 서 있다) 화면 PATCH · 시트 가져오기 · 검사 어느
길로 고쳐도 빠뜨릴 수 없다. 그리고 투자사 줄이 지워져도 소싱 줄은 자기 값을
그대로 들고 남는다.

**이을 때 서로 다른 값은 덮지 않는다.** 잇는 순간에는 소싱 줄의 **빈 칸만**
투자사 줄 값으로 채운다(`link`). 이미 다르게 적힌 값(직함 · 회사 표기)은 둘 다
사람이 적은 것이라 어느 쪽이 맞는지 코드가 모른다 — 딜 소싱 화면의 연결 표시가
`다른 칸` 으로 알려 주고, 어느 쪽에서든 한 번 고치면 그때부터 같아진다.

**빈 값은 넘어가지 않는다.** 따라 고치는 것은 **빈칸이 아닌 값으로 고친 칸**
뿐이다(`_changed` · `_copy`). None · `""` · 공백은 모두 같은 '빈칸' 이라, 수정창이
비어 있던 칸(None)을 `""` 로 다시 적는 것은 고친 것이 아니다 — 수정창은 칸을
전부 보낸다(`contacts.js` 의 `readForm`). 그것을 고친 것으로 읽으면 메모 한 줄
저장에 이어진 소싱 줄의 메일 · 직함이 지워지고, 메일 확인(`sourcing_receipts.
addresses_of`)이 그분을 못 찾는다(PR #284 리뷰). 한쪽에서 일부러 비워도 다른
쪽은 그대로 둔다 — 비운 칸은 `다른 칸` 으로 보이고, 지우는 것은 각 표에서 한다.

## 잇지 않는 것 — 카톡방 · 담당 · 권한  ★

사용자가 짚었다 — "딜소싱에 있다는건 다른 사람 담당자라도 카톡방에 초대
되어있다는 뜻이므로, 투자사 관리 현황이랑은 다르게 생각해야함". 딜 소싱 줄은
**보내는 사람 카톡의 딜 소싱 방**에 있는 분이고, 투자사 줄을 누가 맡았는지와
따로 관리한다.

  · **카톡방** — 잇지도, 베끼지도, 이어받지도 않는다. 이 갈래 줄은 자기 방
    이름이 없으면 `방 없음` 이고(`sourcing_link.linked_rooms`), 딜 소싱 화면의
    [방 후보 찾기]로 보내는 사람 카톡에서 찾아 확정한다(`sourcing_rooms`).
  · **담당** — 따라 고치지 않는다. O 로 새 줄을 만들 때만 **O 를 넣은 사람**을
    담당으로 적는다(`create_row`) — 그 뒤로는 딜 소싱에서 따로 관리한다.
    한꺼번에 넣는 스크립트(`scripts/apply_sourcing_marks.py`)는 담당 이름을
    직접 넘길 수 있다(`set_mark(..., assignee=)`) — 계정 이름(`users.name`)이 팀이
    딜 소싱 담당 칸에 적어 온 이름과 다를 수 있다. 이어지기만 하는 기존 줄의 담당은
    그때도 바꾸지 않는다.
  · **권한** — 투자사 칸(O/X)은 그 투자사 줄을 고칠 수 있는 사람(담당 · 관리자
    — `routers/contacts._owned`)이다. 딜 소싱 쪽은 지금까지처럼 로그인한 누구나
    고친다(이어진 줄이어도 같다). 이어진 줄의 같은 칸을 딜 소싱에서 고치면 남의
    투자사 줄로도 넘어가는데, 그 일은 수정 로그에 `남의 것` 으로 남는다(`edit_log`).
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional
from urllib.parse import quote

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import get_history

from .. import clock
from ..models import SourcingContact, User, VcContact
from . import edit_log, sheet_owner, sourcing_buckets, sourcing_link

#: 시리즈 A 갈래 — 투자사 관리 현황과 잇는 세 갈래 중 하나이고, Series A 딜 공유 ·
#: A1 자동 리마인드가 보는 갈래다. 원본 시트의 탭 이름 그대로다.
#: 잇는 갈래의 이름은 딜 소싱 화면에서 바꿀 수 없다(`sourcing_buckets.rename`) —
#: 바꾸면 이 글자와 갈려 잇기가 통째로 끊긴다.
#: 견줄 때는 **띄어쓰기를 빼고** 본다(`sourcing_buckets.same`) — 저장된 줄이
#: `딜소싱` 처럼 띄어쓰기만 달라도 이 갈래다. 새 줄은 저장된 글자로 적는다(`create_row`).
SYNC_BUCKET = "시리즈 A 이상 딜 소싱 참여 심사역"
MNA_BUCKET = "M&A 찾는 투자사"
FOLLOW_BUCKET = "구주매각 / 후속투자사 찾는 투자사 / 공동투자사 / 앵커투자사"
#: 투자사 관리 현황의 `딜 소싱` 칸이 고르는 갈래 — `(짧은 이름, 갈래 글자)`.
#: 차례가 딱지 · 고르는 창 · 엑셀 글자의 차례다.
BRANCHES = (("Series A", SYNC_BUCKET), ("M&A", MNA_BUCKET), ("구주·후속", FOLLOW_BUCKET))
SYNC_BUCKETS = tuple(bucket for _label, bucket in BRANCHES)

#: 투자사 관리 현황의 칸 이름. 바로 앞 시트 칸 `딜소싱 참여 투자사`(자유 글)와는
#: 이름이 다르다 — 엑셀 머리글도 이 글자 그대로 찾는다(`sheet_import`).
COLUMN_LABEL = "딜 소싱"
#: 예전 칸 이름 — 엑셀 올리기는 이 머리글도 받는다(O → Series A, X → Series A 불참여).
OLD_COLUMN_LABEL = "Series A 딜 소싱"

JOINED = "참여"
LEFT = "불참여"
#: 갈래에는 넣었지만 아직 동의를 받지 않은 분. 딜을 **받지 않는다**(`takes_part`).
ASKING = "참여 의사를 물어보는 중"
#: O 로 갈래에 막 넣은 분 — 참여 제안도 아직이다. O 로 새 줄이 생길 때의 기본값.
#: 흐름: O → 제안 대기중 → 물어보는 중 → 참여 / 불참여. 딜은 **받지 않는다**.
OFFER_PENDING = "딜 소싱 참여 제안 대기중"
#: 표의 고르는 칸이 먼저 세우는 보기 — 이 밖의 글도 적을 수 있다(`normalize_participation`).
CHOICES = (JOINED, LEFT, OFFER_PENDING, ASKING)
#: 사람이 적는 문구의 최대 길이(앞뒤 공백을 뗀 뒤). 표 칸 하나에 읽히는 길이다.
PARTICIPATION_MAX = 40

#: 화면이 칸 색을 고르는 갈래 — 값이 아니라 **받는가**로 나눈다(`kind_of`).
KIND_JOINED = "joined"
KIND_LEFT = "left"
KIND_PENDING = "pending"     # 물어보는 중 · 사람이 적은 문구 — 안 받는다, 갈래에는 있다

MARK_JOINED = "O"
MARK_LEFT = "X"

#: 같은 뜻으로 받아 주는 말 — 띄어쓰기를 뺀 글자로 견준다(`_key`).
_JOINED_WORDS = {"참여", "o", "○"}
_LEFT_WORDS = {"불참여", "불참", "x", "×"}
_ASKING_WORDS = {"참여의사를물어보는중", "물어보는중", "참여의사확인중"}
_OFFER_PENDING_WORDS = {"딜소싱참여제안대기중", "참여제안대기중", "제안대기중", "제안대기"}
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

#: 두 표에 다 있는 칸 — 이어진 뒤에는 한쪽을 고치면 다른 쪽도 같이 고친다.
#: 두 모델에서 **이름이 같은 칸**만 둔다(`getattr` 한 번으로 양쪽을 읽는다).
#: `memo` 는 일부러 뺐다(모듈 머리말 — 담는 이야기가 다르다).
SHARED_FIELDS = ("name", "title", "firm", "phone", "email", "sectors", "round_size")
#: 화면에 부를 이름. 딜 소싱 표의 머리글과 같은 말이다(투자분야는 투자사 관리
#: 현황에서 `선호 투자분야` 라 부른다 — 같은 칸이다).
SHARED_LABELS = {"name": "이름", "title": "직함", "firm": "회사",
                 "phone": "휴대폰", "email": "이메일",
                 "sectors": "투자분야", "round_size": "라운드 사이즈"}

#: 휴대폰으로 인정할 최소 자릿수 — 방을 잇는 규칙과 **같은 값**이다.
MIN_DIGITS = sourcing_link.MIN_DIGITS


class SyncError(Exception):
    """잇지 못한 까닭. 화면에 그대로 띄운다(400)."""


# ── 값 읽기 ──────────────────────────────────────────────────────────────────

def participation_of(row) -> str:
    """이 줄의 `참여` 칸 — 적힌 글자(앞뒤 공백만 뗀다). 비어 있으면 `참여`(칸의 기본값
    — DB 의 `server_default` 와 같다. 이 칸이 빈 줄은 이 값이 생기기 전 줄뿐이다)."""
    return (getattr(row, "participation", "") or "").strip() or JOINED


def kind_of(value) -> str:
    """`참여` 칸 값(또는 줄) → 화면 갈래 `joined` · `left` · `pending`.

    `pending` 은 `참여 의사를 물어보는 중` 과 사람이 적은 문구 — 딜을 받지 않지만
    갈래에는 있는 분이다. 칸 색 · 빠진 수 세기가 이것으로 나눈다(`sourcing.html` ·
    `deals.js` 가 서버가 실어 준 이 값을 쓴다 — 규칙을 화면에 다시 적지 않는다).
    """
    text = value if isinstance(value, str) else participation_of(value)
    text = (text or "").strip() or JOINED
    if text == JOINED:
        return KIND_JOINED
    if text == LEFT:
        return KIND_LEFT
    return KIND_PENDING


def takes_part(row) -> bool:
    """딜 소싱 제안(월간 리마인드 · Series A 딜 공유)을 받는 사람인가. 참여 안내는 `can_get_invite`.

    **정확히 `참여` 일 때만** 받는다(모듈 머리말 — 허용 목록). `불참여` ·
    `참여 의사를 물어보는 중` · 사람이 적은 문구는 모두 안 받는다. 손으로 보내는 길
    (`routers/deals.py`) · 받을 분 목록(`routers/sourcing.sendable_rows`) · A1 소싱
    리마인드(`services/automations/sourcing_remind.py`)가 이 한 자리를 본다.
    """
    return participation_of(row) == JOINED


#: 참여 안내(처음)를 받는 값 — 제안 대기중 · 물어보는 중(다시 보내기)뿐이다. 참여(이미
#: 들어온 분) · 불참여 · 사람이 적은 문구(뜻을 모른다)는 안 보낸다. 다른 글은 `takes_part`.
INVITE_OK = (OFFER_PENDING, ASKING)
#: 참여 안내 회차의 잡 종류(`routers/deals.py`). 리마인드 · Series A 딜 공유도 같은
#: 종류라 `SendJob.topic` 이 빈 것만 참여 안내다. 시험 발송은 `test_send` 라 안 걸린다.
INVITE_JOB_KIND = "sourcing_intro"


def can_get_invite(row) -> bool:
    """참여 안내(처음)를 받는 사람인가 — `INVITE_OK`. 손으로 보내는 참여 안내 길만 본다."""
    return participation_of(row) in INVITE_OK


def mark_invited(db: Session, item, path: str = "") -> None:
    """참여 안내가 `제안 대기중` 인 분께 **나간 뒤** 그 줄을 `물어보는 중` 으로.

    발송 성공을 적는 자리(카톡 `agent_api.item_result` · 메일 `mail_sender`)가 부른다.
    다른 값(참여 · 불참여 · 문구 · 이미 물어보는 중)은 건드리지 않는다. 수정 로그는
    회차를 만든 사람 이름으로 남긴다 — 이 길에는 요청 문맥이 없다(`edit_log.begin`).
    """
    job = item.job
    if (job is None or job.kind != INVITE_JOB_KIND or job.topic
            or item.sourcing_contact_id is None):
        return
    row = db.get(SourcingContact, item.sourcing_contact_id)
    if row is None or participation_of(row) != OFFER_PENDING:
        return
    db.flush()       # 앞서 바뀐 것(발송 건 상태)은 로그 밖에서 먼저 내보낸다
    token = edit_log.begin(job.user_id, "POST", path)
    try:
        row.participation = ASKING
        db.flush()
    finally:
        edit_log.end(token)


def is_left(row) -> bool:
    """`불참여` 인가 — 딜 소싱에서 **빠진** 분. `물어보는 중` 은 빠진 것이 아니다
    (방 맞추기 · 주소 채우기 같은 준비는 그분도 한다 — `sourcing_rooms` · `sourcing_receipts`)."""
    return participation_of(row) == LEFT


def normalize_participation(value: Optional[str]) -> str:
    """사람이 적은 `참여` 칸 값을 저장할 글자로.

    `참여` · `불참여` · `딜 소싱 참여 제안 대기중` · `참여 의사를 물어보는 중` 은 같은
    뜻의 말(`O` · `x` · `제안 대기` · `물어보는 중` …)을 제 글자로 맞춘다. 그 밖의 글은 **앞뒤 공백만 떼고 그대로**
    둔다 — 막는 것은 빈칸, 제어문자(줄바꿈 · 탭 포함), `PARTICIPATION_MAX` 자 넘는
    글뿐이다. 그런 글은 딜을 받지 않는다(`takes_part`).
    """
    text = (value or "").strip()
    if not text:
        raise SyncError("참여 칸은 비울 수 없습니다 — 빠지시면 '불참여' 로 두세요.")
    if _CONTROL.search(text):
        raise SyncError("참여 칸에는 줄바꿈 · 탭 같은 제어문자를 넣을 수 없습니다.")
    key = _key(text)
    if key in _JOINED_WORDS:
        return JOINED
    if key in _LEFT_WORDS:
        return LEFT
    if key in _ASKING_WORDS:
        return ASKING
    if key in _OFFER_PENDING_WORDS:
        return OFFER_PENDING
    if len(text) > PARTICIPATION_MAX:
        raise SyncError(f"참여 칸은 {PARTICIPATION_MAX}자까지 적습니다({len(text)}자).")
    return text


def normalize_mark(value: Optional[str]) -> str:
    """투자사 관리 현황 칸에 적은 값 → `O` · `X` · 빈칸."""
    text = (value or "").strip()
    if not text:
        return ""
    if text in (MARK_JOINED, "o", "○", JOINED):
        return MARK_JOINED
    if text in (MARK_LEFT, "x", "×", LEFT):
        return MARK_LEFT
    raise SyncError(f"{OLD_COLUMN_LABEL} 칸에는 O(참여) 나 X(불참여) 만 적습니다: {text}")


def mark_of(row: Optional[SourcingContact]) -> str:
    """이어진 소싱 줄 → 그 갈래의 O/X. `불참여` 만 X, 그 밖의 값(참여 ·
    물어보는 중 · 사람이 적은 문구)은 O — **갈래에 들어 있다**는 뜻이다(모듈 머리말)."""
    if row is None:
        return ""
    return MARK_LEFT if is_left(row) else MARK_JOINED


def branch_of(value) -> Optional[str]:
    """줄 · 갈래 글자 · 짧은 이름(`M&A`) → 잇는 갈래의 글자(`BRANCHES`), 아니면 None.
    띄어쓰기는 안 본다(`sourcing_buckets.same`) — 짧은 이름은 대소문자도 안 본다."""
    text = value if isinstance(value, str) else getattr(value, "bucket", "")
    for label, bucket in BRANCHES:
        if sourcing_buckets.same(text, bucket) or _key(text) == _key(label):
            return bucket
    return None


def is_synced(row) -> bool:
    """이 소싱 줄이 투자사 관리 현황과 이어지는 갈래(셋 중 하나)의 줄인가."""
    return branch_of(row) is not None


def is_series_a(row) -> bool:
    """시리즈 A 갈래의 줄인가 — 시리즈 A 에만 있는 일(방을 이어받지 않음 ·
    Series A 딜 공유)이 본다."""
    return sourcing_buckets.same(getattr(row, "bucket", ""), SYNC_BUCKET)


#: `(딜 소개 X)` 가 이름에 붙은 분 · 그룹이 `딜 소개 보류` 인 분 — 딜 소싱에 넣지 않는다.
_NO_INTRO = re.compile(r"\(\s*딜\s*소개\s*x\s*\)", re.IGNORECASE)
_HOLD_GROUP = "딜소개보류"      # `pref_group.HOLD` 를 띄어쓰기 없이


def intro_blocked(contact: VcContact) -> bool:
    """딜 소싱에 넣지 않을 분인가 — 이름에 `(딜 소개 X)` · 그룹이 `딜 소개 보류`."""
    return bool(_NO_INTRO.search(contact.name or "")
                or _HOLD_GROUP in _key(contact.group_name))


def digits(phone: Optional[str]) -> str:
    return sourcing_link.digits(phone)


def _key(text: Optional[str]) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def _text(value) -> str:
    """None · `""` · 공백은 모두 `""` — 같은 '빈칸' 이다."""
    return (value or "").strip() if isinstance(value, str) or value is None else str(value)


def _sector_words(value) -> List[str]:
    """투자분야를 낱말로 — 투자사 관리 현황이 읽는 그대로 쉼표로 나눈다
    (`routers/contacts._split_csv`)."""
    return [w.strip() for w in _text(value).split(",") if w.strip()]


def same_value(field: str, a, b) -> bool:
    """두 표의 같은 칸이 같은 값인가. 휴대폰은 **숫자만** 본다 —
    `010-1234-5678` 과 `01012345678` 은 같은 번호다(잇는 규칙도 숫자로 맞춘다).
    투자분야는 **쉼표 뒤 띄어쓰기**만 다른 것을 같게 본다 — `AI,헬스케어` 와
    `AI, 헬스케어` 는 투자사 관리 현황에서 같은 두 분야로 읽힌다."""
    if field == "phone":
        return digits(_text(a)) == digits(_text(b))
    if field == "sectors":
        return _sector_words(a) == _sector_words(b)
    return _text(a) == _text(b)


def linked_all(db: Session, contact_ids: Iterable[int]) -> Dict[int, Dict[str, SourcingContact]]:
    """투자사 줄 번호 → {갈래 글자(`BRANCHES`): 이어진 소싱 줄}. **한 번에** 읽는다
    (표 한 장에 질의 하나)."""
    ids = [i for i in dict.fromkeys(contact_ids) if i]
    if not ids:
        return {}
    rows = db.execute(
        select(SourcingContact).where(SourcingContact.vc_contact_id.in_(ids))
        .order_by(SourcingContact.id)
    ).scalars().all()
    out: Dict[int, Dict[str, SourcingContact]] = {}
    for r in rows:
        bucket = branch_of(r)
        if bucket is not None:
            out.setdefault(r.vc_contact_id, {}).setdefault(bucket, r)
    return out


def linked_rows(db: Session, contact_ids: Iterable[int],
                bucket: str = SYNC_BUCKET) -> Dict[int, SourcingContact]:
    """투자사 줄 번호 → 그 갈래(기본 시리즈 A)의 이어진 소싱 줄."""
    bucket = branch_of(bucket) or bucket
    return {cid: found[bucket] for cid, found in linked_all(db, contact_ids).items()
            if bucket in found}


def marks_for(db: Session, contact_ids: Iterable[int]) -> Dict[int, str]:
    """투자사 줄 번호 → 시리즈 A 갈래의 `O`/`X`. 이어진 줄이 없는 번호는 빠진다(= 빈칸)."""
    return {cid: mark_of(row) for cid, row in linked_rows(db, contact_ids).items()}


def linked_row(db: Session, contact: VcContact,
               bucket: str = SYNC_BUCKET) -> Optional[SourcingContact]:
    return linked_rows(db, [contact.id], bucket).get(contact.id)


#: 딱지에 적는 짧은 참여 — 칸이 좁다. 사람이 적은 문구는 그대로.
_SHORT = {OFFER_PENDING: "제안 대기중", ASKING: "물어보는 중"}


def cells(found: Dict[str, SourcingContact]) -> dict:
    """한 투자사 줄의 `딜 소싱` 칸 — 표 · 응답 · 엑셀이 이 값 하나를 쓴다.

    `chips` — 갈래마다 딱지(`BRANCHES` 차례). `branches` — 고른 갈래(`불참여` 가
    아닌 줄)의 짧은 이름을 `, ` 로(고르는 창의 값 · 엑셀 글자). `filter` — 머리글
    필터 값(`|` 로 나눔 — 고른 갈래는 `M&A`, 빠진 갈래는 `M&A 불참여`).
    `join` — 시리즈 A 갈래의 O/X(예전 칸 — API · 스크립트가 아직 읽는다).
    """
    chips, picked, tags = [], [], []
    for label, bucket in BRANCHES:
        row = found.get(bucket)
        if row is None:
            continue
        value = participation_of(row)
        on = not is_left(row)
        chips.append({"label": label, "text": f"{label}·{_SHORT.get(value, value)}",
                      "kind": kind_of(row), "on": on,
                      "requested": requested_of(row)})
        if on:
            picked.append(label)
        tags.append(label if on else f"{label} {LEFT}")
    return {"chips": chips, "branches": ", ".join(picked), "filter": "|".join(tags),
            "join": mark_of(found.get(SYNC_BUCKET))}


#: 날짜 뒤에 붙은 시각 — 시트 가져오기가 날짜 칸을 `2026-08-11 00:00:00` 으로 적었다.
_TIME_TAIL = re.compile(r"^(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})\s+\d{1,2}:\d{2}(:\d{2})?$")


def requested_label(value: Optional[str]) -> str:
    """`참여 요청일` 을 화면 · 엑셀에 — 적힌 표기(`2026/05/21` · `2026-07-01`)는 그대로
    두고 **날짜 뒤의 시각만** 뗀다. 저장된 글자는 고치지 않는다(`routers/sourcing.
    requested_on` 머리 주석). 딜 소싱 표와 투자사 관리 현황이 이 한 곳을 쓴다."""
    text = (value or "").strip()
    found = _TIME_TAIL.match(text)
    return found.group(1) if found else text


def requested_of(row: Optional[SourcingContact]) -> str:
    """이어진 소싱 줄 → 투자사 관리 현황의 `참여 요청일` 칸 값(`requested_label`).
    이어진 줄이 없으면 빈칸. 이 칸도 `딜 소싱` 처럼 **저장된 값이 아니다.**
    """
    return "" if row is None else requested_label(row.requested_at)


def _sync_rows(db: Session, bucket: str = SYNC_BUCKET) -> List[SourcingContact]:
    """그 갈래의 줄 전부 — 갈래 글자(띄어쓰기만 다른 것까지)로 **질의에서** 거른다.
    표 전체를 읽어 파이썬에서 거르지 않는다 — O 한 번 · 줄 하나 넣기마다 불린다."""
    return list(db.execute(
        select(SourcingContact)
        .where(SourcingContact.bucket.in_(sourcing_buckets.variants(db, bucket)))
        .order_by(SourcingContact.id)
    ).scalars().all())


def _investors(db: Session) -> List[VcContact]:
    """이을 수 있는 투자사 줄 — 투자사로 세는 명단의 감추지 않은 줄
    (`sheet_owner.investors` — 방을 잇는 `sourcing_link` 와 같은 모집단).
    저절로 잇기와 후보가 **같은 모집단**을 본다."""
    return sheet_owner.investors(db, db.execute(select(VcContact)).scalars().all())


def _sheet_of(contact: VcContact, hidden) -> str:
    """이 투자사 줄을 부를 명단 이름 — 여러 명단에 있으면 투자사로 세는 명단이 먼저."""
    labels = sheet_owner.labels_of(contact.source_sheet)
    return next((label for label in labels if label not in hidden), labels[0])


# ── 같은 사람 찾기 ──────────────────────────────────────────────────────────

def _phone_conflict(row: SourcingContact, phone: str) -> bool:
    """두 줄 다 번호가 있는데 다르다 — 이름 · 회사가 같아도 다른 사람이다."""
    other = digits(row.phone)
    return len(phone) >= MIN_DIGITS and len(other) >= MIN_DIGITS and other != phone


def find_row(db: Session, contact: VcContact,
             bucket: str = SYNC_BUCKET) -> Optional[SourcingContact]:
    """이 투자사 줄과 **같은 사람**인 그 갈래의 소싱 줄 — 이름과 번호가 둘 다 같을 때만.

    같은 사람일 수도 있는 줄을 번호, 없으면 이름+회사로 찾는다. 한 줄로 좁혀질 때만
    본다. 둘 이상이면 어느 줄인지 코드가 고르지 않고 **막는다**(`SyncError`) —
    하나를 골라 두면 반은 틀린다.

    찾은 줄이 이름 · 번호가 **둘 다** 같지 않으면(번호만 같다 · 번호가 없어 이름 ·
    회사만 같다) 잇지 않고 **막는다** — 저절로 잇기(`auto_link`)와 같은 규칙이다(#28).
    번호만으로 이으면 번호를 한 자리 잘못 적은 소싱 줄이 남의 투자사 줄과 조용히
    이어진다(PR #311 리뷰). 새 줄을 만들지도 않는다 — 같은 분이면 한 분께 딜 소싱
    제안이 두 번 나간다. 그 줄에는 이 투자사 줄이 후보로 떠(`link_candidates`) 사람이
    [이 분으로 확정]으로 잇는다.

    찾은 줄이 이미 **다른 투자사 줄**과 이어져 있어도 막는다. 같은 분이 두
    팀원 명단에 한 줄씩 있는 경우인데(`sheet_import` 의 `따로 만들기`), 여기서
    새 줄을 또 만들면 그 분께 딜 소싱 제안이 두 번 나간다.
    """
    rows = _sync_rows(db, bucket)
    phone = digits(contact.phone)

    def pick(same: List[SourcingContact], how: str) -> Optional[SourcingContact]:
        mine = [r for r in same if r.vc_contact_id in (None, contact.id)]
        taken = [r for r in same if r.vc_contact_id not in (None, contact.id)]
        if taken and not mine:
            owner = db.get(VcContact, taken[0].vc_contact_id)
            who = sheet_owner.labels_of(owner.source_sheet)[0] if owner else "다른"
            raise SyncError(
                f"딜 소싱 › {bucket} 의 '{taken[0].name}' 줄이 이미 투자사 관리 "
                f"현황의 다른 줄({who} 명단)과 이어져 있습니다 — 같은 분이면 그 줄에서 "
                "딜 소싱 칸을 고치세요(한 분께 딜 소싱 제안이 두 번 나가지 않게 한 줄만 잇습니다).")
        if len(mine) > 1:
            raise SyncError(
                f"딜 소싱 › {bucket} 에 {how}이 같은 줄이 {len(mine)}개라 어느 줄인지 "
                "정할 수 없습니다 — 딜 소싱 화면에서 겹친 줄을 먼저 정리해 주세요.")
        return mine[0] if mine else None

    found, how = None, ""
    if len(phone) >= MIN_DIGITS:
        found, how = pick([r for r in rows if digits(r.phone) == phone], "번호"), "번호"
    name, firm = _key(contact.name), _key(contact.firm)
    if found is None and name and firm:
        found, how = pick([r for r in rows if _key(r.name) == name and _key(r.firm) == firm
                           and not _phone_conflict(r, phone)], "이름 · 회사"), "이름 · 회사"
    if found is not None and (len(phone) < MIN_DIGITS or link_key(found) != (name, phone)):
        raise SyncError(
            f"딜 소싱 › {bucket} 의 '{found.name}' 줄과 {how}만 같아 잇지 않았습니다 "
            "— 같은 분이면 딜 소싱 화면 그 줄의 [이 분으로 확정]으로 이어 주세요(이름과 "
            "번호가 둘 다 같을 때만 저절로 잇습니다). 다른 분이면 딜 소싱 화면에서 따로 넣으세요.")
    return found


def other_buckets(db: Session, contact: VcContact, bucket: str = SYNC_BUCKET) -> List[str]:
    """같은 번호가 **다른 갈래**에도 있는가 — 그 줄은 건드리지 않았다고 말해 준다."""
    phone = digits(contact.phone)
    if len(phone) < MIN_DIGITS:
        return []
    out: List[str] = []
    for other, raw in db.execute(
        select(SourcingContact.bucket, SourcingContact.phone)
    ).all():
        if (digits(raw) == phone and not sourcing_buckets.same(other, bucket)
                and not any(sourcing_buckets.same(other, b) for b in out)):
            out.append(other)
    return out


# ── 잇기 · 만들기 ───────────────────────────────────────────────────────────

def link(row: SourcingContact, contact: VcContact, confirmed: bool = False) -> List[str]:
    """두 줄을 잇는다. 소싱 줄의 **빈 칸만** 투자사 줄 값으로 채운다.

    이미 적힌 값은 덮지 않는다 — 둘 다 사람이 적은 값이라 어느 쪽이 맞는지
    모른다(모듈 머리말). 투자사 줄은 **건드리지 않는다**: 잇는 일은 소싱 줄
    한 줄에만 적힌다. 돌려주는 것은 채운 칸 이름이다. `confirmed` 는 사람이
    [이 분으로 확정]으로 정했는지 — 시트를 다시 가져올 때 되살릴 잇기다
    (`restore_confirmed`). 이을 때마다 다시 적는다.
    """
    row.vc_contact_id = contact.id
    row.vc_link_confirmed = 1 if confirmed else 0
    filled = []
    for field in SHARED_FIELDS:
        theirs = _text(getattr(contact, field, None))
        if theirs and not _text(getattr(row, field, None)):
            setattr(row, field, theirs)
            filled.append(field)
    return filled


def assignee_for(db: Session, contact: VcContact, user: Optional[User]) -> str:
    """새 소싱 줄의 담당 — **O 를 넣은 사람**. 이름이 없으면 그 투자사 줄의 주인.

    투자사 줄의 주인을 그대로 옮기지 않는 까닭은 모듈 머리말(★)에 있다 — 딜
    소싱은 투자사 줄을 누가 맡았는지와 따로 관리한다. 넣은 사람이 그 분을 딜
    소싱 방에 둔 사람이라고 보는 것이 가장 덜 틀린다. 그 뒤로는 따라 고치지 않는다.
    """
    name = sheet_owner.real_name(user) if user is not None else ""
    if name:
        return name
    owner = db.get(User, contact.user_id) if contact.user_id else None
    return sheet_owner.real_name(owner) if owner is not None else ""


def create_row(db: Session, contact: VcContact, participation: str = OFFER_PENDING,
               user: Optional[User] = None,
               assignee: Optional[str] = None,
               bucket: str = SYNC_BUCKET) -> SourcingContact:
    """그 갈래 맨 아래에 새 줄. 카톡방은 **비워 둔다** — 보내는 사람 카톡에서
    [방 후보 찾기]로 찾는다(모듈 머리말 ★).

    참여는 기본 `딜 소싱 참여 제안 대기중` — O 는 갈래에 넣는 것이지 동의를 받았다는
    뜻이 아니다(모듈 머리말). 동의하시면 딜 소싱 화면에서 `참여` 로 바꾼다.
    담당은 `assignee` 를 넘기면 그 이름, 아니면 O 를 넣은 사람(`assignee_for`).

    갈래 글자는 **저장된 그대로** 쓴다(`sourcing_buckets.label_of`) — 줄들이
    `딜소싱` 으로 들어 있는데 코드의 글자로 만들면 딜 소싱 화면에 탭이 둘 선다.
    """
    last = db.execute(
        select(func.max(SourcingContact.position))
        .where(SourcingContact.bucket.in_(sourcing_buckets.variants(db, bucket)))
    ).scalar() or 0
    row = SourcingContact(
        bucket=sourcing_buckets.label_of(db, bucket), position=last + 1,
        name=_text(contact.name) or "(이름 없음)",
        title=_text(contact.title) or None,
        firm=_text(contact.firm) or None,
        phone=_text(contact.phone) or None,
        email=_text(contact.email) or None,
        # 같은 칸(`SHARED_FIELDS`)은 새 줄에도 실어 둔다 — 안 실으면 이을 때는
        # 채워지는 칸이 만들 때만 비어, 어느 길로 들어왔느냐에 따라 줄이 다르다.
        sectors=_text(contact.sectors) or None,
        round_size=_text(contact.round_size) or None,
        assignee_name=_text(assignee) or assignee_for(db, contact, user) or None,
        # 갈래에 넣은 날 — 이 명단은 참여 요청일 최신순이라 방금 넣은 분이 맨 위다.
        requested_at=clock.today().isoformat(),
        room_verified="unverified",
        participation=normalize_participation(participation),
        vc_contact_id=contact.id,
    )
    db.add(row)
    return row


#: `set_mark` 가 한 일 — 한꺼번에 넣는 스크립트가 센다(`scripts/apply_sourcing_marks.py`).
ACT_NONE = "none"          # 빈칸 — 아무것도 안 함
ACT_CREATED = "created"    # 갈래에 새 줄
ACT_LINKED = "linked"      # 갈래에 있던 줄과 이음
ACT_CHANGED = "changed"    # 이미 이어진 줄의 참여만 바꿈
ACT_KEPT = "kept"          # 이미 이어져 있고 바꿀 것이 없음


def set_mark(db: Session, contact: VcContact, value: Optional[str],
             user: Optional[User] = None, assignee: Optional[str] = None,
             participation: str = OFFER_PENDING, bucket: str = SYNC_BUCKET) -> dict:
    """투자사 관리 현황의 `딜 소싱` 칸에서 **갈래 하나**(`bucket` — 기본 시리즈 A)를
    O/X 로 고친다(예전 `Series A 딜 소싱` 칸이 시리즈 A 하나로 하던 일 그대로).

    O 의 규칙(모듈 머리말): 새 줄은 `participation`(기본 `딜 소싱 참여 제안 대기중`)으로
    만들고, 이어진 줄이 `불참여` 면 `participation` 으로 되돌린다(다시 묻는다). 이어진
    줄이 `참여` · `물어보는 중` · 사람이 적은 문구면 **덮지 않는다**. `assignee` 는 새 줄의
    담당(넘기지 않으면 O 를 넣은 사람) — 이어지기만 하는 줄의 담당은 안 바꾼다.

    돌려주는 것: `{"mark": 지금 칸 값, "message": 화면에 띄울 한 줄,
    "action": ACT_*, "participation": 이어진 줄의 참여(없으면 빈 글자)}`.
    `db.commit()` 은 부르는 쪽이 한다. 못 하는 까닭은 `SyncError`.
    """
    bucket = branch_of(bucket) or bucket
    mark = normalize_mark(value)
    row = linked_row(db, contact, bucket)
    if mark == MARK_JOINED and (row is None or is_left(row)) and intro_blocked(contact):
        raise SyncError(
            f"'{contact.name}' 은 이름에 `(딜 소개 X)` 가 붙었거나 그룹이 `딜 소개 보류` 라 "
            "딜 소싱에 넣지 않습니다 — 넣어야 하는 분이면 투자사 관리 현황에서 그 표시를 "
            "먼저 거두세요.")
    if not mark:
        if row is not None:
            raise SyncError(
                f"딜 소싱 › {bucket} 에 이어진 분이라 비울 수 없습니다 — 빠지시면 "
                "X(불참여)로 두세요. 줄을 아예 빼려면 딜 소싱 화면에서 [삭제] 합니다.")
        return {"mark": "", "message": "", "action": ACT_NONE, "participation": ""}

    revive = normalize_participation(participation)
    message = ""
    action = ACT_KEPT
    if row is None:
        if not sheet_owner.on_investor_list(contact, sheet_owner.hidden_labels(db)):
            raise SyncError("투자사 명단의 줄만 딜 소싱에 넣습니다 — 이 줄은 투자사로 "
                            "세지 않는 명단에 있습니다.")
        row = find_row(db, contact, bucket)
        if row is not None:
            link(row, contact)
            action = ACT_LINKED
            message = f"딜 소싱 › {bucket} 에 있던 '{row.name}' 줄과 이었습니다."
        elif mark == MARK_LEFT:
            raise SyncError(
                f"딜 소싱 › {bucket} 에 없는 분이라 X 로 둘 줄이 없습니다 — "
                "빈칸이 '딜 소싱에 없음' 입니다.")
        else:
            row = create_row(db, contact, revive, user, assignee=assignee, bucket=bucket)
            action = ACT_CREATED
            message = (f"딜 소싱 › {bucket} 에 '{row.participation}' 으로 새로 "
                       "넣었습니다 — 카톡방은 딜 소싱 화면의 [방 후보 찾기]로 보내는 분 "
                       "카톡에서 찾아 확정하세요.")
            if not takes_part(row):
                message += (" 동의하시면 딜 소싱 화면의 `참여` 칸을 '참여' 로 바꿔야 "
                            "딜이 나갑니다.")
            others = other_buckets(db, contact, bucket)
            if others:
                message += (f" 다른 갈래({', '.join(others)})에도 있는 분이라 그 줄은 "
                            "그대로 둡니다.")
            return {"mark": mark_of(row), "message": message, "action": action,
                    "participation": participation_of(row)}

    if mark == MARK_LEFT:
        want = LEFT if not is_left(row) else None
    else:
        # O — `불참여` 만 되돌린다(다시 묻는다). 참여 · 물어보는 중 · 문구는 그대로.
        want = revive if is_left(row) else None
    if want is not None and participation_of(row) != want:
        row.participation = want
        if action == ACT_KEPT:
            action = ACT_CHANGED
        note = f"딜 소싱 › {bucket} 에서 '{want}' 으로 바꿨습니다."
        message = f"{message} {note}".strip()
    return {"mark": mark, "message": message, "action": action,
            "participation": participation_of(row)}


def parse_branches(text: Optional[str]) -> Dict[str, bool]:
    """`Series A, M&A 불참여` → `{시리즈 A 갈래: True, M&A 갈래: False}`.

    쉼표로 나눈 낱말마다 짧은 이름(`BRANCHES` — 갈래 글자도 받는다). 뒤에
    `불참여`(또는 `X`)가 붙으면 그 갈래를 빼는 것이다. 모르는 낱말은 막는다 —
    조용히 버리면 넣었다고 생각한 갈래가 빠진다. 엑셀 올리기 · 표의 고르는 창이 함께 쓴다.
    """
    out: Dict[str, bool] = {}
    for word in (text or "").split(","):
        word = word.strip()
        if not word:
            continue
        on = True
        tail = re.search(r"[\s·(]*(불참여|x)\)?$", word, re.IGNORECASE)
        if tail and branch_of(word[:tail.start()]):
            word, on = word[:tail.start()], False
        bucket = branch_of(word)
        if bucket is None:
            names = " · ".join(label for label, _b in BRANCHES)
            raise SyncError(f"{COLUMN_LABEL} 칸에는 {names} 만 적습니다: {word}")
        out[bucket] = on
    return out


def apply_branches(db: Session, contact: VcContact, wanted: Dict[str, bool],
                   user: Optional[User] = None) -> dict:
    """갈래마다 넣고(True) 뺀다(False) — 바뀌는 갈래만 `set_mark` 를 부른다.

    지금 고른 갈래(이어진 줄이 있고 `불참여` 가 아님)와 같으면 아무것도 안 한다 —
    그래야 `물어보는 중` 인 줄에 다시 O 를 보내 값을 흔들지 않고, 이어진 줄이 없는
    갈래에 X 를 보내 막히지 않는다. 돌려주는 것은 `{"message": 화면에 띄울 말}`.
    `db.commit()` 은 부르는 쪽이 한다. 못 하는 까닭은 `SyncError`(한 갈래라도 막히면
    부르는 쪽이 통째로 되돌린다).
    """
    found = linked_all(db, [contact.id]).get(contact.id, {})
    notes = []
    for _label, bucket in BRANCHES:
        if bucket not in wanted:
            continue
        row = found.get(bucket)
        if wanted[bucket] == (row is not None and not is_left(row)):
            continue
        got = set_mark(db, contact, MARK_JOINED if wanted[bucket] else MARK_LEFT,
                       user, bucket=bucket)
        if got["message"]:
            notes.append(got["message"])
        db.flush()      # 다음 갈래의 `find_row` 가 방금 이은 줄을 보게
    return {"message": " ".join(notes)}


def link_key(row) -> tuple:
    """저절로 잇기가 보는 값 — (맞춘 이름, 번호 숫자). 딜 소싱에서 줄을 고쳐
    이 값이 바뀌었을 때만 `auto_link` 를 다시 부른다(`routers/sourcing.update_row`)."""
    return _key(getattr(row, "name", None)), digits(getattr(row, "phone", None))


def auto_link(db: Session, row: SourcingContact) -> Optional[VcContact]:
    """딜 소싱 쪽에서 넣거나 이름 · 번호를 고친 줄 — 투자사 관리 현황의 같은 분과 잇는다.

    **번호가 투자사 쪽 딱 한 줄에만 맞고, 그 줄의 이름도 같을 때만**이다(#28 —
    모듈 머리말). 투자사 쪽에 같은 번호가 둘이거나(두 팀원 명단에 한 줄씩),
    번호는 맞는데 이름이 다르거나, 이 갈래에 같은 번호가 또 있거나, 맞은 투자사
    줄이 이미 다른 소싱 줄과 이어져 있으면 잇지 않는다 — 그런 줄은 딜 소싱 표에
    후보로 뜨고 사람이 확정한다(`link_candidates`). 투자사로 세는 명단만 본다
    (`_investors`).

    이주(`0093_sourcing_vc_link`)가 처음 한 번 이은 규칙은 번호만 봤다. 그때 이은
    줄은 풀지 않는다 — 이주는 고치지 않는다(이미 돈 판이다).

    잇는 세 갈래(`BRANCHES`) 모두 같은 규칙이다 — 맞은 투자사 줄이 **같은 갈래**의
    다른 줄과 이어져 있을 때만 막는다(다른 갈래와 이어진 것은 괜찮다). `참여` 칸은
    건드리지 않는다(`link` 는 빈 칸만 채운다).
    """
    bucket = branch_of(row)
    if bucket is None or row.vc_contact_id:
        return None
    name, phone = link_key(row)
    if not name or len(phone) < MIN_DIGITS:
        return None
    if any(digits(other.phone) == phone for other in _sync_rows(db, bucket)
           if other.id != row.id):
        return None
    contacts = [c for c in _investors(db) if digits(c.phone) == phone]
    if len(contacts) != 1 or _key(contacts[0].name) != name:
        return None
    contact = contacts[0]
    if linked_row(db, contact, bucket) is not None:
        return None
    link(row, contact)
    return contact


def auto_link_all(db: Session, bucket: str) -> int:
    """그 갈래의 안 이어진 줄을 모두 `auto_link` 로 — 딜 소싱 화면의 [저절로 잇기].

    시리즈 A 밖의 갈래(M&A · 구주·후속)는 잇기가 생기기 전부터 있던 줄이라 한 번도
    저절로 잇기를 지나지 않았다. 이주로 몰래 잇지 않고 화면에서 사람이 눌러 돌린다
    (사용자 결정 2026-10-21). 못 이은 줄은 그대로 후보로 뜬다. 돌려주는 것은 이은 수.
    `db.commit()` 은 부르는 쪽이 한다.
    """
    done = 0
    for row in _sync_rows(db, bucket):
        if auto_link(db, row) is not None:
            db.flush()      # 다음 줄이 방금 이은 투자사 줄을 '이미 이어짐' 으로 보게
            done += 1
    return done


def _person_label(contact: VcContact) -> str:
    """`홍길동 심사역 (가나벤처스)` — 후보 한 분. IR 기업 현황의 [이 분으로 확정]
    후보와 같은 모양이다(`series_a_share._person_label`)."""
    who = " ".join(x for x in (_text(contact.name), _text(contact.title)) if x)
    firm = _text(contact.firm)
    return f"{who} ({firm})" if firm else who


def link_candidates(db: Session, rows: Iterable[SourcingContact]) -> Dict[int, List[dict]]:
    """저절로 못 이은 줄의 **후보** — 딜 소싱 표의 [이 분으로 확정].

    `{소싱 줄 번호: [{"id", "label", "sheet", "name_match", "phone_match"}]}`.
    그 갈래의 **안 이어진 줄마다** 한 칸이 선다(후보가 없으면 빈 목록 — 화면은
    숨긴다. 칸이 있어야 이름 · 번호를 고친 뒤 그 자리에 다시 그린다).

    후보는 이름(`_key`)이나 번호(숫자 `MIN_DIGITS` 자리 이상)가 같은 투자사 줄이다.
    모집단은 저절로 잇기와 같고(`_investors` — 감춘 줄 · 투자사로 세지 않는 명단은
    빠진다), **같은 갈래의 다른 소싱 줄과 이미 이어진 투자사 줄은 빠진다** — 한
    투자사 줄에는 갈래마다 소싱 줄이 하나뿐이다(유일 색인 · 한 분께 같은 딜 소싱
    제안이 두 번 나가지 않게).
    차례는 이름 · 번호 둘 다 같은 줄 → 번호만 → 이름만.
    """
    rows = [r for r in rows if is_synced(r) and not r.vc_contact_id]
    if not rows:
        return {}
    # 한 투자사 줄은 **갈래마다** 한 줄과 이어진다 — 같은 갈래에 이미 이어진 줄만 뺀다.
    taken = {(cid, branch_of(bucket)) for cid, bucket in db.execute(
        select(SourcingContact.vc_contact_id, SourcingContact.bucket)
        .where(SourcingContact.vc_contact_id.is_not(None))
    ).all()}
    by_name: Dict[str, List[VcContact]] = {}
    by_phone: Dict[str, List[VcContact]] = {}
    for c in _investors(db):
        name, phone = _key(c.name), digits(c.phone)
        if name:
            by_name.setdefault(name, []).append(c)
        if len(phone) >= MIN_DIGITS:
            by_phone.setdefault(phone, []).append(c)
    hidden = sheet_owner.hidden_labels(db)
    out: Dict[int, List[dict]] = {}
    for row in rows:
        name, phone = link_key(row)
        found = {c.id: c for c in by_name.get(name, [])}
        if len(phone) >= MIN_DIGITS:
            found.update((c.id, c) for c in by_phone.get(phone, []))
        bucket = branch_of(row)
        found = {cid: c for cid, c in found.items() if (cid, bucket) not in taken}
        cands = [{"id": c.id, "label": _person_label(c), "sheet": _sheet_of(c, hidden),
                  "name_match": bool(name) and _key(c.name) == name,
                  "phone_match": len(phone) >= MIN_DIGITS and digits(c.phone) == phone}
                 for c in found.values()]
        cands.sort(key=lambda x: (not (x["name_match"] and x["phone_match"]),
                                  not x["phone_match"], x["label"], x["id"]))
        out[row.id] = cands
    return out


def confirm_link(db: Session, row: SourcingContact, contact_id: Optional[int]) -> List[str]:
    """[이 분으로 확정] — 사람이 고른 투자사 줄과 잇는다. 돌려주는 것은 채운 칸.

    **후보를 다시 세어 보고 그 안에 있을 때만** 잇는다 — 화면이 보낸 번호를 믿지
    않는다(그 사이 다른 사람이 그 투자사 줄을 다른 소싱 줄과 이었을 수 있다).
    이는 일 자체는 저절로 이을 때와 같다(`link` — 빈 칸만 채운다).
    `db.commit()` 은 부르는 쪽이 한다. 못 하는 까닭은 `SyncError`.
    """
    if not is_synced(row):
        names = " · ".join(label for label, _b in BRANCHES)
        raise SyncError(f"딜 소싱의 {names} 갈래 줄만 투자사 관리 현황과 잇습니다.")
    if row.vc_contact_id:
        raise SyncError("이미 투자사 관리 현황의 줄과 이어져 있습니다 — 새로고침해 보세요.")
    picks = {c["id"] for c in link_candidates(db, [row]).get(row.id, [])}
    contact = db.get(VcContact, contact_id) if contact_id in picks else None
    if contact is None:
        raise SyncError(
            "이 줄의 후보가 아닙니다 — 이름이나 번호가 같고 아직 다른 딜 소싱 줄과 "
            "이어지지 않은 투자사 줄만 고를 수 있습니다. 새로고침해 후보를 다시 보세요.")
    return link(row, contact, confirmed=True)


def unlink(row: SourcingContact) -> None:
    """[연결 풀기] — 잘못 이은 잇기를 푼다. **두 줄 다 지우지 않는다** — 소싱 줄의
    `vc_contact_id` 만 비운다(투자사 줄을 지울 때의 `detach` 와 같은 끝). 그쪽
    `딜 소싱` 칸에서 그 갈래가 빠지고, 같은 칸을 따라 고치는 것도 멈춘다. 그 줄은 다시
    후보로 뜬다. `db.commit()` 은 부르는 쪽이 한다."""
    row.vc_contact_id = None
    row.vc_link_confirmed = 0


def confirmed_links(rows: Iterable[SourcingContact]) -> List[tuple]:
    """사람이 확정한 잇기 — 시트를 다시 가져오기 **전에** 적어 둔다.
    `(이름 열쇠, 번호 숫자, 투자사 줄 번호)` — 되살리는 것은 `restore_confirmed`."""
    return [(*link_key(r), r.vc_contact_id) for r in rows
            if r.vc_contact_id and r.vc_link_confirmed and is_synced(r)]


def restore_confirmed(db: Session, rows: List[SourcingContact], kept: List[tuple]) -> int:
    """다시 가져온 줄에 사람이 확정해 둔 잇기를 되살린다(사용자 결정 2026-10-17) —
    이름 · 번호가 둘 다 안 맞아도(그래서 사람이 확정했다). 다시 후보로 띄우지 않는다.

    같은 분은 이름(`_key`)으로 찾고, 같은 이름이 여럿이면 번호까지 같은 줄이다. 그분이
    시트에서 빠졌거나, 투자사 줄이 없어졌거나, 그 줄이 이미 다른 소싱 줄과 이어졌으면
    잇지 않는다. 그 투자사 줄이 그사이 감춰졌거나 투자사로 세지 않는 명단으로 갔어도
    잇지 않는다 — 저절로 잇기 · 후보와 같은 모집단(`_investors`)만 잇는다. 저절로
    잇기(`auto_link`)보다 **먼저** 부른다 — 그래야 확정해 둔 투자사 줄을 다른 줄이 먼저
    가져가지 않는다. 돌려주는 것은 되살린 수.
    """
    if not kept:
        return 0
    linkable = {c.id for c in _investors(db)}
    done = 0
    for name, phone, contact_id in kept:
        same = [r for r in rows if _key(r.name) == name and not r.vc_contact_id]
        if len(same) > 1:
            same = [r for r in same if digits(r.phone) == phone]
        contact = db.get(VcContact, contact_id) if contact_id in linkable else None
        if (len(same) != 1 or contact is None
                or linked_row(db, contact, branch_of(same[0]) or SYNC_BUCKET) is not None):
            continue
        link(same[0], contact, confirmed=True)
        done += 1
    return done


def kept_participation(rows: Iterable[SourcingContact]) -> List[tuple]:
    """시트를 다시 가져오기 **전에** — `참여` 가 아닌 줄의 `(이름 열쇠, 번호 숫자, 값)`.

    시트에는 `참여` 칸이 없다. 갈래를 통째로 갈아 끼우면 새 줄은 기본값 `참여` 가
    되어, `불참여` · `참여 의사를 물어보는 중` 이던 분이 **딜을 받는 분이 된다**
    (`takes_part`). 그래서 갈아 끼우기 전에 적어 두고 `restore_participation` 으로
    되살린다. 어느 갈래에서든 같다(받는 판정은 갈래를 가리지 않는다).
    """
    return [(*link_key(r), participation_of(r)) for r in rows if not takes_part(r)]


def restore_participation(rows: List[SourcingContact], kept: List[tuple]) -> int:
    """다시 가져온 줄에 적어 둔 `참여` 칸을 되살린다. 같은 분은 이름(`_key`)으로 찾고,
    같은 이름이 여럿이면 번호까지 같은 줄이다(`restore_confirmed` 와 같은 손). 한 줄로
    안 좁혀지면 건드리지 않는다. 돌려주는 것은 되살린 수."""
    done = 0
    for name, phone, value in kept:
        same = [r for r in rows if _key(r.name) == name]
        if len(same) > 1:
            same = [r for r in same if digits(r.phone) == phone]
        if len(same) != 1:
            continue
        same[0].participation = value
        done += 1
    return done


# ── 화면 ────────────────────────────────────────────────────────────────────

def badges(db: Session, rows: Iterable[SourcingContact]) -> Dict[int, dict]:
    """딜 소싱 표의 연결 표시 — `투자사 관리 현황: ○○ 명단`.

    `{소싱 줄 번호: {"sheet": 명단 이름, "href": 그 명단 주소, "diff": [다른 칸 이름],
    "title": 풍선말}}`. `diff` 는 **이을 때 이미 달랐던 칸**이다(모듈 머리말) —
    어느 쪽에서든 한 번 고치면 같아진다. `title` 은 **어느 칸이 같이 바뀌는지**다 —
    칸 목록(`SHARED_FIELDS`)에서 만든다. 화면에 칸 이름을 적어 두면 칸이 늘 때
    (#17 투자분야 · 라운드 사이즈) 말만 옛것으로 남는다. 서버가 그리는 표시
    (`sourcing.html`)와 [이 분으로 확정] 뒤 화면이 그리는 표시(`sourcing_vc_link.js`)가
    이 값 하나를 쓴다.
    """
    rows = [r for r in rows if r.vc_contact_id and is_synced(r)]
    if not rows:
        return {}
    contacts = {c.id: c for c in db.execute(
        select(VcContact).where(VcContact.id.in_({r.vc_contact_id for r in rows}))
    ).scalars().all()}
    hidden = sheet_owner.hidden_labels(db)
    shared = " · ".join(SHARED_LABELS[f] for f in SHARED_FIELDS)
    out: Dict[int, dict] = {}
    for row in rows:
        contact = contacts.get(row.vc_contact_id)
        if contact is None:
            continue
        sheet = _sheet_of(contact, hidden)
        out[row.id] = {
            "contact_id": contact.id,
            # 이어진 투자사 줄의 담당 — [연결 풀기]를 누를 수 있는 사람 중 하나
            # (`routers/sourcing._may_unlink`).
            "owner_id": contact.user_id,
            "sheet": sheet,
            "href": f"{sheet_owner.page_href(db, sheet)}?sheet={quote(sheet)}",
            "diff": [SHARED_LABELS[f] for f in SHARED_FIELDS
                     if not same_value(f, getattr(row, f, None),
                                       getattr(contact, f, None))],
            "title": f"두 화면이 같이 바뀌는 칸: {shared} (메모는 따로)",
        }
    return out


# ── 따라 고치기 · 끊기 — 세션 flush 한 자리 ─────────────────────────────────

def _changed(obj) -> List[str]:
    """이번 flush 에서 **빈칸 아닌 값으로 실제로 바뀐** 같은 칸.

    빠지는 것: 같은 값을 다시 적은 것, None ↔ `""` ↔ 공백처럼 빈칸끼리 바뀐 것
    (수정창이 빈 칸을 `""` 로 다시 적는다), 비운 것(빈 값은 넘어가지 않는다 —
    모듈 머리말).
    """
    out = []
    for field in SHARED_FIELDS:
        history = get_history(obj, field)
        if not history.added:
            continue
        after = _text(history.added[0])
        before = _text(history.deleted[0]) if history.deleted else ""
        if after and after != before:
            out.append(field)
    return out


def _copy(src, dst, field: str) -> bool:
    value = _text(getattr(src, field, None))
    if not value:
        # 빈 값은 다른 쪽을 지우지 않는다(모듈 머리말). 이름은 원래 비울 수 없다.
        return False
    if value == _text(getattr(dst, field, None)):
        return False
    setattr(dst, field, value)
    return True


def detach(session: Session, contact_ids: List[int]) -> None:
    """지워지는 투자사 줄을 가리키던 소싱 줄의 연결만 끊는다 — 줄은 남긴다.

    DB 에는 **먼저 바로 적는다**(Core UPDATE). 같은 flush 안에서 소싱 줄을
    고치고 투자사 줄을 지우면, 둘 사이에 관계(`relationship`)가 없어 어느 쪽이
    먼저 나갈지 SQLAlchemy 가 모른다 — 지우기가 먼저 나가면 외래키에 막힌다.
    여기서 먼저 적어 두면 차례를 탈 일이 없다.

    그다음 그 소싱 줄들을 세션에 올려 **ORM 으로도 같은 값**(None)을 적는다 —
    수정 로그(`edit_log`)는 flush 의 바뀐 줄만 읽으므로, 그래야 '끊김' 이
    `vc_contact_id: 번호 → 빈칸` 으로 남는다(PR #284 리뷰 — 잇기 · 만들기는
    남는데 끊기만 빠졌다). 이 ORM UPDATE 는 이미 NULL 인 칸에 NULL 을 다시
    적으므로 지우기보다 늦게 나가도 외래키에 걸리지 않는다. 이 훅은 수정 로그의
    `before_flush` 보다 먼저 걸린다(`models._sync_sourcing_links`).
    """
    ids = [i for i in contact_ids if i]
    if not ids:
        return
    with session.no_autoflush:
        rows = list(session.execute(
            select(SourcingContact).where(SourcingContact.vc_contact_id.in_(ids))
        ).scalars().all())
    # 세션에서 이번 flush 에 막 이어 둔 줄(아직 DB 에 안 적힌 값)도 함께.
    rows += [obj for obj in list(session.identity_map.values())
             if isinstance(obj, SourcingContact) and obj.vc_contact_id in ids
             and obj not in rows]
    table = SourcingContact.__table__
    session.execute(table.update().where(table.c.vc_contact_id.in_(ids))
                    .values(vc_contact_id=None))
    for obj in rows:
        if obj not in session.deleted:
            obj.vc_contact_id = None


def before_flush(session: Session) -> None:
    """flush 직전 — 지워지는 투자사 줄은 끊고, 이어진 두 줄의 같은 칸을 맞춘다.

    `app/models.py` 가 세션 이벤트로 건다(모든 flush 가 지난다).

    한 투자사 줄에 갈래마다 한 줄씩 이어질 수 있다(`BRANCHES`) — 한 줄을 고치면
    투자사 줄과 **다른 갈래의 이어진 줄**에도 같은 값을 적는다.

    **한 칸을 두 쪽에서 동시에 고친 flush** 는 투자사 쪽 값이 이긴다 — 먼저
    투자사 → 소싱으로 옮기고, 이미 옮긴 칸은 거꾸로 옮기지 않는다. 화면에서는
    한 번에 한 쪽만 고치므로 생길 일이 거의 없지만, 순서가 정해져 있어야 같은
    입력에 늘 같은 결과가 나온다.
    """
    gone = [o.id for o in session.deleted if isinstance(o, VcContact) and o.id]
    if gone:
        detach(session, gone)

    dirty = list(session.dirty)
    contacts = {}
    for obj in dirty:
        if isinstance(obj, VcContact) and obj not in session.deleted and obj.id:
            changed = _changed(obj)
            if changed:
                contacts[obj.id] = (obj, changed)
    wrote = set()
    if contacts:
        with session.no_autoflush:
            linked = session.execute(
                select(SourcingContact).where(
                    SourcingContact.vc_contact_id.in_(list(contacts)))
            ).scalars().all()
        for row in linked:
            if row in session.deleted or not is_synced(row):
                continue
            obj, changed = contacts[row.vc_contact_id]
            for field in changed:
                if _copy(obj, row, field):
                    wrote.add((id(row), field))

    for row in dirty:
        if (not isinstance(row, SourcingContact) or row in session.deleted
                or not row.vc_contact_id or not is_synced(row)):
            continue
        changed = [f for f in _changed(row) if (id(row), f) not in wrote]
        if not changed:
            continue
        with session.no_autoflush:
            contact = session.get(VcContact, row.vc_contact_id)
            # 같은 투자사 줄에 이어진 **다른 갈래의 줄**도 같이 — 투자사 줄을 고친 것은
            # 이 flush 의 위 고리가 이미 지났으니 여기서 직접 옮긴다.
            siblings = session.execute(select(SourcingContact).where(
                SourcingContact.vc_contact_id == row.vc_contact_id,
                SourcingContact.id != row.id)).scalars().all()
        if contact is None or contact in session.deleted:
            continue
        for field in changed:
            _copy(row, contact, field)
            for sib in siblings:
                # 그 줄도 이번에 같은 칸을 고쳤으면 그 줄 값을 둔다(제 손으로 고친 값).
                if (sib not in session.deleted and is_synced(sib)
                        and field not in _changed(sib)):
                    _copy(row, sib, field)
