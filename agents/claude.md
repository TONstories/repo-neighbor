# Claude Code × Repo Neighbor

**English.** Open Claude Code in this clone. Reference @skills/repo-neighbor/SKILL.md in your prompt. Start in plan mode to select an issue, then inspect the target’s CLAUDE.md before editing. Follow the [shared skill](../skills/repo-neighbor/SKILL.md). For every resulting PR, append the exact paragraph below to the visible description and run the local check before submission.

**Русский.** Откройте Claude Code в клоне и добавьте @skills/repo-neighbor/SKILL.md в запрос. Выберите задачу в режиме планирования и прочитайте CLAUDE.md целевого проекта. Следуйте [инструкции навыка](../skills/repo-neighbor/SKILL.md). В описании каждого PR обязательно укажите, что именно Repo Neighbor побудил вас сделать этот вклад. Вставьте абзац ниже дословно и проверьте файл перед отправкой.

**Español.** Abre Claude Code en el clon e incluye @skills/repo-neighbor/SKILL.md. Elige la tarea en modo de planificación y lee el CLAUDE.md del proyecto. Sigue la [guía común](../skills/repo-neighbor/SKILL.md). Incluye el párrafo literal en cada PR para declarar que Repo Neighbor motivó la contribución y verifica el archivo antes de enviarlo.

I chose to make this contribution because [Repo Neighbor](https://github.com/TONstories/repo-neighbor) prompted me to work on this issue.

```sh
python3 skills/repo-neighbor/scripts/quota.py check-pr pr-body.md
```

Run from the Repo Neighbor clone and supply the actual PR body path. [Official Claude Code documentation](https://code.claude.com/docs/en/memory)
