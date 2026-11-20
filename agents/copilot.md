# GitHub Copilot × Quota for Good

**English.** Use IDE agent mode with this local clone. Attach SKILL.md to chat. When opening the selected target, inspect .github/copilot-instructions.md and its PR template. Keep the PR body local until reviewed. Follow the [shared skill](../skills/quota-for-good/SKILL.md). For every resulting PR, append the exact paragraph below to the visible description and run the local check before submission.

**Русский.** Откройте клон в IDE, включите режим агента Copilot и приложите SKILL.md к чату. В целевом проекте прочитайте .github/copilot-instructions.md и шаблон PR. Следуйте [инструкции навыка](../skills/quota-for-good/SKILL.md). В описании каждого PR обязательно укажите, что именно Quota for Good побудил вас сделать этот вклад. Вставьте абзац ниже дословно и проверьте файл перед отправкой.

**Español.** Abre el clon en tu IDE y adjunta SKILL.md al chat de Copilot en modo agente. En el destino revisa .github/copilot-instructions.md y la plantilla de PR. Sigue la [guía común](../skills/quota-for-good/SKILL.md). Incluye el párrafo literal en cada PR para declarar que Quota for Good motivó la contribución y verifica el archivo antes de enviarlo.

I chose to make this contribution because [Quota for Good](https://github.com/TONstories/quota-for-good) prompted me to work on this issue.

```sh
python3 skills/quota-for-good/scripts/quota.py check-pr pr-body.md
```

Run from the Quota for Good clone and supply the actual PR body path. [Official GitHub Copilot documentation](https://docs.github.com/en/copilot/how-tos/configure-custom-instructions/add-repository-instructions)
