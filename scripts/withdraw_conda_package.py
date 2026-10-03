"""Archive one digest-verified Conda file before removing its source label."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from binstar_client.errors import BinstarError
from binstar_client.utils import get_server_api

if __package__:
    from .conda_label_utils import (
        LABEL,
        SHA256,
        ExactPackage,
        exact_distribution,
        parse_exact_spec,
        public_api,
    )
else:
    from conda_label_utils import (
        LABEL,
        SHA256,
        ExactPackage,
        exact_distribution,
        parse_exact_spec,
        public_api,
    )


def _observed_file(read_api, package, digest):
    item = exact_distribution(read_api, package)
    if item is None:
        raise RuntimeError("exact package is absent from the public registry")
    if item.get("sha256") != digest:
        raise RuntimeError("public package digest differs from the expected SHA-256")
    return set(item["labels"])


def withdraw_exact_package(
    read_api,
    *,
    write_api,
    package: ExactPackage,
    source_label: str,
    archive_label: str,
    expected_sha256: str,
) -> dict:
    """Verify archive visibility before one exact removal, then verify every label."""
    # Validate even directly constructed dataclasses: missing coordinates broaden API writes.
    if parse_exact_spec(package.full_name) != package:
        raise ValueError("package coordinates must be canonical strings")
    if source_label == archive_label:
        raise ValueError("source and archive labels must differ")
    if not LABEL.fullmatch(source_label) or not LABEL.fullmatch(archive_label):
        raise ValueError("source and archive labels must use safe label names")
    if not SHA256.fullmatch(expected_sha256):
        raise ValueError("expected SHA-256 must contain 64 lowercase hex digits")

    before = _observed_file(read_api, package, expected_sha256)
    if source_label not in before and archive_label not in before:
        raise RuntimeError("exact package is absent from source and archive labels")
    expected = (before - {source_label}) | {archive_label}
    coordinates = {
        "package": package.package,
        "version": package.version,
        "filename": package.basename,
    }
    if source_label in before:
        if archive_label not in before:
            write_api.add_channel(archive_label, package.owner, **coordinates)
            archived = _observed_file(read_api, package, expected_sha256)
            if archived != before | {archive_label}:
                raise RuntimeError(
                    "archive poststate is unverified; source removal forbidden"
                )
        # The archive is now observed, not inferred from a successful write response.
        write_api.remove_channel(source_label, package.owner, **coordinates)
    after = _observed_file(read_api, package, expected_sha256)
    if after != expected:
        raise RuntimeError(
            "withdrawal poststate differs from the intended exact label set"
        )
    return {
        "schema": "uibcdf.conda-withdrawal@1",
        "package": package.full_name,
        "sha256": expected_sha256,
        "source_label": source_label,
        "archive_label": archive_label,
        "labels_before": sorted(before),
        "labels_after": sorted(after),
        "status": "verified",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-spec", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--from-label", default="main")
    parser.add_argument("--archive-label", default="withdrawn")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with Path(github_output).open("a", encoding="utf-8") as stream:
            stream.write(f"receipt={args.output}\n")
    try:
        package = parse_exact_spec(args.package_spec)
        token = os.environ.get("ANACONDA_API_TOKEN")
        if not token:
            raise ValueError("ANACONDA_API_TOKEN is required")
        receipt = withdraw_exact_package(
            public_api(),
            write_api=get_server_api(token, None),
            package=package,
            source_label=args.from_label,
            archive_label=args.archive_label,
            expected_sha256=args.expected_sha256,
        )
        status = 0
    except (OSError, ValueError, RuntimeError, BinstarError):
        receipt = {
            "schema": "uibcdf.conda-withdrawal@1",
            "status": "unverified",
            "instruction": "Inspect the exact public file and labels before any further mutation.",
        }
        status = 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if github_output and status == 0:
        with Path(github_output).open("a", encoding="utf-8") as stream:
            stream.write(f"package={receipt['package']}\n")
            stream.write(f"sha256={receipt['sha256']}\n")
    print(f"Exact-file withdrawal status: {receipt['status']}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
