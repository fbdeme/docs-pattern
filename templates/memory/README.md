# Long Term Memory 메모 양식

| type | 틀 | 기억 종류 | 근거 |
|---|---|---|---|
| feedback | `sop.md` — 목적·언제·절차·확인·Why·사례 | procedural (SOP) | Agent Workflow Memory(목적+단계), SOP-Agent(조건→행동) |
| user · reference | `fact.md` — 무엇·위치·값·함정 | semantic (사실) | Diátaxis reference(건조한 사실) |
| project | `pointer.md` — 무엇·정본·repo에 없는 사실 | 포인터 | 진행 상황은 docs-hub Agent State |

- 사건(episodic)은 따로 메모로 만들지 않는다: SOP 의 **사례** 목록에 한 줄씩, 긴 일지는 docs-hub Archive.
- 단계가 7개를 넘는 SOP 는 스킬로 올린다. 본문 3,000자, description 80자 이내.
- **core**(`<!-- core -->` … `<!-- /core -->`) = 주입되는 짧은 판, 본문 = 필요할 때 여는 전체. 짧게 써도 정보가 빠지지 않게 둘을 나눈다.
  - feedback core = `<언제> → <무엇을 한다>` 한두 줄. 조건(언제)을 빼면 규칙이 아무 때나 적용된다.
  - user · reference core = `- 키: 값` 줄. 사실은 키-값으로 써도 빠지는 것이 없다.
  - core 는 400자 이내. 넘으면 본문으로 내린다.
- feedback 본문의 **Why** 는 빼지 않는다: 날짜와 근거(사용자 말·사고)를 한 줄로. 이유가 없으면 규칙의 경계(예외 상황)를 판단할 수 없다(2026-10-26 인프라 메모 대조: 사실 164건 중 151건이 조건·이유·하지 말 것이었다).
- JSON 으로 쓰지 않는다: 같은 내용이 마크다운보다 길고(주입 한도는 글자 수) 사람이 읽기 어렵다. 기계가 읽는 설정은 `_` 파일(`_tags.md` · `_infra.md`)의 정해진 형식으로.
- `memory_build.py --lint` 가 양식을 검사한다.
