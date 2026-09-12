import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/write_receptor_events.py"


class ProducerEventTests(unittest.TestCase):
    def test_writer_records_observed_files_platforms_digests_and_uploads(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            linux = root / "linux-64" / "example-1.0-py311_0.conda"
            mac = root / "osx-arm64" / "example-1.0-py312_0.conda"
            linux.parent.mkdir()
            mac.parent.mkdir()
            linux.write_bytes(b"linux")
            mac.write_bytes(b"mac")

            document = self._run(root, [mac, linux], [linux], upload=True)

            self.assertEqual(document["schema"], "gh-run-receptor.events@1")
            self.assertEqual(document["subject"]["run_attempt"], 2)
            self.assertEqual(document["subject"]["matrix_index"], 1)
            self.assertEqual(
                [(event["platform"], event["upload"]) for event in document["events"]],
                [("linux-64", "success"), ("osx-arm64", "failure")],
            )
            self.assertEqual(document["events"][0]["python_versions"], ["3.11"])
            self.assertEqual(
                document["events"][0]["sha256"], hashlib.sha256(b"linux").hexdigest()
            )

    def test_writer_marks_upload_as_not_requested_without_claiming_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "win-64" / "example-1.0-pyhd8ed1ab_0.conda"
            package.parent.mkdir()
            package.write_bytes(b"win")

            document = self._run(root, [package], [], upload=False)

            self.assertEqual(document["events"][0]["upload"], "not_requested")
            self.assertNotIn("python_versions", document["events"][0])

    def test_non_matrix_invocation_keeps_matrix_identity_unknown(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "linux-64" / "example-1.0-py311_0.conda"
            package.parent.mkdir()
            package.write_bytes(b"linux")

            result = self._invoke(root, [package], [], upload=False, matrix_index=None)

            self.assertEqual(result.returncode, 0, result.stderr)
            document = json.loads((root / "events.json").read_text(encoding="utf-8"))
            self.assertIsNone(document["subject"]["matrix_index"])

    def test_writer_rejects_missing_packages_and_unsafe_platforms(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            missing = root / "linux-64" / "missing.conda"
            result = self._invoke(root, [missing], [], upload=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("does not exist", result.stderr)

            unsafe = root / "NOT_A_PLATFORM" / "example.conda"
            unsafe.parent.mkdir()
            unsafe.write_bytes(b"unsafe")
            result = self._invoke(root, [unsafe], [], upload=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("safe Conda platform", result.stderr)

    def _invoke(self, root, built, uploaded, *, upload, matrix_index=1):
        output = root / "events.json"
        command = [
            sys.executable,
            str(SCRIPT),
            "--built-paths",
            " ".join(str(path) for path in built),
            "--uploaded-paths",
            " ".join(str(path) for path in uploaded),
            "--upload-requested",
            str(upload).lower(),
            "--producer-repository",
            "uibcdf/action-build-and-upload-conda-packages",
            "--producer-ref",
            "v2.1.0",
            "--repository",
            "uibcdf/example",
            "--run-id",
            "42",
            "--run-attempt",
            "2",
            "--head-sha",
            "abc",
            "--job-key",
            "conda",
            "--output",
            str(output),
        ]
        if matrix_index is not None:
            command[command.index("--output") : command.index("--output")] = [
                "--matrix-index",
                str(matrix_index),
            ]
        return subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True, check=False
        )

    def _run(self, root, built, uploaded, *, upload):
        result = self._invoke(root, built, uploaded, upload=upload)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads((root / "events.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
