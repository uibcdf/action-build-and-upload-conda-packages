"""An artifact inspection must not be invalidated by a second build or upload."""

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.upload_conda_package import (
    parse_coordinate,
    upload_exact_package,
    upload_file,
)

SPEC = "uibcdf/example/1.2.3/noarch/example-1.2.3-py_0.tar.bz2"
SHA = "a" * 40


class ExactUploadTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / SPEC.split("/")[-1]
        self.path.write_bytes(b"validated artifact bytes")
        self.digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.record = {
            "basename": "noarch/" + self.path.name,
            "sha256": self.digest,
            "labels": ["staging"],
        }

    def run_upload(self, reader, uploader):
        return upload_exact_package(
            self.path,
            SPEC,
            self.digest,
            "staging",
            SHA,
            reader=reader,
            uploader=uploader,
        )

    def test_uploads_the_sealed_validated_bytes_once_and_retains_identity(self):
        reads = iter([None, {"distributions": [self.record]}])
        writes = []

        def uploader(path, coordinate, label):
            self.path.write_bytes(b"changed after validation")
            writes.append((path.read_bytes(), coordinate, label))
            self.assertNotEqual(path, self.path)

        receipt = self.run_upload(lambda _: next(reads), uploader)
        self.assertEqual(writes[0][0], b"validated artifact bytes")
        self.assertEqual(len(writes), 1)
        self.assertEqual(receipt["candidate_sha"], SHA)
        self.assertEqual(receipt["sha256"], self.digest)
        self.assertEqual(receipt["state"], "verified")

    def test_occupied_coordinate_under_any_label_blocks_even_identical_bytes(self):
        for labels in (["main"], ["old"], ["staging"]):
            record = dict(self.record, labels=labels)
            with patch("scripts.upload_conda_package.upload_file") as unused:
                with self.assertRaisesRegex(RuntimeError, "occupied"):
                    self.run_upload(
                        lambda _, value=record: {"distributions": [value]}, unused
                    )
                unused.assert_not_called()

    def test_changed_bytes_and_bad_identity_fail_before_network_or_upload(self):
        self.path.write_bytes(b"other bytes")
        with (
            patch("scripts.upload_conda_package.read_release") as reader,
            patch("scripts.upload_conda_package.upload_file") as writer,
        ):
            with self.assertRaisesRegex(ValueError, "digest"):
                self.run_upload(reader, writer)
            reader.assert_not_called()
            writer.assert_not_called()
        for spec in (
            "uibcdf/example/1.2.3",
            SPEC.replace("noarch", ".."),
            SPEC.replace("example-1.2.3", "other-1.2.3"),
            SPEC + ";command",
        ):
            with self.assertRaises(ValueError):
                parse_coordinate(spec)

    def test_unavailable_or_malformed_preflight_never_mutates(self):
        for document in (
            {},
            {"distributions": None},
            {"distributions": ["bad"]},
            {"distributions": [self.record, self.record]},
        ):
            with patch("scripts.upload_conda_package.upload_file") as writer:
                with self.assertRaises(RuntimeError):
                    self.run_upload(lambda _, value=document: value, writer)
                writer.assert_not_called()

    def test_missing_changed_or_unlabeled_poststate_never_retries_upload(self):
        for document in (
            None,
            {"distributions": []},
            {"distributions": [dict(self.record, sha256="b" * 64)]},
            {"distributions": [dict(self.record, labels=["other"])]},
            {"distributions": [dict(self.record, labels=1)]},
        ):
            reads = iter([None, document])
            with patch("scripts.upload_conda_package.upload_file") as writer:
                with self.assertRaisesRegex(RuntimeError, "poststate"):
                    self.run_upload(lambda _, values=reads: next(values), writer)
                self.assertEqual(writer.call_count, 1)

    def test_uncertain_write_never_retries_or_queries_as_if_successful(self):
        with (
            patch(
                "scripts.upload_conda_package.read_release", return_value=None
            ) as reader,
            patch(
                "scripts.upload_conda_package.upload_file",
                side_effect=RuntimeError("uncertain"),
            ) as writer,
        ):
            with self.assertRaises(RuntimeError):
                self.run_upload(reader, writer)
            self.assertEqual(writer.call_count, 1)
            self.assertEqual(reader.call_count, 1)

    def test_write_client_never_puts_the_token_or_force_in_arguments(self):
        with (
            patch.dict(os.environ, {"ANACONDA_API_TOKEN": "private-test-token"}),
            patch("scripts.upload_conda_package.subprocess.run") as command,
        ):
            command.return_value.returncode = 0
            upload_file(self.path, parse_coordinate(SPEC), "staging")
        arguments = command.call_args.args[0]
        self.assertNotIn("private-test-token", " ".join(arguments))
        self.assertNotIn("--force", arguments)
        self.assertEqual(arguments[:2], ["anaconda", "upload"])

    @unittest.skipIf(os.name == "nt", "POSIX publisher shell reproduction")
    def test_composite_activates_the_publisher_client_before_upload(self):
        root = Path(__file__).resolve().parents[1]
        shell = re.search(
            r"^\s+shell: (.+)$", (root / "upload/action.yml").read_text(), re.M
        ).group(1)
        directory = Path(self.directory.name)
        publisher = directory / "publisher-bin"
        publisher.mkdir()
        marker = directory / "upload-called"
        client = publisher / "anaconda"
        client.write_text('#!/bin/sh\n: > "$UPLOAD_MARKER"\n')
        client.chmod(0o755)
        profile = directory / "activate-publisher.sh"
        profile.write_text(
            'if shopt -q login_shell; then\n'
            '  export PATH="$PUBLISHER_BIN:$PATH"\n'
            'fi\n'
        )
        driver = directory / "upload-step.sh"
        driver.write_text(
            '"$TEST_PYTHON" - <<\'PY\'\n'
            'from pathlib import Path\n'
            'from scripts.upload_conda_package import upload_file, parse_coordinate\n'
            f'upload_file(Path({str(self.path)!r}), parse_coordinate({SPEC!r}), "staging")\n'
            'PY\n'
        )
        environment = dict(
            os.environ,
            BASH_ENV=str(profile),
            PUBLISHER_BIN=str(publisher),
            UPLOAD_MARKER=str(marker),
            TEST_PYTHON=sys.executable,
            ANACONDA_API_TOKEN="offline-test-token",
            # The non-login step cannot find an ambient real write client.
            PATH=str(directory / "empty-bin"),
        )
        arguments = shlex.split(shell)
        arguments[0] = "/bin/bash"
        if "{0}" in arguments:
            arguments[arguments.index("{0}")] = str(driver)
        else:
            arguments.append(str(driver))
        result = subprocess.run(
            arguments, cwd=root, env=environment, capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(marker.is_file())

    def test_failed_cli_retains_a_receipt_without_exposing_exception_details(self):
        from scripts.upload_conda_package import main

        receipt = Path(self.directory.name) / "receipt.json"
        outputs = Path(self.directory.name) / "outputs"
        args = [
            "upload",
            "--artifact",
            str(self.path),
            "--package-spec",
            SPEC,
            "--expected-sha256",
            self.digest,
            "--label",
            "staging",
            "--candidate-sha",
            SHA,
            "--output",
            str(receipt),
        ]
        with (
            patch("sys.argv", args),
            patch.dict(os.environ, {"GITHUB_OUTPUT": str(outputs)}),
            patch(
                "scripts.upload_conda_package.upload_exact_package",
                side_effect=RuntimeError("private-test-token"),
            ),
        ):
            self.assertEqual(main(), 1)
        self.assertIn("unverified", receipt.read_text())
        self.assertEqual(json.loads(receipt.read_text())["error_type"], "RuntimeError")
        self.assertNotIn("private-test-token", receipt.read_text())
        self.assertIn("receipt=", outputs.read_text())


if __name__ == "__main__":
    unittest.main()
