"""Promoting one exact Anaconda.org artifact between labels."""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from binstar_client.utils import get_server_api

_SHA256 = re.compile(r"[0-9a-f]{64}")
_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


class AnacondaAPI(Protocol):
    """Describing the bounded API surface used by promotion."""

    def show_channel(self, channel: str, owner: str) -> dict: ...

    def add_channel(
        self,
        channel: str,
        owner: str,
        package: str | None = None,
        version: str | None = None,
        filename: str | None = None,
    ) -> None: ...


@dataclass(frozen=True)
class ExactPackage:
    """Identifying one immutable Anaconda.org distribution file."""

    owner: str
    package: str
    version: str
    basename: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.package}/{self.version}/{self.basename}"


def parse_exact_spec(value: str) -> ExactPackage:
    """Parsing owner/package/version/subdir/filename without broad selectors."""

    parts = value.split("/")
    if len(parts) != 5 or not all(parts):
        raise ValueError("package spec must be owner/package/version/subdir/filename")
    owner, package, version, subdir, filename = parts
    for field_name, field in (
        ("owner", owner),
        ("package", package),
        ("version", version),
        ("subdir", subdir),
        ("filename", filename),
    ):
        if field in {".", ".."} or any(char.isspace() for char in field):
            raise ValueError(f"unsafe {field_name} in package spec")
    if not filename.endswith((".conda", ".tar.bz2")):
        raise ValueError("package filename must end in .conda or .tar.bz2")
    return ExactPackage(owner, package, version, f"{subdir}/{filename}")


def _exact_file(api: AnacondaAPI, label: str, package: ExactPackage) -> dict | None:
    channel = api.show_channel(label, package.owner)
    matches = [
        item
        for item in channel.get("files", [])
        if item.get("full_name") == package.full_name
    ]
    if len(matches) > 1:
        raise RuntimeError(
            f"label {label!r} returned duplicate identity {package.full_name!r}"
        )
    return matches[0] if matches else None


def promote_exact_package(
    api: AnacondaAPI,
    *,
    package: ExactPackage,
    source_label: str,
    target_label: str,
    expected_sha256: str,
) -> dict:
    """Adding a target label only after exact source and digest verification."""

    if source_label == target_label:
        raise ValueError("source and target labels must differ")
    if not _LABEL.fullmatch(source_label) or not _LABEL.fullmatch(target_label):
        raise ValueError("source and target labels must use safe label names")
    if not _SHA256.fullmatch(expected_sha256):
        raise ValueError(
            "expected SHA-256 must contain exactly 64 lowercase hex digits"
        )

    source = _exact_file(api, source_label, package)
    if source is None:
        raise RuntimeError(
            f"exact package is absent from source label {source_label!r}: "
            f"{package.full_name}"
        )
    if source.get("sha256") != expected_sha256:
        raise RuntimeError(
            f"source digest mismatch for {package.full_name}: "
            f"expected {expected_sha256}, observed {source.get('sha256')}"
        )

    target = _exact_file(api, target_label, package)
    if target is None:
        api.add_channel(
            target_label,
            package.owner,
            package=package.package,
            version=package.version,
            filename=package.basename,
        )
        target = _exact_file(api, target_label, package)
    if target is None:
        raise RuntimeError(
            f"promotion returned without publishing {package.full_name} to "
            f"label {target_label!r}"
        )
    if target.get("sha256") != expected_sha256:
        raise RuntimeError(
            f"target digest mismatch for {package.full_name}: "
            f"expected {expected_sha256}, observed {target.get('sha256')}"
        )

    return {
        "schema": "uibcdf.conda-promotion@1",
        "package": package.full_name,
        "sha256": expected_sha256,
        "source_label": source_label,
        "target_label": target_label,
        "status": "verified",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-spec", required=True)
    parser.add_argument("--from-label", default="staging")
    parser.add_argument("--to-label", default="main")
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    token = os.environ.get("ANACONDA_API_TOKEN")
    if not token:
        raise RuntimeError("ANACONDA_API_TOKEN is required")
    package = parse_exact_spec(args.package_spec)
    api = get_server_api(token, None)
    receipt = promote_exact_package(
        api,
        package=package,
        source_label=args.from_label,
        target_label=args.to_label,
        expected_sha256=args.expected_sha256,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with Path(github_output).open("a", encoding="utf-8") as stream:
            stream.write(f"package={package.full_name}\n")
            stream.write(f"sha256={args.expected_sha256}\n")
            stream.write(f"receipt={args.output}\n")
    print(
        f"promoted and verified {package.full_name} "
        f"{args.from_label}->{args.to_label} sha256={args.expected_sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
