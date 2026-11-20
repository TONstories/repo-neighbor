# Agent and model compatibility

On 2026-11-20 four clients connected to a local LM Studio endpoint running Qwen3-4B-Instruct-2507. Each received the same small fixture: a correction to a Python function, a successful local verification command and the required project credit. We extracted each assistant's Markdown body and ran the normal PR checker. This checks brief-to-description transport. It does not establish coding accuracy, autonomous task completion or upstream acceptance.

| Client | Version | Model | Result and transport |
| --- | --- | --- | --- |
| Aider | 0.86.2 | Qwen3-4B-Instruct-2507 | Passed from raw Markdown chat history after attaching the brief with --read. The terminal wrapped the attribution and failed the exact check. |
| Cline CLI | 3.0.74 | Qwen3-4B-Instruct-2507 | Passed with an isolated OpenAI-compatible local provider and the brief in the task prompt. |
| OpenCode | 1.19.6 | Qwen3-4B-Instruct-2507 | Passed with the brief text in the prompt. File attachment introduced line numbers with this model and failed the check. |
| Continue CLI | 1.5.47 | Qwen3-4B-Instruct-2507 | Passed in read-only mode using a local model configuration and the brief text. |
| Codex, Claude Code, Gemini CLI, Cursor, GitHub Copilot | — | — | Individual guides available; client/model sessions were not exercised in this compatibility run. |
| Other local and hosted models | — | — | Use a portable brief. Compatibility depends on the chosen client and model. |

Review the technical wording before submitting. Some generated drafts described the example imprecisely even when the credit check passed. To recover a broken attribution, replace it with the exact output of the credit command and validate the final body.
