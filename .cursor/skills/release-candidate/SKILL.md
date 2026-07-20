---
name: release-candidate
description: >-
  Prepare a release candidate without publishing. Use when the owner asks to
  verify version consistency, artifacts, and manual-testing readiness before a
  potential release. Does not push, tag, or publish.
---

# Release candidate

## When to use

- Owner asks to prepare or verify a release candidate
- Pre-release artifact and documentation review

## Do not use

- To push, tag, create GitHub Releases, or publish to PyPI without explicit owner request
- As automatic post-CI publication

## Checklist

- [ ] Clean working tree
- [ ] Version consistent: `pyproject.toml`, `spell-sync version`, wheel METADATA, sdist PKG-INFO
- [ ] Full `scripts/ci.sh` green
- [ ] Wheel/sdist contents verified (`installed-wheel-smoke` skill)
- [ ] Source ZIP via `git archive` (not parent workspace zip)
- [ ] Privacy scan (`privacy-export` skill)
- [ ] SHA-256 hashes recorded for release artifacts
- [ ] `docs/MANUAL_TESTING.md` scenarios current
- [ ] `python3.11 scripts/check-target-capabilities.py --check` green
- [ ] No false `manual_validation: pass` claims in `docs/target-validation.json`
- [ ] Pending real-app validations listed explicitly
- [ ] Known limitations documented
- [ ] No tag, push, or publish performed

## Workflow

1. Run `spell-sync-ci` skill through green CI.
2. Run `installed-wheel-smoke` skill.
3. Run `privacy-export` skill.
4. Build source archive:

```bash
git archive --format=zip --prefix=spell-sync/ HEAD -o /tmp/spell-sync-source.zip
shasum -a 256 /tmp/spell-sync-source.zip dist/*
```

5. Summarize manual-testing checklist from `docs/MANUAL_TESTING.md`.

## Stop conditions

- All checklist items pass or have documented exceptions
- No remote operations performed

## Final report

- Version verified
- CI result
- Artifact paths and SHA-256 hashes
- Manual-testing readiness
- Known limitations
- Explicit note: publication requires separate owner request

## Finalize workspace snapshot

When this task changed workspace state in any repository:

1. Compare final Git metadata to the baseline captured at task start.
2. Follow skill `create-code-snapshot` in the private maintainer repository (`spell-sync-dev`).
3. Do not finish the success report until `$HOME/code.zip` is validated when recreation was required.
4. Include the **Workspace snapshot** section in the final report.
