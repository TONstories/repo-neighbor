# OpenAI Codex × Repo Neighbor

**English.** Start Codex in this clone and explicitly invoke the skill by path. In the target checkout, read its AGENTS.md chain before editing. Follow the [shared skill](../skills/repo-neighbor/SKILL.md). For every resulting PR, append the exact paragraph below to the visible description and run the local check before submission.

**Русский.** Запустите Codex в клоне и укажите путь к SKILL.md. В целевом проекте прочитайте применимые AGENTS.md. Следуйте [инструкции навыка](../skills/repo-neighbor/SKILL.md). В описании каждого PR обязательно укажите, что именно Repo Neighbor побудил вас сделать этот вклад. Вставьте абзац ниже дословно и проверьте файл перед отправкой.

**Español.** Inicia Codex en el clon e indica la ruta de SKILL.md. Lee los AGENTS.md aplicables en el proyecto elegido. Sigue la [guía común](../skills/repo-neighbor/SKILL.md). Incluye el párrafo literal en cada PR para declarar que Repo Neighbor motivó la contribución y verifica el archivo antes de enviarlo.

I chose to make this contribution because [Repo Neighbor](https://github.com/TONstories/repo-neighbor) prompted me to work on this issue.

```sh
python3 skills/repo-neighbor/scripts/quota.py check-pr pr-body.md
```

Run from the Repo Neighbor clone and supply the actual PR body path. [Official OpenAI Codex documentation](https://developers.openai.com/codex/guides/agents-md/)
