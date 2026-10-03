"""Execute compilation when Conda activation retains a different base manager."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


class CompilationEnvironmentTests(unittest.TestCase):
    def _compile(
        self,
        root,
        *,
        shadow=True,
        mambabuild=False,
        fail_command="",
        host_format=".tar.bz2",
        convert=True,
    ):
        step = next(
            step
            for step in yaml.safe_load((ROOT / "action.yml").read_text())["runs"][
                "steps"
            ]
            if step.get("id") == "packages-compilation"
        )
        active = root / "active environment" / "bin"
        active.mkdir(parents=True)
        executable = active / "conda"
        executable.write_text(
            f"#!{sys.executable}\n"
            "import json, os, pathlib, sys\n"
            "args = sys.argv[1:]\n"
            "with open(os.environ['CALLS'], 'a') as stream:\n"
            "    stream.write(json.dumps(args) + '\\n')\n"
            "if args[0] == os.environ['FAIL_COMMAND']:\n"
            "    raise SystemExit(37)\n"
            "if args[0] in ('build', 'mambabuild'):\n"
            "    output = pathlib.Path(args[args.index('--output-folder') + 1]) / 'linux-64'\n"
            "else:\n"
            "    output = pathlib.Path(args[args.index('-o') + 1]) / 'osx-arm64'\n"
            "output.mkdir(parents=True, exist_ok=True)\n"
            "(output / ('example-1.0-py_0' + os.environ['HOST_FORMAT'])).write_bytes(b'artifact')\n"
        )
        executable.chmod(0o755)
        initializer = root / "initialize.sh"
        initializer.write_text(
            'export PATH="$ACTIVE_BIN:$PATH"\n'
            + (
                'conda() { echo "base manager cannot discover build plugins" >&2; return 2; }\n'
                if shadow
                else ""
            )
        )
        script = root / "compilation.sh"
        script.write_text(step["run"])
        output = root / "outputs.txt"
        calls = root / "calls.jsonl"
        env = dict(os.environ)
        env.update({key: "false" for key in step["env"]})
        env.update(
            BASH_ENV=str(initializer),
            ACTIVE_BIN=str(active),
            CALLS=str(calls),
            FAIL_COMMAND=fail_command,
            GITHUB_OUTPUT=str(output),
            MAMBABUILD=str(mambabuild).lower(),
            PLATFORM_HOST="true",
            PLATFORM_OSX_ARM64=str(convert).lower(),
            HOST_FORMAT=host_format,
            CONDA_BUILD_ARGS="--package-format 1",
            CONDA_CONVERT_ARGS="",
            TMPDIR=str(root),
        )
        result = subprocess.run(
            ["bash", "-l", str(script)],
            env=env,
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        invocations = (
            [json.loads(line) for line in calls.read_text().splitlines()]
            if calls.exists()
            else []
        )
        outputs = (
            dict(line.split("=", 1) for line in output.read_text().splitlines())
            if output.exists()
            else {}
        )
        return result, invocations, outputs

    def test_active_executable_builds_and_converts_despite_base_shell_function(self):
        for mambabuild in (False, True):
            with (
                self.subTest(mambabuild=mambabuild),
                tempfile.TemporaryDirectory() as temporary,
            ):
                result, calls, outputs = self._compile(
                    Path(temporary), mambabuild=mambabuild
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    [call[0] for call in calls],
                    ["mambabuild" if mambabuild else "build", "convert"],
                )
                self.assertIn("--no-anaconda-upload", calls[0])
                self.assertNotIn("--python", calls[0])
                paths = json.loads(outputs["built_paths_json"])
                self.assertEqual(len(paths), 2)
                self.assertEqual(
                    {Path(path).parent.name for path in paths},
                    {"linux-64", "osx-arm64"},
                )
                self.assertTrue(all(Path(path).is_file() for path in paths))

    def test_base_executable_without_shell_function_remains_supported(self):
        with tempfile.TemporaryDirectory() as temporary:
            result, calls, outputs = self._compile(Path(temporary), shadow=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(calls), 2)
            self.assertEqual(len(json.loads(outputs["built_paths_json"])), 2)

    def test_actual_build_failure_is_propagated_before_conversion(self):
        with tempfile.TemporaryDirectory() as temporary:
            result, calls, outputs = self._compile(
                Path(temporary), fail_command="build"
            )
            self.assertEqual(result.returncode, 37, result.stderr)
            self.assertEqual([call[0] for call in calls], ["build"])
            self.assertNotIn("built_paths_json", outputs)

    def test_actual_conversion_failure_is_propagated(self):
        with tempfile.TemporaryDirectory() as temporary:
            result, calls, outputs = self._compile(
                Path(temporary), fail_command="convert"
            )
            self.assertEqual(result.returncode, 37, result.stderr)
            self.assertEqual([call[0] for call in calls], ["build", "convert"])
            self.assertNotIn("built_paths_json", outputs)

    def test_modern_archive_conversion_fails_before_conversion_or_host_removal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result, calls, outputs = self._compile(root, host_format=".conda")
            self.assertEqual(result.returncode, 1)
            self.assertIn("--package-format 1", result.stdout)
            self.assertEqual([call[0] for call in calls], ["build"])
            self.assertNotIn("built_paths_json", outputs)
            self.assertEqual(len(list(root.rglob("*.conda"))), 1)

    def test_modern_host_archive_remains_available_without_conversion(self):
        with tempfile.TemporaryDirectory() as temporary:
            result, calls, outputs = self._compile(
                Path(temporary), host_format=".conda", convert=False
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([call[0] for call in calls], ["build"])
            paths = json.loads(outputs["built_paths_json"])
            self.assertEqual(len(paths), 1)
            self.assertTrue(Path(paths[0]).is_file())
            self.assertTrue(paths[0].endswith(".conda"))
