---
name: docs-pattern
description: "Project docs under docs/ as development documentation: one page per stage (state/S###.md, the active one is the current status), one page per issue (issues/I###.md), a hierarchy of concept pages (documentation/**.md), and one history file per page (history/<same path>). Pages link with [[ID]]; docs_build.py deterministically compiles index.md, current_status.md, _build/compiled.md and backlinks, and fails on broken links, duplicate IDs, missing parents or history. The orchestrator never writes pages: it drops facts into docs/_inbox/ and a sonnet worker edits pages until the checker passes. Use for 'docs 패턴 깔아줘', 'docs init', 'current_status 업데이트', '이슈 등록', '단계 넘어가', 'history', 'docs 이전(v1→v2)', 'docs build/check', and status/drift checks ('status check', 'drift', '이거 했나 안 했나')."
metadata:
  version: "2.0"
  status: active
  lineage: "v1.3 (5 files: current_status/history/issues/todo/research_method) → v2.0 2026-09-28 사용자 결정 D1~D12. REFERENCE: typed-todo render-overview.py(무의존 frontmatter·결정론), archimate-skeleton(사전→컴파일→검사), kepano/obsidian-skills obsidian-markdown(위키링크 문법), addyosmani documentation-and-adrs(결정 상태 전이)"
  related_skills:
    - worker-delegation
    - notion-project-memory
---
<!-- core -->
**docs-pattern 핵심** (세션마다 자동으로 들어감 · 전문은 Skill 로 불러온다)
- 프로젝트 docs 정본 = `~/workspace/docs-hub/projects/<조직>/<repo>/` (아직 옮기지 않은 프로젝트는 그 repo 의 `docs/`). 메뉴: Agent State(`current_status.md`) · Short Term Memory(`rules/R###`) · Document(`documentation/`, 뿌리 `overview` + summary 나무) · Archive(`state/`·`issues/`).
- **사용자가 말하지 않아도**: 이번 작업이 어떤 프로젝트의 사실(구조·도구·결정·진행 단계·규칙)을 바꿨으면, 그 일을 끝냈다고 보고하기 전에 그 프로젝트 `_inbox/<YYYY-MM-DD>-<주제>.md` 에 사실만 적고 워커로 페이지·history 에 반영한 뒤 `docs_build.py <docs> --check` 0 FAIL 을 확인한다. 이 세션은 페이지를 직접 쓰지 않는다.
- 분류: 시간이 지나도 참 = Document · 한 번 하고 끝나는 절차 = 그 이슈 · 진행 = active 단계 · 늘 지킬 규칙·사실 = R###.
- 여러 프로젝트에 두루 쓰이는 것은 Long Term Memory(`~/memory`, 틀 = `templates/memory/`)에 둔다.
- **프로젝트 불러오기**: 어떤 프로젝트의 일을 시작하기 전 → `python3 ~/workspace/docs-pattern/scripts/rules_hook.py --enter <이름|별칭>` 을 Bash 로 부른다(출력 = 그 프로젝트의 Agent State · Short Term Memory · Document 목차 · 고른 Long Term Memory). 이름·별칭은 세션 시작의 `[project-map]` 지도에서 고르고, 프로젝트를 옮길 때마다 다시 부른다. cwd 는 기준이 아니다.
- 사용자가 지도에 없는 말로 프로젝트를 부르면 → `--enter <이름> --as <그 말>` 로 부른다. 별칭이 Long Term Memory `project-aliases` 에 저장된다. 부르지 않고 그 프로젝트 파일을 건드리면 훅이 대신 넣고 `[project-enter]` 로 알린다(안전망).
<!-- /core -->

# docs-pattern v3

프로젝트 `docs/`를 **개발 문서처럼** 관리한다. 페이지는 현재 사실만 담고, 바뀐 이력은 페이지마다
따로 쌓고, 페이지끼리 `[[ID]]`로 연결되며, 목차·현재 상태·전체 문서·백링크는 **컴파일러가 생성**한다.

## 구조

```
docs/
├── index.md              생성물: 현재 단계 · 문서 트리 · 이슈 표 · 단계 표 · 백링크
├── current_status.md     생성물: 현재(active) 단계 페이지 본문 (옛 진입 경로 유지)
├── state/S###.md         단계 1개 = 페이지 1개. 진행 중인 단계는 계속 고치고, 끝나면 done 으로 동결
├── issues/I###.md        이슈 1개 = 페이지 1개. 트래커가 있으면 I### = GitHub #번호
├── rules/R###.md         작업 규칙 1개 = 페이지 1개 (이 프로젝트에서 일하는 법 + 왜). 훅이 자동으로 컨텍스트에 넣는다
├── documentation/**.md   개념 계층. a/b.md 는 a.md 의 하위 (research_method 의 후신)
├── history/<같은 경로>    페이지마다 이력 1개: "- YYYY-MM-DD 무엇 — 왜/근거", 오래된 것이 위
├── _inbox/*.md           오케스트레이터가 남기는 변경 요청(사실 목록). 워커가 처리 후 삭제
└── _build/               생성물: compiled.md(전 페이지 계층 순 컴파일) · backlinks.json
```

## 페이지 규칙

| 페이지 | frontmatter | 본문 |
|---|---|---|
| `state/S###.md` | `title`, `status: active\|done` | 목표 · 완료 조건 · 지금 상태. **active 는 항상 정확히 1개** |
| `issues/I###.md` | `title`, `status: open\|closed\|onhold` | 문제 · 원인 · 해결 |
| `rules/R###.md` | `title` (규칙 한 줄) | 규칙 · **Why**(사용자 발화 인용, 사고) · **How to apply** |
| `documentation/**.md` | `title` | 그 개념의 현재 설명. 하위 개념은 `<이름>/` 아래 파일 |
| `history/…` | 없음 | `- YYYY-MM-DD 무엇이 바뀌었나 — 왜(근거: 커밋·파일·이슈)` 한 줄씩, 날짜 오름차순 |

- 페이지에 **할 일 목록·"결론/기록" 섹션·날짜별 로그를 두지 않는다.** 이력은 history 파일에.
- ID: `S###`, `I###`, `R###`, 문서는 `documentation/` 아래 경로(확장자 뺌, 예: `architecture/redirect`). 재사용 금지.
- 링크: `[[ID]]`, `[[ID|표시 글]]`, `[[ID#제목]]` (Obsidian 호환). 백링크는 쓰지 않는다 — 생성된다.
- 글: 이 대화를 못 본 제3자가 읽어도 이해돼야 한다. 도메인 용어는 쓰되 내부 맥락(호칭·내부 결정 번호·
  기준 없는 상대어)은 쓰지 않는다.
- 할 일은 열린 이슈와 active 단계의 "완료 조건"이 맡는다. `todo.md` 는 없다.
- **프로젝트 docs 에는 그 프로젝트의 일만 적는다.** 문서 구조 이전(v1→v2), 컴파일러 경고 대응, Claude 메모리 정리 같은
  문서 도구 쪽 일은 페이지에도 history 에도 적지 않는다 — 그 기록은 이 스킬의 `docs/` 에 남긴다.

## 컴파일러 `scripts/docs_build.py`

```bash
python3 ~/.claude/skills/docs-pattern/scripts/docs_build.py [docs]          # 검사 + 생성물 쓰기
python3 ~/.claude/skills/docs-pattern/scripts/docs_build.py [docs] --check  # 검사 + 생성물 최신 여부 (쓰지 않음)
python3 ~/.claude/skills/docs-pattern/scripts/docs_build.py --selftest      # 모든 FAIL 규칙 발화 + 결정론 증명
```

- **FAIL (exit 1)**: 깨진 링크 · ID 중복 · 파일 이름 형식 · title/status 누락·오류 · active 단계 ≠ 1 ·
  부모 문서 없음 · history 없음/날짜 없음/역순 · 페이지 없는 history · (`--check`) 생성물이 최신 아님
- **WARN**: 어느 페이지도 링크하지 않는 이슈 · 처리 안 된 `_inbox/`
- 같은 입력 → 바이트 동일 출력(시각 도장 없음). 생성물을 손으로 고치면 `--check` 가 잡는다.

## 쓰는 흐름 — 오케스트레이터는 페이지를 쓰지 않는다

| 단계 | 누가 | 무엇 |
|---|---|---|
| 1 | 오케스트레이터 | `docs/_inbox/YYYY-MM-DD-<slug>.md` 에 **사실만** bullet 로: 무엇이 바뀌었나 · 근거(커밋·파일·이슈·사용자 발화 인용) · 단계 전환 여부 |
| 2 | 워커 (sonnet) | `references/worker_brief.md` 를 채워 [[worker-delegation]] §4 정본 실행줄로 기동. 페이지·history 수정 → `docs_build.py` 0 FAIL 까지 → inbox 삭제 |
| 3 | 컴파일러 | `--check` exit 0 = 구조 판정 (결정론) |
| 4 | 오케스트레이터 | 워커가 쓴 문장이 inbox 사실과 맞는지만 판정 (verdict). 틀리면 inbox 에 정정 사실을 추가해 다시 워커 |

- inbox 가 있어서 "입력이 세션 서사라 위임 불가"(worker-delegation §0) 문제가 풀린다 — 서사는 사실 몇 줄로
  저장소에 들어가고, 배치·문장·이력·검사 통과는 워커 몫이다.
- 트리거: 세션 종료·핸드오프("compact 준비"), 이슈 발견/해결, 단계 전환, 개념 변경. 작은 변경도 같은 흐름.
- 워커 기동·종료 때 워커 카드(worker-delegation §4)를 채팅에 낸다.

## 초기화 / 이전

- 새 프로젝트: `bash ~/.claude/skills/docs-pattern/scripts/init-docs.sh [docs]` — 폴더 + `S001`(active) +
  `documentation/overview` + 각 history 를 만들고 빌드. 기존 파일은 덮어쓰지 않는다.
- v1 → v2 이전은 **프로젝트별로 하나씩**, 워커가 한다. inbox 에 "v1 이전" 과제를 적는다:
  `current_status.md` 세션 블록 → 단계 페이지(S###)와 그 history · `issues.md` → `issues/I###.md` ·
  `research_method.md` → `documentation/` 계층 · `history.md` → 해당 페이지 history · `todo.md` 미완 항목 →
  이슈 또는 active 단계 완료 조건. 옛 파일은 `docs/_v1/` 로 옮겨 둔다(삭제는 사용자 확인 뒤).
  `docs/_v1/` 와 그 밖의 docs/ 파일(설계 문서 등)은 컴파일 대상이 아니다 — 필요하면 `documentation/` 으로 옮긴다.

## 작업 규칙 = `docs/rules/`, 메모리가 아니다

사용자가 "앞으로 이렇게 해라/하지 마라" 고 한 **이 프로젝트의 일하는 법**(저장 정책, 설계 먼저, 진단 전 docs 확인 등)은
Claude 메모리가 아니라 `docs/rules/R###.md` 에 둔다. 메모리는 길어지고, 본문은 목록 한 줄만 자동으로 들어와서 잊힌다.

- 쓰기: 다른 페이지와 같은 흐름(inbox 사실 → 워커 → `--check`). 이력은 `history/rules/R###.md`.
- 읽기: `scripts/rules_hook.py` 가 **UserPromptSubmit·SessionStart 훅**으로 자동 주입한다. 지금 cwd 의 가장 가까운
  `docs/rules/` 를 가진 프로젝트, 그리고 프롬프트에 이름이 나온 `~/workspace_2026/<프로젝트>` 의 규칙을 세션당 한 번,
  규칙이 바뀌면 다시, compact·resume 뒤(SessionStart)에도 다시 넣는다. 등록:
  `~/.claude/settings.json` 의 두 이벤트에 `python3 <repo>/scripts/rules_hook.py`. 검증: `rules_hook.py --selftest`.
- 여러 프로젝트에 걸친 사용자 성향·도구 요령만 메모리에 남긴다.

### 자원 카드 — 공용 자원의 사실은 주인 프로젝트에 한 번만

서버·계정·네트워크처럼 여러 프로젝트가 쓰는 자원의 사실(배정, 접속 경로, 금지, 함께 쓰는 프로세스)은 **그 자원의
주인 프로젝트**의 `docs/rules/R###.md` 한 쪽(자원 카드)에 둔다. 다른 프로젝트 규칙에는 "이 프로젝트는 X 를 쓴다 → 카드"
링크만 남긴다.

- frontmatter `assets:` = 별칭·IP·인스턴스 ID·호스트명(쉼표). 금지 자원은 `deny:` 를 더한다.
- `rules_hook.py` 가 **PreToolUse(Bash)** 에서 명령에 자원 이름이 나오면 그 카드를 세션당 한 번 주입하고, `deny:` 카드는
  명령을 막는다(사용자 승인 뒤 명령에 `# asset-ok:<프로젝트>/R###` 를 붙여야 통과). 프롬프트에 자원 이름이 나와도 주인
  프로젝트 규칙이 들어온다. 등록: `PreToolUse` matcher `Bash` 에 같은 명령.
- **주인 확인 단계**: inbox 에 적는 사실이 공용 자원에 관한 것이면, 지금 프로젝트가 아니라 주인 프로젝트의 `_inbox/` 에
  쓴다. 워커는 카드를 고치고, 지금 프로젝트에는 링크만 남긴다.
- 왜: 2026-10-05 SapiensQ 서버의 집 IP 등록·배정 사실이 그때 작업하던 jepa-pfn 문서·규칙에만 적혀, 2026-10-12 SapiensQ
  작업에서 불러와지지 않았고 배정되지 않은 서버에 두 번 접속했다(같은 계열 두 번째 사고).

## 프로젝트 불러오기 — cwd 가 아니라 `--enter` 와 파일 경로

어디서 세션을 열었는지(cwd)에 따라 기억이 달라지면 안 된다(사용자는 `~/workspace` · `~/INTERX` · `~/SapiensQ` 같은 조직 폴더에서 연다). 그래서:

| 언제 | 들어오는 것 | 누가 넣나 |
|---|---|---|
| 세션 시작 · compact 직후 (어디서 열든 같음) | 필수 스킬 · 필수 메모 · 인프라 · 프로젝트 지도 `[project-map]` | SessionStart 훅 (`memory_build.py --always` · `--infra` · `rules_hook.py`) |
| 에이전트가 `--enter` 를 부를 때 | 그 프로젝트의 Agent State · Short Term Memory · Document 목차 · 고른 Long Term Memory(`rules/_ltm.md`) · 조직 공통 Short Term Memory | 명령 출력 |
| 부르지 않고 그 프로젝트의 파일을 읽거나 고치거나 명령에 그 경로가 나올 때 | 위와 같음 + `[project-enter]` 알림 | PreToolUse 훅 (Read · Edit · Write · Grep · Glob · Bash, heredoc 명령은 제외) |
| 프롬프트에 프로젝트의 정식 이름 · `triggers:` 낱말 · `@이름` 이 나올 때 | 위와 같음 | UserPromptSubmit 훅 |

- 한 번 넣은 프로젝트는 내용이 바뀌지 않으면 다시 넣지 않고, 매 프롬프트에 규칙 제목 한 줄만 붙는다. 세션 기록(`~/.cache/docs-pattern/rules_hook/<세션>.bind`)에 남아 compact 뒤에는 마지막에 부른 프로젝트 본문이 다시 들어오고, 나머지는 이름만 남는다. `@-` 로 지운다.
- 한 번에 넣는 글은 9,500자 안에서 자르고, 넘는 프로젝트는 "`--enter` 로 부른다" 한 줄로 한 번만 알린다.
- 지도 원본 = `~/workspace/docs-hub/projects/<조직>/_registry.md`(프로젝트 · status · 경로 · docs · 메모 = 한 줄 설명). 진행 중은 이름 · 별칭 · 한 줄 · 지금 단계, 쉬는 중은 이름만. `rules_hook.py --map` 으로 지도만 본다. docs-hub Home 그래프도 같은 원본으로 그린다.
- 별칭 = Long Term Memory 메모 `~/memory/project-aliases.md`(core 의 `- 말: 프로젝트` 줄 + 근거 줄). `--enter <이름> --as <말>` 이 자동으로 더하고, 손으로 고쳐도 된다. `--enter` 는 이름 · 별칭을 대소문자 없이 찾고, 허브에 없으면 registry `경로` 칸의 repo 에서 옛 `docs/rules` 를 찾는다. 못 찾으면 지도를 보이고 exit 1.

## 메모리와의 관계

- 프로젝트 상태의 정본은 `docs/` 하나다. Claude 메모리의 프로젝트 항목은 **"무엇인지 + repo 경로 +
  `docs/index.md`"만 담는 바뀌지 않는 포인터**로 두고, 진행 상황을 메모리에 복사하지 않는다.
- 프로젝트 작업을 시작하면 `docs/current_status.md`(= active 단계)부터 읽는다.

## 파생 상태 / drift 검증 (`status_check`) — v1 에서 유지

상태(뭐 했나/안 했나)는 손으로 단언하지 말고 아티팩트에서 파생한다.

- `docs/status_ledger.yaml` — 작업단위 = 완료면 존재해야 할 durable 아티팩트(`artifacts`) + 선택 `contains`
  (grep 으로 검증한 needle) + 선택 `issue` 번호.
- `scripts/status_check.py` (프로젝트로 복사해 씀) — 아티팩트로 done/partial/pending 파생 → `gh issue list`
  대조 → drift(done 인데 OPEN / CLOSED 인데 아티팩트 없음) 출력, drift 면 exit 1. 이슈 닫기는 사람이 한다.
- 원칙: durable 아티팩트로 증명 · 파일 존재는 약한 증거(`contains`) · 충돌 시 아티팩트가 이긴다.
- 이슈 페이지의 `status` 와 GitHub 상태가 다르면 이것도 drift 다 — 닫기 전에 status_check 로 확인하고,
  페이지 status 변경은 inbox → 워커 흐름으로 한다.

## 컨테이너

프로젝트 여러 개가 든 폴더(컨테이너)의 프로젝트 목록은 손으로 적지 않고 `scripts/container_build.py`로 만든다.

```bash
python3 ~/.claude/skills/docs-pattern/scripts/container_build.py CONTAINER          # PROJECTS.md 생성
python3 ~/.claude/skills/docs-pattern/scripts/container_build.py CONTAINER --check  # 최신 여부 + LEGACY.md 형식
python3 ~/.claude/skills/docs-pattern/scripts/container_build.py --selftest
```

- 컨테이너 = `PROJECTS.md` 가 있는 폴더(처음 한 번 실행이 선언). 프로젝트 = 하위 폴더 중 `.git` 또는 `docs/` 가 있는 것.
- 사람이 쓰는 파일은 `LEGACY.md` 하나: `- <이름> — <remote> — <보관일>`. 자세한 설명은 `docs/documentation/container.md`.

## 안티패턴

| 하지 말 것 | 대신 |
|---|---|
| 오케스트레이터가 페이지를 직접 고치기 | inbox 에 사실 → 워커 → `--check` |
| 페이지에 할 일·"결론/기록"·날짜 로그 | 페이지 = 현재 사실, 이력 = history 파일, 할 일 = 이슈·완료 조건 |
| 생성물(index·current_status·_build) 손수정 | 페이지를 고치고 `docs_build.py` |
| 백링크를 손으로 적기 | 링크만 걸면 컴파일러가 모은다 |
| 세션마다 새 단계 페이지 | 단계가 바뀔 때만 새 S###. 같은 단계면 그 페이지를 고친다 |
| 프로젝트 진행 상황을 Claude 메모리에 복사 | 메모리는 포인터, 정본은 `docs/` |
| 프로젝트 작업 규칙(피드백)을 메모리 파일로 | `docs/rules/R###.md` + 훅이 자동 주입 |
| 여러 프로젝트를 한꺼번에 v2 로 이전 | 하나씩, 워커 + `--check` |
