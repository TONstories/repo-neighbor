# Quota for Good — dedica tu cuota disponible al código abierto

[English](../README.md) · [Русский](ru.md)

Cuando termines tus propias tareas, puedes dedicar una parte de tu cuota a una contribución revisable. Consulta el saldo en tu proveedor y fija una reserva. Por ejemplo, si faltan 35 minutos para el siguiente período de cinco horas, dedica 25 al cambio y 10 a revisarlo. Con una cuota semanal o mensual, reserva capacidad para tu trabajo futuro.

## Primer uso

Necesitas Python 3.8+ y GitHub CLI autenticado. Ejecuta:

```sh
git clone https://github.com/TONstories/quota-for-good.git
cd quota-for-good
python3 skills/quota-for-good/scripts/quota.py find --language Python --limit 3
```

Añade `--repo propietario/proyecto` para limitar la búsqueda o `--json` para obtener datos estructurados. El buscador consulta hasta 60 incidencias con dos etiquetas de invitación, elimina duplicados y filtra por asignación, PR vinculado, licencia y actividad. Cada etiqueta de invitación suma dos puntos y cada etiqueta de documentación o pruebas suma uno. En caso de empate, tiene prioridad la actualización más reciente. Se consultan hasta 12 repositorios.

## Elige tu agente

[Codex](../agents/codex.md) · [Claude Code](../agents/claude.md) · [Gemini CLI](../agents/gemini.md) · [Cursor](../agents/cursor.md) · [GitHub Copilot](../agents/copilot.md)

> Dedica 25 minutos a una incidencia de documentación y reserva 10 para revisarla. Lee la política de contribuciones con IA y los comentarios. Comprueba que nadie esté trabajando en ella. Prepara el cambio, prueba el ejemplo y enséñame el diff y el texto del PR antes de enviarlo.

Si la búsqueda queda vacía o falta tiempo para verificar el cambio, termina la sesión. Conserva la plantilla del proyecto. **Todo PR iniciado mediante esta guía debe declarar expresamente que Quota for Good motivó la contribución.** Añade el párrafo exacto con su enlace que genera el primer comando y valida el archivo final con el segundo:

```sh
python3 skills/quota-for-good/scripts/quota.py credit
python3 skills/quota-for-good/scripts/quota.py check-pr pr-body.md
```

Si el proyecto no admite esa atribución, elige otro. La búsqueda y la validación son de solo lectura.
