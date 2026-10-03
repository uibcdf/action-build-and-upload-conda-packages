"""Promoting one exact Anaconda.org artifact between labels."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Protocol

from binstar_client import Binstar
from binstar_client.utils import get_server_api

if __package__:
    from .conda_label_utils import (
        LABEL,
        SHA256,
        ExactPackage,
        exact_distribution,
        parse_exact_spec,
    )
else:
    from conda_label_utils import (
        LABEL,
        SHA256,
        ExactPackage,
        exact_distribution,
        parse_exact_spec,
    )


class AnacondaAPI(Protocol):
    """Describing the bounded API surface used by promotion."""

    def release(self, owner: str, package: str, version: str) -> dict: ...

    def add_channel(
        self,
        channel: str,
        owner: str,
        package: str | None = None,
        version: str | None = None,
        filename: str | None = None,
    ) -> None: ...


def _exact_file(api: AnacondaAPI, label: str, package: ExactPackage) -> dict | None:
    item = exact_distribution(api, package)
    return item if item is not None and label in item["labels"] else None


def _public_api() -> AnacondaAPI:
    """Discarding ambient credentials even when the client discovers a token."""

    return get_server_api(cls=lambda _token, **kwargs: Binstar(None, **kwargs))


def promote_exact_package(
    read_api: AnacondaAPI,
    *,
    write_api: AnacondaAPI | None = None,
    package: ExactPackage,
    source_label: str,
    target_label: str,
    expected_sha256: str,
) -> dict:
    """Adding a target label only after exact source and digest verification."""

    parse_exact_spec(package.full_name)
    if source_label == target_label:
        raise ValueError("source and target labels must differ")
    if not LABEL.fullmatch(source_label) or not LABEL.fullmatch(target_label):
        raise ValueError("source and target labels must use safe label names")
    if not SHA256.fullmatch(expected_sha256):
        raise ValueError(
            "expected SHA-256 must contain exactly 64 lowercase hex digits"
        )

    writer = write_api or read_api
    source = _exact_file(read_api, source_label, package)
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

    target = _exact_file(read_api, target_label, package)
    if target is None:
        writer.add_channel(
            target_label,
            package.owner,
            package=package.package,
            version=package.version,
            filename=package.basename,
        )
        target = _exact_file(read_api, target_label, package)
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
    read_api = _public_api()
    write_api = get_server_api(token, None)
    receipt = promote_exact_package(
        read_api,
        write_api=write_api,
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
