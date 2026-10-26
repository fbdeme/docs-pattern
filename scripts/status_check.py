#!/usr/bin/env python3
"""status_check — derive done/pending from artifacts, reconcile against the issue tracker.

The status-side twin of source-backed-numbers' build_tables.py: instead of hand-asserting
"axis X is done" in prose (which drifts), declare a ledger of work-units, each naming the
artifact(s) that would exist IFF it is done, and let this script derive the status and flag
where the tracker (GitHub issues) disagrees with artifact reality.

Ledger (default docs/status_ledger.yaml):

    units:
      - id: c3-rollout            # short slug
        issue: 22                 # optional GitHub issue number
        artifacts:                # ALL globs must match >=1 file for "done"
          - eval/results_rollout_sim.json
        contains:                 # optional stronger-than-existence proofs
          - {file: paper/main.tex, needle: "sections/rollout.tex"}
        note: "latent rollout, negative"   # optional

Prefer DURABLE committed artifacts (result JSON, .tex, docs) over gitignored run dirs /
checkpoints as proof: they survive a fresh clone and a torn-down GPU box.

Exit code: 0 clean, 1 benign tracking lag (done but issue still open), 2 integrity
regression (issue closed but its artifact is gone). A pre-push hook blocks on 2 and
warns on 1; a CI gate can treat any nonzero as failure.
"""
import glob
import json
import os
import subprocess
import sys

try:
    import yaml
except ImportError:
    sys.exit("status_check needs pyyaml (pip install pyyaml)")


def _present(pattern):
    return bool(glob.glob(pattern))


def _contains(path, needle):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return needle in f.read()
    except OSError:
        return False


def _derive(unit):
    arts = unit.get("artifacts", [])
    hit = [a for a in arts if _present(a)]
    proofs_ok = all(_contains(c["file"], c["needle"]) for c in unit.get("contains", []))
    if arts and len(hit) == len(arts) and proofs_ok:
        return "done", f"{len(hit)}/{len(arts)}"
    if hit or (not arts and proofs_ok and unit.get("contains")):
        return "partial", f"{len(hit)}/{len(arts)}"
    return "pending", f"{len(hit)}/{len(arts)}"


def _issue_states():
    """{number: 'OPEN'|'CLOSED'} from gh, or None if gh is unavailable."""
    try:
        out = subprocess.run(
            ["gh", "issue", "list", "--state", "all", "--limit", "300",
             "--json", "number,state"],
            capture_output=True, text=True, timeout=30,
        )
        if out.returncode != 0:
            return None
        return {i["number"]: i["state"].upper() for i in json.loads(out.stdout or "[]")}
    except Exception:
        return None


def _completeness(runs_glob="runs/*"):
    """Local pre-flight: training runs whose metrics.jsonl stopped short of the configured
    steps. A saved ckpt.pt does NOT mean training finished -- train.py rewrites it every
    validation, so an interrupted run leaves a real-looking checkpoint at a partial step. That
    is the exact gap the artifact-existence checks above cannot see (runs/ is gitignored), and
    it is what silently mixed 7k- and 20k-step ds seeds into a seeded table once. Informational:
    verify/retrain such a run before probing it."""
    short = []
    for cfg_path in sorted(glob.glob(f"{runs_glob}/config.yaml")):
        run_dir = os.path.dirname(cfg_path)
        mpath = os.path.join(run_dir, "metrics.jsonl")
        if not _present(mpath):
            continue
        try:
            with open(cfg_path, encoding="utf-8") as f:
                target = yaml.safe_load(f).get("steps")
            with open(mpath, encoding="utf-8") as f:
                last = max(json.loads(l)["step"] for l in f if l.strip())
        except Exception:
            continue
        if target and last < target:
            short.append((os.path.basename(run_dir), last, target))
    return short


def main(ledger_path="docs/status_ledger.yaml"):
    with open(ledger_path, encoding="utf-8") as f:
        units = yaml.safe_load(f).get("units", [])
    states = _issue_states()

    print(f"{'unit':<22} {'issue':>6} {'status':<8} {'artifacts':>9}")
    print("-" * 50)
    open_lag, regress = [], []   # done-but-open (benign) vs closed-but-missing (integrity)
    for u in units:
        status, frac = _derive(u)
        iss = u.get("issue")
        print(f"{u['id']:<22} {('#'+str(iss)) if iss else '-':>6} {status:<8} {frac:>9}")
        if iss is None or states is None or iss not in states:
            continue
        st = states[iss]
        if status == "done" and st == "OPEN":
            open_lag.append(f"#{iss} ({u['id']}): artifacts DONE but issue OPEN  -> close it")
        elif status == "pending" and st == "CLOSED":
            regress.append(f"#{iss} ({u['id']}): issue CLOSED but artifacts MISSING -> reopen/verify")

    inc = _completeness()
    if inc:
        print(f"\ntraining completeness ({len(inc)}) — ckpt exists but run stopped short of "
              f"config steps (verify before probing):")
        for run, last, target in inc:
            print(f"  {run}: last step {last} < {target} configured")

    print()
    if states is None:
        print("(gh unavailable — artifact status only, no tracker reconciliation)")
        return 0
    if regress:
        print(f"REGRESSION ({len(regress)}) — closed issue lost its artifact:")
        for d in regress:
            print("  " + d)
    if open_lag:
        print(f"tracking lag ({len(open_lag)}) — done but issue still open:")
        for d in open_lag:
            print("  " + d)
    if not regress and not open_lag:
        print("OK — tracker matches artifact reality, no drift.")
    # exit: 2 = integrity regression (block), 1 = benign tracking lag (warn), 0 = clean
    return 2 if regress else (1 if open_lag else 0)


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
