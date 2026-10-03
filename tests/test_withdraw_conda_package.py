"""Withdrawal never broadens a mutation or removes a label before proven archival."""

import copy
import io
import json
import os
import re
import runpy
import shlex
import subprocess
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts.conda_label_utils import ExactPackage, parse_exact_spec, public_api
from scripts.withdraw_conda_package import main, withdraw_exact_package

SPEC = "uibcdf/example/1.2.3/noarch/example-1.2.3-py_0.conda"
DIGEST = "a" * 64


class Registry:
    def __init__(self, labels=None):
        self.record = {
            "full_name": SPEC,
            "sha256": DIGEST,
            "labels": labels or ["main", "staging"],
        }
        self.other = {
            "full_name": SPEC.replace("py_0", "py_1"),
            "sha256": "b" * 64,
            "labels": ["main"],
        }
        self.calls = []
        self.no_effect = ""
        self.fail_after = ""

    def release(self, owner, package, version):
        self.calls.append(("read", owner, package, version))
        return {"distributions": copy.deepcopy([self.record, self.other])}

    def mutate(self, operation, label, owner, *, package, version, filename):
        assert f"{owner}/{package}/{version}/{filename}" == SPEC
        self.calls.append((operation, label, owner, package, version, filename))
        if operation != self.no_effect:
            if operation == "add":
                self.record["labels"].append(label)
            else:
                self.record["labels"].remove(label)
        if operation == self.fail_after:
            raise RuntimeError("uncertain private-test-token")

    def add_channel(self, *args, **kwargs):
        self.mutate("add", *args, **kwargs)

    def remove_channel(self, *args, **kwargs):
        self.mutate("remove", *args, **kwargs)

    @property
    def writes(self):
        return [call for call in self.calls if call[0] != "read"]


class WithdrawalTests(unittest.TestCase):
    def run_withdrawal(self, registry, **kwargs):
        arguments = {
            "write_api": registry,
            "package": parse_exact_spec(SPEC),
            "source_label": "main",
            "archive_label": "withdrawn",
            "expected_sha256": DIGEST,
        }
        arguments.update(kwargs)
        return withdraw_exact_package(registry, **arguments)

    def test_archives_observes_removes_and_verifies_one_file_preserving_other_labels(
        self,
    ):
        registry = Registry()
        receipt = self.run_withdrawal(registry)
        self.assertEqual(
            [call[0] for call in registry.calls],
            ["read", "add", "read", "remove", "read"],
        )
        self.assertEqual(receipt["schema"], "uibcdf.conda-withdrawal@1")
        self.assertEqual(receipt["status"], "verified")
        self.assertEqual(receipt["package"], SPEC)
        self.assertEqual(receipt["sha256"], DIGEST)
        self.assertEqual(receipt["labels_before"], ["main", "staging"])
        self.assertEqual(receipt["labels_after"], ["staging", "withdrawn"])
        self.assertEqual(registry.other["labels"], ["main"])
        self.assertEqual(
            registry.writes,
            [
                (
                    "add",
                    "withdrawn",
                    "uibcdf",
                    "example",
                    "1.2.3",
                    "noarch/example-1.2.3-py_0.conda",
                ),
                (
                    "remove",
                    "main",
                    "uibcdf",
                    "example",
                    "1.2.3",
                    "noarch/example-1.2.3-py_0.conda",
                ),
            ],
        )

    def test_existing_archive_does_not_get_added_again(self):
        registry = Registry(["main", "withdrawn"])
        self.run_withdrawal(registry)
        self.assertEqual([call[0] for call in registry.writes], ["remove"])

    def test_already_withdrawn_exact_file_is_verified_without_writes(self):
        registry = Registry(["withdrawn", "staging"])
        receipt = self.run_withdrawal(registry)
        self.assertEqual(receipt["labels_after"], ["staging", "withdrawn"])
        self.assertEqual(registry.writes, [])

    def test_custom_labels_preserve_other_routes(self):
        registry = Registry(["testing", "main"])
        receipt = self.run_withdrawal(
            registry, source_label="testing", archive_label="archived"
        )
        self.assertEqual(receipt["labels_after"], ["archived", "main"])

    def test_invalid_coordinates_digest_or_labels_never_read_or_mutate(self):
        for arguments in (
            {
                "package": ExactPackage(
                    "uibcdf", "", "1.2.3", "noarch/example-1.2.3-py_0.conda"
                )
            },
            {"expected_sha256": "A" * 64},
            {"source_label": "main;command"},
            {"archive_label": "main"},
        ):
            with self.subTest(arguments=arguments):
                registry = Registry()
                with self.assertRaises(ValueError):
                    self.run_withdrawal(registry, **arguments)
                self.assertEqual(registry.calls, [])
        for spec in (
            "uibcdf/example/1.2.3",
            SPEC.replace("noarch", ".."),
            SPEC + ";command",
            SPEC.replace("example-1.2.3", "other-1.2.3"),
        ):
            with self.assertRaises(ValueError):
                parse_exact_spec(spec)

    def test_missing_or_mismatching_source_never_mutates(self):
        for update in (
            {"full_name": "other/package/1.0/noarch/package-1.0-py_0.conda"},
            {"sha256": "c" * 64},
            {"labels": ["staging"]},
        ):
            registry = Registry()
            registry.record.update(update)
            with self.assertRaises(RuntimeError):
                self.run_withdrawal(registry)
            self.assertEqual(registry.writes, [])

    def test_malformed_duplicate_and_contradictory_public_evidence_never_mutates(self):
        record = Registry().record
        for document in (
            {},
            {"distributions": None},
            {"distributions": ["bad"]},
            {"distributions": [record, record]},
            {"distributions": [dict(record, labels=["main", "main"])]},
            {"distributions": [dict(record, labels="main")]},
            {"distributions": [dict(record, basename="noarch/other.conda")]},
        ):
            with self.subTest(document=document):
                registry = Registry()
                with (
                    patch.object(registry, "release", return_value=document),
                    self.assertRaises(RuntimeError),
                ):
                    self.run_withdrawal(registry)
                self.assertEqual(registry.writes, [])

    def test_unobserved_archive_forbids_source_removal(self):
        registry = Registry()
        registry.no_effect = "add"
        with self.assertRaisesRegex(RuntimeError, "archive poststate"):
            self.run_withdrawal(registry)
        self.assertEqual([call[0] for call in registry.writes], ["add"])
        self.assertIn("main", registry.record["labels"])

    def test_failed_removal_is_not_retried(self):
        registry = Registry()
        registry.no_effect = "remove"
        with self.assertRaisesRegex(RuntimeError, "withdrawal poststate"):
            self.run_withdrawal(registry)
        self.assertEqual([call[0] for call in registry.writes], ["add", "remove"])

    def test_digest_changes_at_archive_or_final_observation_fail(self):
        for stage in (2, 3):
            registry = Registry()
            release = registry.release
            count = 0

            def read(*args, release=release, stage=stage):
                nonlocal count
                count += 1
                result = release(*args)
                if count == stage:
                    result["distributions"][0]["sha256"] = "c" * 64
                return result

            with (
                patch.object(registry, "release", side_effect=read),
                self.assertRaisesRegex(RuntimeError, "digest"),
            ):
                self.run_withdrawal(registry)
            expected = ["add"] if stage == 2 else ["add", "remove"]
            self.assertEqual([call[0] for call in registry.writes], expected)

    def test_uncertain_mutation_never_retries_or_performs_the_next_mutation(self):
        for operation in ("add", "remove"):
            registry = Registry()
            registry.fail_after = operation
            with self.assertRaisesRegex(RuntimeError, "uncertain"):
                self.run_withdrawal(registry)
            expected = ["add"] if operation == "add" else ["add", "remove"]
            self.assertEqual([call[0] for call in registry.writes], expected)
            self.assertEqual(registry.calls[-1][0], operation)

    def test_write_client_is_never_used_for_reads(self):
        registry = Registry()

        class Writer:
            def release(self, *args):
                raise AssertionError("authenticated read forbidden")

            add_channel = registry.add_channel
            remove_channel = registry.remove_channel

        self.run_withdrawal(registry, write_api=Writer())

    def test_public_client_discards_ambient_credentials(self):
        with patch(
            "scripts.conda_label_utils.get_server_api",
            side_effect=lambda *, cls: cls(
                "private-test-token", domain="https://api.anaconda.org"
            ),
        ):
            client = public_api()
        self.assertIsNone(client.token)
        self.assertNotIn("Authorization", client.session.headers)

    def test_cli_failure_retains_receipt_without_raw_exception_or_success_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "receipt.json"
            github_output = root / "outputs"
            args = [
                "withdraw",
                "--package-spec",
                SPEC,
                "--expected-sha256",
                DIGEST,
                "--output",
                str(output),
            ]
            captured = io.StringIO()
            with (
                patch("sys.argv", args),
                patch.dict(
                    os.environ,
                    ANACONDA_API_TOKEN="private-test-token",
                    GITHUB_OUTPUT=str(github_output),
                ),
                patch(
                    "scripts.withdraw_conda_package.public_api", return_value=Registry()
                ),
                patch(
                    "scripts.withdraw_conda_package.get_server_api",
                    return_value=Registry(),
                ),
                patch(
                    "scripts.withdraw_conda_package.withdraw_exact_package",
                    side_effect=RuntimeError("private-test-token"),
                ),
                redirect_stdout(captured),
            ):
                self.assertEqual(main(), 1)
            self.assertEqual(json.loads(output.read_text())["status"], "unverified")
            self.assertEqual(github_output.read_text(), f"receipt={output}\n")
            self.assertNotIn(
                "private-test-token", output.read_text() + captured.getvalue()
            )

    def test_script_is_independently_callable(self):
        script = (
            Path(__file__).resolve().parents[1] / "scripts/withdraw_conda_package.py"
        )
        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--package-spec", result.stdout)

    @unittest.skipIf(
        os.name == "nt",
        "POSIX complete-composite shell; hosted Windows uses the actual action",
    )
    def test_complete_composite_uses_installed_client_and_retains_failure_evidence(
        self,
    ):
        root = Path(__file__).resolve().parents[1]
        fixture = runpy.run_path(
            str(root / "tests/fixtures/label-operations/fixture.py")
        )
        action = (root / "withdraw/action.yml").read_text()
        for mode in ("success", "archive_failure"):
            with (
                self.subTest(mode=mode),
                tempfile.TemporaryDirectory(prefix="withdraw fixture ") as temporary,
            ):
                directory = Path(temporary)
                environment = fixture["prepare"](directory, mode)
                publisher = directory / "publisher bin"
                publisher.mkdir()
                (publisher / "python").symlink_to(sys.executable)
                initializer = directory / "activate.sh"
                initializer.write_text('export PATH="$PUBLISHER_BIN:$PATH"\n')
                script = directory / "withdraw.sh"
                script.write_text(textwrap.dedent(action.split("      run: |\n", 1)[1]))
                environment.update(
                    PACKAGE_SPEC=SPEC,
                    EXPECTED_SHA256=DIGEST,
                    FROM_LABEL="main",
                    ARCHIVE_LABEL="withdrawn",
                    ANACONDA_API_TOKEN="offline-label-token",
                    GITHUB_ACTION_PATH=str(root / "withdraw"),
                    GITHUB_OUTPUT=str(directory / "outputs"),
                    RUNNER_TEMP=str(directory),
                    BASH_ENV=str(initializer),
                    PUBLISHER_BIN=str(publisher),
                    PYTHONDONTWRITEBYTECODE="1",
                )
                shell = re.search(r"^\s+shell: (.+)$", action, re.MULTILINE).group(1)
                arguments = shlex.split(shell)
                arguments[arguments.index("{0}")] = str(script)
                result = subprocess.run(
                    arguments,
                    env=dict(os.environ, **environment),
                    cwd=root,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(
                    result.returncode, 0 if mode == "success" else 1, result.stderr
                )
                receipt = directory / "conda-withdrawal-receipt.json"
                fixture["verify"](directory, receipt)
                outputs = (directory / "outputs").read_text()
                self.assertIn(f"receipt={receipt}", outputs)
                self.assertNotIn(
                    "offline-label-token", result.stdout + result.stderr + outputs
                )
                if mode == "success":
                    self.assertIn(f"package={SPEC}", outputs)
                    self.assertIn(f"sha256={DIGEST}", outputs)
                else:
                    self.assertEqual(outputs, f"receipt={receipt}\n")
