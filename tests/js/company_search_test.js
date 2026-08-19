// 기업 검색 필터의 판단 로직 테스트 (node 로 실행).
//
// deals.js 의 applyCompanyFilter 는 DOM 을 직접 만지므로, 판단 부분만 같은 규칙으로
// 옮겨 검증한다. 핵심 규칙은 하나다:
//   **선택한 기업은 검색어와 무관하게 항상 보여야 한다.**
//   (검색어를 바꾸다 고른 기업이 사라지면 몇 개 골랐는지 알 수 없다)

function isVisible(card, query, pickedOnly) {
  const q = (query || "").trim().toLowerCase();
  const hit = !q || card.search.indexOf(q) !== -1;
  return card.picked || (hit && !pickedOnly);
}

let failed = 0;
function check(name, got, want) {
  const ok = got === want;
  if (!ok) failed += 1;
  console.log(`  ${ok ? "PASS" : "FAIL"}  ${name}${ok ? "" : ` (got ${got}, want ${want})`}`);
}

const agri = { search: "샘플애그 애그테크 b2b 농산물 선도거래", picked: false };
const medi = { search: "샘플메디 헬스케어 뇌영상 분석 ai", picked: false };
const pickedPay = { search: "샘플페이 핀테크 정산", picked: true };

console.log("기업 검색 필터");
check("검색어 없으면 모두 표시", isVisible(agri, "", false), true);
check("이름으로 검색", isVisible(agri, "샘플애그", false), true);
check("분야로 검색", isVisible(medi, "헬스케어", false), true);
check("소개 문구로 검색", isVisible(agri, "농산물", false), true);
check("대소문자 무시", isVisible(medi, "AI", false), true);
check("안 맞으면 숨김", isVisible(medi, "농산물", false), false);

// ★ 가장 중요한 규칙
check("선택한 기업은 검색에 안 걸려도 보인다", isVisible(pickedPay, "농산물", false), true);
check("선택한 기업은 '선택한 것만'에서도 보인다", isVisible(pickedPay, "", true), true);
check("선택 안 한 기업은 '선택한 것만'에서 숨김", isVisible(agri, "", true), false);

// 공백만 입력한 경우는 검색어 없음으로 취급
check("공백 입력은 전체 표시", isVisible(medi, "   ", false), true);

if (failed) {
  console.error(`\n${failed}건 실패`);
  process.exit(1);
}
console.log("\n모두 통과");
