"""`계약서를 받았는가` 를 적는 자리가 **세 곳으로 갈려 있다**는 사실을 못 박는다.

주석은 낡는다. 그래서 사실 쪽을 여기서 잠근다 — 누가 "중복이네" 하고 조용히
셋을 하나로 모으거나, 반대로 하나인 줄 알고 한쪽만 보고 세면 이 시험이
깨지고, 그때 `models.IrCompany.contract_received` 의 주석을 읽게 된다.

지금 세 자리는 이렇다.

    `스타트업` 명단      `VcContact.notes["invoice_received"]`
    `투자컨설턴트`       `ConsultingCompany.contract_received`
    `딜 진행 관리`       `IrCompany.contract_received`

**이 시험은 합치는 것을 막지 않는다.** 합치는 것이 틀렸다는 뜻이 아니라,
세 표 사이에 외래키가 없고 `스타트업`↔`투자컨설턴트` 는 기업명으로 맞춰도
겹치는 곳이 0이라 **칸을 모으기 전에 기업 목록부터 이어야 한다**는 것이다.
합치는 일을 진짜로 한다면 이 시험도 그때 같이 고쳐 쓴다.
"""
from __future__ import annotations

from app.models import ConsultingCompany, IrCompany, VcContact
from app.services import contact_columns as cc


def test_스타트업_계약서_수신여부는_notes의_invoice_received에만_담긴다():
    """`스타트업` 명단의 그 칸은 **테이블 칸이 아니라 `notes` 의 열쇠**다.

    머리글은 `계약서 수신여부` 인데 열쇠는 `invoice_received` 로 어긋나 있다
    (이름만 바꾸고 열쇠는 두었다 — `contact_columns.py` 주석 참고). 열쇠를
    `contract_received` 로 "맞춰" 버리면 이미 들어 있는 값이 통째로 끊기고,
    그래 놓고도 다른 두 자리와 이어지지는 않는다.
    """
    column = next(c for c in cc.STARTUP_LAYOUT.head
                  if c.label == "계약서 수신여부")
    assert column.key == "invoice_received"
    assert column.source == "note"          # `VcContact.notes` 안에 담긴다

    # `VcContact` 에는 이 이름의 테이블 칸이 없다 — 있으면 저장 자리가 둘로
    # 갈려 화면이 보는 쪽과 다른 쪽에 값이 들어간다.
    assert not hasattr(VcContact, "invoice_received")
    assert not hasattr(VcContact, "contract_received")


def test_투자컨설턴트와_IR_기업_현황은_각자_제_contract_received를_갖는다():
    """이름이 같아도 **다른 표의 다른 칸**이다.

    한쪽에 적은 값이 다른 쪽에서 읽히지 않는다. 두 표가 다르다는 것을 여기서
    붙잡아 두어야, 한쪽 화면만 보고 "받은 곳이 몇 곳" 을 세는 일을 막는다.
    """
    consulting = ConsultingCompany.__table__.c["contract_received"]
    ir = IrCompany.__table__.c["contract_received"]

    assert consulting.table.name == "consulting_companies"
    assert ir.table.name == "ir_companies"
    assert consulting is not ir

    # 둘 다 빈칸이 `아직 안 정함` 이다 — NOT NULL 로 조이면 아무도 확인하지
    # 않은 기업이 `X`("확인했는데 안 왔다")로 적힌다.
    assert consulting.nullable and ir.nullable


def test_세_표는_서로를_가리키는_외래키가_없다():
    """**칸을 모으기 전에 기업 목록부터 이어야 한다**는 근거다.

    세 표 어디에도 서로를 가리키는 외래키가 없다. 이어 주는 것이 없는 채로
    칸만 하나로 줄이면 값이 옮겨지는 것이 아니라 갈 곳이 없어 사라진다.
    """
    tables = {VcContact.__tablename__, ConsultingCompany.__tablename__,
              IrCompany.__tablename__}

    for model in (VcContact, ConsultingCompany, IrCompany):
        others = tables - {model.__tablename__}
        pointed = {fk.column.table.name
                   for fk in model.__table__.foreign_keys}
        assert not (pointed & others), \
            f"{model.__tablename__} 이 {pointed & others} 를 가리키게 되었다 — " \
            "세 자리를 잇는 길이 생긴 것이라면 " \
            "`IrCompany.contract_received` 의 주석을 다시 써라"


def test_한_기업이_여러_줄로_실리는_쪽과_한_줄인_쪽이_갈린다():
    """합친다면 **`IrCompany` 가 공통 축**이라는 근거.

    `VcContact` 는 사람 줄이고 `ConsultingCompany` 는 시트 줄이라(`sheet` 칸)
    한 기업이 여러 번 실린다. 기업 이름을 담는 칸에 유일성이 걸린 표가 하나도
    없다는 것은, 어느 쪽을 축으로 삼든 이름만으로는 줄이 하나로 정해지지
    않는다는 뜻이다 — `IrCompany` 만이 기업 하나에 줄 하나로 쓰인다.
    """
    assert "sheet" in ConsultingCompany.__table__.c        # 시트마다 줄이 는다
    assert "company_name" in ConsultingCompany.__table__.c
    assert "name" in IrCompany.__table__.c

    for column in (ConsultingCompany.__table__.c["company_name"],
                   IrCompany.__table__.c["name"]):
        assert not column.unique, \
            f"{column.table.name}.{column.name} 에 유일성이 생겼다 — " \
            "기업 목록을 잇는 길이 열린 것이라면 " \
            "`IrCompany.contract_received` 의 주석을 다시 써라"
