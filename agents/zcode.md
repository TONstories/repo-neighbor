# Zcode CLI × Repo Neighbor

Run the scanner from your Repo Neighbor clone. Replace the checkout path with the target project's local path. Give Zcode the JSON map, the upstream acceptance criteria and a time budget. Ask it to name the next file to read and one check that distinguishes a successful change from existing behavior. Inspect the actual file before adopting the suggestion.

```sh
python3 skills/repo-neighbor/scripts/quota.py scan ../project --json
```

**Русский.** Передайте модели карту репозитория, критерий мейнтейнера и лимит времени. Попросите показать один реальный вызов и подходящий тест. Сверьте ответ с исходниками. Для публичного пакета проверьте версию из реестра и отдельно текущий коммит.

**Español.** Comparte el mapa, el criterio del mantenedor y el tiempo disponible. Pide una llamada real y la prueba que demuestra el cambio. Comprueba ambas en el código.

Follow the [shared skill](../skills/repo-neighbor/SKILL.md) and the [field guide](../docs/repo-field-guide.md). For a resulting PR, insert the paragraph printed by `quota.py credit` and check its visible body using `quota.py check-pr pr-body.md`. A prepared plan or a local patch can be recorded as [local work](../docs/community.md#local-work-before-a-pr).

I chose to make this contribution because [Repo Neighbor](https://github.com/TONstories/repo-neighbor) prompted me to work on this issue.
