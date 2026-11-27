"""Test di carico: N persone, ognuna col suo account, usano DeliR nello stesso momento.

Ogni persona virtuale entra col suo token (ES256, firmato con la chiave che
`fake_openai.py` pubblica come JWKS di Supabase), quindi lavora nel suo account,
come in produzione. Il giro di ognuna, ripetuto per `--minutes`:

1. un turno di chat in streaming (misura: primo pezzo di risposta e turno intero);
2. la navigazione: elenco progetti, elenco clienti, storico delle chat;
3. ogni `--sim-every` turni una simulazione Prosimos (200 casi), seguita fino alla fine.

Fra un'azione e l'altra una pausa da persona (`--think` secondi, a caso). Tutte
partono insieme: e' il caso peggiore, non quello medio.

Mentre gira, ogni 5 secondi campiona memoria del processo dell'app e connessioni
aperte su Postgres. Alla fine scrive `results.json` e `results.md` in `--out`.

    uv run python -m scripts.load_test.run --users 10 --minutes 5 --out docs/load-test/run-1

Prerequisiti (vedi docs/load-test/README.md): Postgres, Prosimos, il finto OpenAI e
l'app avviata con `DELIR_AUTH_PROVIDER=supabase` verso il finto Supabase.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics
import subprocess
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm

ROOT = Path(__file__).resolve().parents[2]
BPMN = (ROOT / "ops" / "prosimos" / "spike" / "p2p_mini.bpmn").read_text(encoding="utf-8")
MODEL = "gpt-5.6-luna"
SIMULATION = {
    "total_cases": 200,
    "resources": [{"id": "clerk", "name": "Impiegato", "cost_per_hour": 30, "amount": 2}],
    "tasks": [
        {"element_id": "T_receive", "mean_seconds": 600, "resource_id": "clerk"},
        {"element_id": "T_approve", "mean_seconds": 1200, "resource_id": "clerk"},
        {"element_id": "T_pay", "mean_seconds": 900, "resource_id": "clerk"},
    ],
    "current_bpmn_xml": BPMN,
}


def make_keys(state: Path) -> ec.EllipticCurvePrivateKey:
    """La chiave degli account di prova; la pubblica va dove la legge il finto Supabase."""
    state.mkdir(parents=True, exist_ok=True)
    pem = state / "signing-key.pem"
    if pem.exists():
        key = serialization.load_pem_private_key(pem.read_bytes(), password=None)
    else:
        key = ec.generate_private_key(ec.SECP256R1())
        pem.write_bytes(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ))
    public = json.loads(ECAlgorithm.to_jwk(key.public_key()))
    public.update({"kid": "load-1", "alg": "ES256", "use": "sig"})
    (state / "jwks.json").write_text(json.dumps({"keys": [public]}), encoding="utf-8")
    return key


def token_for(key, supabase_url: str, subject: str, email: str) -> str:
    now = int(time.time())
    return jwt.encode(
        {"iss": f"{supabase_url}/auth/v1", "aud": "authenticated", "sub": subject,
         "role": "authenticated", "is_anonymous": False, "email": email,
         "iat": now, "exp": now + 4 * 3600},
        key, algorithm="ES256", headers={"kid": "load-1"},
    )


@dataclass
class Recorder:
    samples: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    errors: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))

    def ok(self, name: str, seconds: float) -> None:
        self.samples[name].append(seconds)

    def fail(self, name: str, why: str) -> None:
        self.errors[name].append(why[:300])


class Person:
    def __init__(self, n: int, client: httpx.AsyncClient, token: str, rec: Recorder, args) -> None:
        self.n, self.http, self.rec, self.args = n, client, rec, args
        self.headers = {"Authorization": f"Bearer {token}"}

    async def call(self, name: str, method: str, path: str, **kw) -> httpx.Response | None:
        started = time.perf_counter()
        try:
            response = await self.http.request(method, path, headers=self.headers, **kw)
        except httpx.HTTPError as exc:
            self.rec.fail(name, f"{type(exc).__name__}: {exc}")
            return None
        if response.status_code >= 400:
            self.rec.fail(name, f"{response.status_code}: {response.text[:200]}")
            return None
        self.rec.ok(name, time.perf_counter() - started)
        return response

    async def setup(self) -> bool:
        me = await self.call("auth_me", "GET", "/v1/auth/me")
        client = await self.call("create_client", "POST", "/v1/workspace/clients",
                                 json={"name": f"Cliente carico {self.n}"})
        if not (me and client):
            return False
        project = await self.call("create_project", "POST", "/v1/workspace/projects",
                                  json={"client_id": client.json()["id"], "name": f"Progetto {self.n}"})
        if not project:
            return False
        self.project_id = project.json()["id"]
        process = await self.call("create_process", "POST",
                                  f"/v1/workspace/projects/{self.project_id}/processes",
                                  json={"name": f"Ordini {self.n}"})
        session = await self.call("create_chat", "POST", "/v1/consultant-chat/sessions",
                                  json={"model_name": MODEL, "scope": {"type": "consultant"}})
        if not (process and session):
            return False
        self.bpmn_model_id = process.json()["bpmn_model_id"]
        self.thread_id = session.json()["thread_id"]
        return True

    async def chat_turn(self, i: int) -> None:
        body = {"message": f"Domanda {i}: dove si ferma il processo ordini?", "model_name": MODEL,
                "scope": {"type": "consultant"}}
        started = time.perf_counter()
        first: float | None = None
        last_type = None
        try:
            async with self.http.stream(
                "POST", f"/v1/consultant-chat/sessions/{self.thread_id}/messages/stream",
                headers=self.headers, json=body, timeout=180,
            ) as response:
                if response.status_code >= 400:
                    self.rec.fail("chat_turn", f"{response.status_code}: {(await response.aread())[:200]!r}")
                    return
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    event = json.loads(line)
                    last_type = event.get("type")
                    if last_type == "delta" and first is None:
                        first = time.perf_counter() - started
                    if last_type == "error":
                        self.rec.fail("chat_turn", f"evento error: {json.dumps(event)[:200]}")
                        return
        except httpx.HTTPError as exc:
            self.rec.fail("chat_turn", f"{type(exc).__name__}: {exc}")
            return
        if last_type != "done":
            self.rec.fail("chat_turn", f"stream finito con {last_type}")
            return
        self.rec.ok("chat_turn", time.perf_counter() - started)
        if first is not None:
            self.rec.ok("chat_first_token", first)

    async def browse(self) -> None:
        await self.call("list_projects", "GET", "/v1/workspace/projects")
        await self.call("list_clients", "GET", "/v1/workspace/clients")
        await self.call("list_chats", "GET", "/v1/consultant-chat/sessions")
        await self.call("usage_me", "GET", "/v1/usage/me")

    async def simulate(self) -> None:
        started = time.perf_counter()
        created = await self.call("simulation_start", "POST",
                                  f"/v1/workspace/bpmn-models/{self.bpmn_model_id}/simulation-runs",
                                  json=SIMULATION, timeout=60)
        if not created:
            return
        run_id = created.json()["id"]
        while time.perf_counter() - started < 600:
            await asyncio.sleep(2)
            run = await self.call("simulation_poll", "GET", f"/v1/workspace/simulation-runs/{run_id}")
            if run is None:
                continue
            status = run.json()["status"]
            if status == "completed":
                self.rec.ok("simulation_total", time.perf_counter() - started)
                return
            if status == "failed":
                self.rec.fail("simulation_total", f"failed: {run.json().get('error')}")
                return
        self.rec.fail("simulation_total", "oltre 10 minuti")

    async def think(self) -> None:
        await asyncio.sleep(random.uniform(*self.args.think))

    async def run(self, deadline: float) -> None:
        if not await self.setup():
            return
        i = 0
        while time.monotonic() < deadline:
            i += 1
            await self.chat_turn(i)
            await self.think()
            await self.browse()
            if self.args.sim_every and i % self.args.sim_every == self.n % self.args.sim_every:
                await self.simulate()
            await self.think()


def _pid_of_app(port: int) -> int | None:
    """Il processo Python che serve la porta (l'ultimo nato fra quelli di uvicorn)."""
    out = subprocess.run(["pgrep", "-f", f"uvicorn backend.app:app.*--port {port}"],
                         capture_output=True, text=True).stdout.split()
    return max(int(p) for p in out) if out else None


async def sample_resources(port: int, dsn: str | None, stop: asyncio.Event, out: list[dict]) -> None:
    pid = _pid_of_app(port)
    while not stop.is_set():
        row: dict = {"t": time.time()}
        if pid:
            try:
                status = Path(f"/proc/{pid}/status").read_text()
                row["app_rss_mb"] = int(next(line for line in status.splitlines() if line.startswith("VmRSS")).split()[1]) // 1024
                row["app_threads"] = int(next(line for line in status.splitlines() if line.startswith("Threads")).split()[1])
            except (OSError, StopIteration):
                pass
        if dsn:
            res = subprocess.run(["psql", dsn, "-Atc",
                                  "select count(*), count(*) filter (where state='active') from pg_stat_activity where backend_type='client backend'"],
                                 capture_output=True, text=True)
            if res.returncode == 0 and "|" in res.stdout:
                total, active = res.stdout.strip().split("|")
                row["pg_connections"], row["pg_active"] = int(total), int(active)
        out.append(row)
        try:
            await asyncio.wait_for(stop.wait(), timeout=5)
        except asyncio.TimeoutError:
            pass


def _pct(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(p / 100 * (len(ordered) - 1))))]


def summarize(rec: Recorder, resources: list[dict], args, wall: float) -> dict:
    ops = {}
    for name in sorted(set(rec.samples) | set(rec.errors)):
        values = rec.samples.get(name, [])
        ops[name] = {
            "ok": len(values), "errors": len(rec.errors.get(name, [])),
            **({"p50_s": round(statistics.median(values), 3), "p95_s": round(_pct(values, 95), 3),
                "max_s": round(max(values), 3)} if values else {}),
            "error_examples": sorted(set(rec.errors.get(name, [])))[:3],
        }
    peak = {k: max((r.get(k, 0) for r in resources), default=0)
            for k in ("app_rss_mb", "app_threads", "pg_connections", "pg_active")}
    return {"users": args.users, "minutes": args.minutes, "wall_s": round(wall, 1),
            "fake_llm": {"ttft_ms": os.environ.get("FAKE_TTFT_MS", "800"),
                         "tokens_per_s": os.environ.get("FAKE_TOKENS_PER_S", "40")},
            "operations": ops, "peak": peak}


def write_report(summary: dict, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        f"# Test di carico: {summary['users']} persone per {summary['minutes']} minuti", "",
        f"Durata reale {summary['wall_s']} s. Modello finto: primo token dopo "
        f"{summary['fake_llm']['ttft_ms']} ms, {summary['fake_llm']['tokens_per_s']} token/s.", "",
        "| Operazione | Riuscite | Errori | p50 (s) | p95 (s) | max (s) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, op in summary["operations"].items():
        lines.append(f"| {name} | {op['ok']} | {op['errors']} | {op.get('p50_s', '-')} | "
                     f"{op.get('p95_s', '-')} | {op.get('max_s', '-')} |")
    peak = summary["peak"]
    lines += ["", f"Picchi: memoria dell'app {peak['app_rss_mb']} MB, {peak['app_threads']} thread, "
              f"{peak['pg_connections']} connessioni Postgres ({peak['pg_active']} attive insieme).", ""]
    errors = {n: op["error_examples"] for n, op in summary["operations"].items() if op["error_examples"]}
    if errors:
        lines += ["## Errori (esempi)", ""]
        for name, examples in errors.items():
            lines += [f"- **{name}**"] + [f"  - `{e}`" for e in examples]
    (out / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


async def main_async(args) -> dict:
    key = make_keys(Path(args.state))
    rec = Recorder()
    limits = httpx.Limits(max_connections=args.users * 4, max_keepalive_connections=args.users * 4)
    async with httpx.AsyncClient(base_url=args.base_url, timeout=60, limits=limits) as client:
        people = [
            Person(n, client, token_for(key, args.supabase_url, str(uuid.uuid4()),
                                        f"persona{n}@{args.email_domain}"), rec, args)
            for n in range(args.users)
        ]
        stop = asyncio.Event()
        resources: list[dict] = []
        sampler = asyncio.create_task(sample_resources(args.app_port, args.pg_dsn, stop, resources))
        started = time.monotonic()
        deadline = started + args.minutes * 60
        await asyncio.gather(*(p.run(deadline) for p in people))
        wall = time.monotonic() - started
        stop.set()
        await sampler
    summary = summarize(rec, resources, args, wall)
    write_report(summary, Path(args.out))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--users", type=int, default=10)
    parser.add_argument("--minutes", type=float, default=5)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--app-port", type=int, default=8000)
    parser.add_argument("--supabase-url", default="http://127.0.0.1:8099")
    parser.add_argument("--email-domain", default="carico.test")
    parser.add_argument("--sim-every", type=int, default=3)
    parser.add_argument("--think", type=float, nargs=2, default=(2.0, 5.0))
    parser.add_argument("--state", default="/var/tmp/delir-load")
    parser.add_argument("--pg-dsn", default=os.environ.get("LOAD_PG_DSN"))
    parser.add_argument("--out", default="docs/load-test/latest")
    args = parser.parse_args()
    summary = asyncio.run(main_async(args))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
