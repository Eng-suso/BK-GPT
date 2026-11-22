"""Static acceptance checks for isolated local release stacks; no Docker daemon needed."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from ops import local_release

ROOT = Path(__file__).resolve().parents[2]
OPS = ROOT / "ops"
COMPOSE = (
    OPS / "docker-compose.yml",
    OPS / "docker-compose.prod.yml",
    OPS / "docker-compose.staging.yml",
)


def _config(files: tuple[Path, ...], env_file: Path) -> dict:
    if shutil.which("docker") is None:
        pytest.skip("Docker Compose CLI non installato")
    command = ["docker", "compose", "--env-file", str(env_file)]
    for file in files:
        command.extend(("-f", str(file)))
    command.extend(("config", "--format", "json"))
    environment = os.environ.copy()
    for key in (*local_release.REQUIRED_KEYS, "DELIR_TENANT_ID", "DELIR_IMAGE_TAG"):
        environment.pop(key, None)
    environment["DOCKER_CONFIG"] = str(env_file.parent / "empty-docker-config")
    result = subprocess.run(
        command, capture_output=True, text=True, env=environment, check=False
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _resources(
    config: dict,
) -> tuple[set[str], set[str], set[str], set[tuple[str, str]]]:
    containers = {service["container_name"] for service in config["services"].values()}
    volumes = {volume["name"] for volume in config.get("volumes", {}).values()}
    networks = {network["name"] for network in config.get("networks", {}).values()}
    ports = {
        (str(port.get("host_ip", "")), str(port.get("published", "")))
        for service in config["services"].values()
        for port in service.get("ports", [])
    }
    return containers, volumes, networks, ports


def test_dev_staging_and_prod_sim_have_disjoint_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(local_release, "OPS", tmp_path)
    staging_file = local_release.generate("staging")
    sim_file = local_release.generate("prod-sim")
    assert local_release.validate("staging", dev_path=tmp_path / "missing-dev") == []
    assert local_release.validate("prod-sim", dev_path=tmp_path / "missing-dev") == []

    dev = _config((COMPOSE[0],), OPS / ".env.example")
    staging = _config(COMPOSE, staging_file)
    sim = _config(COMPOSE, sim_file)
    local_release.assert_isolated_config(staging, "staging")
    local_release.assert_isolated_config(sim, "prod-sim")
    with pytest.raises(ValueError, match="project name"):
        local_release.assert_isolated_config(dev, "staging")
    assert dev["name"] == "ops"
    assert staging["name"] == "delir-staging"
    assert sim["name"] == "delir-prod-sim"
    for left, right in ((dev, staging), (dev, sim), (staging, sim)):
        for left_names, right_names in zip(
            _resources(left), _resources(right), strict=True
        ):
            assert left_names.isdisjoint(right_names)
    for config in (dev, staging, sim):
        assert all(
            not volume.get("external", False)
            for volume in config.get("volumes", {}).values()
        )
        assert all(
            not network.get("external", False)
            for network in config.get("networks", {}).values()
        )
        assert all(host == "127.0.0.1" for host, _ in _resources(config)[3])
    assert (
        staging["services"]["app"]["environment"]["DELIR_DEFAULT_TENANT_ID"]
        == "staging"
    )
    assert (
        staging["services"]["app"]["environment"]["DELIR_ALLOWED_TENANT_IDS"]
        == "staging"
    )
    assert staging["services"]["app"]["environment"]["WORKERS_IN_PROCESS"] == "false"
    assert staging["services"]["app"]["environment"]["LANGSMITH_TRACING"] == "false"
    assert staging["services"]["app"]["environment"]["LANGSMITH_API_KEY"] == ""
    assert staging["services"]["app"]["environment"]["DELIR_ADMIN_TOKEN"] == ""
    assert staging["services"]["prosimos"]["environment"]["GUNICORN_WORKERS"] == "1"
    staging["volumes"]["delir_pgdata"]["name"] = "delir_pgdata"
    with pytest.raises(ValueError, match="volumi"):
        local_release.assert_isolated_config(staging, "staging")


def test_validation_rejects_missing_colliding_and_invalid_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(local_release, "OPS", tmp_path)
    staging = local_release.generate("staging")
    dev = tmp_path / ".env"
    assert local_release.validate("staging", dev_path=dev) == []
    values = local_release.read_env(staging)
    dev.write_text(
        f"POSTGRES_PORT={values['POSTGRES_PORT']}\n"
        f"NEO4J_PASSWORD={values['NEO4J_PASSWORD']}\n",
        encoding="utf-8",
    )
    errors = local_release.validate("staging", dev_path=dev)
    assert any("porte condivise" in error for error in errors)
    assert any("credenziali condivise" in error for error in errors)
    assert all(values["NEO4J_PASSWORD"] not in error for error in errors)

    content = staging.read_text(encoding="utf-8")
    content = content.replace(
        "DELIR_ALLOWED_TENANT_IDS=staging", "DELIR_ALLOWED_TENANT_IDS=other"
    )
    staging.write_text(content, encoding="utf-8")
    errors = local_release.validate("staging", dev_path=tmp_path / "missing-dev")
    assert "campo non valido: TENANT_ORIGIN" in errors

    content = content.replace(
        "DELIR_API_TOKEN=" + values["DELIR_API_TOKEN"], "DELIR_API_TOKEN="
    )
    staging.write_text(content, encoding="utf-8")
    errors = local_release.validate("staging", dev_path=tmp_path / "missing-dev")
    assert "variabile mancante: DELIR_API_TOKEN" in errors


def test_pydantic_settings_mask_secrets_and_allow_multiple_tenants(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(local_release, "OPS", tmp_path)
    staging = local_release.generate("staging")
    values = local_release.read_env(staging)
    staging.write_text(
        staging.read_text(encoding="utf-8").replace(
            "DELIR_ALLOWED_TENANT_IDS=staging",
            "DELIR_ALLOWED_TENANT_IDS=staging,second_tenant",
        ),
        encoding="utf-8",
    )
    assert local_release.validate("staging", dev_path=tmp_path / "missing-dev") == []
    settings = local_release.LocalReleaseSettings(_env_file=staging)
    assert str(settings.neo4j_password) == "**********"
    assert values["NEO4J_PASSWORD"] not in repr(settings)
    config = _config(COMPOSE, staging)
    assert (
        config["services"]["app"]["environment"]["DELIR_ALLOWED_TENANT_IDS"]
        == "staging,second_tenant"
    )


def test_shell_override_is_rejected_without_showing_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(local_release, "OPS", tmp_path)
    local_release.generate("staging")
    errors = local_release.validate(
        "staging",
        dev_path=tmp_path / "missing-dev",
        shell_environment={"POSTGRES_PORT": "5432"},
    )
    assert "variabile di shell sovrascrive il file: POSTGRES_PORT" in errors
    assert all("5432" not in error for error in errors)


def test_duplicate_env_key_is_rejected_without_showing_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(local_release, "OPS", tmp_path)
    staging = local_release.generate("staging")
    with staging.open("a", encoding="utf-8") as file:
        file.write("NEO4J_PASSWORD=another-synthetic-value\n")
    errors = local_release.validate("staging", dev_path=tmp_path / "missing-dev")
    assert errors == ["variabile duplicata in .env.staging: NEO4J_PASSWORD"]


def test_validation_rejects_provider_key_shared_with_dev_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(local_release, "OPS", tmp_path)
    staging = local_release.generate("staging")
    prod_sim = local_release.generate("prod-sim")
    dev_runtime = tmp_path / "dev-runtime.env"
    shared_key = "synthetic-test-provider-key"
    for env_file in (staging, prod_sim):
        env_file.write_text(
            env_file.read_text(encoding="utf-8").replace(
                "OPENAI_API_KEY=local-no-provider-calls", f"OPENAI_API_KEY={shared_key}"
            ),
            encoding="utf-8",
        )
    dev_runtime.write_text(f"OPENAI_API_KEY={shared_key}\n", encoding="utf-8")
    errors = local_release.validate(
        "staging",
        dev_path=tmp_path / "missing-dev-compose",
        dev_runtime_path=dev_runtime,
    )
    assert "credenziali condivise con DEV runtime" in errors
    assert "credenziali condivise con .env.prod-sim" in errors
    assert all(shared_key not in error for error in errors)


def test_prod_sim_promotes_staging_images_without_rebuilding():
    commands = local_release.action_commands("prod-sim", "up")
    assert commands[0] == [
        "docker",
        "tag",
        "delir:delir-staging",
        "delir:delir-prod-sim",
    ]
    assert commands[1] == [
        "docker",
        "tag",
        "delir-prosimos-runner:staging",
        "delir-prosimos-runner:prod-sim",
    ]
    assert "--no-build" in commands[2]
    assert "--force-recreate" in commands[2]
    assert "--build" not in commands[2]
