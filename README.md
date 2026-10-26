# docs-pattern v2

Claude Code skill: project `docs/` as development documentation.

- `state/S###.md` — one page per stage; the single `status: active` page is the current status
- `issues/I###.md` — one page per issue (matches GitHub issue numbers when a tracker exists)
- `documentation/**.md` — hierarchical concept pages (`a/b.md` is a child of `a.md`)
- `history/<same path>` — per-page change log, `- YYYY-MM-DD what — why`
- `[[ID]]` links; `scripts/docs_build.py` deterministically generates `index.md`, `current_status.md`,
  `_build/compiled.md`, `_build/backlinks.json` and fails on broken links, duplicate IDs, missing
  parents/history (`--check`, `--selftest`)
- The orchestrating session writes facts to `docs/_inbox/`; a worker edits pages until the checker passes
  (`references/worker_brief.md`)
- `scripts/status_check.py` — derive done/partial/pending from artifacts and reconcile with GitHub issues

See `SKILL.md`. Init: `bash scripts/init-docs.sh [docs]`.
