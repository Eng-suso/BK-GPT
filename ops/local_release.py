"""Generate and validate isolated local Compose configurations without printing secrets."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import SettingsConfigDict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.settings import Settings

OPS = Path(__file__).resolve().parent
MODES = {
    "staging": ("delir-staging", "delir_staging", (15432, 17474, 17687, 15001, 18000)),
    "prod-sim": (
        "delir-prod-sim",
        "delir_prod_sim",
        (25432, 27474, 27687, 25001, 28000),
    ),
}
PORT_KEYS = (
    "POSTGRES_PORT",
    "NEO4J_HTTP_PORT",
    "NEO4J_BOLT_PORT",
    "DOCLING_PORT",
    "APP_PORT",
)
DEV_PORT_DEFAULTS = (5432, 7474, 7687, 5001, 8000)
SECRET_KEYS = (
    "POSTGRES_SUPER_PASSWORD",
    "DELIR_MIGRATOR_PASSWORD",
    "DELIR_APP_PASSWORD",
    "DELIR_WORKER_PASSWORD",
    "DELIR_MEM0_PASSWORD",
    "DELIR_WORKSPACE_PASSWORD",
    "NEO4J_PASSWORD",
    "DELIR_API_TOKEN",
)
COMPARISON_SECRET_KEYS = (*SECRET_KEYS, "OPENAI_API_KEY", "DELIR_ADMIN_TOKEN")
COMPOSE_ENV_KEYS = (
    *COMPARISON_SECRET_KEYS,
    *PORT_KEYS,
    "DELIR_LOCAL_STACK",
    "DELIR_LOCAL_VOLUME_PREFIX",
    "DELIR_LOCAL_ENVIRONMENT",
    "DELIR_DEFAULT_TENANT_ID",
    "DELIR_ALLOWED_TENANT_IDS",
    "DELIR_TENANT_ID",
    "DELIR_PUBLIC_ORIGIN",
    "DELIR_IMAGE_TAG",
    "DOCLING_SERVE_TAG",
    "PROSIMOS_WORKERS",
    "DELIR_IMAGE",
)
REQUIRED_KEYS = (
    *SECRET_KEYS,
    *PORT_KEYS,
    "DELIR_LOCAL_STACK",
    "DELIR_LOCAL_VOLUME_PREFIX",
    "DELIR_LOCAL_ENVIRONMENT",
    "DELIR_DEFAULT_TENANT_ID",
    "DELIR_ALLOWED_TENANT_IDS",
    "DELIR_TENANT_ID",
    "DELIR_PUBLIC_ORIGIN",
    "OPENAI_API_KEY",
    "DELIR_IMAGE_TAG",
)
TENANT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")


class LocalReleaseSettings(Settings):
    """Compose-only settings layered on the existing FastAPI settings schema."""

    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    DELIR_LOCAL_STACK: str = Field(min_length=1)
    DELIR_LOCAL_VOLUME_PREFIX: str = Field(min_length=1)
    DELIR_LOCAL_ENVIRONMENT: Literal["staging", "prod-sim"]
    POSTGRES_PORT: int = Field(ge=1, le=65535)
    NEO4J_HTTP_PORT: int = Field(ge=1, le=65535)
    NEO4J_BOLT_PORT: int = Field(ge=1, le=65535)
    DOCLING_PORT: int = Field(ge=1, le=65535)
    APP_PORT: int = Field(ge=1, le=65535)
    POSTGRES_SUPER_PASSWORD: SecretStr
    DELIR_MIGRATOR_PASSWORD: SecretStr
    DELIR_APP_PASSWORD: SecretStr
    DELIR_WORKER_PASSWORD: SecretStr
    DELIR_MEM0_PASSWORD: SecretStr
    DELIR_WORKSPACE_PASSWORD: SecretStr
    neo4j_password: SecretStr
    delir_api_token: SecretStr
    openai_api_key: SecretStr
    delir_default_tenant_id: str = Field(min_length=1, pattern=TENANT_PATTERN.pattern)
    delir_allowed_tenant_ids: str = Field(min_length=1)
    DELIR_PUBLIC_ORIGIN: str = Field(min_length=1)

    @field_validator(
        "POSTGRES_SUPER_PASSWORD",
        "DELIR_MIGRATOR_PASSWORD",
        "DELIR_APP_PASSWORD",
        "DELIR_WORKER_PASSWORD",
        "DELIR_MEM0_PASSWORD",
        "DELIR_WORKSPACE_PASSWORD",
        "neo4j_password",
        "delir_api_token",
    )
    @classmethod
    def valid_secret(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if len(raw) < 24 or not raw.isalnum() or raw.lower().startswith("change"):
            raise ValueError("credenziale locale non valida")
        return value

    @model_validator(mode="after")
    def valid_tenants_and_origin(self) -> LocalReleaseSettings:
        allowed = [
            item.strip()
            for item in self.delir_allowed_tenant_ids.split(",")
            if item.strip()
        ]
        if not allowed or any(not TENANT_PATTERN.fullmatch(item) for item in allowed):
            raise ValueError("allowlist tenant non valida")
        if self.delir_default_tenant_id not in allowed:
            raise ValueError("tenant di default assente dalla allowlist")
        if self.DELIR_PUBLIC_ORIGIN != f"http://127.0.0.1:{self.APP_PORT}":
            raise ValueError("origine locale non corrisponde alla porta app")
        return self


def env_path(mode: str) -> Path:
    return OPS / f".env.{mode}"


def read_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"riga non valida in {path.name}")
        key, value = line.split("=", 1)
        key = key.strip()
        if key in result:
            raise ValueError(f"variabile duplicata in {path.name}: {key}")
        result[key] = value.strip()
    return result


def generate(mode: str) -> Path:
    stack, volume_prefix, ports = MODES[mode]
    target = env_path(mode)
    tenant = mode.replace("-", "_")
    values = {
        "DELIR_LOCAL_STACK": stack,
        "DELIR_LOCAL_VOLUME_PREFIX": volume_prefix,
        "DELIR_LOCAL_ENVIRONMENT": mode,
        **dict(zip(PORT_KEYS, map(str, ports), strict=True)),
        **{key: secrets.token_hex(24) for key in SECRET_KEYS},
        "DELIR_DEFAULT_TENANT_ID": tenant,
        "DELIR_ALLOWED_TENANT_IDS": tenant,
        # Fallback legacy richiesto dall'interpolazione Compose del file prod.
        "DELIR_TENANT_ID": tenant,
        "DELIR_PUBLIC_ORIGIN": f"http://127.0.0.1:{ports[-1]}",
        # Placeholder intenzionale: i test locali non devono chiamare il provider.
        "OPENAI_API_KEY": "local-no-provider-calls",
        "DELIR_IMAGE_TAG": mode,
        "LANGSMITH_TRACING": "false",
    }
    content = "# Generato localmente; non versionare e non usare con dati reali.\n"
    content += "# OPENAI_API_KEY è un placeholder: nessuna chiamata LLM è prevista.\n"
    content += "\n".join(f"{key}={value}" for key, value in values.items()) + "\n"
    with target.open("x", encoding="utf-8", newline="\n") as file:
        file.write(content)
    return target


def _ports(values: dict[str, str], defaults: tuple[int, ...]) -> set[int]:
    ports: set[int] = set()
    for key, fallback in zip(PORT_KEYS, defaults, strict=True):
        value = values.get(key, str(fallback))
        if not value.isdecimal() or not 1 <= int(value) <= 65535:
            raise ValueError(f"porta non valida: {key}")
        ports.add(int(value))
    return ports


def validate(
    mode: str,
    *,
    path: Path | None = None,
    dev_path: Path | None = None,
    dev_runtime_path: Path | None = None,
    peer_path: Path | None = None,
    shell_environment: dict[str, str] | None = None,
) -> list[str]:
    path = path or env_path(mode)
    custom_dev_path = dev_path is not None
    dev_path = dev_path or OPS / ".env"
    # FastAPI in DEV loads the root .env; Compose reads ops/.env. Compare both.
    if dev_runtime_path is None and not custom_dev_path:
        dev_runtime_path = OPS.parent / ".env"
    other_mode = "prod-sim" if mode == "staging" else "staging"
    peer_path = peer_path or env_path(other_mode)
    try:
        values = read_env(path)
    except ValueError as exc:
        return [str(exc)]
    shell_environment = os.environ if shell_environment is None else shell_environment
    errors: list[str] = []
    if not path.exists():
        return [f"manca {path.name}; esegui init {mode}"]
    stack, volume_prefix, expected_ports = MODES[mode]
    for key in REQUIRED_KEYS:
        if not values.get(key):
            errors.append(f"variabile mancante: {key}")
    for key in COMPOSE_ENV_KEYS:
        if key in shell_environment and shell_environment[key] != values.get(key, ""):
            errors.append(f"variabile di shell sovrascrive il file: {key}")
    try:
        settings = LocalReleaseSettings(_env_file=path)
    except ValidationError as exc:
        settings = None
        for error in exc.errors():
            location = error.get("loc", ())
            field = str(location[0]).upper() if location else "TENANT_ORIGIN"
            if (
                error["type"] != "missing"
                and f"variabile mancante: {field}" not in errors
            ):
                errors.append(f"campo non valido: {field}")
    if settings is not None:
        if settings.DELIR_LOCAL_STACK != stack:
            errors.append("identita' ambiente non valida: DELIR_LOCAL_STACK")
        if settings.DELIR_LOCAL_VOLUME_PREFIX != volume_prefix:
            errors.append("identita' ambiente non valida: DELIR_LOCAL_VOLUME_PREFIX")
        if settings.DELIR_LOCAL_ENVIRONMENT != mode:
            errors.append("identita' ambiente non valida: DELIR_LOCAL_ENVIRONMENT")
        if values.get("DELIR_TENANT_ID") != settings.delir_default_tenant_id:
            errors.append("DELIR_TENANT_ID legacy diverso dal tenant di default")
        if values.get("DELIR_IMAGE_TAG") != mode:
            errors.append("tag immagine locale non valido: DELIR_IMAGE_TAG")
    try:
        ports = _ports(values, expected_ports)
        if len(ports) != len(PORT_KEYS):
            errors.append("porte duplicate nello stesso ambiente")
    except ValueError as exc:
        errors.append(str(exc))
        ports = set()
    for other_path, defaults in (
        (dev_path, DEV_PORT_DEFAULTS),
        (peer_path, MODES[other_mode][2]),
    ):
        if not other_path.exists():
            continue
        try:
            other = read_env(other_path)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        try:
            if ports & _ports(other, defaults):
                errors.append(f"porte condivise con {other_path.name}")
        except ValueError:
            errors.append(f"porte non valide in {other_path.name}")
        if any(
            values.get(key)
            and values.get(key) != "local-no-provider-calls"
            and values.get(key) == other.get(key)
            for key in COMPARISON_SECRET_KEYS
        ):
            errors.append(f"credenziali condivise con {other_path.name}")
    if dev_runtime_path is not None and dev_runtime_path.exists() and dev_runtime_path != dev_path:
        # DEV's root .env may repeat unrelated settings. Inspect every secret
        # assignment without logging values or enforcing release-file syntax.
        dev_runtime_secrets: set[tuple[str, str]] = set()
        for line in dev_runtime_path.read_text(encoding="utf-8-sig").splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, raw = line.split("=", 1)
            key = key.strip()
            if key in COMPARISON_SECRET_KEYS:
                secret = raw.strip().strip("\"'")
                dev_runtime_secrets.add((key, secret))
        if any(
            values.get(key)
            and values.get(key) != "local-no-provider-calls"
            and (key, values[key]) in dev_runtime_secrets
            for key in COMPARISON_SECRET_KEYS
        ):
            errors.append("credenziali condivise con DEV runtime")
    return errors


def compose_command(mode: str) -> list[str]:
    stack = MODES[mode][0]
    return [
        "docker",
        "compose",
        "-p",
        stack,
        "--env-file",
        str(env_path(mode)),
        "-f",
        str(OPS / "docker-compose.yml"),
        "-f",
        str(OPS / "docker-compose.prod.yml"),
        "-f",
        str(OPS / "docker-compose.staging.yml"),
    ]


def assert_isolated_config(config: dict, mode: str) -> None:
    stack, prefix, expected_ports = MODES[mode]
    services = {"postgres", "neo4j", "docling", "prosimos", "app"}
    if config.get("name") != stack or set(config.get("services", {})) != services:
        raise ValueError("project name o servizi Compose non isolati")
    for name, service in config["services"].items():
        if service.get("container_name") != f"{stack}-{name}":
            raise ValueError(f"container Compose non isolato: {name}")
    expected_volumes = {
        f"{prefix}_{suffix}" for suffix in ("pgdata", "neo4jdata", "appdata")
    }
    volumes = config.get("volumes", {})
    if {item.get("name") for item in volumes.values()} != expected_volumes:
        raise ValueError("volumi Compose non isolati")
    if any(item.get("external", False) for item in volumes.values()):
        raise ValueError("volume esterno non ammesso")
    networks = config.get("networks", {})
    if {item.get("name") for item in networks.values()} != {f"{stack}_default"}:
        raise ValueError("rete Compose non isolata")
    if any(item.get("external", False) for item in networks.values()):
        raise ValueError("rete esterna non ammessa")
    ports = {
        (str(port.get("host_ip", "")), int(port.get("published", 0)))
        for service in config["services"].values()
        for port in service.get("ports", [])
    }
    if ports != {("127.0.0.1", port) for port in expected_ports}:
        raise ValueError("porte Compose non isolate")


def check_compose(mode: str) -> None:
    result = subprocess.run(
        [*compose_command(mode), "config", "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise ValueError("configurazione Compose non valida")
    assert_isolated_config(json.loads(result.stdout), mode)


def action_commands(mode: str, action: str) -> list[list[str]]:
    command = compose_command(mode)
    if action == "data-up":
        return [[*command, "up", "-d", "--wait", "postgres", "neo4j"]]
    if action == "up" and mode == "staging":
        return [[*command, "up", "-d", "--build", "--wait", "--wait-timeout", "600"]]
    if action == "up" and mode == "prod-sim":
        # Promuove le immagini gia' verificate in STAGING: nessun rebuild.
        return [
            ["docker", "tag", "delir:delir-staging", "delir:delir-prod-sim"],
            [
                "docker",
                "tag",
                "delir-prosimos-runner:staging",
                "delir-prosimos-runner:prod-sim",
            ],
            [
                *command,
                "up",
                "-d",
                "--no-build",
                "--pull",
                "never",
                "--force-recreate",
                "--wait",
                "--wait-timeout",
                "600",
            ],
        ]
    if action == "stop":
        return [[*command, "stop"]]
    if action == "teardown":
        return [[*command, "down", "-v"]]
    raise ValueError(f"azione non valida: {action}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("init", "check", "data-up", "up", "stop", "teardown")
    )
    parser.add_argument("mode", choices=tuple(MODES))
    args = parser.parse_args()
    if args.action == "init":
        try:
            target = generate(args.mode)
        except FileExistsError:
            print(f"{env_path(args.mode).name} esiste gia': nessuna modifica")
        else:
            print(f"creato {target.name}; valori non mostrati")
    errors = validate(args.mode)
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    try:
        check_compose(args.mode)
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"configurazione {args.mode} valida; valori non mostrati")
    if args.action not in {"init", "check"}:
        for command in action_commands(args.mode, args.action):
            result = subprocess.run(command, check=False)
            if result.returncode:
                return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
