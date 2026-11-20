# Research behind the workflow

## Where to look for work

GitHub exposes labels, assignment, visibility, recency and linked-PR qualifiers in issue search. Two queries collect both invitation labels even when a repository uses just one. Reading repository metadata separately lets the finder check the license record, last push and archive state. Search has its own limits and can return incomplete results. The finder queries GitHub GraphQL, inspects a bounded recent sample and records whether its repository inspection cap truncated the search. It reads issue comments, closing PR references, manifests and contribution guidance before ranking. Review-capacity estimates inspect up to 400 recently updated PRs and close intake when coverage is insufficient. [Issue search qualifiers](https://docs.github.com/en/search-github/searching-on-github/searching-issues-and-pull-requests) · [Search API](https://docs.github.com/en/rest/search/search) · [Repository API](https://docs.github.com/en/rest/repos/repos#get-a-repository)

A recognized license is a discovery signal. Read the actual license and contribution terms. The repository's contribution guidelines, discussion and PR template determine whether a proposed change fits. For example, an unassigned issue may already have a volunteer in the comments. [GitHub contribution guidelines](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/setting-guidelines-for-repository-contributors)

## Why the budget is user supplied

Plans, limits and accounting units vary by provider and can change. A percentage of a rolling allowance cannot be reliably converted to a number of fixable issues. This project uses the contributor's observed reset window, session time box, reserve and spend ceiling. A run never needs billing credentials. [Codex plan usage](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan) · [Claude usage limits](https://support.claude.com/en/articles/9797557-usage-limit-best-practices)

## How instructions reach each agent

Codex reads scoped AGENTS.md files, Claude Code uses CLAUDE.md, Gemini CLI supports GEMINI.md, Cursor uses workspace rules and Copilot supports repository instructions. Each adapter explains how to supply this workflow to an interactive session while preserving the target's own rules. Installing files into someone else's repository is unnecessary. [Codex](https://developers.openai.com/codex/guides/agents-md/) · [Claude Code](https://code.claude.com/docs/en/memory) · [Gemini CLI](https://geminicli.com/docs/cli/gemini-md/) · [Cursor](https://cursor.com/docs/rules) · [Copilot](https://docs.github.com/en/copilot/how-tos/configure-custom-instructions/add-repository-instructions)

## Why the PR mentions this project

The attribution records what prompted a contribution. Place it once in the visible description alongside the issue, change and test evidence. It applies to work initiated through this workflow. If maintainers decline that requirement, respect their policy and choose a different project. A local check can catch a missing paragraph. Only reviewing the published body establishes what was actually submitted.
