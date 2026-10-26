# Long Term Memory 메모 양식

| type | 틀 | 기억 종류 | 근거 |
|---|---|---|---|
| feedback | `sop.md` — 목적·언제·절차·확인·Why·사례 | procedural (SOP) | Agent Workflow Memory(목적+단계), SOP-Agent(조건→행동) |
| user · reference | `fact.md` — 무엇·위치·값·함정 | semantic (사실) | Diátaxis reference(건조한 사실) |
| project | `pointer.md` — 무엇·정본·repo에 없는 사실 | 포인터 | 진행 상황은 docs-hub Agent State |

- 사건(episodic)은 따로 메모로 만들지 않는다: SOP 의 **사례** 목록에 한 줄씩, 긴 일지는 docs-hub Archive.
- 단계가 7개를 넘는 SOP 는 스킬로 올린다. 본문 3,000자, description 80자 이내.
- `memory_build.py --lint` 가 양식을 검사한다.
