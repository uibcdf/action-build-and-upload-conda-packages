"""Prepare and verify an exact-file withdrawal through the installed client's API."""

import argparse
import json
import os
import sys
from pathlib import Path

SPEC = "uibcdf/example/1.2.3/noarch/example-1.2.3-py_0.conda"


def prepare(root, mode):
    root.mkdir(parents=True, exist_ok=True)
    (root / "mode").write_text(mode)
    (root / "registry.json").write_text(
        json.dumps(
            {
                "distributions": [
                    {
                        "full_name": SPEC,
                        "basename": "noarch/" + SPEC.split("/")[-1],
                        "sha256": "a" * 64,
                        "labels": ["main", "staging"],
                    },
                    {
                        "full_name": SPEC.replace("py_0", "py_1"),
                        "sha256": "b" * 64,
                        "labels": ["main"],
                    },
                ]
            }
        )
    )
    return {
        "OFFLINE_LABEL_ROOT": str(root),
        "OFFLINE_LABEL_PREFIX": sys.prefix,
        "PYTHONPATH": str(Path(__file__).resolve().parent),
    }


def verify(root, receipt_path):
    mode = (root / "mode").read_text()
    receipt = json.loads(receipt_path.read_text())
    calls = [
        json.loads(line) for line in (root / "calls.jsonl").read_text().splitlines()
    ]
    registry = json.loads((root / "registry.json").read_text())
    assert receipt["schema"] == "uibcdf.conda-withdrawal@1"
    if mode == "success":
        assert receipt["status"] == "verified", receipt
        assert receipt["package"] == SPEC
        assert receipt["sha256"] == "a" * 64
        assert receipt["labels_before"] == ["main", "staging"]
        assert receipt["labels_after"] == ["staging", "withdrawn"]
        assert registry["distributions"][0]["labels"] == ["staging", "withdrawn"]
        assert [call["method"] for call in calls] == [
            "GET",
            "POST",
            "GET",
            "DELETE",
            "GET",
        ]
    else:
        assert receipt["status"] == "unverified", receipt
        assert registry["distributions"][0]["labels"] == ["main", "staging"]
        assert [call["method"] for call in calls] == ["GET", "POST", "GET"]
    assert registry["distributions"][1]["labels"] == ["main"]
    assert "offline-label-token" not in receipt_path.read_text() + json.dumps(calls)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["prepare", "verify"])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--mode", choices=["success", "archive_failure"], default="success"
    )
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    if args.operation == "prepare":
        environment = prepare(args.root, args.mode)
        with Path(os.environ["GITHUB_ENV"]).open("a") as stream:
            stream.writelines(f"{key}={value}\n" for key, value in environment.items())
    else:
        verify(args.root, args.receipt)
