---
name: platform-validation
description: >-
  Record real-application target validation on a specific OS. Use when manually
  testing discovery, Pull preview, Push preview, or Recovery against a real app.
  Synthetic CI tests are not manual validation.
---

# Platform validation

## When to use

- Recording a real-application test result in `docs/target-validation.json`
- Verifying discovery, Pull preview, Push preview, or Recovery on a dedicated test profile

## Do not use

- To claim manual pass from synthetic fixtures or unit tests alone
- To mutate the owner's primary personal profile or wordlist without explicit permission
- To push, tag, release, or publish automatically

## Workflow

1. Confirm the current OS and target application version.
2. Use a dedicated throwaway profile when possible — not the owner's primary profile.
3. Obtain explicit owner permission before any real dictionary mutation.
4. Back up the test profile custom dictionary.
5. Run read-only detection (`spell-sync doctor --targets` or **Targets → Details**).
6. Build Pull preview only; do not execute unless permitted.
7. Build Push preview only; do not execute unless permitted.
8. Execute controlled Push only with permission and after reviewing the preview.
9. Verify the application recognizes test words, then remove test words.
10. Exercise Recovery separately on a synthetic interrupted transaction when safe.
11. Restore or delete the throwaway profile.
12. Record a redacted result: OS, app version, date, pass/fail — never personal words.
13. Update `docs/target-validation.json` and regenerate docs:

```bash
python3 scripts/check_target_capabilities.py --write
python3 scripts/check_target_capabilities.py --check
```

14. Do not mark other OS platforms as manually validated.

## Forbidden

- Using the primary personal profile without explicit owner permission
- Publishing words, dictionary contents, or personal paths in evidence
- Marking `manual_validation: pass` without `tested_on` and `application_version`
- Marking manual pass on an OS you cannot run
- Automatic push, tag, or release

## Final report

- OS and application version tested
- Profile type (throwaway vs owner-approved primary)
- Pull/Push/Recovery scenarios exercised
- Validation matrix rows updated
- Explicit note of any remaining `not-run` platforms
