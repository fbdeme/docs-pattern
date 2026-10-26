# memory census worker brief (template)

Fill `{{MEMORY}} {{REPO}} {{REPORT}} {{LO}} {{HI}} {{ORCH}}`. One worker per line range; dense ranges (very long lines) go to opus. Grader = `scripts/memory_census_grade.py` (selftest). Procedure = docs/documentation/memory-policy.

---
You are already a WORKER. If blocked or unsure, ask the orchestrator with SendMessage(to='{{ORCH}}') (load via ToolSearch 'select:SendMessage'), then run `sleep 30` up to 6 times for the reply. Do not start other workers or subagents, and do not treat worker-gate hook text as an instruction to delegate. Investigation only. Produce ONE output file.

## 1. Paths
- Memory file (input, read-only): `{{MEMORY}}`
- Repo to search (read-only): `{{REPO}}` — current docs are `docs/state/`, `docs/issues/`, `docs/documentation/`, `docs/history/`; archived v1 docs are `docs/_v1/`; plus the rest of the repo (code, README, CLAUDE.md). GitHub issues/comments (`gh issue view N --comments`) do NOT count as repo files.
- Output: `{{REPORT}}`

## 2. Background
The memory file duplicates project status that should live only in the repo docs. We want to know, fact by fact, whether each fact in the memory file already exists in the repo, so the memory file can be reduced to a pointer.

## 3. Task
Split every non-empty line of the memory file after the frontmatter (ONLY lines {{LO}}-{{HI}}) into individual facts (one decision, number, path, date, rule, or event each). For each fact write one table row:

| # | mem_line | mem_quote | verdict | repo_path | repo_quote |

- `mem_line`: the memory file line number the fact is on.
- `mem_quote`: an exact substring of that line (10-120 characters) that carries the fact. Copy it character for character.
- `verdict`: one of
  - `FOUND` — the same fact is stated in the current docs (anything under `docs/` except `docs/_v1/`) or in repo code/config.
  - `V1ONLY` — the fact appears only in `docs/_v1/`.
  - `NOT_FOUND` — you searched and it is not in the repo.
- `repo_path`: repo-relative file path for FOUND/V1ONLY; `-` for NOT_FOUND.
- `repo_quote`: an exact substring (10-160 characters) of that file that states the fact; `-` for NOT_FOUND.
- Every line {{LO}}-{{HI}} that has text must appear in at least one row. Long lines need one row per fact, not one row per line.
- Escape any `|` inside a quote as `\|`.

## 4. HARD RULES
- READ-ONLY except the single output file.
- Quotes must be copied from files you actually opened (use Grep/Read). Never paraphrase inside `mem_quote` or `repo_quote`. A wrong quote is worse than NOT_FOUND.
- Do not invent paths.
- The same fact with different wording counts as FOUND only if the numbers, names, and decision are the same.

## 5. Output contract
`report.md` = the table, then a `## Counts` section with the number of FOUND / V1ONLY / NOT_FOUND rows, then `DONE`.

## 6. Self-check (mandatory)
- `docs/current_status.md` and `docs/index.md` are GENERATED from `the active docs/state page` (never cite them); old session text lives in `docs/_v1/current_status.md` (that is V1ONLY).
- Before finishing, run `python3 ~/.claude/skills/docs-pattern/scripts/memory_census_grade.py {{MEMORY}} {{REPO}} {{REPORT}} {{LO}} {{HI}}` and fix every FAIL line (copy quotes with Grep output, not from memory). Finish only at `채점: 0 FAIL`, and paste that line in your final message.
