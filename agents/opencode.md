# OpenCode × Repo Neighbor

**English.** Run opencode in the target checkout. Attach the brief with --file or the file picker, and read the target AGENTS.md. Confirm the issue, time reserve and verification command. Every resulting PR must include the exact visible paragraph below.

**Русский.** Откройте целевой проект, приложите brief.md через --file и проверьте AGENTS.md. Уточните задачу, резерв времени и команду проверки. В каждый PR обязательно включите абзац ниже.

**Español.** Abre el proyecto, adjunta brief.md con --file y lee AGENTS.md. Confirma la tarea, la reserva de tiempo y la prueba. Incluye el párrafo literal en cada PR.

I chose to make this contribution because [Repo Neighbor](https://github.com/TONstories/repo-neighbor) prompted me to work on this issue.

For Qwen3-4B, paste the brief text directly into the prompt. File attachments can introduce line numbers in the generated answer.

Run `python3 skills/repo-neighbor/scripts/quota.py check-pr pr-body.md` from the Repo Neighbor clone before submitting. Follow the [shared skill](../skills/repo-neighbor/SKILL.md) and the target project's policies. [Official documentation](https://opencode.ai/docs/rules/)
