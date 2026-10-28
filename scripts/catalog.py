"""데이터 지도 수집기: 홈 서버의 모든 데이터 저장소(컨테이너)와 그 구조, 그리고 누가(서비스) 어느 저장소를 쓰는지.

- 대장: `docker inspect` 이미지로 종류를, compose 작업 폴더의 가장 가까운 상위 폴더 이름을 docs-hub `_registry.md` 와 맞춰 조직 · 프로젝트를 정한다.
- 구조(읽기 전용): postgres · mysql/mariadb = information_schema(테이블 · 컬럼 · 기본키 · 외래키 · 추정 행 수), mongo = 컬렉션 · 문서 수 · 표본 30건의 필드와 형,
  couchdb = DB · 문서 수 · 표본 필드 이름, minio = 버킷 · 객체 수 · 크기 · 최상위 접두어, fuseki = 데이터셋 · 트리플 · 이름 있는 그래프 · 클래스별 인스턴스 수,
  redis = DB 별 키 수 · 키 접두어. 모두 컨테이너 안의 클라이언트로 읽고, 비밀번호는 컨테이너 안 환경 변수로만 쓴다(결과에 남기지 않음).
- 연결(used_by): ① 같은 compose 프로젝트의 depends_on ② 다른 컨테이너 환경 변수의 호스트 값이 이 저장소의 컨테이너 이름(같은 프로젝트면 서비스 이름)을 가리킴
  ③ 컨테이너 · systemd 사용자 서비스의 환경 변수 · 실행 줄이 이 저장소의 호스트 포트(127.0.0.1:PORT 등)를 가리킴. 값은 대조만 하고 남기지 않는다.
- 출력: <hub>/projects/<조직>/_catalog/stores.json · <저장소>.json. 조직마다 따로 둔다 — INTERX 는 projects/INTERX/(회사 git, 개인 GitHub 로 가지 않음).
  누가 무엇을 볼지는 보는 쪽(로그인 · 역할)이 거른다. 결정론(시각 없음, 정렬).
- RDF `--publish`: RDF_ORGS(개인) 저장소만 ontic-fuseki 의 이름 있는 그래프 GRAPH 를 교체한다(기본 그래프 = 데모 온톨로지는 건드리지 않음).

- 샘플 `--samples <폴더> [--orgs a,b]`: postgres · mysql · mongo 의 표 · 컬렉션마다 앞 SAMPLE_ROWS 행을 <폴더>/<저장소>.json 에 쓴다(실제 값이므로 git 밖 폴더).
  이름이 비밀번호 · 토큰 · 키 · 세션 · 이메일 · 전화 등인 컬럼과, 값이 이메일 · 긴 토큰처럼 보이는 칸은 MASK 로 바꾼다. 값은 SAMPLE_CHARS 자에서 자른다.

사용: python3 catalog.py [--hub ~/workspace/docs-hub] [--publish]   ·   python3 catalog.py --samples ~/.local/share/ontic/samples [--orgs workspace]
      python3 catalog.py --selftest
"""
from __future__ import annotations

import base64
import csv
import io
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HUB = Path(os.environ.get("CATALOG_HUB", Path.home() / "workspace/docs-hub"))
RDF_ORGS = {"workspace"}                           # ontic-fuseki 에 싣는 조직 — Ontic 제품 쪽은 개인 데이터만
KINDS = [("pgvector", "postgres"), ("postgres", "postgres"), ("mongo", "mongo"), ("mariadb", "mysql"), ("mysql", "mysql"),
         ("redis", "redis"), ("couchdb", "couchdb"), ("minio/minio", "minio"), ("jena-fuseki", "fuseki")]
APPS = ("nextcloud", "superset", "wordpress", "webprotege")   # 이 앱이 쓰는 저장소의 구조는 앱이 관리하는 내부 구조다(화면에서 숨길 수 있다)
GRAPH = "urn:ontic:catalog"
FUSEKI = os.environ.get("ONTIC_FUSEKI", "http://127.0.0.1:3031/ontic")
S = "urn:ontic:catalog:"
MONGO_JS = Path(__file__).with_name("catalog_mongo.js")
SAMPLE_ROWS, SAMPLE_CHARS, MASK = 10, 80, "•••"
SECRET_COL = re.compile(r"pass|pwd|token|secret|key|hash|salt|session|auth|cookie|otp|credential|e_?mail|phone|mobile|^tel|ssn|card|iban|address", re.I)
SECRET_VAL = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$|^[A-Za-z0-9+/=_.$-]{32,}$")   # 이메일 · 긴 토큰 · 해시
EMAIL_IN = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")   # JSON 같은 긴 값 안에 섞인 이메일
MONGO_SAMPLE_JS = """var want = JSON.parse(%s), out = {};   // ES5 — mongo 4.0 셸도 읽게(구조 분해 · EJSON 없음)
for (var i = 0; i < want.length; i++) { var d = want[i][0], c = want[i][1];
  out[d + '/' + c] = db.getSiblingDB(d).getCollection(c).find({}).limit(%d).toArray().map(function (x) { return JSON.parse(typeof EJSON === 'undefined' ? JSON.stringify(x) : EJSON.stringify(x, {relaxed: true})); }); }
print(JSON.stringify(out));"""

COLS_SQL = ("SELECT c.table_schema, c.table_name, c.column_name, c.data_type, c.is_nullable FROM information_schema.columns c "
            "JOIN information_schema.tables t ON t.table_schema = c.table_schema AND t.table_name = c.table_name "
            "WHERE t.table_type = 'BASE TABLE' AND c.table_schema NOT IN ('pg_catalog', 'information_schema') "
            "ORDER BY 1, 2, c.ordinal_position")
KEYS_SQL = ("SELECT tc.table_schema, tc.table_name, tc.constraint_type, kcu.column_name, coalesce(ccu.table_name, '') "
            "FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu "
            "ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema "
            "LEFT JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name "
            "AND tc.constraint_type = 'FOREIGN KEY' WHERE tc.constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY') ORDER BY 1, 2, 3, 4")
ROWS_SQL = ("SELECT n.nspname, c.relname, greatest(c.reltuples, 0)::bigint FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.relkind = 'r' AND n.nspname NOT IN ('pg_catalog', 'information_schema') ORDER BY 1, 2")
MY_COLS = ("SELECT table_schema, table_name, column_name, data_type, is_nullable FROM information_schema.columns "
           "WHERE table_schema = DATABASE() ORDER BY 1, 2, ordinal_position")
MY_KEYS = ("SELECT k.table_schema, k.table_name, IF(k.constraint_name = 'PRIMARY', 'PRIMARY KEY', 'FOREIGN KEY'), k.column_name, "
           "coalesce(k.referenced_table_name, '') FROM information_schema.key_column_usage k WHERE k.table_schema = DATABASE() "
           "AND (k.constraint_name = 'PRIMARY' OR k.referenced_table_name IS NOT NULL) ORDER BY 1, 2, 3, 4")
MY_ROWS = "SELECT table_schema, table_name, coalesce(table_rows, 0) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE' ORDER BY 1, 2"


def run(cmd: list[str], stdin: str | None = None) -> str:
    return subprocess.run(cmd, input=stdin, capture_output=True, text=True, check=True, timeout=120).stdout


def sh(container: str, script: str, *args: str, stdin: str | None = None, runner=run) -> str:
    """컨테이너 안에서 sh 스크립트 실행 — 비밀번호 같은 환경 변수는 컨테이너 안에서만 펼쳐진다"""
    return runner(["docker", "exec", "-i", container, "sh", "-c", script, "sh", *args], stdin)


def registry(hub: Path) -> dict[str, tuple[str, str]]:
    """{폴더 이름: (조직, 프로젝트)} — docs-hub projects/<조직>/_registry.md 의 경로 칸 마지막 이름과 프로젝트 이름"""
    out = {}
    for f in sorted((hub / "projects").glob("*/_registry.md")):
        for line in f.read_text(encoding="utf-8").splitlines():
            cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
            if len(cells) >= 3 and cells[1] in ("active", "paused", "archived"):
                for key in {cells[0], Path(cells[2]).name} - {"—", ""}:
                    out.setdefault(key, (f.parent.name, cells[0]))
    return out


def kind_of(image: str) -> str | None:
    """이미지 이름 → 저장소 종류 (minio/mc 같은 클라이언트는 패턴에 안 걸린다)"""
    return next((k for pat, k in KINDS if pat in image), None)


def lab(c: dict, k: str) -> str:
    return (c["Config"].get("Labels") or {}).get(k, "")


def host_ports(c: dict) -> list[str]:
    return sorted({b["HostPort"] for bs in (c["NetworkSettings"]["Ports"] or {}).values() for b in (bs or []) if b.get("HostPort")})


def users_of(store: dict, inspect: list[dict], units: list[dict]) -> list[dict]:
    """이 저장소를 쓰는 서비스(컨테이너 · systemd 사용자 서비스). via = depends_on | env-host | host-port.
    환경 변수 · 실행 줄은 여기서 대조만 하고 값은 어디에도 남기지 않는다(비밀번호가 섞여 있다)"""
    me = next(c for c in inspect if c["Name"].lstrip("/") == store["store"])
    proj, svc = lab(me, "com.docker.compose.project"), lab(me, "com.docker.compose.service")
    ports = host_ports(me)
    by_port = re.compile(r"(?:127\.0\.0\.1|localhost|0\.0\.0\.0|host\.docker\.internal)[:\s](?:port=)?(" + "|".join(ports) + r")(?!\d)") if ports else None
    out = {}
    for c in inspect:
        if c is me:
            continue
        same = bool(proj) and lab(c, "com.docker.compose.project") == proj
        names = {store["store"]} | ({svc} if same and svc else set())
        host = re.compile(r"(?:^|[^\w-])(" + "|".join(map(re.escape, names)) + r")(?=[:/]|$)")
        deps = {d.split(":")[0] for d in lab(c, "com.docker.compose.depends_on").split(",") if d}
        vals = [e.split("=", 1)[1] for e in c["Config"].get("Env") or [] if "=" in e] + [" ".join(c["Config"].get("Cmd") or [])]
        via = ("depends_on" if same and svc in deps else "env-host" if any(host.search(v) for v in vals)
               else "host-port" if by_port and any(by_port.search(v) for v in vals) else "")
        if via:
            out[c["Name"].lstrip("/")] = {"service": c["Name"].lstrip("/"), "image": c["Config"]["Image"], "via": via}
    for u in units:
        if by_port and by_port.search(u["text"]):
            out[u["unit"]] = {"service": u["unit"], "image": "systemd", "via": "host-port"}
    return [out[k] for k in sorted(out)]


def stores(inspect: list[dict], reg: dict[str, tuple[str, str]], units=()) -> list[dict]:
    """docker inspect 결과 → 저장소 대장. 조직 = 작업 폴더의 가장 가까운 상위 폴더 중 registry 에 있는 것"""
    out = []
    for c in inspect:
        kind = kind_of(c["Config"]["Image"])
        if not kind:
            continue
        wd = lab(c, "com.docker.compose.project.working_dir")
        org, project = next((reg[p] for p in Path(wd).parts[::-1] if p in reg), ("미상", ""))
        ports = sorted(f"{b['HostIp']}:{b['HostPort']}" for bs in (c["NetworkSettings"]["Ports"] or {}).values() for b in (bs or []))
        st = {"store": c["Name"].lstrip("/"), "kind": kind, "org": org, "project": project, "image": c["Config"]["Image"],
              "host_ports": sorted(set(ports))}
        st["used_by"] = users_of(st, inspect, list(units))
        st["app"] = next((a for a in APPS for u in st["used_by"] if a in u["image"]), "")
        out.append(st)
    return sorted(out, key=lambda s: (s["org"], s["project"], s["store"]))


def systemd_units(runner=run) -> list[dict]:
    """실행 중인 systemd 사용자 서비스의 환경 변수 · 실행 줄(대조용, 남기지 않는다)"""
    try:
        names = [l.split()[0] for l in runner(["systemctl", "--user", "list-units", "--type=service", "--state=running", "--no-legend", "--plain"]).splitlines() if l.strip()]
    except (OSError, subprocess.CalledProcessError):
        return []
    out = []
    for n in names:
        try:
            out.append({"unit": n.removesuffix(".service"), "text": runner(["systemctl", "--user", "show", n, "-p", "Environment", "-p", "ExecStart"])})
        except subprocess.CalledProcessError:
            pass
    return out


def tabular(cols: list[list[str]], keys: list[list[str]], rows: list[list[str]]) -> list[dict]:
    """information_schema 세 질의의 결과 → 테이블마다 이름 · 추정 행 수 · 컬럼 · 기본키 · 외래키"""
    tables: dict[tuple[str, str], dict] = {}
    for sch, tab, col, typ, nul in cols:
        t = tables.setdefault((sch, tab), {"schema": sch, "table": tab, "rows_est": 0, "columns": [], "pk": [], "fks": []})
        t["columns"].append({"name": col, "type": typ, "nullable": nul == "YES"})
    for sch, tab, ctype, col, ref in keys:
        if (sch, tab) in tables:
            t = tables[(sch, tab)]
            if ctype == "PRIMARY KEY" and col not in t["pk"]:
                t["pk"].append(col)
            elif ctype == "FOREIGN KEY" and ref:
                t["fks"].append({"column": col, "ref_table": ref})
    for sch, tab, n in rows:
        if (sch, tab) in tables:
            tables[(sch, tab)]["rows_est"] = int(float(n))
    return [tables[k] for k in sorted(tables)]


def tsv(text: str) -> list[list[str]]:
    return [l.split("\t") for l in text.splitlines() if l]


def pg_schema(container: str, runner=run) -> dict:
    q = lambda sql: tsv(sh(container, 'psql -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-${POSTGRES_USER:-postgres}}" -AtX -F "$(printf "\\t")" -c "$1"', sql, runner=runner))
    return {"tables": tabular(q(COLS_SQL), q(KEYS_SQL), q(ROWS_SQL))}


def mysql_schema(container: str, runner=run) -> dict:
    script = ('U="${MARIADB_USER:-$MYSQL_USER}"; P="${MARIADB_PASSWORD:-$MYSQL_PASSWORD}"; D="${MARIADB_DATABASE:-$MYSQL_DATABASE}"; '
              'B=$(command -v mariadb || command -v mysql); "$B" -u"$U" -p"$P" -D "$D" -N -B -e "$1"')
    q = lambda sql: tsv(sh(container, script, sql, runner=runner))
    return {"tables": tabular(q(MY_COLS), q(MY_KEYS), q(MY_ROWS))}


def mongo_schema(container: str, runner=run) -> dict:
    script = ('B=$(command -v mongosh || command -v mongo); '
              'if [ -n "$MONGO_INITDB_ROOT_USERNAME" ]; then "$B" --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" '
              '--authenticationDatabase admin --eval "$(cat)"; else "$B" --quiet --eval "$(cat)"; fi')
    out = sh(container, script, stdin=MONGO_JS.read_text(encoding="utf-8"), runner=runner)
    return {"collections": sorted(json.loads(out.strip().splitlines()[-1]), key=lambda c: (c["db"], c["collection"]))}


def couch_schema(container: str, runner=run) -> dict:
    get = lambda path: json.loads(sh(container, 'curl -s -u "$COUCHDB_USER:$COUCHDB_PASSWORD" "http://127.0.0.1:5984/$1"', path, runner=runner))
    names = get("_all_dbs")
    if isinstance(names, dict):   # 오류 응답 {"error","reason"} — 그 키를 DB 이름으로 읽으면 안 된다
        raise ValueError(f"couchdb {names.get('error')}: {names.get('reason')}")
    dbs = []
    for db in sorted(d for d in names if not d.startswith("_")):
        e = urllib.parse.quote(db, safe="")
        info, docs = get(e), get(e + "/_all_docs?limit=5&include_docs=true").get("rows", [])
        dbs.append({"db": db, "docs": info.get("doc_count", 0), "fields": sorted({k for r in docs for k in (r.get("doc") or {})})})
    return {"dbs": dbs}


def minio_schema(container: str, port: str, runner=run) -> dict:
    mc = lambda *a: [json.loads(l) for l in sh(container, 'MC_HOST_l="http://$MINIO_ROOT_USER:$MINIO_ROOT_PASSWORD@127.0.0.1:$1" mc "$2" --json "$3"',
                                                  port, *a, runner=runner).splitlines() if l.strip().startswith("{")]
    out = []
    for b in mc("ls", "l"):
        name = b["key"].rstrip("/")
        du = next(iter(mc("du", f"l/{name}")), {})
        out.append({"bucket": name, "objects": du.get("objects", 0), "bytes": du.get("size", 0),
                    "prefixes": sorted(x["key"] for x in mc("ls", f"l/{name}"))[:40]})
    return {"buckets": out}


def fuseki_schema(container: str, runner=run) -> dict:
    get = lambda path: json.loads(sh(container, 'curl -s -u "admin:$ADMIN_PASSWORD" "http://127.0.0.1:3030/$1"', path, runner=runner))
    ask = lambda ds, q: json.loads(sh(container, 'curl -s -u "admin:$ADMIN_PASSWORD" -H "Accept: application/sparql-results+json" '
                                      '--data-urlencode "query=$2" "http://127.0.0.1:3030/$1/query"', ds, q, runner=runner))["results"]["bindings"]
    val = lambda b, k: b[k]["value"] if k in b else ""
    out = []
    for d in sorted(get("$/datasets").get("datasets", []), key=lambda d: d["ds.name"]):
        ds = d["ds.name"].lstrip("/")
        n = lambda q: int(val(ask(ds, q)[0], "n") or 0)
        out.append({"dataset": ds,
                    "default_triples": n("SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }"),
                    "named_triples": n("SELECT (COUNT(*) AS ?n) WHERE { GRAPH ?g { ?s ?p ?o } }"),
                    "graphs": [{"graph": val(b, "g"), "triples": int(val(b, "n"))} for b in
                               ask(ds, "SELECT ?g (COUNT(*) AS ?n) WHERE { GRAPH ?g { ?s ?p ?o } } GROUP BY ?g ORDER BY DESC(?n) LIMIT 20")],
                    "classes": [{"class": val(b, "c"), "instances": int(val(b, "n"))} for b in
                                ask(ds, "SELECT ?c (COUNT(?s) AS ?n) WHERE { { ?s a ?c } UNION { GRAPH ?g { ?s a ?c } } } GROUP BY ?c ORDER BY DESC(?n) LIMIT 30")]})
    return {"datasets": out}


def redis_schema(container: str, runner=run) -> dict:
    info = sh(container, "redis-cli INFO keyspace", runner=runner)
    keys = [k for k in sh(container, "redis-cli --scan --count 1000 | head -n 5000", runner=runner).splitlines() if k]
    pre: dict[str, int] = {}
    for k in keys:
        p = k.split(":")[0] if ":" in k else "(접두어 없음)"
        pre[p] = pre.get(p, 0) + 1
    return {"keyspace": {m.group(1): int(m.group(2)) for m in re.finditer(r"^(db\d+):keys=(\d+)", info, re.M)},
            "prefixes": [{"prefix": p, "keys": n} for p, n in sorted(pre.items(), key=lambda x: -x[1])[:30]], "scanned": len(keys)}


def mask(cols: list[str], rows: list[list]) -> tuple[list[list[str]], list[str]]:
    """민감해 보이는 컬럼 · 값을 가리고 길이를 자른다 → (행, 가린 컬럼)"""
    hidden = [c for c in cols if SECRET_COL.search(c)]
    def cell(c, v):
        if v is None:
            return None
        v = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
        return MASK if c in hidden or SECRET_VAL.match(v.strip()) else EMAIL_IN.sub(MASK, v)[:SAMPLE_CHARS]
    return [[cell(c, v) for c, v in zip(cols, r)] for r in rows], hidden


def sql_sample(kind: str, container: str, tables: list[dict], runner=run) -> dict:
    out = {}
    csv.field_size_limit(1 << 30)   # 큰 칸(문서 · 바이너리)도 읽고, 자르기는 mask() 가 한다
    for t in tables:
        try:
            rows = sql_rows(kind, container, t, runner)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, csv.Error):   # 표 하나가 실패해도 그 저장소의 나머지는 모은다
            continue
        if rows:
            body, hidden = mask(rows[0], rows[1:])
            out[f"{t['schema']}/{t['table']}"] = {"columns": rows[0], "rows": body, "masked": hidden}
    return out


def sql_rows(kind: str, container: str, t: dict, runner=run) -> list[list]:
    if kind == "postgres":
        ident = '"%s"."%s"' % (t["schema"].replace('"', '""'), t["table"].replace('"', '""'))
        text = sh(container, 'psql -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-${POSTGRES_USER:-postgres}}" -AtX -c "$1"',
                  f"COPY (SELECT * FROM {ident} LIMIT {SAMPLE_ROWS}) TO STDOUT WITH CSV HEADER", runner=runner)
        rows = list(csv.reader(io.StringIO(text)))
        rows = [[None if v == "" else v for v in r] for r in rows]
    else:
        script = ('U="${MARIADB_USER:-$MYSQL_USER}"; P="${MARIADB_PASSWORD:-$MYSQL_PASSWORD}"; D="${MARIADB_DATABASE:-$MYSQL_DATABASE}"; '
                  'B=$(command -v mariadb || command -v mysql); "$B" -u"$U" -p"$P" -D "$D" -B -e "$1"')
        rows = [[None if v == "NULL" else v for v in r] for r in tsv(sh(container, script, "SELECT * FROM `%s` LIMIT %d" % (t["table"].replace("`", "``"), SAMPLE_ROWS), runner=runner))]
    return rows


def mongo_sample(container: str, collections: list[dict], runner=run) -> dict:
    script = ('B=$(command -v mongosh || command -v mongo); '
              'if [ -n "$MONGO_INITDB_ROOT_USERNAME" ]; then "$B" --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" '
              '--authenticationDatabase admin --eval "$(cat)"; else "$B" --quiet --eval "$(cat)"; fi')
    want = json.dumps([[c["db"], c["collection"]] for c in collections])
    docs = json.loads(sh(container, script, stdin=MONGO_SAMPLE_JS % (json.dumps(want), SAMPLE_ROWS), runner=runner).strip().splitlines()[-1])
    out = {}
    for k, ds in docs.items():
        cols = list(dict.fromkeys(f for d in ds for f in d))
        body, hidden = mask(cols, [[d.get(c) for c in cols] for d in ds])
        out[k] = {"columns": cols, "rows": body, "masked": hidden}
    return out


def samples(s: dict, schema: dict, runner=run) -> dict:
    if s["kind"] in ("postgres", "mysql"):
        return sql_sample(s["kind"], s["store"], schema.get("tables", []), runner)
    if s["kind"] == "mongo":
        return mongo_sample(s["store"], schema.get("collections", []), runner)
    return {}


def collect(s: dict, inspect: list[dict], runner=run) -> dict:
    c = s["store"]
    me = next(x for x in inspect if x["Name"].lstrip("/") == c)
    if s["kind"] == "minio":
        cmd = me["Config"].get("Cmd") or []
        port = next((a.split(":")[-1] for i, a in enumerate(cmd) if i and cmd[i - 1] == "--address"), "9000")
        return minio_schema(c, port, runner)
    return {"postgres": pg_schema, "mysql": mysql_schema, "mongo": mongo_schema, "couchdb": couch_schema,
            "fuseki": fuseki_schema, "redis": redis_schema}[s["kind"]](c, runner)


def _iri(*parts: str) -> str:
    return "<" + S + "/".join(urllib.parse.quote(p, safe="") for p in parts) + ">"


def _lit(s) -> str:
    return json.dumps(str(s), ensure_ascii=False)


def to_turtle(ledger: list[dict], schemas: dict[str, dict]) -> str:
    """대장 + 구조 → Turtle. 저장소 · 사용 서비스 · 테이블 · 컬럼 · 외래키 · 컬렉션"""
    v = lambda t: f"<{S}{t}>"
    out = []
    for s in ledger:
        st = _iri(s["store"])
        out.append(f"{st} a {v('Store')} ; {v('kind')} {_lit(s['kind'])} ; {v('org')} {_lit(s['org'])} ; {v('project')} {_lit(s['project'])} .")
        for u in s.get("used_by", []):
            out.append(f"{_iri('service', u['service'])} a {v('Service')} ; {v('uses')} {st} ; {v('via')} {_lit(u['via'])} .")
        sch = schemas.get(s["store"], {})
        for t in sch.get("tables", []):
            ti = _iri(s["store"], t["schema"], t["table"])
            out.append(f"{ti} a {v('Table')} ; {v('inStore')} {st} ; {v('name')} {_lit(t['table'])} ; {v('rowsEst')} {t['rows_est']} .")
            for c in t["columns"]:
                out.append(f"{_iri(s['store'], t['schema'], t['table'], c['name'])} a {v('Column')} ; {v('inTable')} {ti} ; "
                           f"{v('name')} {_lit(c['name'])} ; {v('type')} {_lit(c['type'])} ; {v('pk')} {str(c['name'] in t['pk']).lower()} .")
            for fk in t["fks"]:
                out.append(f"{ti} {v('references')} {_iri(s['store'], t['schema'], fk['ref_table'])} .")
        for c in sch.get("collections", []):
            out.append(f"{_iri(s['store'], c['db'], c['collection'])} a {v('Collection')} ; {v('inStore')} {st} ; {v('name')} {_lit(c['collection'])} ; {v('docs')} {c['count']} .")
    return "\n".join(out) + "\n"


def publish(ttl: str) -> int:
    """이름 있는 그래프 GRAPH 만 교체 (Graph Store Protocol PUT ?graph=) — 기본 그래프는 건드리지 않는다"""
    auth = base64.b64encode(f"admin:{os.environ.get('ONTIC_FUSEKI_ADMIN', 'ontic')}".encode()).decode()
    req = urllib.request.Request(f"{FUSEKI}/data?graph={urllib.parse.quote(GRAPH, safe='')}", data=ttl.encode(), method="PUT",
                                 headers={"Content-Type": "text/turtle", "Authorization": f"Basic {auth}"})
    return urllib.request.urlopen(req, timeout=30).status


def write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def main_samples(hub: Path, out: Path, orgs: set[str] | None) -> None:
    """표 · 컬렉션의 앞 몇 행 → out/<저장소>.json (실제 값이므로 git 밖 폴더에만)"""
    import time
    ids = run(["docker", "ps", "-q"]).split()
    inspect = json.loads(run(["docker", "inspect", *ids])) if ids else []
    done, errors = {}, {}
    for s in stores(inspect, registry(hub), systemd_units()):
        if s["kind"] not in ("postgres", "mysql", "mongo") or (orgs and s["org"] not in orgs):
            continue
        try:
            got = samples(s, collect(s, inspect))
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError, KeyError, IndexError) as e:
            errors[s["store"]] = f"{type(e).__name__}: {(getattr(e, 'stderr', '') or str(e))[:160]}"
            continue
        out.mkdir(parents=True, exist_ok=True)
        f = out / f"{s['store']}.json"
        f.write_text(json.dumps({"store": s["store"], "collected_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "samples": got}, ensure_ascii=False) + "\n", encoding="utf-8")
        f.chmod(0o600)
        done[s["store"]] = len(got)
    print(f"샘플 {sum(done.values())}개 자산 · 저장소별 {done} · 실패 {errors or '없음'} → {out}")


def main(hub: Path, do_publish: bool) -> None:
    ids = run(["docker", "ps", "-q"]).split()
    inspect = json.loads(run(["docker", "inspect", *ids])) if ids else []
    ledger = stores(inspect, registry(hub), systemd_units())
    schemas, errors = {}, {}
    for s in ledger:
        try:
            schemas[s["store"]] = {"store": s["store"], "kind": s["kind"], **collect(s, inspect)}
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError, KeyError, IndexError) as e:   # 한 저장소가 실패해도 나머지는 모은다
            msg = (e.stderr or "")[:200] if isinstance(e, subprocess.CalledProcessError) else str(e)[:200]
            errors[s["store"]] = f"{type(e).__name__}: {msg}"
            schemas[s["store"]] = {"store": s["store"], "kind": s["kind"], "error": errors[s["store"]]}
    for org in sorted({s["org"] for s in ledger} - {"미상"}):
        write(hub / "projects" / org / "_catalog/stores.json", [s for s in ledger if s["org"] == org])
        for s in (x for x in ledger if x["org"] == org):
            write(hub / "projects" / org / "_catalog" / f"{s['store']}.json", schemas[s["store"]])
    by_org = {o: sum(1 for s in ledger if s["org"] == o) for o in sorted({s["org"] for s in ledger})}
    print(f"저장소 {len(ledger)}개 · 조직별 {by_org} · 연결 {sum(len(s['used_by']) for s in ledger)}개 · 실패 {errors or '없음'} · "
          f"미상 {[s['store'] for s in ledger if s['org'] == '미상']}")
    if do_publish:
        ttl = to_turtle([s for s in ledger if s["org"] in RDF_ORGS], schemas)
        print(f"RDF {ttl.count(chr(10))}줄 → {FUSEKI} 그래프 {GRAPH}: HTTP {publish(ttl)}")


def selftest() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        hub = Path(tmp)
        for org, row in (("INTERX", "| ob | paused | `~/INTERX/ob` | — | |"), ("workspace", "| app | active | `~/workspace/app` | hub | |")):
            (hub / "projects" / org).mkdir(parents=True)
            (hub / "projects" / org / "_registry.md").write_text("| 프로젝트 | status | 경로 | docs | 메모 |\n|---|---|---|---|---|\n" + row + "\n")
        reg = registry(hub)
        c = lambda name, image, wd, ports=None, proj="", svc="", deps="", env=(): {"Name": "/" + name, "Config": {"Image": image, "Env": list(env), "Cmd": [], "Labels": {
            "com.docker.compose.project.working_dir": wd, "com.docker.compose.project": proj, "com.docker.compose.service": svc,
            "com.docker.compose.depends_on": deps}}, "NetworkSettings": {"Ports": ports or {}}}
        p5432 = {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "5432"}]}
        ins = [c("app-db", "postgres:16", "/h/workspace/app/poc", p5432, proj="app", svc="db"),
               c("api", "x/api", "/h/workspace/app/poc", proj="app", svc="api", env=["DB_HOST=db", "DB_PASSWORD=s3cret"]),
               c("x-db", "mongo:7", "/h/workspace/ob/projects/x", proj="x", svc="mongo"),
               c("agent", "y/agent", "/h/INTERX/ob", proj="y", svc="agent", env=["MONGO_URI=mongodb://u:p@x-db:27017"]),
               c("near", "postgres", "/h/INTERX/ob/app/db"), c("sync", "minio/mc:latest", "/h/workspace/app"),
               c("other", "redis", "/h/workspace/app", proj="zz", svc="o", deps="db:service_healthy:false", env=["X=dbx"])]
        units = [{"unit": "poc", "text": "Environment=PG=host=127.0.0.1 port=5432\nExecStart=python app.py"},
                 {"unit": "far", "text": "Environment=PG=127.0.0.1:54321"}]
        led = stores(ins, reg, units)
        got = {s["store"]: (s["kind"], s["org"], s["project"], [(u["service"], u["via"]) for u in s["used_by"]]) for s in led}
        assert got["app-db"] == ("postgres", "workspace", "app", [("api", "env-host"), ("poc", "host-port")]), got["app-db"]   # 다른 프로젝트의 "db" depends_on 은 아니다
        assert got["x-db"] == ("mongo", "INTERX", "ob", [("agent", "env-host")]), got["x-db"]           # 다른 프로젝트가 컨테이너 이름으로 가리킴
        assert got["near"][1:3] == ("workspace", "app") and "sync" not in got, got                       # 가장 가까운 상위 폴더 · 클라이언트 제외
        assert "s3cret" not in json.dumps(led) and "u:p" not in json.dumps(led), "환경 변수 값이 대장에 남음"
        assert ("far", "host-port") not in got["app-db"][3], "54321 을 5432 로 봄"
        cols = [["public", "users", "id", "integer", "NO"], ["public", "users", "name", "text", "YES"], ["public", "orders", "id", "integer", "NO"],
                ["public", "orders", "user_id", "integer", "YES"]]
        keys = [["public", "orders", "FOREIGN KEY", "user_id", "users"], ["public", "orders", "PRIMARY KEY", "id", ""], ["public", "users", "PRIMARY KEY", "id", ""]]
        tabs = tabular(cols, keys, [["public", "orders", "12"], ["public", "users", "3.0"]])
        assert [t["table"] for t in tabs] == ["orders", "users"] and tabs[0]["fks"] == [{"column": "user_id", "ref_table": "users"}] and tabs[1]["rows_est"] == 3
        seen = []
        replies = {"redis-cli INFO keyspace": "# Keyspace\ndb0:keys=4,expires=0\n", "redis-cli --scan --count 1000 | head -n 5000": "kb:1\nkb:2\nsess:9\nflat\n"}
        r = redis_schema("r", lambda cmd, stdin=None: (seen.append(cmd), replies[cmd[6]])[1])
        assert r["keyspace"] == {"db0": 4} and r["prefixes"][0] == {"prefix": "kb", "keys": 2} and r["scanned"] == 4, r
        assert seen[0][:6] == ["docker", "exec", "-i", "r", "sh", "-c"], seen[0]
        m = mongo_schema("m", lambda cmd, stdin=None: 'noise\n[{"db":"d","collection":"b","count":2,"fields":[]},{"db":"d","collection":"a","count":1,"fields":[]}]\n')
        assert [x["collection"] for x in m["collections"]] == ["a", "b"], m
        ttl = to_turtle([s for s in led if s["store"] == "app-db"], {"app-db": {"tables": tabs}})
        assert f"<{S}app-db/public/orders> <{S}references> <{S}app-db/public/users> ." in ttl and f"<{S}service/api> a <{S}Service> ; <{S}uses> <{S}app-db>" in ttl
        assert "x-db" not in to_turtle([s for s in led if s["org"] in RDF_ORGS], {}), "RDF 조직 밖 저장소가 들어감"
        try:
            couch_schema("c", lambda cmd, stdin=None: '{"error":"unauthorized","reason":"Name or password is incorrect."}'); raise AssertionError("couchdb 오류 응답을 DB 목록으로 읽음")
        except ValueError:
            pass
        csv_text = 'id,email,note,pw_hash\n1,a@b.co,"hi, there",x\n2,,' + "y" * 100 + ',z\n'
        sm = sql_sample("postgres", "p", [{"schema": "public", "table": "users"}], lambda cmd, stdin=None: csv_text)["public/users"]
        assert sm["columns"] == ["id", "email", "note", "pw_hash"] and sm["masked"] == ["email", "pw_hash"], sm
        assert sm["rows"][0] == ["1", MASK, "hi, there", MASK] and sm["rows"][1][1] is None and sm["rows"][1][2] == MASK, sm   # 100자 토큰 꼴 값도 가린다
        assert mask(["note"], [["x" * 200 + " y"]])[0][0][0] == "x" * SAMPLE_CHARS, "길이를 자르지 않음"
        assert mask(["data"], [['{"email":{"value":"me@x.org"}}']])[0][0][0] == '{"email":{"value":"' + MASK + '"}}', "값 안의 이메일을 가리지 않음"
        mg = mongo_sample("m", [{"db": "kb", "collection": "e"}], lambda cmd, stdin=None: 'x\n{"kb/e":[{"_id":"1","name":"a","token":"t"},{"_id":"2","tags":["p"]}]}\n')["kb/e"]
        assert mg["columns"] == ["_id", "name", "token", "tags"] and mg["rows"][0][2] == MASK and mg["rows"][1][3] == '["p"]', mg
    print("selftest OK — 대장(종류 · 가장 가까운 registry 폴더 · 클라이언트 제외) · 연결(같은 프로젝트 서비스 이름 · 다른 프로젝트 컨테이너 이름 · 호스트 포트 · systemd · "
          "다른 프로젝트 depends_on 제외 · 값 안 남김) · 표 구조 · redis 접두어 · mongo 정렬 · RDF(사용 서비스 · 외래키 · 조직 경계) · "
          "couchdb 오류 응답 · 샘플(CSV · 가리기 · 자르기 · mongo)")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        args = sys.argv[1:]
        hub = Path(args[args.index("--hub") + 1]).expanduser() if "--hub" in args else HUB
        if "--samples" in args:
            main_samples(hub, Path(args[args.index("--samples") + 1]).expanduser(), set(args[args.index("--orgs") + 1].split(",")) if "--orgs" in args else None)
        else:
            main(hub, "--publish" in args)
