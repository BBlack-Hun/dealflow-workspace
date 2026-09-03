// 넓은 표의 키를 **감싸개가 실제로 서 있는 자리**에 맞춘다.
//
// ## 왜 상수가 아니라 재는가
//
// CSS 는 표 위쪽 머리 영역(머리말·툴바·요약 패널)의 높이를 `--head: 320px`
// 이라고 **짐작**하고 `max-height: calc(100vh - var(--head))` 로 표를 잘랐다.
// 표를 자르는 까닭은 app.css 에 적어 두었다 — 안 자르면 표가 페이지만큼
// 길어져서 가로 스크롤바가 문서 맨 아래로 밀린다.
//
// 그런데 감싸개는 화면 맨 위가 아니라 **머리 밑**에서 시작한다. 머리가
// 320px 을 넘는 순간 잘라 낸 표의 아래쪽 끝이 화면 밖으로 나가고, 가로
// 스크롤바가 다시 사라진다 — 이 규칙이 애초에 막으려던 그 사고다.
// 실제로 잰 머리 높이(1512×1080):
//
//     딜 소싱 291 · IR 기업 현황 301 · 투자사 관리 현황 443 · 스타트업DB 478px
//
// 320px 은 이미 두 화면에서 틀렸고(스크롤바가 화면 아래 123·158px 밖),
// 나머지 두 화면도 여유가 20px 뿐이다. 머리 높이는 화면마다 다르고 칸·패널이
// 붙을 때마다 또 자란다 — **어떤 상수를 골라도 언젠가는 틀린다.** 그래서
// 숫자를 고르지 않고 화면이 스스로 재게 한다.
//
// ## 왜 CSS 의 `--head` 만 채우는가
//
// 키를 직접(`style.maxHeight`) 박지 않는다. 그러면 표마다 따로 둔 규칙
// (미팅 후기 표의 `max-height: 460px`, 최소 키 `min-height`)을 전부 눌러
// 버린다. 재는 값 하나만 CSS 에 넘겨 주고 나머지 판단은 CSS 에 남긴다.
"use strict";

(function () {
  // 감싸개 아래 남기는 틈. 스크롤바가 화면 맨 끝에 딱 붙으면 잡기 어렵고,
  // 소수점이 1~2px 넘치면 스크롤바가 잘려 보인다.
  var GAP = 16;

  function fitOne(wrap) {
    // 어느 쪽에 맞출지는 **CSS 가 정한다**(`--fit`). 폰이냐 아니냐를 여기서
    // 다시 재면 화면 크기 경계가 두 벌이 되어, 한쪽만 고쳐졌을 때 아무도 모른다.
    var mode = getComputedStyle(wrap).getPropertyValue("--fit").trim();
    // **문서 기준** 위치로 잰다. 화면 기준(`rect.top`)으로 재면 페이지를
    // 세로로 밀 때마다 값이 바뀌어 표 키가 출렁인다.
    var top = wrap.getBoundingClientRect().top + (window.pageYOffset || 0);
    // 감싸개가 아예 첫 화면 밖에서 시작하면(IR 발송처럼 표가 페이지 중간의
    // 한 토막일 때) `머리 밑에 맞추기`는 뜻이 없다 — 남는 자리가 0 이하라
    // 표가 통째로 사라진다. 그때도 `화면 한 장`으로 본다.
    if (window.innerHeight - top - GAP <= 0) mode = "screen";
    var head;
    if (mode === "screen") {
      // 머리가 화면보다 크거나 그에 가까운 배치(폰은 사이드바가 표 위로 쌓여
      // 머리가 650~1,000px 이다). 머리 밑에 욱여넣어 봐야 몇 줄 안 남는다.
      // 머리가 밀려 올라갈 것을 전제로 **화면 한 장**을 표에 준다 — 한 번
      // 밀면 표와 가로 스크롤바가 함께 보인다.
      head = GAP;
    } else {
      head = top + GAP;
      // 남는 자리가 얕을 때 최소 키를 어떻게 지킬지는 CSS 의 `min-height` 가
      // 정한다 — 그 숫자를 여기 옮겨 적지 않는다. 두 벌이 되면 한쪽만 고쳐진다.
    }
    var px = Math.max(0, Math.round(head)) + "px";
    // 같은 값을 다시 쓰면 ResizeObserver 가 또 깨어난다 — 바뀔 때만 쓴다.
    if (wrap.style.getPropertyValue("--head") !== px) {
      wrap.style.setProperty("--head", px);
    }
  }

  function fitAll() {
    var wraps = document.querySelectorAll(".table-wrap.wide");
    // **문서 차례대로** 잰다. 한 화면에 감싸개가 여럿이면(IR 발송) 위 표의
    // 키가 바뀌면서 아래 표의 자리가 따라 움직인다 — 위부터 정해야 아래가
    // 제 자리를 본다.
    for (var i = 0; i < wraps.length; i += 1) fitOne(wraps[i]);
  }

  var pending = false;
  function schedule() {
    if (pending) return;
    pending = true;
    var run = function () { pending = false; fitAll(); };
    if (typeof requestAnimationFrame === "function") requestAnimationFrame(run);
    else setTimeout(run, 0);
  }

  fitAll();
  window.addEventListener("resize", schedule);
  // 머리는 열고 난 뒤에도 자란다 — 접힌 칸을 펴거나, 필터 칩이 줄을 넘기거나,
  // 늦게 도착한 값이 요약 줄을 채울 때. 그래서 한 번 재고 끝내지 않는다.
  if (typeof ResizeObserver === "function") new ResizeObserver(schedule).observe(document.body);
  // 글꼴이 늦게 오면 머리 높이가 한 번 더 바뀐다.
  if (document.fonts && document.fonts.ready && document.fonts.ready.then) {
    document.fonts.ready.then(schedule);
  }

  // 검사가 이 셈을 그대로 돌려 볼 수 있게 내보낸다.
  if (typeof module === "object" && module.exports) {
    module.exports = { fitAll: fitAll, fitOne: fitOne, GAP: GAP };
  }
})();
