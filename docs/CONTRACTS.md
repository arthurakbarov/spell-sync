# State contracts

Formal vocabulary for doctor, status, TUI dashboard, and validation honesty.
Product exit codes: `spell_sync/exit_codes.py`. Doctor JSON exit mapping:
`spell_sync/health/serialize.py` (`doctor_report_exit_code`). Dashboard severity:
`spell_sync/operation_reports.py` (`DashboardSeverity`).

## Product states

States describe **one check, target, or dashboard issue**, not the whole machine.

| State | Meaning |
|-------|---------|
| **declared** | Target or feature exists in config / support matrix / discovery registry. Not yet proven readable or writable on this host. |
| **discovered** | Path resolved for this platform/profile. Does not imply readable content or Push safety. |
| **readable** | Custom dictionary (or wordlist) opened successfully in a probe. Does not imply writable or in sync. |
| **writable** | Probe or capability marks the path writable. Does not imply Push ran or apps are closed. |
| **configured** | Project config validates (`config-check` / setup). Pending Recovery or lock may still block writes. |
| **ready** | Dashboard `DashboardSeverity.READY` - no blocking issues for the presented scope. |
| **attention** | Dashboard `WARNING` or doctor warn-level checks - usable with caveats; user action may help. |
| **blocked** | Dashboard `BLOCKED` or pending Recovery / invalid config / unreadable wordlist - new writes must not proceed. |
| **planned** | Pull/Push preview produced an immutable plan; confirmation not yet bound. |
| **executed** | Confirmed mutation finished (success, partial, or aborted per exit code). |
| **verified** | Automated synthetic tests or doctor/status probes passed. Not real-app acceptance. |
| **manually-validated** | Real application sample recorded in `docs/target-validation.json` (`manual_validation: pass`). |
| **not-run** | Manual validation never recorded for that target/OS row. |
| **skipped** | Check intentionally not run (wrong OS, dry-run, optional dependency). Not a failure. |
| **failed** | Invariant broken: blocking doctor error, failed mutation, or CI gate failure. |

## Doctor / status exit codes

| Code | Enum | When |
|------|------|------|
| **0** | `OK` | No blocking doctor errors; default doctor mode may still list optional next steps. |
| **1** | `PUSH_ABORT` | Blocking doctor errors (`has_errors`), or many mutation aborts. |
| **2** | `LINT_FAILED` | `doctor --health-check` (or health JSON) when required next-step actions exist without blocking errors. |
| **3+** | other `ExitCode` | Command-specific (unknown command, cancel, partial push, interrupt). |

`status` is informational and exits **0** when it can render; readiness lives in payload / TUI severity, not in a non-zero exit alone.

## False equivalences (prohibited)

Scripts, docs, TUI copy, and agent claims must not imply these.

| Prohibition | Why |
|-------------|-----|
| **declared = discovered** | Support matrix row is not a live path on this host. |
| **discovered = readable** | Path may exist but be locked, missing profile, or unreadable. |
| **readable = writable** | Read-only probe is not Push permission. |
| **configured = ready** | Valid TOML can still have pending Recovery or operation lock. |
| **ready = in sync** | Dashboard ready does not mean dictionaries match the wordlist. |
| **plan preview = executed** | Stale preview must not run; confirmation binds plan ID + fingerprint. |
| **exit 0 = healthy forever** | Doctor/status are point-in-time; apps can start and block Push later. |
| **automated pass = manually validated** | Synthetic CI fixtures are not real-app samples (R-CON). |
| **manual pass = mutation proven** | Read-only discovery / dry-run plan is not Pull/Push execution. |
| **full CI green = publish done** | Publish still needs owner push/tag/release and privacy scan. |
| **local minimal = full CI** | `run_dev_loop.py` has no coverage wall; `scripts/ci.sh` does. |
| **TUI Ready = no advisories** | Warnings may still show; Ready means not blocked for writes. |

## Validation honesty layers

| Layer | Evidence | Does not prove |
|-------|----------|----------------|
| Implementation | Code in repo for target | Host has the app |
| Automated | Synthetic fixtures in CI | Real dictionary layout / app version |
| Manual (R-CON) | `target-validation.json` | Every profile or future app release |
| Mutation sample | Owner-approved Pull/Push on throwaway profile | Primary-profile safety without care |

See [FEATURE_MATRIX.md](FEATURE_MATRIX.md), [SUPPORTED_TARGETS.md](SUPPORTED_TARGETS.md), and residual R-CON in [PRODUCT_COMPLETION.md](PRODUCT_COMPLETION.md).

## Usage

- Human: `spell-sync doctor`, `status`, TUI dashboard.
- Machine: `--json` on doctor/status; do not invent severity from git diff alone.
- Agents: `python3 scripts/agent_context.py`; cross-check claims against this vocabulary before saying a target "works".
