"""Verifica runtime che STAGING o PROD-SIM non accetti le credenziali degli altri ambienti.

Legge `ops/.env`, `ops/.env.staging` e `ops/.env.prod-sim` e prova contro lo
stack acceso (API, PostgreSQL, Neo4j) sia le credenziali proprie sia quelle
degli altri ambienti. Non stampa mai valori: solo esiti.

Da `ops`, con lo stack scelto acceso:

    & ..\\.venv\\Scripts\\python.exe verify_env_isolation.py staging
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request
from pathlib import Path

import psycopg
from neo4j import GraphDatabase

OPS = Path(__file__).resolve().parent
FILES = {"dev": OPS / ".env", "staging": OPS / ".env.staging", "prod-sim": OPS / ".env.prod-sim"}
PLACEHOLDER_OPENAI = "local-no-provider-calls"
DISTINCT_SECRETS = (
    "DELIR_API_TOKEN",
    "DELIR_APP_PASSWORD",
    "DELIR_WORKSPACE_PASSWORD",
    "NEO4J_PASSWORD",
    "POSTGRES_SUPER_PASSWORD",
    "OPENAI_API_KEY",
)


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


class Probe:
    def __init__(self, target: str) -> None:
        self.env = {name: read_env(path) for name, path in FILES.items()}
        self.target = target
        self.own = self.env[target]
        self.base = f"http://127.0.0.1:{self.own['APP_PORT']}"
        self.results: list[tuple[str, str, str]] = []

    def others(self, *, include_dev: bool) -> list[str]:
        names = ["dev", "staging", "prod-sim"] if include_dev else ["staging", "prod-sim"]
        return [name for name in names if name != self.target]

    def record(self, check: str, expected: str, got: str) -> None:
        self.results.append((check, expected, got))

    def http(self, path: str, token: str | None = None, tenant: str | None = None) -> str:
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if tenant:
            headers["X-Delir-Tenant-Id"] = tenant
        request = urllib.request.Request(self.base + path, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return str(response.status)
        except urllib.error.HTTPError as error:
            return str(error.code)
        except OSError as error:
            return type(error).__name__

    def postgres(self, password: str) -> str:
        try:
            with psycopg.connect(
                host="127.0.0.1",
                port=int(self.own["POSTGRES_PORT"]),
                dbname="delir",
                user="delir_app",
                password=password,
                connect_timeout=5,
            ) as connection:
                connection.execute("select 1")
            return "ok"
        except psycopg.OperationalError as error:
            if "password authentication failed" in str(error):
                return "rifiutata"
            return "errore:" + type(error).__name__

    def neo4j(self, password: str) -> str:
        driver = GraphDatabase.driver(
            f"bolt://127.0.0.1:{self.own['NEO4J_BOLT_PORT']}", auth=("neo4j", password)
        )
        try:
            driver.verify_connectivity()
            return "ok"
        except Exception as error:  # noqa: BLE001 - il driver solleva tipi diversi per versione
            if "Unauthorized" in type(error).__name__ or "auth" in str(error).lower():
                return "rifiutata"
            return "errore:" + type(error).__name__
        finally:
            driver.close()

    def run(self) -> bool:
        own_token = self.own["DELIR_API_TOKEN"]
        own_tenant = self.own["DELIR_DEFAULT_TENANT_ID"]

        self.record("readiness /health/ready", "200", self.http("/health/ready"))
        self.record("API senza token", "401", self.http("/v1/auth/me", tenant=own_tenant))
        self.record(
            "API token e tenant propri", "200", self.http("/v1/auth/me", own_token, own_tenant)
        )
        for other in self.others(include_dev=False):
            values = self.env[other]
            if not values:
                continue
            self.record(
                f"API token di {other}",
                "401",
                self.http("/v1/auth/me", values["DELIR_API_TOKEN"], own_tenant),
            )
            self.record(
                f"API tenant di {other}",
                "403",
                self.http("/v1/auth/me", own_token, values["DELIR_DEFAULT_TENANT_ID"]),
            )
        self.record("API tenant DEV 'local'", "403", self.http("/v1/auth/me", own_token, "local"))

        self.record("PostgreSQL password propria", "ok", self.postgres(self.own["DELIR_APP_PASSWORD"]))
        self.record("Neo4j password propria", "ok", self.neo4j(self.own["NEO4J_PASSWORD"]))
        for other in self.others(include_dev=True):
            values = self.env[other]
            if values.get("DELIR_APP_PASSWORD"):
                self.record(
                    f"PostgreSQL password di {other}",
                    "rifiutata",
                    self.postgres(values["DELIR_APP_PASSWORD"]),
                )
            if values.get("NEO4J_PASSWORD"):
                self.record(
                    f"Neo4j password di {other}", "rifiutata", self.neo4j(values["NEO4J_PASSWORD"])
                )

        for key in DISTINCT_SECRETS:
            present = [
                values[key]
                for values in self.env.values()
                if values.get(key) and values[key] != PLACEHOLDER_OPENAI
            ]
            distinct = "si" if len(present) == len(set(present)) else "NO"
            self.record(f"{key} diverso in ogni ambiente", "si", distinct)

        print(f"== {self.target} ({self.base})")
        for check, expected, got in self.results:
            print(f"{'PASS' if expected == got else 'FAIL'}  {check}: atteso {expected}, ottenuto {got}")
        passed = sum(expected == got for _, expected, got in self.results)
        print(f"TOTALE: {passed}/{len(self.results)}")
        return passed == len(self.results)


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"staging", "prod-sim"}:
        print("uso: verify_env_isolation.py staging|prod-sim", file=sys.stderr)
        return 2
    return 0 if Probe(sys.argv[1]).run() else 1


if __name__ == "__main__":
    raise SystemExit(main())
