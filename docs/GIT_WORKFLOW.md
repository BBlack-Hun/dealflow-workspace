# Git 작업 규칙 (GitHub Flow)

1인 개발 + AI 협업에 맞춘 **가벼운** 규칙. `main` 은 항상 동작하는 상태로 유지한다.

```
main ────●──────────────●────────────▶  항상 배포 가능
          \            /
           ●──●──●────●   feat/sprint2-sheet-import
           작업 → PR → 머지 → 브랜치 삭제
```

## 1. 브랜치

| 종류 | 형식 | 예시 |
|---|---|---|
| 기능 | `feat/<주제>` | `feat/sprint2-sheet-import` |
| 버그 | `fix/<주제>` | `fix/room-name-mismatch` |
| 문서 | `docs/<주제>` | `docs/windows-guide` |
| 리팩터링 | `refactor/<주제>` | `refactor/sender-config` |
| 잡무 | `chore/<주제>` | `chore/deps-bump` |

- **짧게 유지**: 한 브랜치 = 한 덩어리 작업. 며칠씩 끌지 않는다.
- 머지 후 브랜치는 **삭제**한다.
- `main` 에 직접 커밋하지 않는다(오타 수정 같은 사소한 건 예외).

## 2. 커밋 메시지 (Conventional Commits)

```
<타입>: <한 줄 요약>

<본문 — 왜 이렇게 했는지. 무엇을 했는지는 diff가 말해준다>
```

타입: `feat` `fix` `docs` `refactor` `test` `chore` `perf`

```
feat: 구글시트 임포트 — 담당자 126명 CRUD

시트의 이름 셀은 '이름+직함'이 합쳐져 있어 분리 파서를 둔다.
월별 3열 세트는 행(contact_activities)으로 정규화한다.
```

## 3. PR (Pull Request)

작업이 끝나면 PR을 올려 **본인이 diff를 검토**하고 머지한다.
AI가 작성한 코드를 그냥 main에 넣지 않기 위한 안전장치다.

```bash
git switch -c feat/sprint2-sheet-import   # 브랜치 생성
# ... 작업 ...
git add -A && git commit -m "feat: ..."
git push -u origin feat/sprint2-sheet-import
gh pr create --fill                        # PR 생성
gh pr view --web                           # 브라우저에서 diff 확인
gh pr merge --squash --delete-branch       # 검토 후 머지
```

**Squash 머지**를 기본으로 한다 — 작업 중 자잘한 커밋이 main 히스토리를 어지럽히지 않는다.

## 4. 머지 전 체크리스트

- [ ] 테스트 통과 (`docker exec dealflow-web-1 python -m pytest -q`)
- [ ] 실명·API키가 섞이지 않았는가 (이 저장소는 **public**)
- [ ] 발송 관련 변경이면 오발송 방지 로직이 그대로인가

## 5. 되돌리기

```bash
git log --oneline                  # 지점 확인
git revert <커밋>                   # 머지된 것을 안전하게 되돌림(히스토리 보존)
git switch -c fix/xxx <커밋>        # 특정 시점에서 새 브랜치로 복구
```

---

> **왜 1인인데 브랜치를 쓰나**
> ① main이 항상 돌아가는 상태로 유지된다 (데모 중에 깨지지 않음)
> ② PR diff가 AI 작업 검토 지점이 된다
> ③ 실패한 시도를 브랜치째 버릴 수 있다
> ④ 나중에 팀이 늘어도 규칙을 다시 만들 필요가 없다
