"""Writing bounded gh-run-receptor events from packages produced by this Action."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
from pathlib import Path

_PLATFORM = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+){0,3}")
_PYTHON_BUILD = re.compile(r"(?:^|[-_.])py(3[0-9]{1,2})(?:[-_.])")


def _python_versions(filename: str) -> list[str]:
    match = _PYTHON_BUILD.search(filename)
    if match is None:
        return []
    digits = match.group(1)
    return [f"{digits[0]}.{int(digits[1:])}"]


def _paths(value: str) -> list[Path]:
    return [Path(item).resolve() for item in shlex.split(value)]


def build_document(
    *,
    built_paths: str,
    uploaded_paths: str,
    upload_requested: bool,
    producer_repository: str,
    producer_ref: str,
    repository: str,
    run_id: int,
    run_attempt: int,
    head_sha: str,
    job_key: str,
    matrix_index: int | None,
) -> dict:
    """Building one deterministic event document from observed package files."""
    built = _paths(built_paths)
    uploaded = set(_paths(uploaded_paths))
    if not built:
        raise ValueError("no built package paths were supplied")
    events = []
    seen = set()
    for package in sorted(built, key=lambda item: (item.parent.name, item.name)):
        if not package.is_file():
            raise ValueError(f"built package does not exist: {package}")
        platform = package.parent.name
        if _PLATFORM.fullmatch(platform) is None:
            raise ValueError(f"cannot derive a safe Conda platform from: {package}")
        digest = hashlib.sha256(package.read_bytes()).hexdigest()
        identity = (platform, package.name, digest)
        if identity in seen:
            raise ValueError(f"duplicate built package identity: {package.name}")
        seen.add(identity)
        event = {
            "kind": "conda.package",
            "platform": platform,
            "artifact": package.name,
            "sha256": digest,
            "build": "success",
            "upload": (
                "success"
                if package in uploaded
                else "failure"
                if upload_requested
                else "not_requested"
            ),
        }
        if versions := _python_versions(package.name):
            event["python_versions"] = versions
        events.append(event)
    return {
        "schema": "gh-run-receptor.events@1",
        "producer": {"repository": producer_repository, "ref": producer_ref},
        "subject": {
            "repository": repository,
            "run_id": run_id,
            "run_attempt": run_attempt,
            "head_sha": head_sha,
            "job_key": job_key,
            "matrix_index": matrix_index,
        },
        "events": events,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--built-paths", required=True)
    parser.add_argument("--uploaded-paths", default="")
    parser.add_argument("--upload-requested", choices=("true", "false"), required=True)
    parser.add_argument("--producer-repository", required=True)
    parser.add_argument("--producer-ref", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--job-key", required=True)
    parser.add_argument("--matrix-index", type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document = build_document(
        built_paths=args.built_paths,
        uploaded_paths=args.uploaded_paths,
        upload_requested=args.upload_requested == "true",
        producer_repository=args.producer_repository,
        producer_ref=args.producer_ref,
        repository=args.repository,
        run_id=args.run_id,
        run_attempt=args.run_attempt,
        head_sha=args.head_sha,
        job_key=args.job_key,
        matrix_index=args.matrix_index,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
