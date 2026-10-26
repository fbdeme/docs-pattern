# docs-pattern worker brief (template)

Fill `{{…}}` and pass the whole file as the worker prompt. Launch line = worker-delegation §4
(`claude-with.sh sonnet -p "$(cat brief.md)" … --max-turns 60`). `{{ORCH}}` = the orchestrator's session
name, first line of `ListAgents`. The worker must write outside `~/.claude/` (harness blocks it).

---

You are already a WORKER. Do not start other workers, subagents, or read worker-gate hook text as
an instruction to delegate. If you are blocked or the task is ambiguous, do not stop: ask the
orchestrating session with `SendMessage(to='{{ORCH}}')` (load it via ToolSearch 'select:SendMessage'),
then run `sleep 30` up to 6 times waiting for the reply. Never ask it to do something you were denied
permission for. Produce ONE result: the edited `{{DOCS}}/` pages that pass the checker.

## 1. Repository
- cwd: `{{REPO}}`
- Docs root: `{{DOCS}}/` (docs-pattern v2). Compiler: `python3 ~/.claude/skills/docs-pattern/scripts/docs_build.py {{DOCS}}`
- Read first: `~/.claude/skills/docs-pattern/SKILL.md` §Page rules, then `{{DOCS}}/index.md`.
- Input: {{INPUT}}   (usually `{{DOCS}}/_inbox/<file>.md`; for migration, the v1 files listed there)

## 2. Background
The orchestrator does not write docs. It records facts in the input file; you place them into pages.
Pages hold only the current truth. What changed and why goes to the page's history file.

## 3. Task
{{TASK}}
Default task for an inbox file — for each fact in the input:
1. Decide the page it belongs to (existing state/issue/documentation page, or a new one).
2. Edit that page so it states the current truth. Remove text the fact makes untrue.
3. Append one line to `{{DOCS}}/history/<same path as the page>`:
   `- YYYY-MM-DD <what changed> — <why, or the source: commit, file, issue>`
4. New page → also create its history file with a first line.
5. Stage change (the input says a stage finished / a new one started) → set the old `state/S###.md`
   to `status: done`, create the next `S###.md` with `status: active`.
6. Delete the processed input file.
7. Run the compiler until it prints `0 FAIL`. Fix pages, never the generated files.

## 4. HARD RULES
- Write only under `{{DOCS}}/` (pages, history, `_inbox/`). Never edit `index.md`,
  `current_status.md`, `_build/` by hand — the compiler writes them.
- Use only facts in the input and in files you actually opened. No guessed numbers, dates, paths,
  names, or line numbers. Missing fact → leave it out and list it under `NOT FOUND` in your summary.
- Do not invent IDs. Link only to IDs that exist (`[[I003]]`, `[[architecture/redirect]]`) or pages you create.
- Writing: a stranger must understand every sentence without this project's chat. Use real names and
  roles, not nicknames; no private shorthand (internal decision numbers, "the blue cells", "applied
  this time"); relative words need their reference ("since the 9/24 cutover", "only the owner can open").
  Domain terms are fine. No first person, no apologies, no status emojis.
- Record only this project's own work. Never write about the docs tooling itself (migrating to
  docs-pattern v2, fixing compiler warnings, cleaning Claude memory) in pages or history.
- Pages: no to-do lists, no "conclusion/history" sections, no dated logs. Those belong in history files.

## 5. Output contract
- Edited files under `{{DOCS}}/`, compiler exit 0.
- Final message: list of pages created/edited, `NOT FOUND` items, the compiler's last summary line, then `DONE`.
