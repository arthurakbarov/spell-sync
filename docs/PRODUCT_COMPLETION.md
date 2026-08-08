# Product completion checklist (v1)

Definition of done for Spell Sync Version 1 (`1.0.0`) product UX and release readiness.
Engineering / agent gates: [`ENGINEERING_COMPLETION.md`](ENGINEERING_COMPLETION.md).
Residuals accepted for v1 are listed explicitly; they are not silent blockers.

## Done when all product criteria are true

1. **Spelling toggles** — `macos_spelling` / `win_spelling` gated discovery; TUI/config.
2. **Path presets** — Documents/Home/Desktop under `Spell Sync/` on setup.
3. **Storage fork** — setup asks local / synced folder / private Git; docs + GitHub recipe;
   migrate via Change word list location.
4. **Repoint** — change wordlist location without file move (dashboard Change wordlist).
5. **Operation linger** — OperationScreen keeps result until any-key / Close; progress details.
6. **No Plan id in UI** — preview/confirm copy omits plan IDs; technical paths only.
7. **Technical log support-only** — Technical log reachable from Health, not primary chrome.
8. **Two test modes** — local minimal (`run_dev_loop.py`, 60s edit / 120s commit gate) and
   full CI (`scripts/ci.sh`, hard wall ≤20 min). See `docs/TESTING_STRATEGY.md`.
9. **No CHANGELOG required** for v1 — release notes may live in GitHub Release body only.
10. **Release path** — exact-head full CI evidence, then owner publish command (tag / GitHub
   Release / package publish). Agent does not push or publish without explicit owner request.

Checklist status: criteria 1–9 complete; criterion 10 awaits explicit owner publish.
Post-v1 engineering ops are closed; tracker current focus is `owner-publish`.

## Retired residuals

| ID | Topic |
|----|-------|
| R-PWR | Legacy coverage-padding inventory retired (zero bare tests; frozen allowlist only) |

## Accepted residuals (v1)

Documented and accepted for initial release; follow-up on second machine or later cycle:

| ID | Topic |
|----|-------|
| R-WIN | Windows real-hardware adversarial validation (reparse/junction) — **not runnable on this macOS host** |
| R-DUR | Physical power-loss / fsync durability proof not claimed (POSIX best-effort journal sync only) |
| R-CON | Real-application manual validation coverage (see `docs/target-validation.json` and `docs/FEATURE_MATRIX.md`) — **partial** `2/35`: chrome/macos + macos_spelling/macos recorded 2026-08-05 (read-only); Firefox + mutation samples still open |

## Second-machine follow-up

- Real-application target validation on maintainer hardware (macOS primary; Windows when available).
- Windows-specific adversarial suite R1–R7 on physical hardware.
- Installed-wheel smoke outside source checkout before publication.
