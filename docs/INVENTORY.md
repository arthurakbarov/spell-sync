# Non-repo inventory

Items not fully managed by the public spell-sync repository. Update when maintainer-only
or manual steps change. Private wordlist content must never appear in public commits.

## Maintainer workspace (outside this repo)

| Item | Location | Notes |
|------|----------|-------|
| Canonical wordlist | private `spell-words` repo | Never copy into public tree |
| Local `spell-sync.toml` | private project root | Effective project context from wordlist path |
| Nested tool clone | `spell-words/spell-sync/` (gitignored) | Develop in the public clone |
| Maintainer topology / snapshot | `spell-sync-dev` | `create-code-snapshot`; canonical owner-home `code.zip` |
| Daily maintainer scripts | private repos only | Do not reference `daily.sh` from public agent config |

## Manual / local-only

| Item | Notes |
|------|-------|
| Real-application validation | Skill `platform-validation`; record in `docs/target-validation.json` |
| Windows adversarial R1–R7 | Physical Windows hardware only (residual R-WIN) |
| Installed-wheel smoke outside checkout | Skill `installed-wheel-smoke` before publish |
| Owner push / tag / GitHub Release / PyPI | Explicit owner request only |
| Privacy scan before share | Skills `privacy-export` + `security-audit` |
| Publish preflight | Skill `preflight-publish` (necessity → CI → evidence → privacy) |

## CI and evidence (local machine)

| Item | Notes |
|------|-------|
| CI evidence store | Bound to CI input digest; exact HEAD for release |
| Execution timing history | Learning samples; timeouts do not train the model |
| `.venv` | Disposable; never commit or snapshot |

## Intentionally not copied from nix-darwin

Hosts/sops/flake/brew, shell-runtime roles, owner nx TUI menu, rebuild/runtime-verify, and
"no commits on main" policy stay nix-only. Spell-sync allows local commits on any branch;
push remains owner-gated ([GIT-WORKFLOW.md](GIT-WORKFLOW.md)).

## Ported from nix-darwin methodology (shape only)

| Item | Where |
|------|-------|
| Evidence ladder | `docs/CONTRACTS.md` |
| When-not-to-rerun | `docs/WORKFLOW.md` |
| Fail-closed change classes | `ci/ci-impact.toml` + necessity `unknown-change` |
| Status-contract binding | `scripts/contracts/status-contract.json` |
| Methodology reuse tests | `tests/test_methodology_reuse.py` |
| Run triage index | `scripts/dev_runs.py index` |
| Absolute no-canvas rule | `.cursor/rules/no-canvas-for-text.mdc` |
| Recovery archive + source identity | spell-sync-dev snapshot profiles |
