# Repo Neighbor — dedica tu cuota disponible al código abierto

[Consultar la cuota de Codex y activar una sesión antes del reinicio](reset-window.md)


[English](../README.md) · [Русский](ru.md)

Cuando termines tus propias tareas, puedes dedicar una parte de tu cuota a una contribución revisable. Consulta el saldo en tu proveedor y fija una reserva. Por ejemplo, si faltan 35 minutos para el siguiente período de cinco horas, dedica 25 al cambio y 10 a revisarlo. Con una cuota semanal o mensual, reserva capacidad para tu trabajo futuro.

## Comunidad y presupuesto

[Cómo proponer tu propio proyecto](maintainers.md)

Propón un proyecto y vota por la próxima semana. El peso crece con las tareas aceptadas. Los informes muestran participantes, PR y valor estimado en dólares.

[Dashboard](../campaigns/reports/README.md) · [Voting](community.md) · [API donations](../sponsorship/README.md) · [Goose](../agents/goose.md) · [Mistral Vibe](../agents/vibe.md) · [Qwen Code](../agents/qwen-code.md)

## [Proyectos de la semana](../campaigns/README.md)

Reserva una tarea de la selección semanal o utiliza la búsqueda libre. Puedes indicar varios lenguajes, tiempo disponible, reserva y tipo de tarea. El comando brief genera una instrucción portátil para cualquier agente o modelo local.

[Aider](../agents/aider.md) · [Cline](../agents/cline.md) · [OpenCode](../agents/opencode.md) · [Continue](../agents/continue.md)

```sh
python3 skills/repo-neighbor/scripts/quota.py find --language Python --language TypeScript --kind tests --minutes 90 --reserve 15
python3 skills/repo-neighbor/scripts/quota.py brief https://github.com/OWNER/PROJECT/issues/123 > brief.md
```

## Primer uso

Necesitas Python 3.8+ y GitHub CLI autenticado. Ejecuta:

```sh
git clone https://github.com/TONstories/repo-neighbor.git
cd repo-neighbor
python3 skills/repo-neighbor/scripts/quota.py find --language Python --limit 3
```

Añade `--repo propietario/proyecto` para limitar la búsqueda o `--json` para obtener datos estructurados.

## Elige tu agente

[Codex](../agents/codex.md) · [Claude Code](../agents/claude.md) · [Gemini CLI](../agents/gemini.md) · [Cursor](../agents/cursor.md) · [GitHub Copilot](../agents/copilot.md)

> Dedica 25 minutos a una incidencia de documentación y reserva 10 para revisarla. Lee la política de contribuciones con IA y los comentarios. Comprueba que nadie esté trabajando en ella. Prepara el cambio, prueba el ejemplo y enséñame el diff y el texto del PR antes de enviarlo.

Si la búsqueda queda vacía o falta tiempo para verificar el cambio, termina la sesión. Conserva la plantilla del proyecto. **Todo PR iniciado mediante esta guía debe declarar expresamente que Repo Neighbor motivó la contribución.** Añade el párrafo exacto con su enlace que genera el primer comando y valida el archivo final con el segundo:

```sh
python3 skills/repo-neighbor/scripts/quota.py credit
python3 skills/repo-neighbor/scripts/quota.py check-pr pr-body.md
```

Si el proyecto no admite esa atribución, elige otro. La búsqueda y la validación son de solo lectura.
