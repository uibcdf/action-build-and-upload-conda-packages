"""Execute the complete composite with an offline publisher and registry."""

import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
fixture_spec = importlib.util.spec_from_file_location(
    "upload_fixture", ROOT / "tests/fixtures/exact-upload/fixture.py"
)
fixture = importlib.util.module_from_spec(fixture_spec)
fixture_spec.loader.exec_module(fixture)


@unittest.skipIf(os.name == "nt", "POSIX publisher shell boundary")
class UploadCompositeTests(unittest.TestCase):
    def execute(self, directory, mode, *, shell=None):
        action = (ROOT / "upload/action.yml").read_text()
        shell = shell or re.search(r"^\s+shell: (.+)$", action, re.M).group(1)
        step = directory / "upload-step.sh"
        step.write_text(textwrap.dedent(action.split("      run: |\n", 1)[1]))
        publisher = directory / "publisher bin"
        environment = fixture.prepare(directory, publisher, mode)
        (publisher / "python").symlink_to(sys.executable)
        neutral = directory / "neutral-bin"
        neutral.mkdir()
        (neutral / "python").symlink_to(sys.executable)
        initializer = directory / "activate.sh"
        initializer.write_text(
            'if shopt -q login_shell; then export PATH="$PUBLISHER_BIN:$PATH"; fi\n'
        )
        environment.update(
            BASH_ENV=str(initializer),
            PUBLISHER_BIN=str(publisher),
            GITHUB_ACTION_PATH=str(ROOT / "upload"),
            RUNNER_TEMP=str(directory),
            GITHUB_OUTPUT=str(directory / "outputs"),
            PATH=str(neutral),
            PYTHONDONTWRITEBYTECODE="1",
        )
        arguments = shlex.split(shell)
        arguments[0] = "/bin/bash"
        if "{0}" in arguments:
            arguments[arguments.index("{0}")] = str(step)
        else:
            arguments.append(str(step))
        result = subprocess.run(
            arguments, cwd=ROOT, env=dict(os.environ, **environment),
            capture_output=True, text=True, check=False,
        )
        receipt = directory / "conda-upload-receipt.json"
        self.assertIn(f"receipt={receipt}", (directory / "outputs").read_text())
        self.assertNotIn(fixture.TOKEN, result.stdout + result.stderr)
        return result, receipt

    def test_complete_composite_selects_client_and_verifies_one_upload(self):
        with tempfile.TemporaryDirectory(prefix="upload fixture ") as temporary:
            directory = Path(temporary)
            result, receipt = self.execute(directory, "success")
            self.assertEqual(result.returncode, 0, result.stderr)
            fixture.verify(directory, receipt)
            self.assertEqual((directory / "reads").read_text().count("public-read"), 2)

    def test_uncertain_client_failure_retains_safe_receipt_and_never_retries(self):
        with tempfile.TemporaryDirectory(prefix="upload fixture ") as temporary:
            directory = Path(temporary)
            result, receipt = self.execute(directory, "write_failure")
            self.assertEqual(result.returncode, 1, result.stderr)
            fixture.verify(directory, receipt)
            self.assertEqual((directory / "reads").read_text().count("public-read"), 1)

    def test_previous_nonlogin_shell_loses_client_before_any_mutation(self):
        with tempfile.TemporaryDirectory(prefix="upload fixture ") as temporary:
            directory = Path(temporary)
            result, receipt = self.execute(
                directory, "success", shell="bash --noprofile --norc -e -o pipefail {0}"
            )
            self.assertEqual(result.returncode, 1, result.stderr)
            document = json.loads(receipt.read_text())
            self.assertEqual(document["state"], "unverified")
            self.assertEqual(document["error_type"], "FileNotFoundError")
            self.assertFalse((directory / "calls.jsonl").exists())
            self.assertFalse((directory / "registry.json").exists())
