# Repo Neighbor

[Community allocation and volunteer computing · Правила выбора и кластер · Selección y computación](docs/allocation.md)

[Русский](docs/ru.md) · [Español](docs/es.md)

Turn spare AI coding-agent quota into a reviewed open-source contribution. If your own queue is empty, give your agent a time box, find a GitHub issue where maintainers are asking for help, and spend the session on one change they can actually use.

## Choose the next project

[Submit your project as a maintainer](docs/maintainers.md)

[Community desk, ballots and contributions](campaigns/reports/README.md) · [Nominate and vote](docs/community.md) · [Donate capped inference](sponsorship/README.md)

Propose a repository for next week. A new participant has one vote; each distinct upstream task they helped land before voting opened adds one. Reserve one independent work package at a time. The public reports show contributors, merged PRs and estimated engineering value in USD. Donated compute never increases voting power.

## [Projects of the week](campaigns/README.md)

Join one coordinated campaign, reserve an available issue and track accepted improvements. Prefer to choose your own project? Use the free finder below. [Reservations and owner edits](campaigns/guide.md)

## Try it

Use Python 3.8+ and the authenticated GitHub CLI (`gh auth status`). The finder uses standard-library Python and read-only GitHub API calls. It never calls a model provider.

```sh
git clone https://github.com/TONstories/repo-neighbor.git
cd repo-neighbor
python3 skills/repo-neighbor/scripts/quota.py find --language Python --limit 3
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
| Aider | [Agent guide](agents/aider.md) |
| Cline | [Agent guide](agents/cline.md) |
| OpenCode | [Agent guide](agents/opencode.md) |
| Continue | [Agent guide](agents/continue.md) |
| Goose | [Agent guide](agents/goose.md) |
| Mistral Vibe | [Agent guide](agents/vibe.md) |
| Qwen Code | [Agent guide](agents/qwen-code.md) |

[Client and model checks](docs/compatibility.md) · [Stack recipes](docs/stacks.md)

For example, give your agent this request along with its guide:

> My queue is empty. I have 35 minutes before my five-hour window resets. Reserve the last 10 minutes for review. Use Repo Neighbor to find one Python documentation issue. Check the project's contribution and AI policies, reproduce the problem, prepare a patch and show me the evidence and PR description. Stop before posting.

For a weekly allowance, specify how much to preserve for the rest of the week. For a monthly allowance, give a session time box and keep a reserve for your own work. The user checks the provider dashboard. The tool does not infer remaining tokens from wall-clock time, switch accounts, or enable metered usage.

## How discovery works

Start with the invitation labels, then inspect issue text, recent comments, linked PRs, policy files, manifests and review history. The issue's referenced language takes priority over the repository language. Time estimates are rough ranges. An unclear scope is marked for investigation. Every recommendation explains its stack evidence, checks and uncertainty. Sampling is bounded; an empty shortlist is valid. Review availability is a ranking signal in free search and a gate for campaigns.

```sh
python3 skills/repo-neighbor/scripts/quota.py find --language Python --language TypeScript --minutes 90 --reserve 15 --kind tests --json
python3 skills/repo-neighbor/scripts/quota.py brief https://github.com/OWNER/PROJECT/issues/123 --minutes 90 --reserve 15 > brief.md
```

Give the Markdown brief to your preferred agent or local model. It includes the budget, evidence to verify, work limits and exact PR credit. Read the target's full policy and discussion before starting.

## What goes in the pull request

Keep the target project's template. Describe the change, link the issue, list the checks you ran, and include this exact visible paragraph in **every PR initiated through Repo Neighbor**:

I chose to make this contribution because [Repo Neighbor](https://github.com/TONstories/repo-neighbor) prompted me to work on this issue.

Use the [sample body](templates/contribution.md) when the target has no template. If project rules prohibit this attribution, choose a different project. Check the actual file you intend to submit:

```sh
python3 skills/repo-neighbor/scripts/quota.py credit
python3 skills/repo-neighbor/scripts/quota.py check-pr pr-body.md
```

A missing paragraph produces a nonzero exit. Review the rendered body and diff before submitting. The CLI performs discovery and local validation. The contributor controls the agent, reviews the patch and authorizes any external submission.

[Research and design decisions](docs/research.md) · [Contribution guide](CONTRIBUTING.md) · [MIT license](LICENSE)

## Local models

Generate a checklist with your running Ollama or LM Studio model. This optional step uses only loopback and never publishes.

```sh
python3 skills/repo-neighbor/scripts/quota.py brief ISSUE_URL --runtime ollama --model LOCAL_MODEL_ID
python3 skills/repo-neighbor/scripts/quota.py brief ISSUE_URL --runtime lmstudio --model LOCAL_MODEL_ID
```
