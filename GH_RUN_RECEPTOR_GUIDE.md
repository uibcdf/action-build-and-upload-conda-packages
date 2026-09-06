# gh-run-receptor Guide (Canonical)

Source of truth for adopting **gh-run-receptor** in a client repository.

Metadata

- Source repository: `gh-run-receptor`
- Source document: `standards/GH_RUN_RECEPTOR_GUIDE.md`
- Source version: `gh-run-receptor@0.15.0`
- Last synced: 2026-09-06

## What gh-run-receptor is

gh-run-receptor is a read-only evidence receptor for GitHub Actions. It obtains structured
run evidence through the authenticated GitHub CLI, preserves GitHub's authoritative status
and conclusion, and renders a bounded report for either a human or an LLM.

It complements GitHub's native commands. It does not rerun, cancel, approve, upload,
publish, or deploy anything.

## Why a client repository adopts it

- Reduce repeated workflow output before passing it to a human or language model.
- Preserve run, attempt, job, platform, artifact, and evidence-completeness identity.
- Capture evidence once and replay it without another API request.
- Distinguish official GitHub state from profile interpretation such as `PARTIAL`.
- Retain a clear fallback to native GitHub inspection whenever evidence is incomplete or a
  workflow shape is unknown.

Measured MolSysMT examples reduced a competent diagnostic baseline from 5,138 to 296
`cl100k_base` tokens for a partial Conda failure, and a matrix-verification baseline from
143 to 39 tokens for a successful run. These are case measurements, not a universal rate.
For a status-only green query, native GitHub JSON was smaller and remains preferable.
A failing seven-job MolSysViewer CI case reduced an already filtered native result from
223 to 198 tokens (11.2%) while adding roles and replay identity; the ungrouped draft was
larger than native output and was rejected.
A successful MolSysViewer noarch Conda case reduced an equivalent run/jobs plus artifact
inventory baseline from 101 to 45 tokens (55.4%).
A failing MolSysViewer notebook case reduced a competent filtered baseline from 136 to
113 tokens (16.9%); a successful MolSysMT Sphinx/Pages case fell from 254 to 48 (81.1%).
A failing MolSysViewer npm release case fell from 103 to 93 tokens (9.7%), and a
successful npm release case from 95 to 84 tokens (11.6%).

## Supported integration level

Version `0.15.0` is a source preview with:

- `inspect`, `capture`, offline `replay`, and transition-only `watch`;
- `human`, `llm`, and JSON rendering;
- generic, initial CI, documentation, Conda, and release profiles;
- strict `bundle@1`, `model@1`, and `report@1` boundaries;
- dependency-free runtime on Python 3.11 through 3.13;
- installation as a GitHub CLI script extension;
- trusted default-branch repository configuration with exact workflow matching;
- offline `config check` and `config explain` commands;
- bounded local workflow discovery and non-overwriting `init` configuration generation;
- required-platform enforcement for the Conda profile.
- attempt-consistent historical capture and fail-closed bundle identity validation;
- real-fixture coverage of cancellation, expired logs, and failed/successful reruns.
- structured, bounded, and redacted GitHub acquisition-error categories.
- Python console-command, test, build, wheel-installation, and smoke-test validation on
  Ubuntu, macOS, and Windows with Python 3.11, 3.12, and 3.13.
- a composite GitHub Action with bounded log, job summary, scalar outputs, canonical JSON
  artifact, and exact source provenance;
- checkout-local and remote-source Action validation on Ubuntu, macOS, and Windows.
- bounded published-report consumption with fresh terminal source-fact verification and
  no source job or log download.
- explicit `source_facts=verified` and `interpretation=published_not_recomputed` fields in
  successful compact published-report output.
- deterministic attempt-qualified Action artifacts and fail-closed source-to-reporter
  discovery through the exact canonical reporter workflow.
- trusted inline Action `config@1` rules using the same parser and interpretation path as
  repository policy, with default-branch caller provenance;
- `report-ready` and `error-category` outputs for bounded fail-open automation;
- hosted public-permission, same-repository pull-request rejection, and canonical inline
  `workflow_run` validation.

Configurable required jobs, documentation phases, or release gates; pattern matching;
arbitrary rule keys; remote workflow discovery; and external registry/archive verification
are not implemented in `0.15.0`. Private-repository and fork token behavior remains
unclaimed. Cross-platform validation covers installation as a
GitHub CLI script extension and the composite Action on hosted runners.

## Installation

The client requires Git, Python 3.11 through 3.13, and an authenticated GitHub CLI.
Install the exact preview tag:

```text
gh extension install uibcdf/gh-run-receptor --pin 0.15.0
gh run-receptor --version
```

Expected version output:

```text
0.15.0
```

Pinning is deliberate. A pinned script extension does not advance through an ordinary
upgrade. To change tags, remove and reinstall it explicitly:

```text
gh extension remove gh-run-receptor
gh extension install uibcdf/gh-run-receptor --pin NEW_VERSION
```

For development from a local checkout:

```text
gh extension install .
gh run-receptor --help
```

## Embedded Action

Use a downstream `workflow_run` workflow when a terminal source-run conclusion is needed:

```yaml
name: Compact CI report

on:
  workflow_run:
    workflows: [CI]
    types: [completed]

permissions:
  actions: read
  contents: read

jobs:
  report:
    runs-on: ubuntu-latest
    steps:
      - uses: uibcdf/gh-run-receptor@0.15.0
        with:
          run-id: ${{ github.event.workflow_run.id }}
          repository: ${{ github.repository }}
          profile: ci
```

Store this workflow at `.github/workflows/gh-run-receptor-report.yml` to use source-first
discovery without extra options. The Action emits compact stdout, an escaped bounded job
summary, scalar outputs, and a `gh-run-receptor.report@1` JSON artifact named with the
source run ID and attempt. It preserves source failure without failing the
reporter. Internal reporter errors are fail-open by default; controlled validation may set
`strict-reporter: "true"`. A same-run invocation observes that run while active and must
therefore report `PENDING`, not a terminal result. Pin a full commit SHA instead of the tag
where immutable third-party Action source is required.

For a small dedicated reporter, the same complete configuration accepted by `config check`
may be placed beside the Action call:

```yaml
      - uses: uibcdf/gh-run-receptor@0.15.0
        with:
          run-id: ${{ github.event.workflow_run.id }}
          repository: ${{ github.repository }}
          profile: auto
          rules: |
            schema_version: 1
            workflows:
              - match:
                  path: .github/workflows/build_conda.yaml
                profile: conda
                settings:
                  expected_platforms: [linux-64, osx-arm64, win-64]
```

Inline rules are accepted only when GitHub context proves that the caller workflow runs
from the same repository's default branch. Pull-request refs, other branches, tags,
cross-repository evaluation, and incomplete provenance are rejected before evidence
acquisition. Use repository configuration when rules are shared or extensive. On success,
`report-ready` is `true` and `error-category` is empty; on a fail-open reporter error they
provide `false` and a bounded category. The canonical workflow should retain explicit
`actions: read` and `contents: read`. Public probes may succeed after removing a scope and
do not establish private-repository or fork requirements.

Consume the canonical report from the original source run ID without recapturing source
jobs or logs:

```text
gh run-receptor published-source SOURCE_RUN_ID --repo OWNER/REPO --receptor=llm
```

The command derives the attempt-qualified artifact name and fails closed unless GitHub
returns exactly one artifact published by a completed `workflow_run` execution of
`.github/workflows/gh-run-receptor-report.yml`. If a repository deliberately uses another
reporter path, pass it with `--reporter-workflow`. The explicit diagnostic fallback is:

```text
gh run-receptor published REPORTER_RUN_ID --repo OWNER/REPO \
  --artifact EXACT_ARTIFACT_NAME --receptor=llm
```

Selection is exact. The command bounds and validates the artifact ZIP, verifies a supplied
GitHub digest, and compares source repository, run ID, attempt, SHA, completed status,
conclusion, and URL with a fresh source-run API response. It adds an explicit warning that
profile interpretation was published rather than independently recomputed. Use native
`inspect SOURCE_RUN_ID` when the artifact is absent, expired, or does not cover the decision.

## Minimum use from a client

Inspect a completed or active run by numeric ID:

```text
gh run-receptor inspect RUN_ID --repo OWNER/REPO --receptor=llm
```

A full run URL also carries repository and hostname identity:

```text
gh run-receptor inspect https://github.com/OWNER/REPO/actions/runs/RUN_ID \
  --receptor=llm
```

Use `human` for an explanatory terminal view:

```text
gh run-receptor inspect RUN_ID --repo OWNER/REPO --receptor=human
```

If no receptor is supplied, an interactive terminal selects `human` and redirected output
selects `llm`. Automation should pass the receptor explicitly rather than depending on
terminal detection.

## Capture and replay

`inspect` captures and reports in one operation. Use `capture` when evidence should be
stored without interpreting the run, and `replay` to render that exact bundle later:

```text
gh run-receptor capture RUN_ID --repo OWNER/REPO --capture=full --output BUNDLE
gh run-receptor replay BUNDLE --receptor=llm
```

Capture policies:

| Policy | Behavior |
| --- | --- |
| `full` | Requests structured metadata and logs. Use for corpus work and difficult failures. |
| `adaptive` | Requests logs for completed unsuccessful runs. This is the normal inspection mode. |
| `metadata` | Requests structured resources without logs. Use when official state and job/artifact inventory are sufficient. |

Bundles separate hostname, repository, run, attempt, and policy. Members carry exact byte
counts and SHA-256 digests. A metadata bundle is never reused as if it satisfied a full
request. An explicit historical attempt uses attempt-specific run, job, and log evidence;
replay rejects contradictory retained identity. If requested logs have expired, capture
remains replayable but is marked incomplete and cannot produce `PASS`.

## Monitoring without repeated output

```text
gh run-receptor watch RUN_ID --repo OWNER/REPO --receptor=llm
```

`watch` sends transition-only progress to stderr and one final report to stdout. It avoids
reprinting an unchanged job tree on every poll.

## Profiles

Use `generic` when no workflow-specific interpretation is wanted:

```text
gh run-receptor inspect RUN_ID --repo OWNER/REPO --profile=generic --receptor=llm
```

Use `conda` for a recognizable native-platform package matrix:

```text
gh run-receptor inspect RUN_ID --repo OWNER/REPO --profile=conda --receptor=llm
```

Omitting `--profile` enables conservative auto-detection. Current Conda detection requires
at least two recognized platform names and a workflow identity containing `conda` or
`rattler`. An exact reviewed repository rule is preferable in automation.

The initial Conda profile reports observed platform outcomes and calls an artifact reusable
only when its platform job succeeded and a matching artifact exists. It does not yet prove
ABI validation, upload, or channel publication.

For a `noarch: python` package, declare the package kind explicitly instead of inventing a
native matrix:

```yaml
  - match:
      path: .github/workflows/build_and_upload_conda_packages.yaml
    profile: conda
    settings:
      package_kind: noarch
```

The report then summarizes package jobs and says whether GitHub artifact evidence is
available, expired, observed with unknown expiry, or currently not observed. It does not
equate a successful job with verified channel publication. A noarch rule cannot also set
`expected_platforms`.

Use `ci` for test, lint, coverage, documentation-check, build, or publication jobs:

```text
gh run-receptor inspect RUN_ID --repo OWNER/REPO --profile=ci --receptor=llm
```

The initial CI profile assigns every job one bounded presentation role and preserves
unknown names under `other`. When several unsuccessful jobs have the same official
conclusion and ordered failed-step names, LLM text reports one group with a count and
sample; JSON retains every individual job. It does not yet enforce required jobs, coverage
thresholds, annotations, or structured matrix dimensions, and never derives `PARTIAL`
merely because some CI jobs succeeded.

Use `docs` for Sphinx, notebook, link-checking, documentation-artifact, or Pages workflows:

```text
gh run-receptor inspect RUN_ID --repo OWNER/REPO --profile=docs --receptor=llm
```

The first documentation profile retains complete step state in JSON and groups it into
bounded phases. A single Sphinx-to-Pages action remains `build_deploy`; the receptor does
not pretend its build and deployment succeeded independently. A separately successful
build followed by failed deployment is `PARTIAL` while preserving GitHub's failure and
exit status 1. Required phases, warning parsing, page validation, and deployment probing
are not implemented.

Use `release` for package-registry publication, GitHub Release, or archive-verification
workflows:

```text
gh run-receptor inspect RUN_ID --repo OWNER/REPO --profile=release --receptor=llm
```

The first release profile retains the observed event, head ref, and exact SHA. It marks
the tag as unverified unless a future capture source proves the Git ref, keeps composite
package/test/publish steps indivisible, and distinguishes successful workflow steps from
external registry or archive verification. Separate successful packaging followed by
failed or skipped publication may be `PARTIAL`; GitHub's failure and exit status 1 remain
authoritative. It does not yet query npm, Anaconda, GitHub Releases, Git refs, or Zenodo.

## Repository workflow rules

Generate a local proposal before writing rules manually:

```text
gh run-receptor init > /tmp/gh-run-receptor.yaml
gh run-receptor config check /tmp/gh-run-receptor.yaml
```

The command scans only regular, non-symlink `.yml` and `.yaml` files immediately under
`.github/workflows/`. It prints one bounded explanation per workflow to stderr and the
deterministic configuration to stdout. Unknown or ambiguous shapes remain `generic` and
are never omitted. To create the default file directly:

```text
gh run-receptor init --write
```

`--write` refuses an existing `.github/gh-run-receptor.yaml`. Discovery does not execute
workflow YAML, contact GitHub, edit workflows, or infer required jobs, release gates, or
native platforms. Treat every suggestion as a starting point for human review.

Place the version 1 configuration at `.github/gh-run-receptor.yaml`:

```yaml
schema_version: 1
workflows:
  - match:
      path: .github/workflows/docs-notebooks.yaml
    profile: docs

  - match:
      path: .github/workflows/npm-publish.yaml
    profile: release

  - match:
      path: .github/workflows/build_and_upload_conda_packages.yaml
    profile: conda
    settings:
      expected_platforms:
        - linux-64
        - linux-aarch64
        - osx-64
        - osx-arm64
        - win-64
```

Version `0.15.0` supports exactly one identity per rule: an exact `path`, positive numeric
`id`, or exact display `name`. Path has precedence over ID, and ID over name, if more than
one distinct rule matches the observed workflow. Rules select `generic`, `ci`, `docs`,
`conda`, or `release`.
Conda rules accept `expected_platforms`, whose values are `linux-64`, `linux-aarch64`,
`osx-64`, `osx-arm64`, and `win-64`, or `package_kind` with `native` or `noarch`.

Unknown fields, duplicates, globs, YAML tags, anchors, multiline scalars, flow mappings,
and unsupported profile or platform values are errors. This strict subset prevents a
misspelling or future-looking inert rule from appearing to protect a workflow.

Before committing a client rule, run:

```text
gh run-receptor config check
gh run-receptor config explain .github/workflows/build_and_upload_conda_packages.yaml
```

`config check` and `config explain` inspect an explicit local candidate. Remote `inspect`,
`capture`, and `watch` do not trust the current checkout: they fetch the file from the
target repository's default branch and store its path, branch, Git blob SHA, and content
SHA-256 in `config.json`. Replay uses that captured policy offline. If the default branch
has no configuration, existing conservative auto-detection remains active.

An explicit CLI `--profile` overrides the repository profile. A matched rule's settings
remain visible, but settings that do not apply to the explicit profile cannot change its
assessment. A successful GitHub run missing a required Conda platform is receptor `FAIL`
with exit code 1; the report still retains GitHub's authoritative `conclusion=success`.

## Reading the result safely

Every report retains both layers:

```text
PARTIAL conclusion=failure status=completed | OWNER/REPO | run=123 attempt=1
```

`conclusion=failure` is the GitHub source fact. `PARTIAL` says that the selected profile
found a meaningful completed phase separately from the failed or skipped phase; some
profiles impose stronger artifact-reuse requirements. It never means success.

Preliminary exit codes:

| Code | Meaning |
| ---: | --- |
| 0 | Completed GitHub success and successful receptor processing |
| 1 | GitHub failure or required profile expectation failure |
| 2 | Cancelled, timed out, stale, action-required, or another non-success terminal state |
| 3 | Pending or in progress |
| 4 | Evidence incomplete for the requested operation |
| 5 | Acquisition, configuration, normalization, or rendering error |
| 64 | CLI usage error |

Network acquisition errors use exit status 5 and add a stable stderr category:
`authentication_required`, `authentication_failed`, `permission_denied`,
`not_found_or_inaccessible`, `rate_limited`, or `acquisition_failed`. A 404 deliberately
does not claim that a private resource is absent. Run `gh auth login` for missing
authentication; review token/repository permissions for 401 or 403. Diagnostics are
bounded and credential-shaped values are redacted.

Shell or agent automation must inspect the report as well as the exit code when it needs to
distinguish these cases. Never coerce codes 2 through 5 into success.

## Required fallback

Use native GitHub inspection when:

- the receptor reports `INCOMPLETE`, `UNKNOWN`, or `RECEPTOR_ERROR`;
- a decision requires evidence outside the captured dimensions;
- a new workflow shape has not been covered by a profile or sanitized fixture;
- only a minimal `status/conclusion` query is needed.

Typical fallback commands:

```text
gh run view RUN_ID --repo OWNER/REPO
gh run view RUN_ID --repo OWNER/REPO --log-failed
gh run view RUN_ID --repo OWNER/REPO --json status,conclusion,jobs
```

Keep raw logs local. Do not paste a full log into an LLM merely because the compact report
could not decide; narrow the missing question first.

## Security and repository policy

- Treat workflow logs, artifacts, configuration, and pull-request content as untrusted.
- Do not commit raw captures, tokens, private logs, or unsanitized evidence bundles.
- Use a reviewed allow-list when converting a public capture into a test fixture.
- Do not let a pull request define the rules used to certify that same pull request.
- Preserve unknown jobs, conclusions, and unmatched failures rather than filtering them
  away.
- Never describe a tag or a successful subset as proof that publication completed.

## Client repository checklist

For adoption at the current level:

1. Pin a verified gh-run-receptor tag.
2. Copy this guide to `GH_RUN_RECEPTOR_GUIDE.md` and record it in the repository's required
   external-tooling guides.
3. Use `--receptor=llm` explicitly in agent-facing commands.
4. Preview `init`, review every suggested profile, and add requirements discovery cannot
   prove.
5. Add `.github/gh-run-receptor.yaml` only for settings supported by the pinned version.
6. Run `config check` and test each workflow path with `config explain`.
7. Start with known archived runs before relying on live development runs.
8. Confirm that live JSON reports show `configuration.matched: true` and the expected
   default-branch source.
9. Record unsupported workflow shapes in gh-run-receptor, not as silent local filters.
10. Preserve `gh run view` as the fallback for incomplete evidence.
