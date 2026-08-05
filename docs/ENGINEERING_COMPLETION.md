# Engineering completion criteria

Repo and agent done-definition for spell-sync development arcs. Product UX /
release readiness lives in [`PRODUCT_COMPLETION.md`](PRODUCT_COMPLETION.md).

## Done when all are true

1. **Environment** — `python3 scripts/project_environment.py check` succeeds.
2. **Edit loop** — changed scope validated with `python3 scripts/run_dev_loop.py`
   (≤60s wall; no coverage; L0 sample fill-to-budget unless `--no-sample`).
3. **Commit gate** — before declaring a commit boundary complete:
   `python3 scripts/run_dev_loop.py --commit-gate` (≤120s).
4. **Necessity** — `python3 scripts/check_ci_necessity.py --purpose local --explain`
   is `commit-gate-sufficient`, `lightweight-sufficient`, or `no-action`
   (not ignored).
5. **Full CI** — only when owner requests push/publish/final:
   skill `preflight-publish` / `python3 scripts/preflight_publish.py --execute`,
   or `scripts/ci.sh` then `python3 scripts/check_ci_evidence.py`
   (use `--release` for tag/publish).
6. **Triage** — on failure, diagnose via `python3 scripts/dev_runs.py failures`
   / `show <run-id>` and `CI_SUMMARY`/`CI_LOG` — do not pipe CI through `tail`.
7. **Snapshot** — modifying tasks finalize the workspace snapshot per
   `docs/AGENT_DEVELOPMENT.md` § Workspace snapshot.
8. **No publish** — no push, tag, GitHub Release, or package publish without
   explicit owner request. Local commits on any branch do not need owner approval.

Honesty SSOT: `docs/CONTRACTS.md`, `docs/FEATURE_MATRIX.md`, `docs/INVENTORY.md`.

## Verify locally

```bash
python3 scripts/project_environment.py check
python3 scripts/run_dev_loop.py
python3 scripts/run_dev_loop.py --commit-gate
python3 scripts/check_ci_necessity.py --purpose local --explain
# owner publish / final only:
scripts/ci.sh
python3 scripts/check_ci_evidence.py
python3 scripts/execution_budget_report.py --execution-id gate:full-ci
```

## Not required for engineering done

- Real-application manual matrix (R-CON)
- Windows hardware adversarial suite (R-WIN)
- Owner push/tag/publish
