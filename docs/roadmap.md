# Repo Neighbor roadmap

## Project selection

Select active public GitHub repositories with at least 100 stars and a verified approving review on an open or merged PR in the previous 72 hours. Count the review submission time. Use the latest opinionated review from an owner, member or collaborator, exclude bots and self-approvals, and skip PRs with a changes-requested decision. Verify these signals again for a new reservation. Preserve earlier campaign records and follow existing reservations and tracked PRs to their outcomes.

## Pilot and expansion

1. Start one bounded contribution with a runnable acceptance check. Refresh stars, approval, issue availability and project rules before starting. Reuse the recorded shortlist while its evidence is current. Record exclusions so a subsequent round can resume with the next eligible project.
2. For a contributor-led issue, follow the upstream rules for assignment, AI assistance, credit and contributor eligibility. Contact a maintainer or arrange review when upstream requires it. Check CLA eligibility before implementing and leave signing to the contributor. For a coordinated pilot, agree the scope and a review contact with each participating project.
3. Reproduce the issue when applicable and test the patch on the target module. Inspect the jobs triggered by the changed paths and run relevant contract checks, including exact catalog or schema assertions. Refresh the issue and base before publishing. Record the checkout, base, exact commands and outcomes so another participant can resume.
4. Track a ready patch, an opened PR and an upstream decision as separate milestones. Record the PR URL and head, pending or failed checks, and the next action. Revisit open PRs on a meaningful change and at the 30-day checkpoint. Fix in-scope failures on the existing branch with a normal fast-forward update.
5. For the two-project coordinated pilot, track up to ten sessions and aim for three appropriate submissions and one confirmed merge. After the pilot, aim for three attributable merges across two projects. Keep TypeScript/JavaScript, Go and Python as the first priorities. Extend Rust and one of JVM or .NET when a participant requests it and someone can maintain the fixtures. Validate each new stack with an upstream pilot and a negative control.
6. Aim for six attributable merges across at least three projects in six months and record any repeat invitation. Start a GitLab or Forgejo adapter when a project there agrees to pilot.

## November 27, 2026 contributor outcomes

Four upstream PRs were submitted. [CodeToVideo #12](https://github.com/Anatomik5/codetovideo/pull/12) and [Nightshift #268](https://github.com/orwa-mahmoud/nightshift/pull/268) merged. [Nightshift #270](https://github.com/orwa-mahmoud/nightshift/pull/270) and [OnlyRead #55](https://github.com/onlyreadai/onlyread/pull/55) were open at the review. The Nightshift stack exposed an exact catalog assertion outside the initial local checks. OnlyRead surfaced a contributor-only CLA step after submission. Carry both checks into preflight. The two-project coordinated pilot remains a separate milestone.

## November 26, 2026 selection refresh

HawDB work is paused and the repository is out of the W48 rotation. The previous selection remains in the campaign archive.

| Project | GitHub stars | Approval (UTC) | Pilot status |
| --- | ---: | --- | --- |
| Nightshift | 603 | [Nov 26, 00:25](https://github.com/orwa-mahmoud/nightshift/pull/265#pullrequestreview-6066890853) | Candidate for a catalog contribution. [Evidence kinds](https://github.com/orwa-mahmoud/nightshift/issues/219) has a local acceptance command. [Gate stacks](https://github.com/orwa-mahmoud/nightshift/issues/220) needs a distinct proposal from the ordering pack already in progress. |
| OnlyRead | 109 | [Nov 25, 11:11](https://github.com/onlyreadai/onlyread/pull/51#pullrequestreview-6056534605) | Conditional candidate. The [CI task](https://github.com/onlyreadai/onlyread/issues/32) and [search task](https://github.com/onlyreadai/onlyread/issues/52) require first-time contributor eligibility and an issue comment before work begins. |
| Editor Code Assistant | 1,061 | [Nov 24, 12:20](https://github.com/editor-code-assistant/eca/pull/707#pullrequestreview-6039082300) | Reserve. The maintainers publish [development checks](https://github.com/editor-code-assistant/eca/blob/c7fbd65c161f04b65c259e589f11d62ccb1f53ef/AGENTS.md), and the pilot needs a bounded task and confirmed contribution rules. |

The weekly board uses its own task and review-capacity checks when selecting a project slot.
