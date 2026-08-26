"""카톡 방 이름 생성/분리 테스트 — 실제 운영 방 이름 규칙 기준."""
from app.services import room_name as rn


def test_build_room_name_matches_real_format():
    """실제 방 이름: '이서준 이사님 다라인베스트먼트 Deal 공유 우리브이씨 Asset'"""
    assert rn.build_room_name("이서준", "이사님", "다라인베스트먼트") == (
        "이서준 이사님 다라인베스트먼트 Deal 공유 우리브이씨 Asset"
    )


def test_build_room_name_adds_honorific():
    # 직함에 '님'이 없으면 붙여서 방 이름을 만든다.
    assert rn.build_room_name("박민수", "심사역", "자차벤처스").startswith("박민수 심사역님 자차벤처스")
    assert rn.build_room_name("박지훈", "파트너", "사아파트너스").startswith("박지훈 파트너님 사아파트너스")


def test_build_room_name_skips_blank_parts():
    out = rn.build_room_name("홍길동", None, "")
    assert out == "홍길동 Deal 공유 우리브이씨 Asset"
    assert "  " not in out  # 공백 중복 없음


def test_build_room_name_custom_suffix():
    out = rn.build_room_name("이서준", "이사님", "다라", suffix="Deal 공유 테스트")
    assert out.endswith("Deal 공유 테스트")


def test_split_name_title():
    assert rn.split_name_title("이서준 이사님") == ("이서준", "이사님")
    assert rn.split_name_title("홍길동 대표님") == ("홍길동", "대표님")
    # '님'이 없어도 알려진 직함이면 분리
    assert rn.split_name_title("박민수 심사역") == ("박민수", "심사역")
    assert rn.split_name_title("박지훈 파트너") == ("박지훈", "파트너")


def test_split_name_title_keeps_unknown_as_name():
    """직함으로 확신할 수 없으면 통째로 이름 — 잘못 분리해 방 이름을 틀리게 만들지 않는다."""
    assert rn.split_name_title("홍길동") == ("홍길동", None)
    assert rn.split_name_title("에이비씨 캐피탈") == ("에이비씨 캐피탈", None)


def test_split_name_title_handles_extra_space():
    assert rn.split_name_title("  이서준   이사님  ") == ("이서준", "이사님")


def test_roundtrip_sheet_cell_to_room_name():
    """시트 한 칸('이서준 이사님') + 투자사명 → 방 이름 자동 생성."""
    name, title = rn.split_name_title("이서준 이사님")
    assert rn.build_room_name(name, title, "다라인베스트먼트") == (
        "이서준 이사님 다라인베스트먼트 Deal 공유 우리브이씨 Asset"
    )

# --- 동명이인 -----------------------------------------------------------------
#
# 카톡 검색은 방 제목뿐 아니라 **참여자 이름으로도** 걸린다. 같은 이름의 다른
# 사람이 있는데 방 이름에 회사가 없으면, 검색 결과 중 어느 쪽이 맞는지 알 수
# 없다. 확인을 시켜 봐야 소용이 없고, 보내고 나서 알면 이미 남의 방이다.

class _C:
    def __init__(self, name, firm, room):
        self.name, self.firm, self.kakao_room_name = name, firm, room


def test_a_room_name_with_the_firm_tells_people_apart():
    assert rn.tells_people_apart("홍길동 이사님 가나벤처스 Deal 공유", "가나벤처스")


def test_a_room_name_without_the_firm_does_not():
    """실제로 `김형준 이사님 Deal 공유 …` 가 이랬다 — 같은 이름이 둘 더 있었다."""
    assert not rn.tells_people_apart("홍길동 이사님 Deal 공유", "가나벤처스")


def test_spacing_and_brackets_do_not_matter():
    """같은 회사를 `한국투자캐피탈` · `한국투자 캐피탈` 로 다르게 적는다."""
    assert rn.tells_people_apart("홍길동 사원님 한국투자 캐피탈 Deal 공유", "한국투자캐피탈")
    assert rn.tells_people_apart("홍길동 수석님 TKG VENTURES CO., LTD. Deal 공유",
                                 "TKG VENTURES")


def test_only_duplicated_names_are_flagged():
    """이름이 하나뿐이면 방 이름에 회사가 없어도 헷갈릴 상대가 없다."""
    people = [_C("홍길동", "가나벤처스", "홍길동 이사님 Deal 공유"),
              _C("김서연", "다라인베스트", "김서연 팀장님 Deal 공유")]
    assert rn.ambiguous_contacts(people) == []


def test_both_sides_of_a_clash_are_flagged():
    people = [_C("홍길동", "가나벤처스", "홍길동 이사님 Deal 공유"),
              _C("홍길동", "다라인베스트", "홍길동 팀장님 다라인베스트 Deal 공유"),
              _C("김서연", "마바캐피탈", "김서연 팀장님 마바캐피탈 Deal 공유")]
    flagged = {c.firm for c in rn.ambiguous_contacts(people)}
    # 회사가 적힌 쪽은 구별된다 — 안 적힌 쪽만 걸린다
    assert flagged == {"가나벤처스"}


def test_an_empty_room_is_flagged_when_the_name_repeats():
    people = [_C("홍길동", "가나벤처스", ""),
              _C("홍길동", "다라인베스트", "홍길동 팀장님 다라인베스트 Deal 공유")]
    assert [c.firm for c in rn.ambiguous_contacts(people)] == ["가나벤처스"]

