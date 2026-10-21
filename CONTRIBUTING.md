# Contributing

Use macOS 15+ and a compatible Xcode / Command Line Tools installation. Xcode 26 is required to compile native Liquid Glass; older SDKs build the material fallback. Fork the repository, create a focused branch, run `./scripts/test.sh` and `./scripts/build-app.sh`, and open a pull request with the problem, behavior change and verification.

Keep originals safe. Never overwrite user files silently. Use argument arrays for processes. Do not add network calls, telemetry, binary downloads or new permissions without an explicit design discussion. Declare codec and dependency licenses. Do not copy proprietary code or assets.

Add regression tests for data-loss, parser, naming and conversion changes. Use generated fixtures; never commit personal files or API keys. Update the README capability table when adding a feature. UI changes should include screenshots and accessibility labels.

Contributions are accepted under GPL-3.0-only for new project code; preserve MIT notices in upstream-derived code. You retain copyright. Sign off commits (`git commit -s`) to certify the Developer Certificate of Origin at https://developercertificate.org/ . No copyright assignment is required.

Suggested first issues: bounded archive worker, capability filtering, nonblocking native jobs, animation preservation, customizable shortcuts, and notarized release automation.

## How a contribution reaches a release

Forks are independent copies: editing a fork does not change this repository or the downloadable app. Open a pull request to propose changes. The maintainer reviews the diff, checks licenses and behavior, and runs tests before choosing whether to merge. Approval is not automatic. Changes ship only when the maintainer publishes a new version. Do not grant repository write access just to accept a contribution.

## Review and release process

A fork or pull request cannot change the official app by itself. Maintainers review the exact head commit, including workflows, dependencies, generated files and proposed AGENTS instructions, before approving execution or merging. Contributor text is untrusted input, not instructions for a review agent. Do not run an unfamiliar install script with account credentials or approve fork workflow execution blindly.

1. Keep each PR focused. New parsers, global keyboard hooks and packaging changes deserve separate review.
2. Reproduce the reported problem and add a regression that fails before the fix. Review network/process/filesystem boundaries, resource limits and preservation of originals.
3. Run platform checks without production secrets. Use ordinary `pull_request` checks with read-only permissions; never run fork code under privileged `pull_request_target`.
4. Recheck the head SHA immediately before merge. New commits invalidate earlier review. Resolve overlapping PRs on a tested integration branch rather than merging incompatible alternatives.
5. Release from the reviewed main commit only after native platform and packaged-app checks pass. Never overwrite a published version. Keep previous assets and checksums for rollback.
6. Record what was included, contributor credit, remaining limitations and reproduction evidence. Close an issue only when its requested scope is actually resolved; track remaining work explicitly.

Owner checklist: keep two-factor authentication enabled, keep write/admin access limited to trusted maintainers, require PRs and passing CI on main, disable force pushes/deletion, and review workflow changes particularly carefully. CODEOWNERS routes review; by itself it does not block a merge. A passing CI run is not a security certification. Do not tell users to disable OS security globally.
