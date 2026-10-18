# Local monthly delivery pipeline

Python 3.10+ on Linux/macOS; standard library only. Run commands from the repository
root. This is a small **operator-run assistant**, not hosting infrastructure or a
self-running SaaS/scheduler. No dependency installation is needed for the pipeline.

It prepares one **small, owner-agreed** source fix with an installed LLM CLI, runs
operator-defined acceptance checks, imports actual evidence, writes a deterministic
plain-English monthly report and diff, and records approval of exact artifact hashes.
It **never publishes, changes DNS, sends email, bills, creates accounts, or calls
PageSpeed/analytics APIs**. Missing measurements are `not measured/unavailable`,
not invented zeros. Technical changes do not establish conversion uplift.

## The service boundary

The $10 USD/month offer covers eligible small brochure/service sites: hosting,
a monthly metrics/change report, and prioritized small agreed speed/mobile/conversion
fixes. Agree setup, migration, eligibility, authorization, and practical monthly scope
before work. Larger rebuilds, backend/e-commerce, domains, email, and third-party fees
require separate approval. No unlimited-work or guaranteed-score/lead promise.

Hosting setup and continuity remain the operator's responsibility on the existing
approved hosting service. This pipeline does not provision hosting or monitor uptime.
Supply real hosting/availability evidence when available; otherwise the report says
it was not measured. Use the existing deployment process **only after manual review**.
The Pages build (`python3 scripts/build_site.py`) publishes root `index.html` and
the curated static files in `previews/`, not `.frictionless-reports/`. Never deploy
`pipeline/`, a private manifest/run directory/baseline, prompts, logs, or reports.
An approved public preview must contain only reviewed site files, with its routes
and assets working under `/previews/<domain>/original/` or `/optimized/`, no active
production integrations, and clear preview/noindex treatment. Copy only that
curated output into `previews/`; merely placing files in a report run does not
publish them. Public deep links are on `https://frictionlessly.github.io/`.
The build requires a new or empty `_site/`; use `--output PATH` for another empty
destination. Publisher checks: `python3 -m unittest discover -s tests -v`.

## Quickstart: safe preparation, then explicit execution

First review the example config and fictional source. Make your private manifest:

```sh
mkdir -p pipeline/.customers
cp pipeline/examples/customer.json pipeline/.customers/example-garden.json
```

Edit the copy. For this fictional demonstration, confirm your authorization to modify
the bundled demo, set `authorization.owner_approved` to `true`, and replace
`approved_by` and `reference`. For real customers, obtain and record authorization,
point `source_dir` at a **minimal owner-authorized local source tree**, explicitly list
`source_paths`, and replace the demo task/checks with the actual agreed fix and
meaningful acceptance assertions. Do not simply reuse the demo assertions.

Paths in the manifest (`source_dir`, optional `instructions_file`) resolve relative
to the manifest's location. Source must be outside the private state directory and
the state directory must be outside the source tree. For this repository's single
HTML site, use an authorized private source copy such as
`pipeline/.sources/customer/index.html`, not the entire repository as `source_dir`.
No URL cloning or source downloading takes place.

```sh
python3 -m pipeline onboard --config pipeline/.customers/example-garden.json
python3 -m pipeline prepare --customer example-garden --month 2026-10
python3 -m pipeline status --customer example-garden --month 2026-10
```

`prepare` makes attempt `001` (then `002`, etc.) without calling an LLM. Inspect the
printed run directory, `prompt.txt`, immutable baseline, config, and
`measurement-instructions.md`. The optional `instructions_file` is read **at prepare
time**, copied to `trusted-instructions.md`, and included in the prompt as
operator-designated trusted input. The example deliberately leaves it unset: the
full Frictionless skill is for the outer orchestrator, not context the small fix
model must process on every paid call. Use this option only for short, relevant,
owner-approved customer conventions. Do not use untrusted page content as instructions.
A later instruction/config edit cannot silently change a prepared run.

Import a real baseline audit if available, then explicitly allow one CLI invocation:

```sh
python3 -m pipeline run --customer example-garden --month 2026-10 --attempt 001
python3 -m pipeline status --customer example-garden --month 2026-10 --attempt 001
```

`run` invokes your **installed and already authenticated** CLI and may incur charges.
It supplies the precise prompt, requests one bounded fix plus JSON explanation, then
runs the configured checks automatically. A CLI exit code or model claim alone never
makes a candidate ready. No measurements are fabricated to fill a report.

### Installed CLI configuration

The example uses flags verified against the installed `copilot --help` and
`copilot help permissions`: `-p` for a noninteractive prompt, selective write permission,
denied shell/URL tools, no custom instruction discovery, disabled built-in MCP tools,
and `.pipeline-output/usage.json` for the CLI's usage output. **No real LLM invocation
is needed to run this project's tests.** Authenticate separately using your CLI's
normal setup and review its permission settings and pricing first.

`llm.argv` is an exact argument array. With `prompt_mode: "argument"`, the full prompt
is appended as **one final argument** (so Copilot's `-p` is last). With `"stdin"`, the
same prompt is passed on stdin without appending an argument. There is no shell,
`eval`, placeholder expansion, or interpolation of arbitrary config text into argv.
Choose a suitable installed low-cost model through its documented CLI arguments if
desired; model names and availability are deliberately not guessed or hard-coded.

Different CLI versions/permission policies may refuse unattended edits. That is a
logged failure, not permission to add `--allow-all`, `--yolo`, disable protections, or
broaden access. Inspect that CLI's help and use normal narrowly scoped permissions.
The pipeline rejects common permission-bypass flags and removes Copilot's blanket
approval environment switch, but **does not audit wrappers, plugins, CLI settings,
or executable behavior**. The prompt forbids further agents, calls, network use, and
deployment; an operator must still trust the installed CLI and its normal permissions.

## Evidence and truthful monthly reports

Nothing is measured over the network automatically. To supply performance evidence:

1. Use Chrome DevTools Lighthouse on an authorized baseline page; export raw JSON.
2. Preview **only** `work/site/` using your normal local preview setup; audit the candidate
   with the same device/throttling settings and export JSON. Never serve the run root.
3. Import the raw exports:

```sh
python3 -m pipeline import-evidence --customer example-garden --month 2026-10 --attempt 001 --kind lighthouse --phase baseline --file PATH_TO_BASELINE_JSON
python3 -m pipeline import-evidence --customer example-garden --month 2026-10 --attempt 001 --kind lighthouse --phase candidate --file PATH_TO_CANDIDATE_JSON
```

A raw PSI v5 response containing `lighthouseResult` is accepted too. Obtaining it is
an explicit manual task; consent, page privacy, API keys, quota, and any fees are
yours to manage. Never put keys in a manifest or source. No downloaded page is run
as a script by this pipeline. Your browser/audit tool may fetch page dependencies.

For analytics, copy `pipeline/example.metrics.json` privately and supply authorized
monthly values, source description, IANA timezone, and limitations. `sessions` means
eligible measured sessions; `converted_sessions` is the subset with at least one
verified primary outcome. Supply the `conversion_event` and same-population `cohort`
(including consent/test/bot filters) whenever supplying that subset. The pipeline
calculates the session conversion rate from these counts, not from clicks or total
enquiry events. `enquiries` is a separate verified count. A zero denominator or missing
numerator means the rate is unavailable. Counts may genuinely be zero; use `null` if
unavailable. For example, 8 converted sessions out of 100 measured sessions gives 8%,
even if there were 12 enquiries; this example is not customer evidence. `hosting_note`
can describe a real manual hosting check with its date and source. Do not paste
personal customer/visitor data.

```sh
python3 -m pipeline import-evidence --customer example-garden --month 2026-10 --attempt 001 --kind metrics --phase monthly --file PATH_TO_METRICS_JSON
python3 -m pipeline verify --customer example-garden --month 2026-10 --attempt 001
```

Raw inputs are retained with hashes and provenance, never overwritten. Reports show
every imported lab run separately, including mobile/desktop, URL/time/settings,
Lighthouse version, and PSI versus standalone-export source. They do not pool unlike
measurements, discard the mobile audit when desktop arrives, or infer stable gains
from a single run. Business metrics use the most recent monthly aggregate import.
Importing evidence invalidates readiness/approval: run `verify` again for a fix
attempt, or `report` again for a report-only attempt.
Audits are explicitly **operator-supplied, not independently bound to the candidate**:
the operator must establish that the page, deployment, date, and settings match.
Lighthouse lab scores are not real-user measurements or proven conversion uplift.

### Months without an agreed code change

Do not invent a fix just to produce a monthly report. Prepare a fresh attempt, import
available real measurements, and generate the report without invoking an LLM:

```sh
python3 -m pipeline report --customer example-garden --month 2026-10 --attempt 001
```

This requires an unchanged snapshot and no LLM invocation in that attempt. It checks
input integrity and produces a hash-bound report for review, not a claim that website
functional checks ran. Missing measurements remain unavailable. Review and approve
the report using the same hash workflow below; a report-only approval does not
authorize source changes or a new deployment.

## Verification, approval, and manual handoff

Each manifest check supplies `name`, `purpose`, `argv`, and `timeout_seconds`.
Checks execute in `work/site/`, must exercise the real acceptance condition, and
must return nonzero on failure. These are **trusted operator-authored arbitrary code**,
not sandboxed commands. A model must not author its own acceptance gate.
Use existing project tests/build checks where available; add a focused assertion for
the agreed behavior. Generic HTML syntax checks alone cannot prove a conversion fix.
Visual/mobile/contact-path review is outside this command's configured checks unless
the operator supplies a real browser acceptance command. The outer Frictionless
skill can perform those checks and collect/import audits with approved tools.

For fix attempts, the pipeline requires all configured checks to pass, an actual in-scope file change,
a matching explanation schema, stable source during checking, and unchanged baseline/
inputs. Empty verification arrays become `blocked_unverified`, never success.
Failed commands, timeouts, invalid JSON/config, unapproved file changes, symlinks,
and modified baselines persist failure status and return nonzero.
Checks should not mutate `work/site/`; if a trusted build does, run `verify` again on
the stable result, keeping outputs inside agreed scope and no private files.

Inspect `report.md`, `changes.diff`, `work/site/`, evidence, `llm.log`, `checks/`, and
`usage.json`. The model's explanation is labeled as model-supplied, not as evidence.
`artifact-manifest.json` hashes all run artifacts except mutable state and approval
records. `status` prints its SHA-256. After human review:

```sh
python3 -m pipeline approve --customer example-garden --month 2026-10 --attempt 001 --reviewer "Your name" --artifact-sha256 COPY_THE_REVIEWED_HASH
python3 -m pipeline status --customer example-garden --month 2026-10 --attempt 001
```

Approval records bind the site, report, diff, and verified artifact manifest hashes.
Editing any verified artifact invalidates the approval; `status` detects staleness and
`approve` refuses a stale hash. `verify` reruns fix checks and creates a new review hash; use `report` for a report-only attempt.
Historical approval records remain but are not approvals of new content.

**`approval_recorded` means permission for manual handoff, NOT deployed or sent.**
Immediately before handoff, check status/hashes again. Manually deploy only the reviewed
`work/site/` files through the existing approved hosting process, verify the live site,
and manually send the reviewed report through your approved channel. Remove internal
notes only through another reviewed report revision, never silently after approval.
The pipeline does not record a fake live/sent event or enable deployment automatically.
Update your authoritative local source from the accepted version for the next month's
baseline; the original source tree is never modified by the pipeline.

## Reruns, failure recovery, and privacy

- Every `prepare` creates a new isolated customer/month/attempt directory; nothing is
  overwritten. `--attempt` is recommended; omission chooses the latest in that month.
- `onboard` can register a new owner-approved manifest revision for a future attempt.
  Existing attempts retain their original config and instructions.
- A failed LLM attempt cannot be reused: inspect its evidence and prepare a fresh attempt.
  After a successful LLM invocation but a failed check, correct the working copy within
  the same agreed scope and run `verify` again. No additional LLM is called by `verify`.
- Operations use a nonblocking OS lock per customer. Concurrent work for the same
  customer fails rather than racing; other customers are independent. Do not remove
  audit directories or edit state to evade a call budget.
- LLM launches, including failed/timed-out launches, count against
  `max_calls_per_month` across attempts. The operator may deliberately change that
  ceiling in a new approved manifest. One process invocation may make many provider
  requests; call count and wall-clock timeout are **not token/dollar limits**.
  CLI-reported usage is retained as reported, without guessing prices or units.
  Use provider-side controls for spending; CLI/model operations may be paid.
- Timeout kills the command's process group on Linux/macOS. This is not protection
  against a hostile/detaching command. A workstation crash can leave an interrupted
  attempt; `status` marks an abandoned in-progress operation failed once its OS lock
  is free. Inspect logs and prepare a new one rather than assuming completion.
- Baseline files are read-only and hash-checked. This protects against accidental
  mutation, **not a hostile same-user process**. Working-directory isolation and
  prompts are not a filesystem/network sandbox. CLIs inherit the normal environment
  to authenticate and may use global logs/config/plugins. The pipeline does not dump
  the environment, but CLI logs, prompt arguments, source, reports, and evidence can
  still contain private information. Obtain consent for the chosen LLM provider,
  minimize data, review global CLI settings, and protect/delete artifacts under your
  retention policy. Do not assume ignored files are encrypted or backed up.
- Source paths are an explicit allowlist. Hidden paths (except `.well-known`),
  `.git`, `.env*`, `node_modules`, reports, credential/key files, and symlinks are not
  copied. These filename rules cannot find secrets embedded in HTML/JS; review the
  source yourself. Inputs are limited to 2,000 files, 10 MiB/file, and 100 MiB total.
- Private defaults are ignored: `pipeline/.state/`, `.customers/`, and `.sources/`.
  A custom `--root` must be private and separately ignored/backed up as appropriate.
  Put global options before the subcommand:
  `python3 -m pipeline --root pipeline/.state onboard --config ...`.
- Global validation failures are recorded under `<root>/failures/`; attempt failures
  also persist in `state.json`. Exit `0` means the requested operation completed, not
  that a site deployed; `1` means operation failure; `2` means blocked/stale state
  (or argparse usage failure). A missing check does not become success.

## Tests

```sh
python3 -m unittest discover -s pipeline/tests -v
```

Tests use a local fake CLI and synthetic fixtures, never a real LLM, PSI call,
production measurement, deployment, or email. Test workspaces are created and cleaned
under ignored `pipeline/.test-runs/`, not the system temporary directory.
