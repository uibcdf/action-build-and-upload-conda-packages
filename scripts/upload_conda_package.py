"""Upload one already validated Conda file once, preserving its exact bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import urlopen


def parse_coordinate(value: str) -> dict:
    """Accept one exact identity, without paths, selectors or shell arguments."""
    parts = value.split("/")
    if len(parts) != 5 or any(
        not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+-]*", part) or part in {".", ".."}
        for part in parts
    ):
        raise ValueError(
            "package spec must be an exact safe owner/package/version/subdir/filename"
        )
    owner, package, version, subdir, filename = parts
    if not filename.startswith(f"{package}-{version}-") or not filename.endswith(
        (".conda", ".tar.bz2")
    ):
        raise ValueError("filename does not match the requested package/version")
    return {
        "owner": owner,
        "package": package,
        "version": version,
        "subdir": subdir,
        "filename": filename,
    }


def read_release(coordinate: dict) -> dict | None:
    """Read public registry metadata without discovering an ambient credential."""
    segments = [coordinate[key] for key in ("owner", "package", "version")]
    url = "https://api.anaconda.org/release/" + "/".join(
        quote(value, safe="") for value in segments
    )
    try:
        with urlopen(url, timeout=20) as response:
            payload = response.read(16 * 1024 * 1024 + 1)
    except HTTPError as error:
        if error.code == 404:
            return None
        raise RuntimeError(f"public registry read failed: HTTP {error.code}") from None
    if len(payload) > 16 * 1024 * 1024:
        raise RuntimeError("public registry response exceeds its bound")
    return json.loads(payload)


def exact_file(document: dict | None, coordinate: dict) -> dict | None:
    """Find the coordinate across every label; malformed evidence fails closed."""
    if document is None:
        return None
    entries = document.get("distributions") if isinstance(document, dict) else None
    if not isinstance(entries, list) or any(
        not isinstance(entry, dict) for entry in entries
    ):
        raise RuntimeError("public distribution inventory is incomplete")
    basename = f"{coordinate['subdir']}/{coordinate['filename']}"
    full_name = f"{coordinate['owner']}/{coordinate['package']}/{coordinate['version']}/{basename}"
    matches = [
        entry
        for entry in entries
        if entry.get("basename") == basename or entry.get("full_name") == full_name
    ]
    if len(matches) > 1:
        raise RuntimeError("public coordinate identity is duplicated")
    return matches[0] if matches else None


def upload_file(path: Path, coordinate: dict, label: str) -> None:
    """Run the installed client once; token stays in environment, never argv."""
    if not os.environ.get("ANACONDA_API_TOKEN"):
        raise RuntimeError("ANACONDA_API_TOKEN is required")
    result = subprocess.run(
        [
            "anaconda",
            "upload",
            "--user",
            coordinate["owner"],
            "--label",
            label,
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if result.returncode != 0:
        # The CLI may include credentials in an error. Preserve only its status.
        raise RuntimeError(
            f"upload client exited {result.returncode}; inspect public state before any new mutation"
        )


def upload_exact_package(
    path: Path,
    package_spec: str,
    expected_sha256: str,
    label: str,
    candidate_sha: str,
    *,
    reader=read_release,
    uploader=upload_file,
) -> dict:
    """Seal validated bytes, reject occupied coordinates and observe upload poststate."""
    coordinate = parse_coordinate(package_spec)
    if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256) or not re.fullmatch(
        r"[a-f0-9]{40}", candidate_sha
    ):
        raise ValueError("exact digest and immutable candidate SHA are required")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", label):
        raise ValueError("target label is not canonical")
    if path.name != coordinate["filename"] or not path.is_file():
        raise ValueError("artifact path differs from the exact coordinate")
    with tempfile.TemporaryDirectory(prefix="conda-exact-upload-") as directory:
        sealed = Path(directory) / path.name
        shutil.copyfile(path, sealed)
        with sealed.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != expected_sha256:
            raise ValueError("local artifact digest differs from the validated bytes")
        sealed.chmod(0o400)
        if exact_file(reader(coordinate), coordinate) is not None:
            raise RuntimeError(
                "immutable coordinate is occupied under some label; upload forbidden"
            )
        uploader(sealed, coordinate, label)
        poststate = exact_file(reader(coordinate), coordinate)
        labels = poststate.get("labels") if poststate is not None else None
        if (
            poststate is None
            or poststate.get("sha256") != digest
            or not isinstance(labels, list)
            or any(not isinstance(value, str) for value in labels)
            or label not in labels
        ):
            raise RuntimeError(
                "upload poststate is unverified; inspect public state without repeating the upload"
            )
    return {
        "schema": "uibcdf.conda-upload@1",
        "state": "verified",
        "coordinate": coordinate,
        "candidate_sha": candidate_sha,
        "sha256": digest,
        "label": label,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "preflight": {"state": "absent", "scope": "all-labels"},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--package-spec", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # Expose the receipt location before a possible failure so always() can retain it.
    if github_output := os.environ.get("GITHUB_OUTPUT"):
        with Path(github_output).open("a") as stream:
            stream.write(f"receipt={args.output}\n")
    try:
        receipt = upload_exact_package(
            args.artifact,
            args.package_spec,
            args.expected_sha256,
            args.label,
            args.candidate_sha,
        )
        status = 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        receipt = {
            "schema": "uibcdf.conda-upload@1",
            "state": "unverified",
            "instruction": "Inspect the exact public coordinate before any further mutation.",
        }
        status = 1
    receipt["subject"] = {
        "repository": os.environ.get("GITHUB_REPOSITORY"),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"Exact-file upload state: {receipt['state']}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
