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


def projects(cwd, prompt, bound=()):
    """cwd 의 프로젝트 · 프롬프트에 이름이 나온 프로젝트 · @이름 으로 묶인 프로젝트"""
    found = []
    for d in [Path(cwd), *Path(cwd).parents]:
        hub = hub_by_name(d.name) if d != Path.home() and d.parent != Path("/") else None
        if is_hub(d) or hub:
            found.append(d if is_hub(d) else hub)
            break
        if rule_dirs(d) and not hub_by_name(d.name):
            found += rule_dirs(d)
            break
    low = "" if "<task-notification>" in prompt else prompt.lower()   # 백그라운드 알림 속 이름은 사용자 언급이 아니다
    for rules in all_rule_dirs():
        if rules not in found and name_of(rules) in bound:
            found.append(rules)
    for rules in all_rule_dirs():
        if rules in found:
            continue
        named = re.search(rf"(?<![\w-]){re.escape(name_of(rules).lower())}(?![\w-])", low)
        if named or any(w in low for w in triggers(rules)):
            found.append(rules)
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


def main(event):
    sid = re.sub(r"[^\w-]", "_", event.get("session_id") or "nosession")
    state_file, bind_file = STATE / f"{sid}.json", STATE / f"{sid}.bind"   # bind 는 SessionStart(compact)에도 지우지 않는다
    bound = set(bind_file.read_text().split()) if bind_file.exists() else set()
    names = {name_of(r) for r in all_rule_dirs()}
    for tok in BIND.findall(event.get("prompt") or ""):
        if tok == "-":
            bound = set()
        elif tok in names:
            bound.add(tok)
    if event.get("hook_event_name") == "UserPromptSubmit" and BIND.search(event.get("prompt") or ""):
        STATE.mkdir(parents=True, exist_ok=True)
        bind_file.write_text(" ".join(sorted(bound)))
    if event.get("hook_event_name") == "SessionStart":
        state_file.unlink(missing_ok=True)
    seen = json.loads(state_file.read_text()) if state_file.exists() else {}
    if event.get("hook_event_name") == "PreToolUse":
        res = pre_tool(event, seen)
        if res:
            STATE.mkdir(parents=True, exist_ok=True)
            state_file.write_text(json.dumps(seen))
            print(json.dumps(res, ensure_ascii=False))
        return
    out = []
    for rules in projects(event.get("cwd") or os.getcwd(), event.get("prompt") or "", bound):
        text = render(rules)
        h = hashlib.sha256(text.encode()).hexdigest()[:16]
        if text and seen.get(str(rules)) != h:
            out.append(text)
            seen[str(rules)] = h
        elif text:
            out.append(titles(rules))
    if out:
        STATE.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(seen))
        print("\n\n".join(out))


def selftest():
    import subprocess
    global WORKSPACE, STATE, HUB
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        WORKSPACE, STATE = tmp / "ws", tmp / "state"
        HUB = WORKSPACE / "docs-hub"
        env = {**os.environ, "RULES_WORKSPACE": str(WORKSPACE), "RULES_STATE": str(STATE), "RULES_HUB": str(HUB)}
        for name, rule in (("alpha", "산출은 전부 저장"), ("beta-x", "문서 먼저")):
            d = WORKSPACE / name / "docs/rules"
            d.mkdir(parents=True)
            (d / "R001.md").write_text(f"---\ntitle: {rule}\n---\n본문 {name}\n")
        (WORKSPACE / "alpha/src").mkdir()

        def hook(**ev):
            r = subprocess.run([sys.executable, __file__], input=json.dumps(ev), env=env, capture_output=True, text=True)
            assert r.returncode == 0, r.stderr
            return r.stdout

        a = dict(session_id="s1", cwd=str(WORKSPACE / "alpha/src"))
        out = hook(hook_event_name="UserPromptSubmit", prompt="학습 상태", **a)
        assert "[project-rules alpha]" in out and "## R001 산출은 전부 저장" in out and "본문 alpha" in out, out
        again = hook(hook_event_name="UserPromptSubmit", prompt="또", **a)
        assert "R001 산출은 전부 저장" in again and "본문 alpha" not in again, "두 번째부터는 제목 한 줄만이어야 함"
        assert "[project-rules alpha]" in hook(hook_event_name="SessionStart", **a), "compact 뒤 다시 넣지 않음"
        (WORKSPACE / "alpha/docs/rules/R002.md").write_text("---\ntitle: 새 규칙\n---\nx\n")
        assert "R002 새 규칙" in hook(hook_event_name="UserPromptSubmit", prompt="", **a), "바뀐 규칙을 넣지 않음"
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
        assert hook(hook_event_name="UserPromptSubmit", prompt="상태", session_id="s5", cwd=str(g.parent / "documentation")) \
            .startswith("[project-rules gamma]"), "docs-personal 안 cwd 의 조상 규칙을 못 잡음"
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
        out = hook(hook_event_name="UserPromptSubmit", prompt="상태", session_id="s8", cwd=str(WORKSPACE / "docs-x/src"))
        for needle in ("[project ws/docs-x]", "# Agent State", "지금 할 일", "본문 허브규칙", "본문 가", "- [[a]] 나 — 나 한 줄"):
            assert needle in out, f"허브 프로젝트 주입에 {needle!r} 없음: {out}"
        assert "본문 나" not in out and "본문 단계" not in out, "뿌리 아닌 문서 본문이나 Archive 가 들어감"
        assert "project-rules projects" not in out and out.count("[project ws/docs-x]") == 1, "허브 규칙을 옛 경로로도 잡음"
        assert "[project ws/docs-x]" in hook(hook_event_name="UserPromptSubmit", prompt="docs-x 보자", session_id="s9",
                                          cwd=str(WORKSPACE)), "프롬프트의 허브 프로젝트 이름을 못 잡음"
        assert "[project ws/docs-x]" in hook(hook_event_name="UserPromptSubmit", prompt="", session_id="s10",
                                          cwd=str(hp / "documentation")), "허브 폴더 안 cwd 를 못 잡음"
        (HUB / "projects/ws/rules").mkdir(parents=True)
        (HUB / "projects/ws/rules/R001.md").write_text("---\ntitle: 조직 규칙\n---\n본문 조직규칙")
        out = hook(hook_event_name="UserPromptSubmit", prompt="", session_id="s12", cwd=str(WORKSPACE / "docs-x/src"))
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
        out = hook(hook_event_name="UserPromptSubmit", prompt="", session_id="s15", cwd=str(WORKSPACE / "docs-x/src"))
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
    print("selftest OK — 자원 카드(명령 주입·세션당 1회·부분 이름 무시·deny 차단·asset-ok 통과·프롬프트 자원 이름) · cwd 프로젝트·이름 언급·본문 세션당 1회·매번 제목·SessionStart 재주입·변경 재주입·밖에서 무주입·부분 이름 무시·triggers·docs-* 루트·하위 깊이 · 허브(조직 계층·조직 규칙 상속·@묶기/compact 유지/@- 풀기·코드 repo cwd·허브 cwd·이름 언급·Agent State/STM/Document(뿌리 본문+summary 나무)·나머지 본문과 Archive 제외·자원 카드)")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        try:
            main(json.load(sys.stdin))
        except Exception as e:   # a hook must never block the prompt
            print(f"[project-rules] hook error: {e}", file=sys.stderr)
