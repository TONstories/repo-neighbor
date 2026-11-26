# Repo Neighbor roadmap

## Project selection

Select active public GitHub repositories with at least 100 stars and a verified approving review on an open or merged PR in the previous 72 hours. Count the review submission time. Use the latest opinionated review from an owner, member or collaborator, exclude bots and self-approvals, and skip PRs with a changes-requested decision. Verify these signals again for a new reservation. Preserve earlier campaign records and follow existing reservations and tracked PRs to their outcomes.

## Pilot and expansion

1. Refresh the shortlist before each new pilot round. Record the stars, approval link and UTC time for each project. Check issue availability, contribution and AI rules, review capacity and runnable acceptance checks. Move paused projects out of the active rotation and record the reason and date. Preserve their historical results and replace them with eligible projects as review capacity allows.
2. Invite two eligible projects with a named reviewer. Track up to ten sessions and the reason each stopped. Aim for three appropriate submissions and one confirmed merge, then check any open PR after 30 days.
3. Improve module checks for TypeScript/JavaScript, Go and Python. Record revision, working directory, command, exit status and tests that actually ran. Label incomplete search and unknown review capacity. Track opens, merges, closures without merge and review feedback. The next outcome target is three attributable merges across at least two projects.
4. Expand Rust and either JVM or .NET when participants request them and a maintainer owns the fixtures. Expand other stacks after a public pilot and a negative control. Aim for six attributable merges across at least three projects in six months, including a repeat invitation. Consider GitLab or Forgejo when a project there agrees to pilot.

## November 26, 2026 selection refresh

HawDB work is paused and the repository is out of the W48 rotation. The previous selection remains in the campaign archive.

| Project | GitHub stars | Approval (UTC) | Pilot status |
| --- | ---: | --- | --- |
| Nightshift | 603 | [Nov 26, 00:25](https://github.com/orwa-mahmoud/nightshift/pull/265#pullrequestreview-6066890853) | Candidate for a catalog contribution. [Evidence kinds](https://github.com/orwa-mahmoud/nightshift/issues/219) has a local acceptance command. [Gate stacks](https://github.com/orwa-mahmoud/nightshift/issues/220) needs a distinct proposal from the ordering pack already in progress. |
| OnlyRead | 109 | [Nov 25, 11:11](https://github.com/onlyreadai/onlyread/pull/51#pullrequestreview-6056534605) | Conditional candidate. The [CI task](https://github.com/onlyreadai/onlyread/issues/32) and [search task](https://github.com/onlyreadai/onlyread/issues/52) require first-time contributor eligibility and an issue comment before work begins. |
| Editor Code Assistant | 1,061 | [Nov 24, 12:20](https://github.com/editor-code-assistant/eca/pull/707#pullrequestreview-6039082300) | Reserve. The maintainers publish [development checks](https://github.com/editor-code-assistant/eca/blob/c7fbd65c161f04b65c259e589f11d62ccb1f53ef/AGENTS.md), and the pilot needs a bounded task and confirmed contribution rules. |

Confirm issue scope, maintainer consent and the reviewer before starting a pilot. The weekly board runs its independent task and capacity checks separately.
