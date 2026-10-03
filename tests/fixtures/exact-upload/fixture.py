"""Prepare and verify an offline registry/client for the actual upload composite."""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

SPEC = "uibcdf/example/1.2.3/noarch/example-1.2.3-py_0.tar.bz2"
PAYLOAD = b"reviewed offline candidate bytes"
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()
TOKEN = "offline-test-token"


def prepare(root, client_bin, mode):
    root.mkdir(parents=True, exist_ok=True)
    client_bin.mkdir(parents=True, exist_ok=True)
    artifact = root / SPEC.split("/")[-1]
    artifact.write_bytes(PAYLOAD)
    (root / "mode").write_text(mode)
    client = client_bin / "anaconda"
    client.write_text(
        f"#!{sys.executable}\n"
        "import hashlib, json, os, sys\n"
        "from pathlib import Path\n"
        "root = Path(os.environ['OFFLINE_UPLOAD_ROOT'])\n"
        "args = sys.argv[1:]\n"
        "assert args[:5] == ['upload', '--user', 'uibcdf', '--label', 'staging']\n"
        "assert len(args) == 6\n"
        "artifact = Path(args[-1])\n"
        "assert artifact != Path(os.environ['ARTIFACT'])\n"
        "assert artifact.name == Path(os.environ['ARTIFACT']).name\n"
        "assert artifact.read_bytes() == Path(os.environ['ARTIFACT']).read_bytes()\n"
        "assert sys.prefix == os.environ['OFFLINE_UPLOAD_PREFIX']\n"
        "assert os.environ['ANACONDA_API_TOKEN'] == 'offline-test-token'\n"
        "with (root / 'calls.jsonl').open('a') as stream:\n"
        "    stream.write(json.dumps(args) + '\\n')\n"
        "if (root / 'mode').read_text() == 'write_failure':\n"
        "    print(os.environ['ANACONDA_API_TOKEN'], file=sys.stderr)\n"
        "    raise SystemExit(19)\n"
        "record = {'basename': 'noarch/' + artifact.name,\n"
        "          'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest(),\n"
        "          'labels': ['staging']}\n"
        "(root / 'registry.json').write_text(json.dumps({'distributions': [record]}))\n"
    )
    client.chmod(0o755)
    return {
        "ARTIFACT": str(artifact),
        "PACKAGE_SPEC": SPEC,
        "EXPECTED_SHA256": DIGEST,
        "CANDIDATE_SHA": "a" * 40,
        "LABEL": "staging",
        "ANACONDA_API_TOKEN": TOKEN,
        "OFFLINE_UPLOAD_ROOT": str(root),
        "OFFLINE_UPLOAD_PREFIX": sys.prefix,
        "PYTHONPATH": str(Path(__file__).resolve().parent),
    }


def verify(root, receipt_path):
    receipt = json.loads(receipt_path.read_text())
    mode = (root / "mode").read_text()
    calls = [json.loads(line) for line in (root / "calls.jsonl").read_text().splitlines()]
    assert len(calls) == 1, calls
    assert calls[0][:5] == ["upload", "--user", "uibcdf", "--label", "staging"]
    assert receipt["schema"] == "uibcdf.conda-upload@1"
    if mode == "success":
        assert receipt["state"] == "verified", receipt
        assert receipt["sha256"] == DIGEST
        assert receipt["candidate_sha"] == "a" * 40
        assert receipt["coordinate"]["filename"] == SPEC.split("/")[-1]
        assert receipt["preflight"] == {"state": "absent", "scope": "all-labels"}
        assert receipt["label"] == "staging"
    else:
        assert receipt["state"] == "unverified", receipt
        assert receipt["error_type"] == "RuntimeError", receipt
        assert not (root / "registry.json").exists()
    assert TOKEN not in receipt_path.read_text()
    assert TOKEN not in json.dumps(calls)
    assert (root / SPEC.split("/")[-1]).read_bytes() == PAYLOAD
    expected_reads = 2 if mode == "success" else 1
    assert (root / "reads").read_text().splitlines() == ["public-read"] * expected_reads


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["prepare", "verify"])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--client-bin", type=Path)
    parser.add_argument("--mode", choices=["success", "write_failure"], default="success")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    if args.operation == "prepare":
        environment = prepare(args.root, args.client_bin, args.mode)
        with Path(os.environ["GITHUB_ENV"]).open("a") as stream:
            for key, value in environment.items():
                stream.write(f"{key}={value}\n")
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as stream:
            stream.write(f"artifact={environment['ARTIFACT']}\n")
            stream.write(f"sha256={DIGEST}\n")
    else:
        verify(args.root, args.receipt)
