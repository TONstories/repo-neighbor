# Participation · Участие · Participación

[Current selection](README.md) · [Archive](archive) · [Editor](editor.json) · [Receipts](ledger.json)

| English | Русский | Español |
| --- | --- | --- |
| Choose a task on the current board. Click **Reserve**, adjust the session length in minutes in the issue title, and submit it here. | Выберите задачу в выпуске, нажмите **Забронировать**, укажите длительность сессии в минутах в заголовке и создайте issue здесь. | Elige una tarea, pulsa **Reservar**, ajusta los minutos en el título y abre la incidencia aquí. |
| Look up your request number in the receipt ledger. Start after confirmation. One active reservation per person. | Найдите номер своего запроса в журнале. Начните после подтверждения. У одного человека одна активная бронь. | Busca el número de tu solicitud en el registro. Empieza tras la confirmación. Una reserva activa por persona. |
| A reservation expires one hour after your time box, capped at 24 hours. Release early or record your PR before expiry. | Бронь истекает через час после сессии, максимум через 24 часа. Освободите ее раньше или привяжите свой PR до истечения. | La reserva vence una hora después de la sesión, con un máximo de 24 horas. Libérala o registra tu PR antes del vencimiento. |
| Follow the upstream project's AI and assignment rules. Check the discussion again before editing. | Соблюдайте правила проекта по ИИ и назначению исполнителей. Перед правкой проверьте обсуждение. | Respeta las reglas sobre IA y asignaciones del proyecto. Revisa la conversación antes de editar. |

Create an issue **in Quota for Good** with one of these exact title formats. Replace the URLs and minutes. GitHub supplies the requester identity. Only the holder can release or submit. Include the source issue URL and mandatory attribution in the PR body. Results are recorded by command issue number; the workflow closes processed requests. A failed run leaves requests available for reconciliation.

```text
qfg claim https://github.com/OWNER/PROJECT/issues/123 90
qfg release https://github.com/OWNER/PROJECT/issues/123
qfg submit https://github.com/OWNER/PROJECT/issues/123 https://github.com/OWNER/PROJECT/pull/456
```

## How a week works

Monday at 09:15 Moscow time is the intended release. GitHub can delay scheduled jobs. Up to three repositories with at least two distinct tasks qualify. We compare mentioned file paths and similar titles; the contributor must confirm the change is independent. A repository without sufficient review bandwidth waits. External PR decisions over the last 28 days set the weekly limit: round up decisions/4, clamp to 1–5, subtract current open external PRs and unsubmitted active reservations. Owner/member/collaborator PRs and recognized bot accounts are excluded. A bounded review sample with incomplete coverage yields zero slots. An open submitted PR counts only through the upstream queue. Results follow the original week after merge. The board is a snapshot; command processing checks live eligibility. The additional reconciliation runs every six hours.

## Owner edits and project exclusions

Edit `editor.json` in the GitHub web editor and commit to main. Use the ISO week in Moscow time. Up to three pins are evaluated before automatically chosen targets; pins must still pass eligibility. `exclude` at the root applies across weeks. To request exclusion, open an issue here and identify the repository. The owner adds it to the exclusion list. Previously issued reservations remain in the ledger.

```json
{
  "exclude": ["example/excluded"],
  "weeks": {
    "2027-W01": {
      "pin": ["example/pinned"],
      "exclude": [],
      "descriptions": {
        "example/pinned": {
          "en": "Make the examples run on a fresh install.",
          "ru": "Проверить запуск примеров после чистой установки.",
          "es": "Probar los ejemplos en una instalación limpia."
        }
      }
    }
  }
}
```

After four releases compare accepted changes, outstanding external reviews and expired reservations before adjusting the pilot limits.
