---
name: docs-pattern
description: "Bootstrap and maintain the personal project-docs pattern under docs/: current_status.md (where things stand right now), history.md (what changed over time), issues.md (numbered technical issues + resolution), todo.md (categorized checklist), and optionally research_method.md (versioned methodology spec). Use when the user wants to initialize this pattern in a new project ('docs 패턴 깔아줘', 'docs init', 'set up project docs', 'init docs-pattern'), or wants to update any of those files after doing work ('current_status 업데이트', 'history에 추가', '이슈 등록해줘', 'todo 정리', 'mark X done', 'log session', 'project status update'). Skill enforces which file gets which kind of information."
metadata:
  version: "1.2"
  status: active
---

# docs-pattern

프로젝트 루트에 `docs/` 폴더를 만들고, 그 안에 **5개의 정해진 .md 파일**을 사용자 규율대로 유지하는 스킬. 사용자가 EEG-WM-JEPA·Agentic_tree_search·icml2026-gwm-nuclear-rag·JPTAKU·openpencil-server 등에서 일관되게 써 온 패턴을 코드화한 것.

**철학**: planning-with-files처럼 hook으로 자동 주입하지 않음. 컨텍스트 윈도우는 깨끗하게 두고, **필요할 때만 사용자가/Claude가 명시적으로 읽고 업데이트**한다.

---

## 파일별 역할

| 파일 | 무엇을 적나 | 언제 업데이트 |
|---|---|---|
| `current_status.md` | **지금 이 순간** 프로젝트가 어디까지 와 있는지. 서버/환경 상태, 직전 세션 작업, 즉시 다음 할 일. 최신 세션이 **맨 위**. | 작업 세션을 시작·전환·종료할 때 |
| `history.md` | **방법론·아키텍처·중요 의사결정의 변경 이력**. 날짜·단계(Phase)별로 그룹핑. 시간 순(예전 게 위). | 의미 있는 방법론 변경이 생겼을 때 |
| `issues.md` | **기술적 이슈 + 해결 방법**. `Issue #N` 번호 매김, `상태: ✅ 해결됨` / `🔄 진행 중` / `⏸️ 보류` 표기. 문제 → 원인 → 해결 방법 구조. (이슈 트래커 있으면 **TOC**로 축소 — 아래 규율) | 새 이슈 발견 시 / 해결 시 |
| `todo.md` | **카테고리별 체크리스트**. `## 1. 카테고리` 아래에 `- [x] 항목 (YYYY-MM-DD)` 또는 `- [ ] 항목`. 완료 시 날짜 기록. | 작업 추가·완료 시 |
| `research_method.md` (선택) | **방법론 스펙**. 버전 번호 명시(`v2.0`). 파이프라인 단계별 상세. | 방법론 자체가 바뀔 때 |

`research_method.md`는 리서치/실험 프로젝트에만 만들고, 일반 소프트웨어 프로젝트(예: `openpencil-server`)는 생략한다.

---

## 초기화 (`init`)

새 프로젝트에서 패턴을 처음 깔 때:

```bash
# 풀 init (research_method.md 포함, 기본)
bash ${CLAUDE_PLUGIN_ROOT}/scripts/init-docs.sh

# 리서치 파일 빼고 4개만
bash ${CLAUDE_PLUGIN_ROOT}/scripts/init-docs.sh --no-research
```

또는 스킬 디렉토리를 모르면, Claude가 `templates/` 안 5개 파일을 프로젝트의 `docs/`로 그대로 복사하면 된다. 이미 존재하는 파일은 **덮어쓰지 않는다**.

---

## 업데이트 규율

### `current_status.md`

- 헤더 바로 아래 `> 최종 업데이트: YYYY-MM-DD (한 줄 요약)`을 갱신.
- 새 세션은 `## Session YYYY-MM-DD — 제목` 헤딩으로 **파일 상단**(헤더 바로 아래)에 prepend.
- 서버/하드웨어 환경이 의미 있으면 `**서버**: ...` 한 줄로 명시.
- 표·체크리스트 적극 사용. 산문은 핵심만.

#### 멀티 에이전트 / 협업 시

여러 사람·에이전트가 한 repo에서 각자 브랜치로 작업할 때, `current_status.md`는
**세션 핸드오프 로그**가 된다 — 다음 사람/에이전트가 작업 전 먼저 읽고 맥락을 이어받는다.

- **단일 소스**: "지금 상태"의 유일한 출처. `LATEST.md` 같은 **평행 상태 파일을 새로 만들지 말 것** (진실이 갈라진다).
- **작성자 태그**: 세션 헤딩에 이름을 붙인다 — `## Session YYYY-MM-DD — 제목 (작성자)`.
- **실시간 상태는 여기가 아님**: "지금 누가 뭐 하는 중"은 이슈 트래커/보드(assign·진행 중)가 담당. 이 파일은 머지된 *확정 맥락*만 담는다 (git은 머지 시점에만 공유됨).
- **충돌 완화**: prepend 충돌이 잦아지면 세션을 `docs/sessions/<날짜>-<이름>.md`로 1인 1파일 분리하고, `current_status.md`는 요약/인덱스만 유지한다.

### `history.md`

- 시간 순 (예전 게 위). 가장 최근은 맨 아래에 append.
- `## YYYY-MM-DD ~ MM-DD: 제목` 또는 `## YYYY-MM-DD: Phase N — 제목`.
- **의사결정의 *이유***를 적는다 — "무엇을 했다"가 아니라 "왜 그 방향으로 갔다".

### `issues.md`

- `## Issue #N: 제목` + `**상태: ✅ 해결됨 (YYYY-MM-DD)**` / `🔄 진행 중` / `⏸️ 보류`.
- 안쪽 구조: `### 문제` → `### 원인` (선택) → `### 해결 방법` → `### 향후 고려사항` (선택).
- 번호는 절대 재사용 안 함 — 해결되거나 무효화돼도 그대로 두고 상태만 바꿈.

#### 이슈 트래커가 있을 때 / 협업 시 (GitHub·GitLab)

프로젝트에 **이슈 트래커(또는 연결된 Project 보드)** 가 있으면, `issues.md`를 상세 저장소로 쓰지
말고 **이슈를 트래커에 올려 단일 소스로 삼는다**:

- 각 이슈 = 트래커의 실제 이슈(+보드에 추가). 상세 논의·상태는 거기서 갱신.
- `issues.md`는 **인덱스(TOC)** 로 축소 — `# | 제목 | 상태 | 링크` 표(+ MVP-critical 묶음 정도).
- **번호는 트래커 번호와 일치**시킨다 — 빈 repo면 순서대로 생성해 `doc #N = issue #N`. 기존 이슈가
  있으면 실제 번호로 매핑하고 표에 명시.
- 새 이슈: 트래커에서 생성 → 보드 추가 → `issues.md` 표에 한 줄.

**트래커가 없으면** repo 루트에 **`issues/` 디렉토리**를 만들고 이슈별 `issues/NNN-제목.md`(위
`## Issue #N` 내부 구조 그대로)로 관리하며, `issues.md`는 그 인덱스로 둔다.

### `todo.md`

- `## N. 카테고리` 헤딩 아래 체크박스 리스트.
- 완료: `- [x] 내용 (YYYY-MM-DD)` — 날짜 필수.
- 미완료: `- [ ] 내용`.
- 하위 항목은 `  - [ ] ...` 들여쓰기.
- 완료된 항목을 삭제하지 않음 — 작업 이력으로 남김.

### `research_method.md`

- 헤더 아래 `> 최종 업데이트: YYYY-MM-DD` + `> 버전: vX.Y (한 줄 요약)`.
- 구조 자체를 바꿀 때 버전 올림 (`v2.0` → `v3.0`).
- 세부만 바뀌면 마이너 (`v2.1` → `v2.2`).

---

## 트리거 예시

| 사용자 발화 | Claude가 할 일 |
|---|---|
| "이 프로젝트에 docs 패턴 깔아줘" | `docs/` + 5개 파일 생성 (이미 있으면 스킵) |
| "오늘 한 거 current_status에 정리해줘" | `current_status.md` 상단에 새 Session 블록 prepend |
| "Issue #N 해결됐어, 마크해줘" | `issues.md`에서 해당 Issue 상태를 `✅ 해결됨 (오늘 날짜)`로 변경 |
| "todo에서 X 끝남" | `todo.md`에서 해당 줄을 `- [x] X (오늘 날짜)`로 변경 |
| "방법론 v3로 올라간 거 반영" | `research_method.md`의 버전·요약 줄 갱신 + 변경 내용 본문 반영 |
| "지금 프로젝트 상태 어떻게 돼?" | `current_status.md` + 최근 `history.md` 5줄 + 미해결 `issues.md` + 미체크 `todo.md` 묶어서 요약 출력 |

---

## 안티패턴

| 하지 말 것 | 대신 |
|---|---|
| `current_status.md`를 무한히 늘리기 | 4개 세션 넘으면 오래된 세션을 `history.md`로 이동 |
| 이미 닫은 Issue를 다시 열기 | 새 Issue 번호로 등록하고 `(연관: Issue #N)`로 표기 |
| `todo.md`에서 완료 항목 삭제 | 체크 + 날짜만, 작업 이력으로 남김 |
| `history.md`를 "무엇을 했다" 로그로 사용 | 그건 `current_status.md`/`progress`. history는 **방향성 변경 이유** |
| 리서치 아닌 프로젝트에 `research_method.md` 강제 | 옵션. `--no-research` 또는 그냥 생략 |
| 모든 파일을 매 응답마다 자동 읽기 | 사용자가 요청하거나 명시적으로 필요할 때만 |
| 협업 시 `LATEST.md` 등 평행 상태 파일 새로 만들기 | `current_status.md` 단일 소스 유지 (필요하면 `docs/sessions/`로 분리) |
| 이슈 트래커가 있는데 `issues.md`에만 상세 쌓기 | 트래커에 올려 단일 소스, `issues.md`는 TOC (트래커 없으면 `issues/` 디렉토리) |
