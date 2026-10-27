#!/usr/bin/env python3
"""Claude Code hook (UserPromptSubmit + SessionStart): put the working rules of the project in use into context.

Rules live in the project, not in Claude's memory: docs/rules/R###.md, one rule per page (docs-pattern).
docs-hub project (v3, HUB/projects/<name>/): injects docs_build.context() = Agent State (current_status.md) +
Short Term Memory (rules/) + Document (root page overview.md + one summary line per other page). The project is in use when the
cwd is inside HUB/projects/<name>/ or inside a WORKSPACE directory named <name> (its code repo), or the prompt names it.
Project = the nearest ancestor of the hook's cwd that has docs/rules/, plus every project directly under
WORKSPACE whose directory name appears in the prompt. A project's rules are injected once per session and again
when they change; SessionStart (startup, resume, compact, clear) forgets what was injected, because compaction
drops earlier hook output. Every prompt also gets one line per rule (its title) so a long session keeps them in view.

Asset cards: a rule whose frontmatter has `assets:` (aliases, IPs, instance ids of a shared resource) is a card for that
resource. PreToolUse(Bash): a command naming an asset gets its card injected (once per session per card version); a card
with `deny:` blocks the command unless it carries `asset-ok:<project>/<R###>` (added only after the user approves).
Asset names in a prompt pull the owning project's rules in, like `triggers:`.

Settings (~/.claude/settings.json): UserPromptSubmit + SessionStart, and PreToolUse with matcher "Bash":
{"type": "command", "command": "python3 <this file>"}
Selftest:  rules_hook.py --selftest
"""
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

WORKSPACE = Path(os.environ.get("RULES_WORKSPACE", Path.home() / "workspace"))
STATE = Path(os.environ.get("RULES_STATE", Path.home() / ".cache/docs-pattern/rules_hook"))
HUB = Path(os.environ.get("RULES_HUB", WORKSPACE / "docs-hub"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import docs_build  # noqa: E402
from hub_build import read_registry  # noqa: E402
import memory_build  # noqa: E402
MEMORY = Path(os.environ.get("RULES_MEMORY", Path.home() / "memory"))   # 별칭 = Long Term Memory 메모 project-aliases


DEPTH = ("*/", "*/*/", "*/*/*/")   # projects may sit below WORKSPACE (e.g. sapienceQ/research/Personapolis)


def rule_dirs(d):
    """Rules of project d: <d>/docs/rules or any <d>/docs-*/rules (a personal docs root such as docs-personal)."""
    return sorted(p for p in d.glob("docs*/rules") if p.is_dir() and HUB not in p.parents
                  and (p.parent.name == "docs" or p.parent.name.startswith("docs-")))


def is_hub(p):
    """hub 프로젝트 = HUB/projects/<조직>/<프로젝트>/"""
    return p.parent.parent == HUB / "projects"


def hub_projects():
    return sorted(d for d in (HUB / "projects").glob("*/*") if d.is_dir() and not d.name.startswith(("_", ".")))   # . = 조직 폴더의 .git 등


def hub_by_name(name):
    return next((d for d in hub_projects() if d.name == name), None)


def org_rules(p):
    """조직(container) 공통 Short Term Memory = HUB/projects/<조직>/rules/ — 그 아래 모든 프로젝트가 물려받는다"""
    r = p.parent / "rules"
    return sorted(r.glob("R[0-9][0-9][0-9].md")) if is_hub(p) and r.is_dir() else []


def name_of(p):
    """p = a legacy rules dir or a hub project dir"""
    return p.name if is_hub(p) else p.parent.parent.name


def rules_of(p):
    return p / "rules" if is_hub(p) else p


def front(p, key):
    """Comma list in frontmatter field `key` of rule page p."""
    m = re.search(rf"^{key}:\s*(.+)$", p.read_text(encoding="utf-8").split("\n---\n", 1)[0], re.M)
    return [w.strip().lower() for w in m.group(1).split(",") if w.strip()] if m else []


def triggers(rules):
    """Words in the rules' `triggers:` and `assets:` frontmatter; a prompt containing one pulls this project's rules in."""
    return [w for p in rules_of(rules).glob("R[0-9][0-9][0-9].md") for w in front(p, "triggers") + front(p, "assets")]


def mentions(text, word):
    """word as a whole token: aict-gpu1 does not match aict-gpu12, 13.209.2.8 does not match 13.209.2.89."""
    return re.search(rf"(?<![\w.-]){re.escape(word)}(?![\w-]|\.\d)", text.lower()) is not None


def all_rule_dirs():
    """legacy rules dirs + hub project dirs"""
    legacy = {r for pat in DEPTH for r in WORKSPACE.glob(pat + "docs*/rules") if r in rule_dirs(r.parent.parent)
              and not hub_by_name(r.parent.parent.name)}   # hub 로 옮기거나 링크한 프로젝트는 hub 쪽만
    return sorted(legacy) + hub_projects()


def cards(command):
    """(id, page, deny) for every asset card the command names."""
    return [(f"{name_of(rules)}/{p.stem}", p, bool(front(p, "deny")))
            for rules in all_rule_dirs() for p in sorted(rules_of(rules).glob("R[0-9][0-9][0-9].md"))
            if any(mentions(command, a) for a in front(p, "assets"))]


def card_text(cid, p):
    return f"[asset-card {cid}] 정본 = {p}\n" + p.read_text(encoding="utf-8").split("\n---\n", 1)[-1].strip()


def pre_tool(event, seen):
    """PreToolUse(Bash): inject the asset cards a command names; block a deny card without the user's asset-ok mark."""
    command = (event.get("tool_input") or {}).get("command") or ""
    found = cards(command)
    blocked = [(c, p) for c, p, deny in found if deny and f"asset-ok:{c}".lower() not in command.lower()]
    if blocked:
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                "permissionDecisionReason": "자원 카드가 이 명령을 막았다. 사용자 승인을 받은 뒤에만 명령에 "
                f"`# asset-ok:<카드>` 를 붙여 다시 실행한다.\n\n" + "\n\n".join(card_text(c, p) for c, p in blocked)}}
    new = [(c, p) for c, p, _ in found if seen.get("card:" + c) != p.stat().st_mtime]
    for c, p in new:
        seen["card:" + c] = p.stat().st_mtime
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
            "additionalContext": "\n\n".join(card_text(c, p) for c, p in new)}} if new else None


BIND = re.compile(r"(?<![\w.])@([\w.-]+|-)")


def path_projects(p):
    """경로 p 가 속한 프로젝트: 허브 폴더 · 이름이 같은 코드 repo · 옛 docs/rules repo. 세션의 cwd 는 쓰지 않는다 —
    어디서 세션을 열었는지에 따라 기억이 달라지면 안 되므로, 실제로 읽고 고치는 파일의 경로로만 판단한다"""
    p = Path(os.path.expanduser(str(p)))
    for d in [p, *p.parents]:
        if d == Path.home() or d.parent == Path("/"):
            break
        hub = hub_by_name(d.name)
        if (is_hub(d) and d.is_dir()) or hub:
            return [d if is_hub(d) and d.is_dir() else hub]
        if rule_dirs(d):
            return rule_dirs(d)
    return []


ORG_ORDER = ("INTERX", "workspace", "SapiensQ")   # hub_build 와 같은 조직 순서


def registry():
    orgs = sorted((o for o in (HUB / "projects").glob("*") if o.is_dir() and not o.name.startswith(".")),
                  key=lambda o: (ORG_ORDER.index(o.name) if o.name in ORG_ORDER else 99, o.name))
    al = memory_build.project_aliases(MEMORY)
    return [dict(r, org=o.name, aliases=[w for w, n in al.items() if n.lower() == r["name"].lower()]) for o in orgs for r in read_registry(o)]


def resolve(word):
    """프로젝트 이름 · 별칭(대소문자 무시, 별칭 = Long Term Memory project-aliases) -> 허브 프로젝트 폴더 또는 옛 rules 폴더, 없으면 None"""
    w = word.lower()
    for r in registry():
        if w in [r["name"].lower(), *(a.lower() for a in r["aliases"])]:
            if hub_by_name(r["name"]):
                return hub_by_name(r["name"])
            found = path_projects(r["path"]) if r["path"].startswith(("~", "/")) else []
            return found[0] if found else None
    return next((d for d in all_rule_dirs() if name_of(d).lower() == w), None)


ENTER_CMD = "python3 ~/workspace/docs-pattern/scripts/rules_hook.py --enter"
ENTER = re.compile(r"rules_hook\.py\s+--enter\s+['\"]?([^\s'\";|&]+)")


def stage_of(d):
    if not is_hub(d):
        return ""
    pages = docs_build.load(d)[0]
    return next((p["title"] for p in pages.values() if p["kind"] == "state" and p["status"] == "active"), "")


def project_map():
    """세션 시작에 넣는 프로젝트 지도 = _registry.md 의 진행 중 프로젝트(이름 · 별칭 · 한 줄 · 지금 단계) + 쉬는 중 이름"""
    out = [f"[project-map] 프로젝트 지도 (필수 스킬 docs-pattern). 어떤 프로젝트의 일을 시작하기 전에 `{ENTER_CMD} <이름|별칭>` 을 "
           "부른다 → 그 프로젝트의 Agent State · Short Term Memory · Document 목차 · 고른 Long Term Memory 가 들어온다. "
           "사용자가 지도에 없는 말로 부르면 `--as <그 말>` 을 붙여 부른다 → 별칭이 Long Term Memory 에 저장된다. "
           f"원본 = {HUB}/projects/<조직>/_registry.md · 별칭 = {MEMORY / memory_build.ALIASES}"]
    rows = registry()
    for org in dict.fromkeys(r["org"] for r in rows):
        out.append(f"## {org}")
        spell = {w.lower(): w for w in re.findall(r"^- ([^:\n]+):", (MEMORY / memory_build.ALIASES).read_text(encoding="utf-8"), re.M)} \
            if (MEMORY / memory_build.ALIASES).exists() else {}
        for r in (x for x in rows if x["org"] == org and x["status"] == "active"):
            r["aliases"] = [spell.get(a, a) for a in r["aliases"]]
            d = resolve(r["name"])
            stage = stage_of(d) if d else ""
            out.append(f"- {r['name']}" + (f" ({', '.join(r['aliases'])})" if r["aliases"] else "")
                       + (f" — {r['note']}" if r["note"] else "") + (f" · 지금: {stage}" if stage else "")
                       + ("" if d else " · 문서 없음"))
        rest = [x["name"] for x in rows if x["org"] == org and x["status"] == "paused"]
        if rest:
            out.append(f"- 쉬는 중 {len(rest)}: " + ", ".join(rest))
    return "\n".join(out)


def said(low, word):
    """word 가 낱말로 나왔나: 앞은 글자가 아니고, 뒤는 영숫자·- 가 아니다(한국어 조사 '를 · 는 · 에' 는 붙어도 된다)"""
    return re.search(rf"(?<![\w-]){re.escape(word.lower())}(?![A-Za-z0-9_-])", low) is not None


def projects(prompt, bound=()):
    """@이름 · --enter · 파일 경로로 이 세션에 붙은 프로젝트(bound, 경로 문자열) + 프롬프트에 이름이 나온 프로젝트"""
    found = [Path(b) for b in bound if Path(b).exists()]
    low = "" if "<task-notification>" in prompt else prompt.lower()   # 백그라운드 알림 속 이름은 사용자 언급이 아니다
    for rules in all_rule_dirs():
        if rules in found:
            continue
        named = said(low, name_of(rules))
        if named or any(w in low for w in triggers(rules)):
            found.append(rules)
    for word, name in memory_build.project_aliases(MEMORY).items():   # 별칭(Long Term Memory)이 프롬프트에 나오면 그 프로젝트
        d = resolve(name) if said(low, word) else None
        if d and d not in found:
            found.append(d)
    return found


def titles(rules):
    out = []
    for p in sorted(rules_of(rules).glob("R[0-9][0-9][0-9].md")):
        t = re.search(r"^title:\s*(.+)$", p.read_text(encoding="utf-8"), re.M)
        out.append(f"{p.stem} {t.group(1).strip() if t else ''}")
    return f"[project-rules {name_of(rules)}] " + " | ".join(out) if out else ""


def render(rules):
    if is_hub(rules):
        ctx = docs_build.context(rules, docs_build.load(rules)[0])
        out = [f"[project {rules.parent.name}/{rules.name}] 이 프로젝트의 Agent State · Short Term Memory · Document. 정본 = {rules}/ "
               "(바꿀 땐 docs-pattern inbox → 워커). Archive(state/ 지난 단계 · issues/)는 필요할 때 읽는다."]
        org = org_rules(rules)
        if org:
            out.append(f"# 조직 공통 Short Term Memory ({rules.parent.name})\n\n" + "\n\n".join(
                f"## {p.stem} {(re.search(r'^title:\s*(.+)$', p.read_text(encoding='utf-8'), re.M) or [None, ''])[1]}\n"
                + p.read_text(encoding="utf-8").split("\n---\n", 1)[-1].strip() for p in org))
        if sum(map(len, ctx.values())) > docs_build.CONTEXT_LIMIT:   # 넘치는 칸은 본문 대신 위치 한 줄 (파일로 빠지지 않게)
            for part, text in sorted(ctx.items(), key=lambda kv: -len(kv[1])):
                if sum(map(len, ctx.values())) <= docs_build.CONTEXT_LIMIT:
                    break
                where = {"Agent State": "current_status.md", "Short Term Memory": "rules/", "Document": "documentation/",
                         "Long Term Memory": "rules/_ltm.md"}[part]
                ctx[part] = f"(상한 {docs_build.CONTEXT_LIMIT:,}자를 넘어 생략: {len(text):,}자 — `{rules / where}` 를 직접 읽는다. 줄이는 일 = docs_build WARN)"
        return "\n\n".join(out + [f"# {part}\n\n{text}" for part, text in ctx.items() if text])
    root = rules.parent.parent
    pages = sorted(rules.glob("R[0-9][0-9][0-9].md"))
    if not pages:
        return ""
    out = [f"[project-rules {root.name}] 이 프로젝트의 작업 규칙. 정본 = {rules}/ (바꿀 땐 docs-pattern inbox → 워커)"]
    for p in pages:
        text = p.read_text(encoding="utf-8")
        title = re.search(r"^title:\s*(.+)$", text, re.M)
        body = text.split("\n---\n", 1)[1].strip() if text.startswith("---\n") else text.strip()
        out += [f"## {p.stem} {title.group(1).strip() if title else ''}", body]
    return "\n".join(out)


LIMIT = 9500   # hook 출력 한 줄(문자열)이 10,000자를 넘으면 파일로 빠지고 앞 2,000자만 들어간다


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def add(bound, d):
    if str(d) not in bound:
        bound.append(str(d))


def fill(targets, seen, bound, used=0, why=""):
    """targets 의 본문을 한도 안에서 넣는다 -> 글 조각들. 이미 넣은(같은 내용) 프로젝트는 제목 줄만"""
    out = []
    for d in targets:
        text = render(d)
        if not text:
            continue
        if seen.get(str(d)) == digest(text):
            out.append(titles(d))
        elif used + len(text) > LIMIT:
            out.append(f"[project {name_of(d)}] 본문 {len(text):,}자는 한 번에 넣을 한도를 넘어 뺐다 — `{ENTER_CMD} {name_of(d)}` 로 부른다")
            seen[str(d)] = digest(text)   # 이 줄은 한 번만 — 내용이 다시 바뀌면 또 알린다
        else:
            out.append(why + text)
            seen[str(d)] = digest(text)
            add(bound, d)
        used += len(out[-1])
    return out


def touched(event):
    """도구 호출이 건드리는 경로들: 파일 도구의 경로 · Bash 명령 속 홈 경로"""
    ti = event.get("tool_input") or {}
    paths = [ti[k] for k in ("file_path", "notebook_path", "path") if isinstance(ti.get(k), str)]
    if event.get("tool_name") == "Bash" and "<<" not in (ti.get("command") or ""):
        # shortcut: heredoc 은 글(지시문·inbox)을 쓰는 것이라 그 속 경로는 건드림이 아니다 — 오탐이 다른 모양으로 또 나면 명령 인자만 보도록 바꾼다
        paths += re.findall(r"(?<![\w.])(?:~/|/)[^\s'\"|;&<>()*]+", ti.get("command") or "")
    return paths


def main(event):
    sid = re.sub(r"[^\w-]", "_", event.get("session_id") or "nosession")
    state_file, bind_file = STATE / f"{sid}.json", STATE / f"{sid}.bind"   # bind 는 SessionStart(compact)에도 지우지 않는다
    bound = [b for b in (bind_file.read_text().splitlines() if bind_file.exists() else []) if b]
    bound = [str(resolve(b) or b) if not b.startswith("/") else b for b in bound]   # 옛 형식(이름)도 읽는다
    before = list(bound)
    for tok in BIND.findall(event.get("prompt") or ""):
        if tok == "-":
            bound = []
        elif resolve(tok):
            add(bound, resolve(tok))
    ev = event.get("hook_event_name")
    if ev == "SessionStart":
        state_file.unlink(missing_ok=True)
    seen = json.loads(state_file.read_text()) if state_file.exists() else {}
    if ev == "PreToolUse":
        res = pre_tool(event, seen)
        command = (event.get("tool_input") or {}).get("command") or ""
        for word in ENTER.findall(command if event.get("tool_name") == "Bash" and "<<" not in command else ""):   # 명령이 본문을 출력한다 — 여기선 기록만
            d = resolve(word)
            if d:
                seen[str(d)] = digest(render(d))
                add(bound, d)
        targets = [d for p in touched(event) for d in path_projects(p) if str(d) not in seen]
        if targets and not (res and "permissionDecision" in res["hookSpecificOutput"]):
            ctx = (res or {}).get("hookSpecificOutput", {}).get("additionalContext", "")
            extra = fill(list(dict.fromkeys(targets)), seen, bound, len(ctx),
                         "[project-enter] `--enter` 없이 이 프로젝트의 파일을 건드려 훅이 대신 넣는다. 프로젝트 일을 시작할 땐 먼저 부른다.\n")
            if extra:
                res = {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                       "additionalContext": "\n\n".join(([ctx] if ctx else []) + extra)}}
    else:
        targets = projects(event.get("prompt") or "", bound)
        out = []
        if ev == "SessionStart":   # 어디서 열든 같은 지도. compact 뒤엔 마지막에 부른 프로젝트 본문을 다시, 나머지는 이름만
            out.append(project_map())
            if targets:
                out += fill(targets[-1:], seen, bound, len(out[0]))
                if targets[:-1]:
                    out.append("[project-enter] 이 세션에서 부른 다른 프로젝트: " + ", ".join(name_of(d) for d in targets[:-1])
                               + f" — compact 로 본문이 빠졌다. 그 프로젝트로 돌아가면 `{ENTER_CMD} <이름>` 으로 다시 부른다")
        else:
            out += fill(targets, seen, bound)
        res = "\n\n".join(x for x in out if x) or None
    if bound != before or ev == "SessionStart" or res:
        STATE.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(seen))
        bind_file.write_text("\n".join(bound))
    if res:
        print(res if isinstance(res, str) else json.dumps(res, ensure_ascii=False))


def selftest():
    import subprocess
    global WORKSPACE, STATE, HUB, MEMORY, render
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        WORKSPACE, STATE, MEMORY = tmp / "ws", tmp / "state", tmp / "mem"
        HUB = WORKSPACE / "docs-hub"
        MEMORY.mkdir()
        env = {**os.environ, "RULES_WORKSPACE": str(WORKSPACE), "RULES_STATE": str(STATE), "RULES_HUB": str(HUB), "RULES_MEMORY": str(MEMORY)}
        for name, rule in (("alpha", "산출은 전부 저장"), ("beta-x", "문서 먼저")):
            d = WORKSPACE / name / "docs/rules"
            d.mkdir(parents=True)
            (d / "R001.md").write_text(f"---\ntitle: {rule}\n---\n본문 {name}\n")
        (WORKSPACE / "alpha/src").mkdir()

        def hook(**ev):
            r = subprocess.run([sys.executable, __file__], input=json.dumps(ev), env=env, capture_output=True, text=True)
            assert r.returncode == 0, r.stderr
            return r.stdout

        def read(path, **kw):   # 파일 도구 호출(PreToolUse) -> 넣은 글
            r = hook(hook_event_name="PreToolUse", tool_name="Read", tool_input={"file_path": str(path)}, **kw)
            return json.loads(r)["hookSpecificOutput"]["additionalContext"] if r else ""

        a = dict(session_id="s1", cwd=str(WORKSPACE / "alpha/src"))
        assert hook(hook_event_name="UserPromptSubmit", prompt="학습 상태", **a) == "", "cwd 만으로 주입함 — 어디서 열었는지는 기준이 아니다"
        out = read(WORKSPACE / "alpha/src/train.py", **{**a, "cwd": str(WORKSPACE)})
        assert "[project-enter]" in out and "[project-rules alpha]" in out and "## R001 산출은 전부 저장" in out and "본문 alpha" in out, out
        assert read(WORKSPACE / "alpha/src/eval.py", **a) == "", "같은 프로젝트 파일마다 다시 넣음"
        again = hook(hook_event_name="UserPromptSubmit", prompt="또", **a)
        assert "R001 산출은 전부 저장" in again and "본문 alpha" not in again, "두 번째부터는 제목 한 줄만이어야 함"
        assert "[project-rules alpha]" in hook(hook_event_name="SessionStart", **a), "compact 뒤 경로로 붙은 프로젝트를 다시 넣지 않음"
        (WORKSPACE / "alpha/docs/rules/R002.md").write_text("---\ntitle: 새 규칙\n---\nx\n")
        assert "R002 새 규칙" in hook(hook_event_name="UserPromptSubmit", prompt="", **a), "바뀐 규칙을 넣지 않음"
        bash = hook(hook_event_name="PreToolUse", tool_name="Bash", tool_input={"command": f"cat {WORKSPACE}/beta-x/README"}, session_id="s1b", cwd=str(WORKSPACE))
        assert "[project-rules beta-x]" in json.loads(bash)["hookSpecificOutput"]["additionalContext"], "Bash 명령 속 경로로 못 잡음"
        assert hook(hook_event_name="PreToolUse", tool_name="Bash", session_id="s1c", cwd=str(WORKSPACE),
                    tool_input={"command": f"cat > brief.md <<EOF\nread {WORKSPACE}/beta-x/README\nEOF"}) == "", "heredoc 글 속 경로로 주입함"
        w = dict(session_id="s2", cwd=str(WORKSPACE))
        assert hook(hook_event_name="UserPromptSubmit", prompt="상태 봐줘", **w) == "", "프로젝트 밖에서 주입함"
        out = hook(hook_event_name="UserPromptSubmit", prompt="beta-x 쪽 보자", **w)
        assert "[project-rules beta-x]" in out and "alpha" not in out, "프롬프트의 프로젝트 이름을 못 잡음"
        assert hook(hook_event_name="UserPromptSubmit", prompt="beta 만", session_id="s3", cwd=str(WORKSPACE)) == "", \
            "이름 일부(beta)로 beta-x 를 잡음"
        g = WORKSPACE / "co/research/gamma/docs-personal/rules"
        g.mkdir(parents=True)
        (g / "R001.md").write_text("---\ntitle: 피드백 문구를 정의로 쓰지 않는다\ntriggers: 필기, Saber\n---\n본문 gamma\n")
        out = hook(hook_event_name="UserPromptSubmit", prompt="모델 page 에 필기했어", session_id="s4", cwd=str(WORKSPACE))
        assert "[project-rules gamma]" in out and "본문 gamma" in out, "triggers 낱말로 하위 깊이·docs-personal 규칙을 못 잡음"
        assert "triggers" not in out, "frontmatter 가 본문에 섞임"
        assert "[project-rules gamma]" in read(g.parent / "documentation/x.md", session_id="s5", cwd=str(WORKSPACE)), \
            "docs-personal 안 경로의 조상 규칙을 못 잡음"
        c = WORKSPACE / "beta-x/docs/rules"
        (c / "R002.md").write_text("---\ntitle: 서버 A\nassets: srv-a, 10.0.0.1\n---\n본문 서버A\n")
        (c / "R003.md").write_text("---\ntitle: 서버 B\nassets: srv-b\ndeny: 접속 금지\n---\n본문 서버B\n")
        t = dict(hook_event_name="PreToolUse", tool_name="Bash", session_id="s6", cwd=str(WORKSPACE / "alpha"))
        out = json.loads(hook(tool_input={"command": "ssh srv-a nvidia-smi"}, **t))
        assert "본문 서버A" in out["hookSpecificOutput"]["additionalContext"], "명령의 자원 이름으로 카드를 못 넣음"
        assert hook(tool_input={"command": "ssh srv-a ls"}, **t) == "", "같은 카드를 세션에 두 번 넣음"
        assert hook(tool_input={"command": "ping 10.0.0.12 && ssh srv-a2"}, **t) == "", "이름·IP 일부로 카드를 넣음"
        out = json.loads(hook(tool_input={"command": "ssh srv-b hostname"}, **t))
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny" and "본문 서버B" in out["hookSpecificOutput"]["permissionDecisionReason"], "deny 카드가 막지 않음"
        out = json.loads(hook(tool_input={"command": "ssh srv-b hostname  # asset-ok:beta-x/R003"}, **t))
        assert "permissionDecision" not in out["hookSpecificOutput"], "asset-ok 표식이 있어도 막음"
        out = hook(hook_event_name="UserPromptSubmit", prompt="srv-a 상태 봐줘", session_id="s7", cwd=str(WORKSPACE))
        assert "[project-rules beta-x]" in out, "프롬프트의 자원 이름으로 주인 프로젝트 규칙을 못 잡음"
        hp = HUB / "projects/ws/docs-x"
        for rel, text in (("current_status.md", "# 현재 단계: S001 시작\n지금 할 일"),
                          ("rules/R001.md", "---\ntitle: 허브 규칙\nassets: srv-h\n---\n본문 허브규칙"),
                          ("documentation/overview.md", "---\ntitle: 가\n---\n본문 가"),
                          ("documentation/a.md", "---\ntitle: 나\nsummary: 나 한 줄\n---\n본문 나"),
                          ("state/S001.md", "---\ntitle: 시작\nstatus: active\n---\n본문 단계")):
            (hp / rel).parent.mkdir(parents=True, exist_ok=True)
            (hp / rel).write_text(text)
        (WORKSPACE / "docs-x/src").mkdir(parents=True)
        out = read(WORKSPACE / "docs-x/src/m.py", session_id="s8", cwd=str(WORKSPACE))
        for needle in ("[project ws/docs-x]", "# Agent State", "지금 할 일", "본문 허브규칙", "본문 가", "- [[a]] 나 — 나 한 줄"):
            assert needle in out, f"허브 프로젝트 주입에 {needle!r} 없음: {out}"
        assert "본문 나" not in out and "본문 단계" not in out, "뿌리 아닌 문서 본문이나 Archive 가 들어감"
        assert "project-rules projects" not in out and out.count("[project ws/docs-x]") == 1, "허브 규칙을 옛 경로로도 잡음"
        assert "[project ws/docs-x]" in hook(hook_event_name="UserPromptSubmit", prompt="docs-x 보자", session_id="s9",
                                          cwd=str(WORKSPACE)), "프롬프트의 허브 프로젝트 이름을 못 잡음"
        assert "[project ws/docs-x]" in read(hp / "documentation/a.md", session_id="s10", cwd=str(WORKSPACE)), "허브 폴더 안 경로를 못 잡음"
        assert read(HUB / "projects/ws/_registry.md", session_id="s10b", cwd=str(WORKSPACE)) == "", "조직 폴더의 파일을 프로젝트로 봄"
        (HUB / "projects/ws/rules").mkdir(parents=True)
        (HUB / "projects/ws/rules/R001.md").write_text("---\ntitle: 조직 규칙\n---\n본문 조직규칙")
        out = read(WORKSPACE / "docs-x/src/m.py", session_id="s12", cwd=str(WORKSPACE))
        assert "조직 공통 Short Term Memory (ws)" in out and "본문 조직규칙" in out, "조직 규칙 미상속"
        (tmp / "elsewhere/docs-x").mkdir(parents=True)
        b = dict(session_id="s13", cwd=str(WORKSPACE))
        assert hook(hook_event_name="UserPromptSubmit", prompt="그냥 질문", **b) == "", "묶기 전인데 주입"
        assert "[project ws/docs-x]" in hook(hook_event_name="UserPromptSubmit", prompt="이제 @docs-x 하자", **b), "@ 묶기 실패"
        assert "[project ws/docs-x]" in hook(hook_event_name="SessionStart", **b), "compact(SessionStart) 뒤 묶은 프로젝트를 다시 안 넣음"
        assert "R001 허브 규칙" in hook(hook_event_name="UserPromptSubmit", prompt="계속", **b), "묶은 프로젝트 제목 줄이 매 프롬프트에 없음"
        hook(hook_event_name="UserPromptSubmit", prompt="@- 끝", **b)
        assert hook(hook_event_name="UserPromptSubmit", prompt="다음", **b) == "", "@- 로 안 풀림"
        assert hook(hook_event_name="UserPromptSubmit", prompt="mail me@docs-x.com", session_id="s14", cwd=str(WORKSPACE)).count("[project ws/docs-x]") <= 1
        (hp / "current_status.md").write_text("# 현재 단계\n" + "가" * 12000)
        out = read(WORKSPACE / "docs-x/src/m.py", session_id="s15", cwd=str(WORKSPACE))
        assert "상한 9,000자를 넘어 생략" in out and "가" * 100 not in out and "본문 허브규칙" in out, "넘치는 칸 생략 실패"
        (hp / "current_status.md").write_text("# 현재 단계: S001 시작\n지금 할 일")
        lg = WORKSPACE / "docs-x/docs/rules"
        lg.mkdir(parents=True)
        (lg / "R001.md").write_text("---\ntitle: 옛 규칙\n---\n본문 옛규칙")
        out = hook(hook_event_name="UserPromptSubmit", prompt="docs-x 보자", session_id="s16", cwd=str(WORKSPACE / "docs-x/src"))
        assert "본문 옛규칙" not in out and out.count("[project ws/docs-x]") == 1, "hub 에 있는데 옛 repo 규칙도 넣음"
        assert hook(hook_event_name="UserPromptSubmit", session_id="s17", cwd=str(WORKSPACE),
                    prompt="<task-notification><summary>worker for docs-x completed</summary></task-notification>") == "", "알림 속 이름으로 주입함"
        out = json.loads(hook(tool_input={"command": "ssh srv-h ls"}, **{**t, "session_id": "s11"}))
        assert "docs-x/R001" in out["hookSpecificOutput"]["additionalContext"], "허브 규칙의 자원 카드를 못 넣음"
        # 프로젝트 지도 · --enter (에이전트가 부르는 도구) · compact 뒤 다시 넣기
        (HUB / "projects/ws/_registry.md").write_text("| 프로젝트 | status | 경로 | docs | 메모 |\n|---|---|---|---|---|\n"
                                                    "| docs-x | active | `~/x` | hub | 한 줄 x |\n| alpha | active | `" + str(WORKSPACE / "alpha") + "` | repo | |\n"
                                                    "| zeta | paused | `~/z` | — | |\n")
        memory_build.add_alias("DX", "docs-x", "시험", MEMORY)
        memory_build.add_alias("엑스", "docs-x", "시험", MEMORY)
        m = dict(session_id="s18", cwd=str(WORKSPACE / "alpha/src"))
        start = hook(hook_event_name="SessionStart", **m)
        assert "[project-map]" in start and "- docs-x (DX, 엑스) — 한 줄 x · 지금: 시작" in start and "쉬는 중 1: zeta" in start, start
        assert "본문 alpha" not in start, "SessionStart 에 cwd 프로젝트를 넣음"
        assert start == hook(hook_event_name="SessionStart", session_id="s19", cwd=str(tmp)), "시작 위치에 따라 시작 주입이 다름"
        r = subprocess.run([sys.executable, __file__, "--enter", "엑스"], env=env, capture_output=True, text=True)
        assert r.returncode == 0 and "[project ws/docs-x]" in r.stdout and "본문 허브규칙" in r.stdout, r.stdout + r.stderr
        r = subprocess.run([sys.executable, __file__, "--enter", "alpha"], env=env, capture_output=True, text=True)
        assert "[project-rules alpha]" in r.stdout, "registry 경로로 옛 rules 를 못 찾음"
        r = subprocess.run([sys.executable, __file__, "--enter", "docs-x", "--as", "디 엑스"], env=env, capture_output=True, text=True)
        assert "별칭 '디 엑스' → docs-x" in r.stdout and memory_build.project_aliases(MEMORY).get("디 엑스") == "docs-x", "--as 가 별칭을 LTM 에 저장 안 함"
        r = subprocess.run([sys.executable, __file__, "--enter", "디 엑스"], env=env, capture_output=True, text=True)
        assert "[project ws/docs-x]" in r.stdout, "저장한 별칭으로 못 부름"
        for i, (prompt, hit) in enumerate((("엑스 결과 보자", True), ("DX를 열어", True), ("dx-tool 설치", False), ("docs-x의 상태", True))):
            got = "[project ws/docs-x]" in hook(hook_event_name="UserPromptSubmit", prompt=prompt, session_id=f"al{i}", cwd=str(WORKSPACE))
            assert got == hit, f"프롬프트 별칭·조사 감지: {prompt!r} → {got}"
        r = subprocess.run([sys.executable, __file__, "--enter", "docs-x", "--as", "DX"], env=env, capture_output=True, text=True)
        assert "별칭" not in r.stdout.split("[project ws/docs-x]")[0] and "저장했다" not in r.stdout, "이미 있는 별칭을 또 저장"
        r = subprocess.run([sys.executable, __file__, "--enter", "없는것"], env=env, capture_output=True, text=True)
        assert r.returncode == 1 and "[project-map]" in r.stdout, "모르는 이름에 지도를 안 보여줌"
        hook(hook_event_name="PreToolUse", tool_name="Bash", tool_input={"command": f"{ENTER_CMD} dx"}, **m)
        out = hook(hook_event_name="UserPromptSubmit", prompt="계속", **m)
        assert "R001 허브 규칙" in out and "본문 허브규칙" not in out, "--enter 뒤 본문을 또 넣음"
        hook(hook_event_name="PreToolUse", tool_name="Bash", tool_input={"command": f"{ENTER_CMD} alpha"}, **m)
        start = hook(hook_event_name="SessionStart", **m)
        assert "[project-map]" in start and "본문 alpha" in start and "본문 허브규칙" not in start and "다른 프로젝트: docs-x" in start, \
            "compact 뒤: 마지막에 부른 것만 본문, 나머지는 이름"
        assert len(start) <= LIMIT
        real, render = render, lambda d: f"[project {d.name}] " + "가" * 6000   # 한도 넘는 둘째 프로젝트: 알림 줄은 한 번만
        sn, bd = {}, []
        first = fill([WORKSPACE / "p1", WORKSPACE / "p2"], sn, bd)
        assert "한도를 넘어 뺐다" in first[1] and "한도를 넘어" not in "".join(fill([WORKSPACE / "p0", WORKSPACE / "p2"], sn, bd)), "한도 초과 줄을 매번 반복"
        render = real
    print("selftest OK — cwd 무시 · 파일 경로·Bash 경로 안전망(세션당 1회) · 프로젝트 지도(별칭·단계·쉬는 중, 시작 위치 무관) · --enter(별칭·registry 경로·모르는 이름) · 프롬프트 별칭·조사 · --enter 기록·compact 뒤 마지막 본문 · 자원 카드(명령 주입·세션당 1회·부분 이름 무시·deny 차단·asset-ok 통과·프롬프트 자원 이름) · 이름 언급·본문 세션당 1회·매번 제목·SessionStart 재주입·변경 재주입·밖에서 무주입·부분 이름 무시·triggers·docs-* 루트·하위 깊이 · 허브(조직 계층·조직 규칙 상속·@묶기/compact 유지/@- 풀기·코드 repo 경로·허브 경로·이름 언급·Agent State/STM/Document(뿌리 본문+summary 나무)·나머지 본문과 Archive 제외·자원 카드)")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--enter" in sys.argv:   # 에이전트가 부르는 도구: 그 프로젝트 본문을 출력한다(세션 기록은 PreToolUse 훅이 한다)
        word = (sys.argv[sys.argv.index("--enter") + 1:] or [""])[0]
        d = resolve(word) if word else None
        if not d:
            print(f"'{word}' 프로젝트를 못 찾았다. 이름이나 별칭으로 부른다.\n\n" + project_map())
            sys.exit(1)
        print(render(d) or f"[project {name_of(d)}] 넣을 문서가 없다 ({d})")
        if "--as" in sys.argv:   # 사용자가 부른 말을 별칭으로 Long Term Memory 에 남긴다
            alias = " ".join(sys.argv[sys.argv.index("--as") + 1:]).strip()
            if alias and memory_build.add_alias(alias, name_of(d), "사용자가 이 말로 불러 `--enter --as` 로 저장", MEMORY):
                print(f"\n[project-enter] 별칭 '{alias}' → {name_of(d)} 를 {MEMORY / memory_build.ALIASES} 에 저장했다")
    elif "--map" in sys.argv:
        print(project_map())
    else:
        try:
            main(json.load(sys.stdin))
        except Exception as e:   # a hook must never block the prompt
            print(f"[project-rules] hook error: {e}", file=sys.stderr)
