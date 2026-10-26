#!/usr/bin/env python3
"""docs-pattern v3 hub builder — docs-hub sources -> MkDocs site source (HUB/_site/) + HUB/mkdocs.yml.

Sources (never written by this script):
  HUB/projects/<name>/        v2 docs of one project (docs_build.py checks it; its pages never link memos,
                              memos may link its pages)
    The first three menus are what rules_hook puts into the agent's context (docs_build.context, BUDGET):
    current_status.md         -> "Agent State" (one page: where the project is now)
    rules/R###.md             -> "Short Term Memory" (this project's rules and facts, one flat list)
    documentation/            -> "Document" (what the project is)
    state/ issues/            -> "Archive" (stages and issues, read on demand)
  MEMORY_DIR                  Claude auto-memory -> "Long Term Memory" (memos used across projects;
                              stays where Claude loads it, read only here)
  SKILLS_DIR/*/SKILL.md       -> skills.md catalog (source, backup, calls in the last 30 days)
Generated (never edit by hand): HUB/_site/**, HUB/mkdocs.yml. A file is written only when its content
changes, so `mkdocs serve` reloads only on real edits. history/, _build/, _inbox/ are not published.
Links [[ID]], [[ID|text]], [[ID#h]] become relative .md links (anchor dropped); unresolved ones stay text.

Usage: hub_build.py [HUB] [--selftest]
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docs_build  # noqa: E402
from memory_build import MARK as MEM_MARK, archived as mem_archived, areas_of, fm as mem_fm, ordered  # noqa: E402

HOME = Path.home()
MEMORY_DIR = HOME / "memory"   # v3 공유 메모리 원본 (계정별 보기 = memory/view/<계정>)
SKILLS_DIR = HOME / ".claude/skills"
SESSIONS = HOME / ".claude/projects"
SKIP = {"history", "_build", "_inbox", "mounts"}
LINK = re.compile(r"(?<!!)\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]*))?\]\]")


def fm_of(path):
    fm, _ = docs_build.frontmatter(path.read_text(encoding="utf-8"))
    return fm


def memo_keys(path):
    """-> names a memo answers to: file stem, frontmatter name, and both with _ <-> -"""
    keys = {path.stem, fm_of(path).get("name", "")}
    return {k for key in keys if key for k in (key, key.replace("_", "-"), key.replace("-", "_"))}


def rewrite(text, here, targets):
    """[[ID]] -> [text](relative path) for IDs in targets {id: output path}"""
    def sub(m):
        tid, label = m.group(1).strip(), m.group(2)
        if tid not in targets:
            return label or tid
        return f"[{label or tid}]({os.path.relpath(targets[tid], here.parent)})"
    return LINK.sub(sub, text)


def skills_page(skills_dir, sessions, always=()):
    """-> ({site path: text}, nav). 목록 page + 스킬마다 page(SKILL.md 본문 · 파일 목록 · 백업 · 호출), 메뉴는 필수 / 나머지"""
    since = time.time() - 30 * 86400
    calls = {}
    for f in sessions.glob("*/*.jsonl"):
        if f.stat().st_mtime >= since:
            for m in re.finditer(rb'"name":"Skill","input":\{"skill":"([^"]+)"', f.read_bytes()):
                name = m.group(1).decode().split(":")[-1]
                calls[name] = calls.get(name, 0) + 1
    rows, pages, must, rest = [], {}, [], []
    skip = {".git", "node_modules", "__pycache__", ".venv", ".trash"}
    for d in sorted(p for p in skills_dir.iterdir() if (p / "SKILL.md").exists()):
        fm = fm_of(d / "SKILL.md")
        real = d.resolve()
        git = lambda *a: subprocess.run(["git", "-C", str(real), *a], capture_output=True, text=True).stdout.strip()
        top = git("rev-parse", "--show-toplevel")
        remote = git("remote", "get-url", "origin") if top else ""
        if (d / "VENDORED.md").exists():
            backup = "벤더링(원본에서 다시 받음)"
        elif not top:
            backup = "**없음** (git 아님)"
        elif not remote:
            backup = "**없음** (원격 없음)"
        else:
            dirty = len(git("status", "--porcelain").splitlines())
            ahead = git("rev-list", "--count", "@{u}..HEAD") or "?"
            repo = re.sub(r"^.*github\.com[:/]|\.git$", "", remote)
            backup = repo + ("" if dirty == 0 and ahead == "0" else f" — 미커밋 {dirty} · 미push {ahead}")
        desc = fm.get("description", "").replace("|", "\\|")
        short = desc[:110] + ("…" if len(desc) > 110 else "")
        is_must = d.name in always
        rows.append(f"| [{d.name}](skills/{d.name}.md) | {'필수' if is_must else ''} | {calls.get(d.name, 0)} | {backup} | {short} |")
        files = sorted(f.relative_to(real).as_posix() for f in real.rglob("*") if f.is_file() and not skip & set(f.relative_to(real).parts))
        text = (d / "SKILL.md").read_text(encoding="utf-8")
        body = text[4:].partition("\n---\n")[2] if text.startswith("---\n") else text
        pages[f"skills/{d.name}.md"] = "\n".join([
            f"# {d.name}", "", f"> {desc}", "",
            "| 항목 | 값 |", "|---|---|", f"| 세션 시작에 자동 | {'필수 (핵심 부분)' if is_must else '아니오 — 필요할 때 Skill 툴로'} |",
            f"| 최근 30일 호출 | {calls.get(d.name, 0)} |", f"| 백업 | {backup} |", f"| 위치 | `{real}` |", "",
            f"## 파일 ({len(files)})", "", *[f"- `{f}`" for f in files[:80]], *(["- …"] if len(files) > 80 else []), "",
            "## SKILL.md", "", body.strip(), ""])
        (must if is_must else rest).append({d.name: f"skills/{d.name}.md"})
    pages["skills.md"] = "\n".join(["# Skills", "", f"`{skills_dir}` 의 스킬 {len(rows)}개. 필수 = 세션 시작에 핵심 부분이 자동으로 들어감"
                      "(목록 `~/memory/_always.md`). 호출 = 최근 30일 세션 기록의 Skill 도구 호출 수.", "",
                      "| 스킬 | 필수 | 호출 | 백업 | 설명 |", "|---|---|---:|---|---|", *rows, ""])
    return pages, [{"목록": "skills.md"}, {"필수": must}, {"나머지": rest}]


MOUNT_NAV_SKIP = {"legacy", "releases", "_inputs", "diagrams", "node_modules", ".git", ".build"}   # 사이트엔 있되 메뉴엔 안 넣는 폴더


def page_title(f):
    text = f.read_text(encoding="utf-8", errors="replace")
    fm, body = docs_build.frontmatter(text)
    head = next((l[2:].strip() for l in body.splitlines() if l.startswith("# ")), "")
    return fm.get("title") or head or f.stem


def mount_nav(root, base):
    """바깥 문서 폴더(제품 문서 등)의 메뉴. SUMMARY.md(GitBook)가 있으면 그 순서, 없으면 `a/b.md` = `a.md` 의 자식인 파일 나무"""
    summary = root / "SUMMARY.md"
    if summary.exists():
        nav, sec = [], None
        for line in summary.read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                sec = []; nav.append({line[3:].strip(): sec})
            elif m := re.match(r"\s*[*-] \[([^\]]+)\]\(([^)#]+\.md)\)", line):
                (sec if sec is not None else nav).append({m.group(1): f"{base}/{m.group(2)}"})
        return nav

    def tree(d, rel):
        files = sorted(f for f in d.glob("*.md") if f.name != "SUMMARY.md")
        first = [f for f in files if f.stem.lower() in ("home", "index", "readme")]
        out = []
        for f in first + [f for f in files if f not in first]:
            link = f"{base}/{rel}{f.name}"
            sub = d / f.stem
            kids = tree(sub, f"{rel}{f.stem}/") if sub.is_dir() and f.stem not in MOUNT_NAV_SKIP else []
            out.append({page_title(f): [{page_title(f): link}] + kids} if kids else {page_title(f): link})
        for sub in sorted(p for p in d.iterdir() if p.is_dir() and not (d / f"{p.name}.md").exists() and p.name not in MOUNT_NAV_SKIP and not p.name.startswith(".")):
            if kids := tree(sub, f"{rel}{sub.name}/"):
                out.append({sub.name: kids})
        return out
    return tree(root, "")


def read_registry(org):
    """projects/<조직>/_registry.md 의 표 -> [{name, status, path, docs, note}]"""
    f = org / "_registry.md"
    out = []
    for line in (f.read_text(encoding="utf-8").splitlines() if f.exists() else []):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[1] in ("active", "paused", "archived"):
            out.append({"name": cells[0], "status": cells[1], "path": cells[2].strip("`"),
                        "docs": cells[3] if len(cells) > 3 else "", "note": cells[4] if len(cells) > 4 else ""})
    return out


def build(hub, memory_dir=MEMORY_DIR, skills_dir=SKILLS_DIR, sessions=SESSIONS):
    """-> (files written, project check failures)"""
    hub, site = Path(hub), Path(hub) / "_site"
    out, nav, fails = {}, [{"Home": "index.md"}], {}
    ltm = sorted(p for p in Path(memory_dir).glob("*.md") if p.name != "MEMORY.md" and not p.name.startswith("_"))
    root = Path(memory_dir) / "_root.md"
    ltm_targets = {k: f"long-term-memory/{p.name}" for p in ltm for k in memo_keys(p)}
    ORDER = ("INTERX", "workspace", "SapiensQ")   # 사용자가 정한 조직 순서, 나머지는 뒤에 가나다
    orgs = sorted((o for o in (hub / "projects").iterdir() if o.is_dir()), key=lambda o: (ORDER.index(o.name) if o.name in ORDER else 99, o.name)) if (hub / "projects").exists() else []
    projects = [p for o in orgs for p in sorted(o.iterdir()) if p.is_dir() and not p.name.startswith(("_", ".")) and p.name != "rules"]   # . = 조직 폴더가 따로 git 이면 .git
    registry = {o.name: read_registry(o) for o in orgs}   # 조직마다 _registry.md: 이름 · status · 경로 · 메모
    rows, nodes, edges, proj_nav, links = [], [], [], {}, {}
    for proj in projects:
        pages, _ = docs_build.load(proj)
        fails[proj.name] = docs_build.run(proj, check=True, quiet=True)[0]
        base = f"projects/{proj.parent.name}/{proj.name}"
        targets = {**ltm_targets, **{pid: f"{base}/{p['rel']}" for pid, p in pages.items()}}
        act = next((pg["rel"] for pg in pages.values() if pg["kind"] == "state" and pg["status"] == "active"), None)
        for f in sorted(proj.rglob("*.md")):
            rel = f.relative_to(proj)
            if not SKIP & set(rel.parts):
                dst = f"{base}/{rel.as_posix()}"
                text = f.read_text(encoding="utf-8")
                hist = proj / "history" / (act if rel.as_posix() == "current_status.md" and act else rel.as_posix())
                if hist.exists() and hist.read_text(encoding="utf-8").strip():   # page 아래 접힌 변경 기록 (Agent 주입에는 안 들어감)
                    lines = hist.read_text(encoding="utf-8").strip().splitlines()
                    text = text.rstrip() + f'\n\n??? note "변경 기록 {len(lines)}"\n' + "\n".join("    " + l for l in lines) + "\n"
                out[dst] = rewrite(text, Path(dst), targets)
        title = lambda p: {p["title"]: f"{base}/{p['rel']}"}
        group = lambda kind: [title(p) for p in sorted(pages.values(), key=lambda p: p["rel"]) if p["kind"] == kind]
        archive = [{name: items} for name, items in (("Stages", group("state")), ("Issues", group("issues"))) if items]
        mounts = sorted(m for m in (proj / "mounts").iterdir() if m.is_dir()) if (proj / "mounts").is_dir() else []
        for m in mounts:   # 바깥 문서는 복사하지 않고 심링크로 건다 — 원본이 바뀌면 사이트도 바로 바뀐다
            links[f"{base}/mounts/{m.name}"] = m.resolve()
        section = [{"Agent State": f"{base}/current_status.md"}, {"Short Term Memory": group("rules")},
                   {"Document": group("doc") + [{m.name: mount_nav(m.resolve(), f"{base}/mounts/{m.name}")} for m in mounts]},
                   {"Archive": archive}]
        proj_nav.setdefault(proj.parent.name, []).append({proj.name: [s for s in section if list(s.values())[0]]})
        active = next((p["title"] for p in pages.values() if p["kind"] == "state" and p["status"] == "active"), "—")
        ctx = sum(map(len, docs_build.context(proj, pages).values()))
        kinds = lambda k, st=None: sum(1 for p in pages.values() if p["kind"] == k and (st is None or p["status"] == st))
        pn = f"proj:{proj.parent.name}/{proj.name}"
        nodes.append({"id": pn, "label": proj.name + (f" · 열린 이슈 {kinds('issues', 'open')}" if kinds("issues", "open") else ""),
                      "group": "project", "url": f"{base}/current_status.html",
                      "title": f"{proj.name} — {active} · context {ctx:,}/{docs_build.CONTEXT_LIMIT:,}자 · 열린 이슈 {kinds('issues', 'open')}",
                      "bad": bool(fails[proj.name]) or ctx > docs_build.CONTEXT_LIMIT})
        for pid, pg in pages.items():
            nid = f"{proj.parent.name}/{proj.name}:{pid}"
            nodes.append({"id": nid, "label": pg["title"][:28], "group": pg["kind"], "url": f"{base}/{pg['rel'][:-3]}.html",
                          "title": f"{pid} {pg['title']}" + (f" ({pg['status']})" if pg["status"] else ""), "status": pg["status"]})
            edges.append({"from": pn, "to": nid, "kind": "in"})
            for t in sorted({m.strip() for m in docs_build.LINK.findall(pg["body"])}):
                if t in pages and t != pid:
                    edges.append({"from": nid, "to": f"{proj.parent.name}/{proj.name}:{t}", "kind": "link"})
        rows.append(f"| {proj.parent.name} | {proj.name} | [Agent State]({base}/current_status.md) | {active} | {len(group("rules"))} | "
                    f"{'OK' if not fails[proj.name] else f'**FAIL {len(fails[proj.name])}**'} |")
    org_nav = []
    for o in orgs:
        reg = registry[o.name]
        nodes.append({"id": f"org:{o.name}", "label": o.name, "group": "org", "url": f"projects/{o.name}/index.html", "title": f"조직 {o.name}"})
        hubbed = {p.name for p in projects if p.parent == o}
        lines = [f"# {o.name}", "", "프로젝트 목록. status = active(진행 중) · paused(쉬는 중) · archived(보관). 원본 = `_registry.md`.", "",
                 "| 프로젝트 | status | 경로 | docs | 메모 |", "|---|---|---|---|---|"]
        for r in reg:
            link = f"[{r['name']}]({r['name']}/current_status.md)" if r["name"] in hubbed else r["name"]
            lines.append(f"| {link} | {r['status']} | `{r['path']}` | {'hub' if r['name'] in hubbed else r.get('docs', '—')} | {r.get('note', '')} |")
            if r["status"] == "active":
                pid = f"proj:{o.name}/{r['name']}"
                if r["name"] not in hubbed:
                    nodes.append({"id": pid, "label": r["name"], "group": "project", "url": f"projects/{o.name}/index.html",
                                  "title": f"{r['name']} — 진행 중, docs 아직 hub 에 없음"})
                edges.append({"from": f"org:{o.name}", "to": pid, "kind": "in"})
        out[f"projects/{o.name}/index.md"] = "\n".join(lines) + "\n"
        active = [x for x in proj_nav.get(o.name, []) if any(r["name"] == list(x)[0] and r["status"] == "active" for r in reg) or not reg]
        rest = [x for x in proj_nav.get(o.name, []) if x not in active]
        items = [{"목록": f"projects/{o.name}/index.md"}] + active + ([{"쉬는 중 · 보관": rest}] if rest else [])
        org_nav.append({o.name: items})
    nav.append({"Projects": org_nav})
    groups = {}
    for p in ltm:
        dst = f"long-term-memory/{p.name}"
        out[dst] = rewrite(p.read_text(encoding="utf-8"), Path(dst), ltm_targets)
        f = mem_fm(p)
        title = (f.get("index") or f.get("description") or p.stem).partition(" — ")[0]
        mid = f"mem:{p.stem}"
        if not mem_archived(f):   # 보관 메모는 그래프에 넣지 않는다(보관 page 에만)
            areas = areas_of(f) or ["미분류"]
            nodes.append({"id": mid, "label": title[:28], "group": "memo", "url": f"long-term-memory/{p.stem}.html",
                          "parent": "area:필수" if "필수" in areas else f"area:{areas[0]}",
                          "title": f"{title} — {', '.join(areas)}" + (f" · org {f['org']}" if f.get("org") else "")})
        for area in (["보관"] if mem_archived(f) else areas_of(f) or ["미분류"]):   # 여러 area 면 여러 분야 page 에 나온다, 보관은 보관 page 만
            groups.setdefault(area, []).append(f"- [{title}](../{p.name})")
            edges.append({"from": mid, "to": f"area:{area}", "kind": "in"})
        text = p.read_text(encoding="utf-8")
        for t in set(LINK.findall(text)) | {(m, "") for m in re.findall(r"\]\(([\w.-]+)\.md\)", text)}:
            tgt = ltm_targets.get(t[0].strip())
            if tgt and tgt != dst:
                edges.append({"from": mid, "to": "mem:" + Path(tgt).stem, "kind": "link"})
    view = Path(memory_dir) / "view/personal"
    if (view / "MEMORY.md").exists():   # 개요 = 개인 계정 Agent 가 세션 시작에 받는 색인 그대로
        idx = (view / "MEMORY.md").read_text(encoding="utf-8").replace(MEM_MARK, "").strip()
        out["long-term-memory/index.md"] = "# Long Term Memory\n\n" + idx + "\n"
        for pf in view.glob("_project-*.md"):
            out[f"long-term-memory/{pf.name}"] = pf.read_text(encoding="utf-8")
    elif root.exists():
        out["long-term-memory/index.md"] = "# Long Term Memory\n\n" + root.read_text(encoding="utf-8").strip() + "\n"
    area_nav = []
    for area, lines in ordered(groups).items():
        slug = "area/" + re.sub(r"[^\w-]+", "-", area).strip("-") + ".md"
        if area != "보관":
            nodes.append({"id": f"area:{area}", "label": f"{area} {len(lines)}", "group": "area", "url": f"long-term-memory/{slug[:-3]}.html", "title": f"분야 {area} — 메모 {len(lines)}"})
        out[f"long-term-memory/{slug}"] = f"# {area}\n\n메모 {len(lines)}개\n\n" + "\n".join(lines) + "\n"
        area_nav.append({area: f"long-term-memory/{slug}"})
    nav.append({"Long Term Memory": ([{"개요": "long-term-memory/index.md"}] if "long-term-memory/index.md" in out else [])
                + area_nav})
    from memory_build import always_skills
    spages, snav = skills_page(Path(skills_dir), Path(sessions), set(always_skills(memory_dir)))
    out.update(spages)
    nav.append({"Skills": [x for x in snav if list(x.values())[0]]})
    from memory_build import lint as mem_lint
    bad = {f_[:-3] for f_, _ in mem_lint(memory_dir)} if Path(memory_dir).exists() else set()
    ids = {n["id"] for n in nodes}
    for n in nodes:
        if n["group"] == "memo" and n["id"][4:] in bad:
            n["bad"] = True
    must = {list(x)[0] for x in snav[1]["필수"]}
    for x in snav[1]["필수"] + snav[2]["나머지"]:
        name = list(x)[0]
        nodes.append({"id": f"skill:{name}", "label": name, "group": "skill", "url": f"skills/{name}.html",
                      "title": f"스킬 {name}" + (" — 필수(세션마다 자동)" if name in must else ""), "must": name in must,
                      "parent": "area:필수" if name in must else "hub:skills"})
        edges.append({"from": f"skill:{name}", "to": "hub:skills", "kind": "in"})   # 스킬은 한 중심점에 묶는다
        if name in must:
            edges.append({"from": f"skill:{name}", "to": "area:필수", "kind": "in"})
    nodes.append({"id": "hub:skills", "label": f"스킬 {len(snav[1]['필수']) + len(snav[2]['나머지'])}", "group": "area", "url": "skills.html", "title": "스킬 목록"})
    if any(e["to"] == "area:필수" for e in edges) and "area:필수" not in ids:
        nodes.append({"id": "area:필수", "label": "필수", "group": "area", "url": "skills.html", "title": "세션마다 자동으로 들어가는 것"})
    # 메모가 스킬 이름을 [[링크]] 하면 선
    skill_ids = {n["id"][6:] for n in nodes if n["group"] == "skill"}
    for p in ltm:
        for t in {m[0].strip() for m in LINK.findall(p.read_text(encoding="utf-8"))} & skill_ids:
            edges.append({"from": f"mem:{p.stem}", "to": f"skill:{t}", "kind": "link"})
    # 분야·필수·스킬 묶음을 한 점에 묶는다 — 선이 없는 점은 흩어져서 화면이 멀어진다
    nodes.append({"id": "hub:ltm", "label": "Long Term Memory", "group": "org", "url": "long-term-memory/index.html", "title": "Long Term Memory 개요"})
    edges.extend({"from": n["id"], "to": "hub:ltm", "kind": "in"} for n in nodes if n["group"] == "area" and n["id"] not in ("hub:skills",))
    edges.append({"from": "hub:skills", "to": "area:필수", "kind": "in"})
    # 기본 화면 = 지금 진행 중인 것만(조직 · 프로젝트 · 진행 중 단계 · 분야 · 필수 · 스킬 묶음). 나머지는 부모 점을 눌러 펼치거나 '모두 보기'
    for n in nodes:
        g = n["group"]
        if g in ("state", "issues", "rules", "doc"):
            n["parent"] = "proj:" + n["id"].split(":")[0]
            n["show"] = ("base" if n.get("status") == "active" else "all") if g == "state" else \
                        ("child" if n.get("status") == "open" else "all") if g == "issues" else "child"
        else:
            n["show"] = "child" if n.get("parent") else "base"
        if n["id"] == "area:필수":
            n["label"] = f"필수 {sum(1 for m in nodes if m.get('parent') == 'area:필수')}"
    ids = {n["id"] for n in nodes}
    edges = [e for e in edges if e["from"] in ids and e["to"] in ids]
    out["assets/graph.json"] = json.dumps({"nodes": nodes, "edges": edges}, ensure_ascii=False, sort_keys=True)
    tpl = Path(__file__).resolve().parent.parent / "templates/hub"
    for name in ("graph.js", "graph.css"):
        out[f"assets/{name}"] = (tpl / name).read_text(encoding="utf-8")
    out["index.md"] = "\n".join(["# docs-hub", "",
                                 '<div class="hub-graph" id="hub-graph" data-src="assets/graph.json"></div>',
                                 '<div class="hub-legend" id="hub-legend"></div>', "",
                                 f"처음엔 지금 진행 중인 것만 보인다(점 {sum(1 for n in nodes if n['show'] == 'base')} / 전체 {len(nodes)}). 프로젝트·분야·필수·스킬 점을 누르면 그 아래가 펼쳐지고 다시 누르면 접힌다. "
                                 "두 번 누르면 그 page 로 간다. '모두 보기'는 끝난 단계·닫힌 이슈까지 전부, 범례의 종류를 누르면 그 종류를 숨긴다, '문제 보기'는 문제 점만 빨간 테두리로. 보관 메모는 그래프에 없다(Long Term Memory › 보관).", "",
                                 "## 프로젝트", "", "프로젝트마다 Agent State(지금 상황 한 장)부터 본다.", "",
                                 "| 조직 | 프로젝트 | 입구 | 현재 단계 | Short Term Memory | docs 검사 |",
                                 "|---|---|---|---|---:|---|", *rows, "",
                                 f"Long Term Memory {len(ltm)}개 · [Skills](skills.md)", ""])
    nav_names = [list(n)[0] for n in nav]
    nav = [nav[0], nav[nav_names.index("Projects")], nav[nav_names.index("Long Term Memory")], nav[nav_names.index("Skills")]]
    yml = "\n".join([
        "# generated by docs-pattern/scripts/hub_build.py; do not edit",
        "site_name: docs-hub", "docs_dir: _site", "use_directory_urls: false",
        "theme:", "  name: material", "  language: ko",
        "  features: [navigation.prune, navigation.sections, navigation.indexes, search.highlight]",   # prune: 페이지마다 메뉴 전체를 굽지 않는다 (1,100쪽에서 13.5 s → 7.5 s)
        "  palette:",
        "    - media: '(prefers-color-scheme: light)'", "      scheme: default",
        "      toggle: {icon: material/brightness-7, name: dark}",
        "    - media: '(prefers-color-scheme: dark)'", "      scheme: slate",
        "      toggle: {icon: material/brightness-4, name: light}",
        "markdown_extensions: [tables, toc, admonition, pymdownx.details]", "plugins: [search]",
        "extra_css: [assets/graph.css]",
        "extra_javascript: [https://cdnjs.cloudflare.com/ajax/libs/vis-network/10.1.2/standalone/umd/vis-network.min.js, assets/graph.js]",
        "nav: " + json.dumps(nav, ensure_ascii=False), ""])
    written = []
    for rel, text in {**{f"_site/{k}": v for k, v in out.items()}, "mkdocs.yml": yml}.items():
        p = hub / rel
        if not p.exists() or p.read_text(encoding="utf-8") != text:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
            written.append(rel)
    for rel, target in links.items():
        p = site / rel
        if not p.is_symlink() or p.resolve() != target:
            if p.is_symlink():
                p.unlink()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.symlink_to(target, target_is_directory=True)
            written.append(f"_site/{rel}")
    keep = {hub / f"_site/{k}" for k in out}
    for p in sorted(site.rglob("*"), reverse=True):   # rglob 은 심링크 폴더 안으로 들어가지 않는다 — 원본을 지우지 않음
        if p.is_symlink():
            if p.relative_to(site).as_posix() not in links:
                p.unlink(); written.append(f"-{p.relative_to(hub)}")
        elif p.is_file() and p not in keep:
            p.unlink(); written.append(f"-{p.relative_to(hub)}")
        elif p.is_dir() and not any(p.iterdir()):
            p.rmdir()
    return written, fails


def selftest():
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        w = lambda rel, s: ((t / rel).parent.mkdir(parents=True, exist_ok=True), (t / rel).write_text(s))
        w("hub/projects/o/_registry.md", "| 프로젝트 | status | 경로 | docs | 메모 |\n|---|---|---|---|---|\n| p | active | ~/p | hub | |\n| q | paused | ~/q | — | 쉬는 중 |\n")
        w("hub/projects/o/p/state/S001.md", "---\ntitle: 시작\nstatus: active\n---\n[[arch|구조]]")
        w("hub/projects/o/p/documentation/arch.md", "---\ntitle: 구조\n---\n[[S001#목표]]")
        w("hub/projects/o/p/rules/R001.md", "---\ntitle: 규칙 하나\n---\n[[S001]]")
        for rel in ("state/S001.md", "documentation/arch.md", "rules/R001.md"):
            w(f"hub/projects/o/p/history/{rel}", "- 2026-09-01 만듦 — x")
        w("mem/ltm_a.md", "---\nname: ltm-a\nmetadata:\n  type: feedback\narea: [일하는 방식, 새분야]\n---\n[[ltm_b]]")
        w("mem/view/personal/MEMORY.md", "<!-- generated by docs-pattern/scripts/memory_build.py from memo files; edit memos, not this file -->\n색인본문 [ltm-a](ltm_a.md)\n")
        w("mem/_root.md", "뿌리 문단")
        w("mem/ltm_b.md", "---\nname: ltm-b\nmetadata:\n  type: user\n---\n[[ltm-a]] [[없는것]]")
        w("mem/MEMORY.md", "- index")
        w("mem/ltm_old.md", "---\nname: ltm-old\narea: 새분야\nstatus: archived\n---\n옛것")
        w("skills/s1/SKILL.md", "---\nname: s1\ndescription: a|b\n---\n")
        (t / "sess").mkdir()
        (t / "hub/projects/o/.git").mkdir(parents=True)   # 조직 폴더가 따로 git repo 여도 .git 은 프로젝트가 아니다
        w("ext/Home.md", "# 입구"); w("ext/concepts.md", "# 개념"); w("ext/concepts/cq.md", "---\ntitle: CQ\n---\n")
        w("ext/legacy/old.md", "# 옛것"); w("ext/how-to/x.md", "# 하기")
        (t / "hub/projects/o/p/mounts").mkdir(parents=True)
        (t / "hub/projects/o/p/mounts/제품문서").symlink_to(t / "ext")
        docs_build.run(t / "hub/projects/o/p", quiet=True)
        args = (t / "hub", t / "mem", t / "skills", t / "sess")
        written, fails = build(*args)
        site = t / "hub/_site"
        s1 = (site / "projects/o/p/state/S001.md").read_text()
        assert "[구조](../documentation/arch.md)" in s1, s1
        assert "[S001](../state/S001.md)" in (site / "projects/o/p/rules/R001.md").read_text()
        note = (site / "long-term-memory/ltm_b.md").read_text()
        assert "[ltm-a](ltm_a.md)" in note and "[ltm_b](ltm_b.md)" in (site / "long-term-memory/ltm_a.md").read_text(), note
        arch = (site / "projects/o/p/documentation/arch.md").read_text()
        assert "[S001](../state/S001.md)" in arch and '??? note "변경 기록 1"' in arch and "    - 2026-09-01 만듦" in arch, arch
        assert "없는것" in note and "[[" not in note, "미해석 링크는 글자로 남아야 함"
        assert not (site / "projects/o/p/history").exists(), "history 가 사이트에 나옴"
        assert not (site / "long-term-memory/MEMORY.md").exists(), "MEMORY.md 가 사이트에 나옴"
        assert "a\\|b" in (site / "skills.md").read_text(), "표 칸 구분자 미이스케이프"
        assert (site / "skills/s1.md").exists() and "SKILL.md" in (site / "skills/s1.md").read_text(), "스킬 page 없음"
        g = json.loads((site / "assets/graph.json").read_text())
        grp = {n["group"] for n in g["nodes"]}
        assert {"project", "state", "doc", "memo", "area", "skill"} <= grp, grp
        assert {"from": "o/p:arch", "to": "o/p:S001", "kind": "link"} in g["edges"], "page 링크 선 없음"
        sh = {n["id"]: (n["show"], n.get("parent")) for n in g["nodes"]}
        assert sh["o/p:S001"] == ("base", "proj:o/p") and sh["o/p:arch"] == ("child", "proj:o/p") and sh["proj:o/p"][0] == "base", sh
        assert sh["mem:ltm_a"] == ("child", "area:일하는 방식") and sh["area:일하는 방식"][0] == "base" and "mem:ltm_old" not in sh and "area:보관" not in sh, "기본 화면·펼침·보관 제외"
        assert any(e["from"] == "mem:ltm_a" and e["to"] == "mem:ltm_b" for e in g["edges"]), "메모 링크 선 없음"
        assert 'id="hub-graph"' in (site / "index.md").read_text() and (site / "assets/graph.js").exists() and "mermaid" not in (t / "hub/mkdocs.yml").read_text()
        yml = (t / "hub/mkdocs.yml").read_text()
        assert '"Agent State"' in yml and '"일하는 방식"' in yml and '"미분류"' in yml and '"개요"' in yml, yml
        ov = (site / "long-term-memory/index.md").read_text()
        assert "색인본문 [ltm-a](ltm_a.md)" in ov and "generated by" not in ov and not (site / "long-term-memory/_root.md").exists(), "개요 = 색인 아님"
        assert "ltm_a.md" in (site / "long-term-memory/area/새분야.md").read_text() and "ltm_a.md" in (site / "long-term-memory/area/일하는-방식.md").read_text(), "여러 area 분야 page"
        assert "ltm_b.md" in (site / "long-term-memory/area/미분류.md").read_text() and '"새분야"' in yml
        assert "ltm_old.md" in (site / "long-term-memory/area/보관.md").read_text() and "ltm_old.md" not in (site / "long-term-memory/area/새분야.md").read_text(), "보관 메모가 보관 page 에만 있어야 함"
        projs = json.loads(yml.split("nav: ", 1)[1])[1]["Projects"][0]["o"]
        assert projs[0] == {"목록": "projects/o/index.md"}, projs
        proj = projs[1]["p"]
        assert [list(x)[0] for x in proj] == ["Agent State", "Short Term Memory", "Document", "Archive"], proj
        assert proj[1]["Short Term Memory"] == [{"규칙 하나": "projects/o/p/rules/R001.md"}], "STM 은 폴더 없이 나열"
        reg = (site / "projects/o/index.md").read_text()
        assert "| q | paused |" in reg and "[p](p/current_status.md)" in reg, reg
        assert "쉬는 중 · 보관" not in yml, "active 인데 보관으로 감"
        assert [list(x)[0] for x in proj[3]["Archive"]] == ["Stages"], proj
        assert fails == {"p": []}, fails
        mdoc = proj[2]["Document"][-1]["제품문서"]
        mb = "projects/o/p/mounts/제품문서"
        assert mdoc[0] == {"입구": f"{mb}/Home.md"} and mdoc[1] == {"개념": [{"개념": f"{mb}/concepts.md"}, {"CQ": f"{mb}/concepts/cq.md"}]}, mdoc
        assert {"how-to": [{"하기": f"{mb}/how-to/x.md"}]} in mdoc and "legacy" not in json.dumps(mdoc), mdoc
        assert (site / mb).is_symlink() and (site / mb / "legacy/old.md").exists(), "바깥 문서 심링크 없음"
        assert build(*args)[0] == [], "두 번째 실행이 파일을 다시 씀(결정론 아님)"
        (t / "hub/projects/o/p/mounts/제품문서").unlink()
        assert f"-_site/{mb}" in build(*args)[0] and not (site / mb).exists(), "뺀 바깥 문서가 사이트에 남음"
        assert (t / "ext/Home.md").exists() and (t / "ext/legacy/old.md").exists(), "정리가 바깥 원본을 지움"
        (t / "mem/ltm_b.md").unlink()
        assert "-_site/long-term-memory/ltm_b.md" in build(*args)[0], "지운 원본이 사이트에 남음"
    print("selftest OK — 링크(프로젝트·STM·LTM·미해석)·제외 폴더·표 이스케이프·nav·결정론·삭제 반영")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
        sys.exit(0)
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    written, fails = build(Path(args[0] if args else Path.home() / "workspace/docs-hub"))
    for name, f in fails.items():
        for line in f:
            print(f"FAIL {name}: {line}")
    print(f"written {len(written)}" + (": " + ", ".join(written[:10]) if written else ""))
