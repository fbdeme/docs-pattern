# docs-pattern v3

A Claude Code skill that turns project documentation and Claude's memory into one system.
You get the same memory no matter which folder or account a session starts from.
Every project's docs live in one hub. Rules that apply everywhere live in a shared Long Term Memory.
Hooks put the right parts into the agent's context: what every session needs when it starts,
and a project's memory when the agent starts work on that project.

## Memory layers

| Layer | What it holds | Where |
|---|---|---|
| Agent State | The current stage of a project: goal, done-conditions, status, next step | `docs-hub/projects/<org>/<project>/current_status.md` (compiled from the active `state/S###.md`) |
| Short Term Memory | Rules and facts to keep in mind while working on that project | `…/<project>/rules/R###.md` (org-wide rules: `projects/<org>/rules/`) |
| Document | Pages that stay true over time, as a tree under a root `overview` page | `…/<project>/documentation/**.md`, plus outside docs linked under `mounts/` |
| Archive | Finished stages and issues | `…/<project>/state/` · `…/<project>/issues/` |
| Long Term Memory | Rules and facts shared by every project and account | `~/memory/*.md` (templates in `templates/memory/`, tag list `_tags.md`) |
| Skills | Required skills whose short core is injected into every session | `~/memory/_always.md` |

Every page has a history file at the same path under `history/`, one line per change: `- YYYY-MM-DD what — why`.
Pages hold only the current truth.

## What enters the context, and when

| When | What | Who puts it there |
|---|---|---|
| Session start and right after compaction (the same from any folder) | Required memos and skills · infrastructure table · project map | SessionStart hooks: `memory_build.py --always`, `--infra`, `rules_hook.py` |
| The agent calls `rules_hook.py --enter <name or alias>` before working on a project | That project's Agent State · Short Term Memory · Document outline · selected Long Term Memory · org rules | The command's output |
| The prompt names a project, one of its aliases, or a `triggers:` word (Korean particles may follow) | The same | UserPromptSubmit hook |
| The agent touches a project's files without calling `--enter` (safety net) | The same, once per session, with a `[project-enter]` notice | PreToolUse hook on Read · Edit · Write · Grep · Glob · Bash |

- The session's working directory is never used to pick a project. Projects are picked by the agent's call, the prompt, or the paths the agent touches.
- The project map is built from `projects/<org>/_registry.md`. Columns: project · status · path · docs · note. Active projects show their name, aliases, note and current stage. Paused projects show their name only.
- Aliases live in one Long Term Memory memo, `~/memory/project-aliases.md`, one `- <word>: <project>` line each.
  When the user calls a project by a new word, the agent runs `--enter <project> --as <word>`, which adds the line and the date it was added.
- A project already injected is not injected again unless it changed. Each prompt carries one line of its rule titles.
  After compaction, the last project the agent called comes back in full and the others by name.
- Claude Code saves any hook output over 10,000 characters to a file and injects only a 2,000-character preview.
  So each injection is held to 9,500 characters; a project that does not fit is replaced by a one-line "call `--enter`" notice, shown once.

## Writing docs

The orchestrating session never edits pages. It writes facts to `<project>/_inbox/<date>-<topic>.md`.
A worker places them into pages and history (`references/worker_brief.md`) and runs the compiler until it reports `0 FAIL`.
Classification:
- Stays true over time → Document.
- A procedure done once → its issue.
- Progress → the active stage.
- A rule to always follow → `R###`.

## Tools

| Script | Does |
|---|---|
| `scripts/docs_build.py <docs> [--check]` | Compiles `index.md`, `current_status.md`, `_build/compiled.md`, backlinks. Fails on broken `[[ID]]` links, duplicate IDs, missing parents or history. Also builds the injected project context |
| `scripts/rules_hook.py` | The hooks above; `--enter <name or alias> [--as <word>]`; `--map` prints the project map |
| `scripts/memory_build.py` | `--always` (required injection) · `--infra` · `--lint` (memo format, tags, core length) · `--views` (index per account) |
| `scripts/hub_build.py [hub]` | Builds the docs-hub MkDocs site. Its Home graph opens on the project map: orgs, active projects with aliases, and their current stage |
| `scripts/status_check.py` | Derives done / partial / pending from artifacts and reconciles with GitHub issues |
| `scripts/init-docs.sh [docs]` | Starts a new project's docs: folders plus an active `S001` |

Every Python script except `status_check.py` has a `--selftest`.

## Install

```bash
git clone https://github.com/fbdeme/docs-pattern ~/workspace/docs-pattern
ln -s ~/workspace/docs-pattern ~/.claude/skills/docs-pattern
```

Hooks in `~/.claude/settings.json`, all with the command `python3 ~/workspace/docs-pattern/scripts/<script>`:

| Event | Script | Matcher |
|---|---|---|
| SessionStart | `memory_build.py --always` | — |
| SessionStart | `memory_build.py --infra` | — |
| SessionStart | `rules_hook.py` | — |
| UserPromptSubmit | `rules_hook.py` | — |
| PreToolUse | `rules_hook.py` | `Bash\|Read\|Edit\|Write\|MultiEdit\|NotebookEdit\|Grep\|Glob` |

Use the same hooks in every Claude config directory you use, so every account gets the same memory.

## Single-project mode (v2)

A repo can still keep its own `docs/` with the same page types (`state/`, `issues/`, `documentation/`, `history/`, `rules/`).
`rules_hook.py` finds those rules through the registry path or the files being touched.
See `SKILL.md` for page rules, migration and anti-patterns.
