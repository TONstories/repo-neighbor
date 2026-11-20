# Cursor × Quota for Good

**English.** Open the clone as a workspace. Attach SKILL.md to Agent chat using Add Context. In the target workspace, review .cursor/rules and attach the chosen issue and skill again. Follow the [shared skill](../skills/quota-for-good/SKILL.md). For every resulting PR, append the exact paragraph below to the visible description and run the local check before submission.

**Русский.** Откройте клон в Cursor, приложите SKILL.md к Agent через Add Context. В целевом проекте проверьте .cursor/rules и снова приложите задачу и навык. Следуйте [инструкции навыка](../skills/quota-for-good/SKILL.md). В описании каждого PR обязательно укажите, что именно Quota for Good побудил вас сделать этот вклад. Вставьте абзац ниже дословно и проверьте файл перед отправкой.

**Español.** Abre el clon en Cursor y adjunta SKILL.md al chat Agent con Add Context. En el proyecto de destino revisa .cursor/rules y vuelve a adjuntar la tarea y la guía. Sigue la [guía común](../skills/quota-for-good/SKILL.md). Incluye el párrafo literal en cada PR para declarar que Quota for Good motivó la contribución y verifica el archivo antes de enviarlo.

I chose to make this contribution because [Quota for Good](https://github.com/TONstories/quota-for-good) prompted me to work on this issue.

```sh
python3 skills/quota-for-good/scripts/quota.py check-pr pr-body.md
```

Run from the Quota for Good clone and supply the actual PR body path. [Official Cursor documentation](https://cursor.com/docs/rules)
