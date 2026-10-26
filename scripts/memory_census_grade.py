#!/usr/bin/env python3
"""Claude 메모 ↔ repo 대조 census 채점 (메모를 포인터로 줄이기 전, docs/documentation/memory-policy 절차 ②).

워커 보고서 = 표 `| # | mem_line | mem_quote | verdict | repo_path | repo_quote |`
검사: 메모 인용이 그 줄에 실제로 있나 · repo 인용이 그 파일에 실제로 있나 · 판정값 · FOUND 는 _v1 밖, V1ONLY 는 _v1 안 ·
지정한 줄 범위의 내용 있는 줄을 전부 다뤘나. 공백은 정규화해 비교, `\\|` 는 `|` 로.

Usage: memory_census_grade.py MEMORY.md REPO REPORT.md [LO HI]   |   --selftest
"""
import re
import sys
import tempfile
from pathlib import Path

norm = lambda s: re.sub(r"\s+", " ", s.replace("\\|", "|")).strip()


def grade(mem_path, repo, report, lo=1, hi=10**9):
    mem = Path(mem_path).read_text(encoding="utf-8").split("\n")
    body = next((i + 2 for i, l in enumerate(mem[1:]) if l.strip() == "---"), 0) + 1 if mem and mem[0] == "---" else 1
    rows, fails, cnt, covered = [], [], {}, set()
    for line in Path(report).read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line)[1:-1]]
        if len(cells) == 6 and cells[0].isdigit():
            rows.append(cells)
    if not rows:
        fails.append("파싱된 행 0")
    for n, ml, mq, v, rp, rq in rows:
        cnt[v] = cnt.get(v, 0) + 1
        if v not in ("FOUND", "V1ONLY", "NOT_FOUND"):
            fails.append(f"#{n} 판정값 {v!r}"); continue
        if not ml.isdigit() or not 1 <= int(ml) <= len(mem):
            fails.append(f"#{n} mem_line {ml!r}"); continue
        ml = int(ml); covered.add(ml)
        if norm(mq) not in norm(mem[ml - 1]):
            fails.append(f"#{n} 메모 인용이 {ml}행에 없음: {mq[:40]}")
        if v == "NOT_FOUND":
            continue
        p = Path(repo) / rp
        if not p.is_file():
            fails.append(f"#{n} 파일 없음: {rp}"); continue
        if v == "FOUND" and "/_v1/" in f"/{rp}":
            fails.append(f"#{n} FOUND 인데 _v1 경로")
        if v == "V1ONLY" and "/_v1/" not in f"/{rp}":
            fails.append(f"#{n} V1ONLY 인데 _v1 아님")
        if norm(rq) not in norm(p.read_text(encoding="utf-8", errors="ignore")):
            fails.append(f"#{n} repo 인용이 {rp}에 없음: {rq[:40]}")
    need = {i for i in range(max(body, lo), min(len(mem), hi) + 1) if mem[i - 1].strip() and mem[i - 1].strip() != "---"}
    if need - covered:
        fails.append(f"다루지 않은 줄: {sorted(need - covered)}")
    return rows, cnt, fails


def selftest():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t); (t / "repo/docs/_v1").mkdir(parents=True)
        (t / "mem.md").write_text("---\nname: x\n---\n사과는 빨갛다. 배는 노랗다.\n\n포도는 보라다.\n", encoding="utf-8")
        (t / "repo/docs/fruit.md").write_text("사과는 빨갛다고 적혀 있다.\n", encoding="utf-8")
        (t / "repo/docs/_v1/old.md").write_text("배는 노랗다 (옛 기록)\n", encoding="utf-8")
        good = ("| 1 | 4 | 사과는 빨갛다 | FOUND | docs/fruit.md | 사과는 빨갛다고 |\n"
                "| 2 | 4 | 배는 노랗다 | V1ONLY | docs/_v1/old.md | 배는 노랗다 (옛 |\n"
                "| 3 | 6 | 포도는 보라다 | NOT_FOUND | - | - |\n")
        r = t / "r.md"; r.write_text(good, encoding="utf-8")
        assert not grade(t / "mem.md", t / "repo", r)[2], grade(t / "mem.md", t / "repo", r)[2]
        cases = [("메모 인용이", good.replace("사과는 빨갛다 |", "사과는 파랗다 |")),
                 ("repo 인용이", good.replace("사과는 빨갛다고 |", "사과는 초록이라고 |")),
                 ("다루지 않은 줄", good.rsplit("| 3 |", 1)[0]),
                 ("FOUND 인데 _v1", good.replace("| V1ONLY | docs/_v1", "| FOUND | docs/_v1")),
                 ("판정값", good.replace("NOT_FOUND", "MAYBE")),
                 ("파일 없음", good.replace("docs/fruit.md", "docs/none.md")),
                 ("파싱된 행 0", "no table\n")]
        for needle, text in cases:
            r.write_text(text, encoding="utf-8")
            assert any(needle in f for f in grade(t / "mem.md", t / "repo", r)[2]), needle
    print(f"selftest OK — 규칙 {len(cases)}개 발화")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest(); sys.exit(0)
    a = sys.argv[1:]
    rows, cnt, fails = grade(a[0], a[1], a[2], *(int(x) for x in a[3:5]))
    print("행", len(rows), cnt)
    for f in fails:
        print("FAIL", f)
    print(f"채점: {len(fails)} FAIL"); sys.exit(1 if fails else 0)
