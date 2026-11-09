#!/usr/bin/env python3
"""Generate weeks of demo-app history from recorded telemetry, with incidents planted.

Two steps:

  history.py templates                 recordings in capture/ -> templates.json.gz
  history.py generate --send           templates -> OTLP, sent to OTEL_EXPORTER_OTLP_*
  history.py generate --out DIR        templates -> OTLP JSON files, one batch per line

Recordings come from capture.sh: the real app, sending through the agent to files.
Each recorded backend request (its spans and logs) becomes a template. Generating
replays copies of the templates minute by minute across the history window, with
fresh IDs and timestamps relative to now, so it must run again before each delivery.

What it plants, relative to now, always on a Saturday so every learner sees the
same weekend traffic whichever day they load:
  * a bad deploy of 2.0.0 on the latest Saturday at least 2 days ago (5 hours),
    then a rollback to 1.0.0, and
  * a Docs-crash burn on the Saturday a week before it (40 minutes).
Both are sized as shares of the 28-day error budget of a 99.9% SLO over user
requests: every backend server span except GET /health.

Only the Python standard library is used.
"""

import argparse
import collections
import datetime as dt
import gzip
import json
import math
import os
import random
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURE_DIR = os.path.join(HERE, "capture")
TEMPLATES = os.path.join(HERE, "templates.json.gz")

BACKEND = "subscription-backend"
DOCS = "docs-loader"
MINUTE_NS = 60 * 10**9

# Request types the generator schedules. "user" ones count toward the SLI.
USER_CLASSES = ("page", "css", "subscribe_ok", "subscribe_err", "docs_err")
ROOT_CLASS = {
    "GET /health": "health",
    "GET /": "page",
    "GET /css/<path:filename>": "css",
    "GET /load-docs": "docs_err",
}
# docs-loader's health check: "/" in recordings made before the port to OpenTelemetry, "GET /" from otelhttp
DOCS_HEALTH_NAMES = ("/", "GET /")
ACCESS_LOG_TIME = re.compile(r"\[\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+\]")
RESTART_BODY = "** Service Started on Port"


# --------------------------------------------------------------------------
# templates
# --------------------------------------------------------------------------

def _attrs(lst):
    return {a["key"]: next(iter(a.get("value", {}).values()), None) for a in lst or []}


def _read_jsonl(path):
    with open(path) as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


class _Interner:
    """Stores each distinct resource or scope once, referenced by index."""

    def __init__(self):
        self.items, self.index = [], {}

    def __call__(self, obj):
        key = json.dumps(obj, sort_keys=True)
        if key not in self.index:
            self.index[key] = len(self.items)
            self.items.append(obj)
        return self.index[key]


def _shift(rec, fields, base):
    for f in fields:
        if f in rec and rec[f]:
            rec[f] = int(rec[f]) - base
    for ev in rec.get("events", []) or []:
        if ev.get("timeUnixNano"):
            ev["timeUnixNano"] = int(ev["timeUnixNano"]) - base


def build_version(capture):
    resources, scopes = _Interner(), _Interner()
    spans_by_trace = collections.defaultdict(list)
    t_min, t_max = None, None
    for batch in _read_jsonl(os.path.join(capture, "traces.jsonl")):
        for rs in batch.get("resourceSpans", []):
            svc = _attrs(rs["resource"].get("attributes")).get("service.name")
            if svc not in (BACKEND, DOCS):
                continue
            r = resources(rs["resource"])
            for ss in rs.get("scopeSpans", []):
                s = scopes(ss.get("scope", {}))
                for sp in ss.get("spans", []):
                    spans_by_trace[sp["traceId"]].append((r, s, svc, sp))
                    t = int(sp["startTimeUnixNano"])
                    t_min = t if t_min is None else min(t_min, t)
                    t_max = t if t_max is None else max(t_max, t)

    logs_by_trace = collections.defaultdict(list)
    docs_logs, restarts = [], []
    for batch in _read_jsonl(os.path.join(capture, "logs.jsonl")):
        for rl in batch.get("resourceLogs", []):
            svc = _attrs(rl["resource"].get("attributes")).get("service.name")
            if svc not in (BACKEND, DOCS):
                continue
            r = resources(rl["resource"])
            for sl in rl.get("scopeLogs", []):
                s = scopes(sl.get("scope", {}))
                for rec in sl.get("logRecords", []):
                    body = str(rec.get("body", {}).get("stringValue", ""))
                    if rec.get("traceId"):
                        logs_by_trace[rec["traceId"]].append((r, s, rec))
                    elif svc == DOCS and body.startswith(RESTART_BODY):
                        restarts.append((r, s, rec))
                    elif svc == DOCS:
                        docs_logs.append((int(rec["timeUnixNano"]), r, s, rec))
    docs_logs.sort(key=lambda x: x[0])

    classes = collections.defaultdict(list)
    for trace_id, spans in spans_by_trace.items():
        ids = {sp["spanId"] for _, _, _, sp in spans}
        roots = [x for x in spans if x[3].get("parentSpanId", "") not in ids]
        _, _, root_svc, root = min(roots, key=lambda x: int(x[3]["startTimeUnixNano"]))
        name = root["name"]
        if root_svc == DOCS and name in DOCS_HEALTH_NAMES:
            cls = "docs_health"
        elif root_svc != BACKEND:
            continue
        elif name == "POST /api/subscribe":
            failed = any(sp.get("status", {}).get("code") == 2 for _, _, _, sp in spans)
            cls = "subscribe_err" if failed else "subscribe_ok"
        elif name in ROOT_CLASS:
            cls = ROOT_CLASS[name]
        else:
            continue
        base = int(root["startTimeUnixNano"])
        items = []
        for r, s, _, sp in spans:
            sp = json.loads(json.dumps(sp))
            if sp.get("parentSpanId", "") not in ids:
                sp["parentSpanId"] = ""  # its parent was a browser span, not replayed
            _shift(sp, ("startTimeUnixNano", "endTimeUnixNano"), base)
            items.append({"sig": "span", "res": r, "scope": s, "rec": sp})
        logs = list(logs_by_trace.get(trace_id, []))
        if cls == "docs_health":
            # docs-loader's logs carry no trace ID; take the pair around its span.
            end = int(root["endTimeUnixNano"])
            logs += [(r, s, rec) for t, r, s, rec in docs_logs
                     if base - 5_000_000 <= t <= end + 50_000_000][:2]
        for r, s, rec in logs:
            rec = json.loads(json.dumps(rec))
            _shift(rec, ("timeUnixNano", "observedTimeUnixNano"), base)
            items.append({"sig": "log", "res": r, "scope": s, "rec": rec})
        classes[cls].append(items)

    for r, s, rec in restarts:
        rec = json.loads(json.dumps(rec))
        _shift(rec, ("timeUnixNano", "observedTimeUnixNano"), int(rec["timeUnixNano"]))
        classes["docs_restart"].append([{"sig": "log", "res": r, "scope": s, "rec": rec}])

    minutes = max((t_max - t_min) / MINUTE_NS, 1.0)
    rates = {cls: len(tpls) / minutes for cls, tpls in classes.items()}
    return {"resources": resources.items, "scopes": scopes.items,
            "classes": classes, "rates": rates, "minutes": minutes}


def cmd_templates(args):
    out = {}
    for version, phase in (("1.0.0", "v1"), ("2.0.0", "v2")):
        out[version] = build_version(os.path.join(CAPTURE_DIR, phase))
        v = out[version]
        print(f"{version}: {v['minutes']:.1f} recorded minutes")
        for cls in sorted(v["classes"]):
            print(f"  {cls:14} {len(v['classes'][cls]):4} templates  {v['rates'][cls]:6.1f}/min")
    with gzip.open(TEMPLATES, "wt") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"wrote {TEMPLATES} ({os.path.getsize(TEMPLATES) / 1e6:.1f} MB)")


# --------------------------------------------------------------------------
# generate
# --------------------------------------------------------------------------

def diurnal(t):
    """User traffic multiplier: busy afternoons (UTC), quiet nights and weekends."""
    hour = t.hour + t.minute / 60
    day = max(0.0, math.sin(math.pi * (hour - 6) / 16)) if 6 <= hour <= 22 else 0.0
    weekend = 0.5 if t.weekday() >= 5 else 1.0
    return (0.2 + 0.8 * day) * weekend


def poisson(rng, lam):
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= l:
            return k
        k += 1


def at_time_of_day(day, hhmm):
    h, m = (int(x) for x in hhmm.split(":"))
    return day.replace(hour=h, minute=m, second=0, microsecond=0)


class Plan:
    def __init__(self, args, tpl):
        self.args, self.tpl = args, tpl
        self.now = (dt.datetime.fromisoformat(args.now) if args.now
                    else dt.datetime.now(dt.timezone.utc)).replace(second=0, microsecond=0)
        self.start = self.now - dt.timedelta(days=args.days)
        # Incidents always fall on the same weekday (Saturday by default), so the shares a
        # learner reads don't depend on the day they load: traffic halves at weekends.
        deploy_day = self.now - dt.timedelta(days=args.deploy_days_ago)
        deploy_day -= dt.timedelta(days=(deploy_day.weekday() - args.incident_weekday) % 7)
        self.deploy_start = at_time_of_day(deploy_day, args.deploy_at)
        self.burn_start = at_time_of_day(deploy_day - dt.timedelta(weeks=args.burn_weeks_before), args.burn_at)
        self.burn_end = self.burn_start + dt.timedelta(minutes=args.burn_minutes)
        self.deploy_end = self.deploy_start + dt.timedelta(minutes=args.deploy_minutes)
        self._size()

    def version(self, t):
        return "2.0.0" if self.deploy_start <= t < self.deploy_end else "1.0.0"

    def expected(self, cls, t):
        """Expected requests of a class in the minute starting at t, before planting."""
        rates = self.tpl[self.version(t)]["rates"]
        base = rates.get(cls, 0.0) * self.args.scale
        if cls in ("health", "docs_health"):
            return base
        if cls == "subscribe":
            base = (rates.get("subscribe_ok", 0) + rates.get("subscribe_err", 0)) * self.args.scale
        if cls in ("docs_err", "subscribe_err", "subscribe_ok"):
            return 0.0  # planted separately
        return base * diurnal(t)

    def minutes(self):
        t = self.start
        while t < self.now:
            yield t
            t += dt.timedelta(minutes=1)

    def _size(self):
        """Turn the budget shares into a burn click rate and a deploy failure rate."""
        user = 0.0
        deploy_signups = {}
        for t in self.minutes():
            user += self.expected("page", t) + self.expected("css", t) + self.expected("subscribe", t)
            if self.deploy_start <= t < self.deploy_end:
                deploy_signups[t] = self.expected("subscribe", t)
        self.user_total = user
        self.budget = (1 - self.args.slo) * user
        # Planted errors are exact, not random, so every delivery shows the same
        # budget shares: the burn spreads evenly over its minutes, the deploy's
        # failures follow the signup traffic.
        self.burn_errors = round(self.args.burn_budget_share * self.budget)
        self.burn_rate = self.burn_errors / self.args.burn_minutes
        self.burn_plan = self._spread(self.burn_errors, {
            self.burn_start + dt.timedelta(minutes=i): 1.0 for i in range(self.args.burn_minutes)})
        self.deploy_errors = round(self.args.deploy_budget_share * self.budget)
        total_signups = sum(deploy_signups.values())
        self.deploy_fail = min(0.9, self.deploy_errors / total_signups) if total_signups else 0.0
        self.deploy_plan = self._spread(self.deploy_errors, deploy_signups)

    @staticmethod
    def _spread(total, weights):
        """Split an exact integer total across minutes in proportion to weights."""
        plan, cum, done, wsum = {}, 0.0, 0, sum(weights.values()) or 1.0
        for t in sorted(weights):
            cum += weights[t]
            target = round(total * cum / wsum)
            plan[t] = target - done
            done = target
        return plan

    def counts(self, rng, t):
        c = {cls: poisson(rng, self.expected(cls, t)) for cls in ("health", "docs_health", "page", "css")}
        c["subscribe_err"] = self.deploy_plan.get(t, 0)
        c["subscribe_ok"] = poisson(rng, max(0.0, self.expected("subscribe", t) - c["subscribe_err"]))
        c["docs_err"] = self.burn_plan.get(t, 0)
        return c

    def summary(self):
        f = "%Y-%m-%d %H:%M UTC"
        return "\n".join([
            f"window      {self.start:{f}} -> {self.now:{f}} ({self.args.days} days, scale {self.args.scale})",
            f"user reqs   ~{self.user_total:,.0f}; 99.9% budget ~{self.budget:,.0f} errors",
            f"Docs burn   {self.burn_start:{f}} for {self.args.burn_minutes} min, "
            f"~{self.burn_rate:.1f} errors/min, {self.burn_errors:,} errors "
            f"({self.args.burn_budget_share:.0%} of budget)",
            f"bad deploy  2.0.0 {self.deploy_start:{f}} -> {self.deploy_end:{f}}, "
            f"{self.deploy_fail:.0%} of signups fail, {self.deploy_errors:,} errors "
            f"({self.args.deploy_budget_share:.0%} of budget)",
        ])


def _rand_hex(rng, nbytes):
    return "%0*x" % (nbytes * 2, rng.getrandbits(nbytes * 8))


def materialize(rng, items, base_ns, ids):
    """Copy one template at base_ns with fresh IDs. Yields (sig, res, scope, record)."""
    span_map = {}
    for it in items:
        if it["sig"] == "span":
            span_map[it["rec"]["spanId"]] = _rand_hex(rng, 8)
    trace_id = _rand_hex(rng, 16)
    for it in items:
        rec = json.loads(json.dumps(it["rec"]))
        if it["sig"] == "span":
            rec["traceId"] = trace_id
            rec["spanId"] = span_map[rec["spanId"]]
            if rec.get("parentSpanId"):
                rec["parentSpanId"] = span_map.get(rec["parentSpanId"], "")
            for f in ("startTimeUnixNano", "endTimeUnixNano"):
                rec[f] = str(base_ns + int(rec[f]))
            for ev in rec.get("events", []) or []:
                if "timeUnixNano" in ev:
                    ev["timeUnixNano"] = str(base_ns + int(ev["timeUnixNano"]))
        else:
            if rec.get("traceId"):
                rec["traceId"] = trace_id
                rec["spanId"] = span_map.get(rec.get("spanId"), _rand_hex(rng, 8))
            for f in ("timeUnixNano", "observedTimeUnixNano"):
                if f in rec:
                    rec[f] = str(base_ns + int(rec[f]))
            body = rec.get("body", {})
            if "stringValue" in body and ACCESS_LOG_TIME.search(body["stringValue"]):
                stamp = dt.datetime.fromtimestamp(int(rec["timeUnixNano"]) / 1e9, dt.timezone.utc)
                body["stringValue"] = ACCESS_LOG_TIME.sub(
                    "[" + stamp.strftime("%Y-%m-%d %H:%M:%S.%f") + "]", body["stringValue"], count=1)
        yield it["sig"], it["res"], it["scope"], rec


class Batcher:
    """Groups records into OTLP requests of about batch_size records."""

    def __init__(self, version_tpl, batch_size, sink):
        self.tpl, self.batch_size, self.sink = version_tpl, batch_size, sink
        self.buf = {"span": collections.defaultdict(list), "log": collections.defaultdict(list)}
        self.n = {"span": 0, "log": 0}

    def add(self, version, sig, res, scope, rec):
        self.buf[sig][(version, res, scope)].append(rec)
        self.n[sig] += 1
        if self.n[sig] >= self.batch_size:
            self.flush(sig)

    def flush(self, sig=None):
        for s in ([sig] if sig else ["span", "log"]):
            if not self.n[s]:
                continue
            by_res = collections.defaultdict(list)
            for (version, res, scope), recs in self.buf[s].items():
                by_res[(version, res)].append((version, scope, recs))
            if s == "span":
                body = {"resourceSpans": [
                    {"resource": self.tpl[v]["resources"][r],
                     "scopeSpans": [{"scope": self.tpl[v2]["scopes"][sc], "spans": recs}
                                    for v2, sc, recs in groups]}
                    for (v, r), groups in by_res.items()]}
                self.sink("traces", body)
            else:
                body = {"resourceLogs": [
                    {"resource": self.tpl[v]["resources"][r],
                     "scopeLogs": [{"scope": self.tpl[v2]["scopes"][sc], "logRecords": recs}
                                   for v2, sc, recs in groups]}
                    for (v, r), groups in by_res.items()]}
                self.sink("logs", body)
            self.buf[s].clear()
            self.n[s] = 0


def load_env_file(path):
    """Fill in unset variables from a .env file (KEY=VALUE lines, optional quotes)."""
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip().removeprefix("export ").strip(), value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            os.environ.setdefault(key, value)


class Sender:
    def __init__(self, threads):
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").rstrip("/")
        headers = os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", "")
        if not endpoint or "=" not in headers:
            sys.exit("Set OTEL_EXPORTER_OTLP_ENDPOINT and OTEL_EXPORTER_OTLP_HEADERS, "
                     "as copied from ClickHouse Observability.")
        self.endpoint = endpoint
        self.headers = {"Content-Type": "application/json", "Content-Encoding": "gzip"}
        for pair in headers.split(","):
            k, _, v = pair.partition("=")
            self.headers[k.strip()] = urllib.request.unquote(v.strip())
        self.pool = ThreadPoolExecutor(max_workers=threads)
        self.slots = threading.Semaphore(threads * 2)
        self.sent = collections.Counter()
        self.retries = collections.Counter()
        self.errors = []

    def __call__(self, signal, body):
        data = gzip.compress(json.dumps(body, separators=(",", ":")).encode())
        self.slots.acquire()
        self.pool.submit(self._post, signal, data)

    def _post(self, signal, data):
        try:
            for attempt in range(6):
                req = urllib.request.Request(f"{self.endpoint}/v1/{signal}", data=data,
                                             headers=self.headers, method="POST")
                try:
                    with urllib.request.urlopen(req, timeout=60) as resp:
                        resp.read()
                    self.sent[signal] += 1
                    return
                except urllib.error.HTTPError as e:
                    self.retries[f"HTTP {e.code}"] += 1
                    if e.code not in (408, 429, 500, 502, 503, 504) or attempt == 5:
                        self.errors.append(f"{signal}: HTTP {e.code} {e.read()[:200]!r}")
                        return
                except (urllib.error.URLError, TimeoutError) as e:
                    self.retries[type(e).__name__] += 1
                    if attempt == 5:
                        self.errors.append(f"{signal}: {e}")
                        return
                time.sleep(2 ** attempt)
        finally:
            self.slots.release()

    def close(self):
        self.pool.shutdown(wait=True)


class FileSink:
    def __init__(self, out):
        os.makedirs(out, exist_ok=True)
        self.files = {s: gzip.open(os.path.join(out, f"{s}.json.gz"), "wt") for s in ("traces", "logs")}
        self.sent = collections.Counter()
        self.retries = collections.Counter()
        self.errors = []

    def __call__(self, signal, body):
        self.files[signal].write(json.dumps(body, separators=(",", ":")) + "\n")
        self.sent[signal] += 1

    def close(self):
        for f in self.files.values():
            f.close()


def cmd_generate(args):
    with gzip.open(TEMPLATES, "rt") as f:
        tpl = json.load(f)
    plan = Plan(args, tpl)
    print(plan.summary())
    if args.dry_run:
        return
    rng = random.Random(args.seed)
    if args.send:
        load_env_file(args.env_file)
    sink = Sender(args.threads) if args.send else FileSink(args.out)
    batcher = Batcher(tpl, args.batch_size, sink)
    records = collections.Counter()
    total_minutes = args.days * 24 * 60
    started = time.time()
    for i, t in enumerate(plan.minutes()):
        version = plan.version(t)
        classes = tpl[version]["classes"]
        t_ns = int(t.timestamp()) * 10**9
        for cls, n in plan.counts(rng, t).items():
            for _ in range(n):
                base = t_ns + rng.randrange(MINUTE_NS)
                for sig, res, scope, rec in materialize(rng, rng.choice(classes[cls]), base, None):
                    batcher.add(version, sig, res, scope, rec)
                    records[sig] += 1
                if cls == "docs_err":  # each crash restarts docs-loader a moment later
                    restart = base + rng.randrange(1, 3) * 10**9
                    for sig, res, scope, rec in materialize(rng, rng.choice(classes["docs_restart"]), restart, None):
                        batcher.add(version, sig, res, scope, rec)
                        records[sig] += 1
        if i % 1440 == 0:
            print(f"  day {i // 1440 + 1}/{args.days}: {records['span']:,} spans, "
                  f"{records['log']:,} logs, {time.time() - started:.0f}s", flush=True)
    batcher.flush()
    sink.close()
    print(f"done: {records['span']:,} spans and {records['log']:,} logs in "
          f"{sink.sent['traces'] + sink.sent['logs']:,} requests, {time.time() - started:.0f}s")
    if sink.retries:
        print("  retried:", ", ".join(f"{k} x{v}" for k, v in sink.retries.most_common()))
    for e in sink.errors[:10]:
        print("  error:", e)
    if sink.errors:
        sys.exit(f"{len(sink.errors)} requests failed")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("templates", help="build templates.json.gz from capture/")
    g = sub.add_parser("generate", help="generate history from templates.json.gz")
    dest = g.add_mutually_exclusive_group(required=True)
    dest.add_argument("--send", action="store_true", help="send to OTEL_EXPORTER_OTLP_ENDPOINT")
    dest.add_argument("--out", help="write OTLP JSON batches to this directory")
    dest.add_argument("--dry-run", action="store_true", help="print the plan only")
    g.add_argument("--days", type=int, default=28)
    g.add_argument("--scale", type=float, default=0.2,
                   help="traffic relative to the recording (5 Locust users); the default 0.2 "
                        "matches docker-compose.managed.yml's single Locust user")
    g.add_argument("--slo", type=float, default=0.999)
    g.add_argument("--burn-weeks-before", type=int, default=1,
                   help="weeks before the deploy that the Docs burn happens")
    g.add_argument("--burn-at", default="10:20", help="UTC time of day the burn starts")
    g.add_argument("--burn-minutes", type=int, default=40)
    g.add_argument("--burn-budget-share", type=float, default=0.4)
    g.add_argument("--deploy-days-ago", type=int, default=2,
                   help="the deploy is on the latest incident weekday at least this many days ago")
    g.add_argument("--incident-weekday", type=int, default=5,
                   help="weekday both incidents fall on, Monday=0 (default 5, Saturday)")
    g.add_argument("--deploy-at", default="13:05", help="UTC time of day 2.0.0 is deployed")
    g.add_argument("--deploy-minutes", type=int, default=300)
    g.add_argument("--deploy-budget-share", type=float, default=0.3)
    g.add_argument("--now", help="ISO time to end at (default: now)")
    g.add_argument("--env-file", default=os.path.join(HERE, "..", ".env"),
                   help="read OTEL_EXPORTER_OTLP_* from here when they aren't set (default: the app's .env)")
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--batch-size", type=int, default=2000)
    g.add_argument("--threads", type=int, default=8)
    args = p.parse_args()
    {"templates": cmd_templates, "generate": cmd_generate}[args.cmd](args)


if __name__ == "__main__":
    main()
