# Quota for Good

[Русский](docs/ru.md) · [Español](docs/es.md)

Turn spare AI coding-agent quota into a reviewed open-source contribution. If your own queue is empty, give your agent a time box, find a GitHub issue where maintainers are asking for help, and spend the session on one change they can actually use.

## Try it

Use Python 3.8+ and the authenticated GitHub CLI (`gh auth status`). The finder uses standard-library Python and read-only GitHub API calls. It never calls a model provider.

```sh
git clone https://github.com/TONstories/quota-for-good.git
cd quota-for-good
python3 skills/quota-for-good/scripts/quota.py find --language Python --limit 3
```

Each result contains the issue title, link and ranking signals. Add `--repo owner/name` to stay within one project or `--json` for scored records, license identifiers and partial-search status. No eligible results? Stop, or change the language or repository on your next run.

## Hand one issue to your agent

| Agent | Start here |
| --- | --- |
| OpenAI Codex | [Invoke the repository skill](agents/codex.md) |
| Claude Code | [Attach the workflow in a Claude session](agents/claude.md) |
| Gemini CLI | [Load the workflow and target context](agents/gemini.md) |
| Cursor | [Use Agent with workspace rules](agents/cursor.md) |
| GitHub Copilot | [Start in IDE agent mode](agents/copilot.md) |

For example, give your agent this request along with its guide:

> My queue is empty. I have 35 minutes before my five-hour window resets. Reserve the last 10 minutes for review. Use Quota for Good to find one Python documentation issue. Check the project's contribution and AI policies, reproduce the problem, prepare a patch and show me the evidence and PR description. Stop before posting.

For a weekly allowance, specify how much to preserve for the rest of the week. For a monthly allowance, give a session time box and keep a reserve for your own work. The user checks the provider dashboard. The tool does not infer remaining tokens from wall-clock time, switch accounts, or enable metered usage.

## How discovery works

Two GitHub searches sample the 30 most recently updated issues for each of `good first issue` and `help wanted`. The query selects public, open, unassigned issues updated in the past 90 days without a linked PR. The finder deduplicates by URL, skips locked and blocked issues and awards two points per invitation label plus one for each of `documentation` and `tests`. Newer updates break ties, then URL. It inspects up to 12 distinct repository records and skips forks, archived or disabled projects, missing or unrecognized licenses, and repositories without a push in the past 90 days.

The result is a bounded sample. Labels describe work, not permission to use AI. Search can miss an unlinked PR or a contributor who volunteered in a comment. Read the thread, policy and existing changes before starting. The skill includes a stop condition when the project has incompatible contribution rules.

## What goes in the pull request

Keep the target project's template. Describe the change, link the issue, list the checks you ran, and include this exact visible paragraph in **every PR initiated through Quota for Good**:

I chose to make this contribution because [Quota for Good](https://github.com/TONstories/quota-for-good) prompted me to work on this issue.

Use the [sample body](templates/contribution.md) when the target has no template. If project rules prohibit this attribution, choose a different project. Check the actual file you intend to submit:

```sh
python3 skills/quota-for-good/scripts/quota.py credit
python3 skills/quota-for-good/scripts/quota.py check-pr pr-body.md
```

A missing paragraph produces a nonzero exit. Review the rendered body and diff before submitting. The CLI performs discovery and local validation. The contributor controls the agent, reviews the patch and authorizes any external submission.

[Research and design decisions](docs/research.md) · [Contribution guide](CONTRIBUTING.md) · [MIT license](LICENSE)
