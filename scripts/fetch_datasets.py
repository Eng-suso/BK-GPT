"""Scarica e verifica i dataset di DeliR elencati in datasets/manifest.json.

I dataset ``vendored`` sono gia' nel repo: ``verify`` controlla che ci siano.
Quelli ``fetch`` si scaricano una volta nella cache (``DELIR_DATASETS_CACHE``,
default ``~/.cache/delir-datasets``) e si accettano solo se l'MD5 coincide con
il manifest; i repository git si fermano sul commit fissato. Quelli
``academic`` hanno una licenza non commerciale: servono per la ricerca, non
per i numeri commerciali, e richiedono ``--allow-noncommercial``.

Uso:
    uv run python scripts/fetch_datasets.py list
    uv run python scripts/fetch_datasets.py verify
    uv run python scripts/fetch_datasets.py fetch bpic2012 simod
    uv run python scripts/fetch_datasets.py fetch --all
    uv run python scripts/fetch_datasets.py path bpic2012
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "datasets" / "manifest.json"


class DatasetError(RuntimeError):
    """Il dataset non e' disponibile o non e' quello dichiarato."""


def load_manifest(path: Path = MANIFEST) -> dict[str, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = {entry["id"]: entry for entry in data["datasets"]}
    if len(entries) != len(data["datasets"]):
        raise DatasetError("id duplicati nel manifest")
    return entries


def cache_dir() -> Path:
    default = Path.home() / ".cache" / "delir-datasets"
    return Path(os.environ.get("DELIR_DATASETS_CACHE", default))


def md5_of(path: Path) -> str:
    digest = hashlib.md5()  # noqa: S324 - integrita' del file, non sicurezza
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dataset_path(entry: dict) -> Path:
    if entry["mode"] == "vendored":
        return ROOT / entry["path"]
    return cache_dir() / entry["id"]


def _download(url: str, target: Path, md5: str) -> None:
    if target.exists() and md5_of(target) == md5:
        return
    partial = target.with_suffix(target.suffix + ".part")
    target.parent.mkdir(parents=True, exist_ok=True)
    # URL fisso dal manifest, verificato con l'MD5 qui sotto.
    with (
        urllib.request.urlopen(url, timeout=120) as response,  # noqa: S310
        partial.open("wb") as out,
    ):
        shutil.copyfileobj(response, out)
    got = md5_of(partial)
    if got != md5:
        partial.unlink(missing_ok=True)
        raise DatasetError(f"{target.name}: MD5 {got}, atteso {md5}")
    partial.replace(target)


def _fetch_git(entry: dict, target: Path) -> None:
    commit = entry["git_commit"]
    if not (target / ".git").exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "git",
                "clone",
                "--filter=blob:none",
                "--no-checkout",
                entry["git"],
                str(target),
            ],
            check=True,
        )
    subprocess.run(
        ["git", "-C", str(target), "fetch", "--quiet", "origin", commit], check=True
    )
    subprocess.run(
        ["git", "-C", str(target), "checkout", "--quiet", "--detach", commit],
        check=True,
    )
    for name, md5 in entry.get("files_md5", {}).items():
        got = md5_of(target / name)
        if got != md5:
            raise DatasetError(f"{entry['id']}/{name}: MD5 {got}, atteso {md5}")


def fetch(entry: dict, *, allow_noncommercial: bool = False) -> Path:
    mode = entry["mode"]
    if mode == "vendored":
        return verify(entry)
    if mode == "academic" and not allow_noncommercial:
        raise DatasetError(
            f"{entry['id']}: licenza {entry['license']}, serve --allow-noncommercial"
        )
    target = dataset_path(entry)
    if "git" in entry:
        _fetch_git(entry, target)
        return target
    files = entry.get("files") or [entry]
    for item in files:
        archive = target / item["file"]
        _download(item["url"], archive, item["md5"])
        if item.get("extract", entry.get("extract")) and zipfile.is_zipfile(archive):
            marker = target / f".{item['file']}.extracted"
            done = marker.read_text(encoding="utf-8") if marker.exists() else ""
            if done != item["md5"]:
                with zipfile.ZipFile(archive) as bundle:
                    bundle.extractall(target)
                marker.write_text(item["md5"], encoding="utf-8")
    return target


def verify(entry: dict) -> Path:
    path = dataset_path(entry)
    if not path.is_dir() or not any(path.iterdir()):
        raise DatasetError(f"{entry['id']}: {path} mancante")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    sub.add_parser("verify")
    p_fetch = sub.add_parser("fetch")
    p_fetch.add_argument("ids", nargs="*")
    p_fetch.add_argument("--all", action="store_true")
    p_fetch.add_argument("--allow-noncommercial", action="store_true")
    p_path = sub.add_parser("path")
    p_path.add_argument("id")
    args = parser.parse_args(argv)

    manifest = load_manifest()
    if args.command == "list":
        for entry in manifest.values():
            print(f"{entry['id']:34} {entry['mode']:9} {entry['license']}")
        return 0
    if args.command == "path":
        if args.id not in manifest:
            print(f"ERR {args.id}: non nel manifest", file=sys.stderr)
            return 1
        print(dataset_path(manifest[args.id]))
        return 0
    if args.command == "verify":
        failed = 0
        for entry in manifest.values():
            if entry["mode"] != "vendored":
                continue
            try:
                print(f"ok  {entry['id']}: {verify(entry)}")
            except DatasetError as exc:
                failed += 1
                print(f"ERR {exc}", file=sys.stderr)
        return 1 if failed else 0

    if args.all:
        wanted = {"fetch", "academic"} if args.allow_noncommercial else {"fetch"}
        ids = [i for i, e in manifest.items() if e["mode"] in wanted]
    else:
        ids = args.ids
    if not ids:
        parser.error("indica gli id o --all")
    failed = 0
    for dataset_id in ids:
        if dataset_id not in manifest:
            print(f"ERR {dataset_id}: non nel manifest", file=sys.stderr)
            failed += 1
            continue
        try:
            path = fetch(
                manifest[dataset_id], allow_noncommercial=args.allow_noncommercial
            )
            print(f"ok  {dataset_id}: {path}")
        except (DatasetError, OSError, subprocess.CalledProcessError) as exc:
            failed += 1
            print(f"ERR {dataset_id}: {exc}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
