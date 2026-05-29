# docs-pattern

A [Claude Code](https://claude.com/claude-code) skill that bootstraps and maintains a five-file project-docs pattern under `docs/`:

| File | Owns |
|---|---|
| `current_status.md` | Where the project stands **right now** — latest session at top |
| `history.md` | Why the methodology / architecture changed over time |
| `issues.md` | Numbered technical issues + resolution status |
| `todo.md` | Categorized checklist (with completion dates) |
| `research_method.md` *(optional)* | Versioned methodology spec — research projects only |

No hooks, no auto-injection. The skill is explicit: Claude reads and updates these files only when you ask. Lighter alternative to [`planning-with-files`](https://github.com/OthmanAdi/planning-with-files) when you'd rather codify your own discipline than adopt a framework's.

## Install (per project)

```bash
mkdir -p .claude/skills
curl -sL https://github.com/fbdeme/docs-pattern/archive/main.tar.gz \
  | tar xz -C .claude/skills --strip-components=1
```

This drops `SKILL.md`, `templates/`, and `scripts/` into `.claude/skills/docs-pattern/`.

## Install (user-global)

```bash
mkdir -p ~/.claude/skills/docs-pattern
curl -sL https://github.com/fbdeme/docs-pattern/archive/main.tar.gz \
  | tar xz -C ~/.claude/skills/docs-pattern --strip-components=1
```

## Quick start

After install, in a new project:

```
docs 패턴 깔아줘                # or: init docs-pattern
```

Claude runs `scripts/init-docs.sh`, which creates `docs/` with the five templates (idempotent — existing files are never overwritten). Skip the research file with `--no-research`.

Then, as work happens:

```
오늘 한 거 current_status에 정리해줘
Issue #3 해결됐어
todo X 끝남
방법론 v3로 올라간 거 반영
지금 프로젝트 상태 어떻게 돼?
```

Trigger phrases and per-file update rules are spelled out in [`SKILL.md`](./SKILL.md).

## Why this pattern

Converged on across five of my projects (EEG-WM-JEPA, Agentic_tree_search, icml2026-gwm-nuclear-rag, JPTAKU, openpencil-server). Three things it gets right:

1. **Forward + backward separation** — `current_status.md` answers "where am I?", `history.md` answers "how did I get here?". Not the same file.
2. **Decisions vs work logs** — `history.md` records *why* a direction changed, not what you did today (that's `current_status.md` or commit logs).
3. **Issues as a permanent ledger** — numbered, never deleted, status mutates. Re-reading old resolved issues is how you remember why a constraint exists.

## License

MIT. See [`LICENSE`](./LICENSE).
