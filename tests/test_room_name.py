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
