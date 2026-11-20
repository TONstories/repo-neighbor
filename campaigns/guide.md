# Participation · Участие · Participación

[Current selection](README.md) · [Archive](archive) · [Editor](editor.json) · [Receipts](ledger.json)

| English | Русский | Español |
| --- | --- | --- |
| Choose a task on the current board. Click **Reserve**, adjust the session length in minutes in the issue title, and submit it here. | Выберите задачу в выпуске, нажмите **Забронировать**, укажите длительность сессии в минутах в заголовке и создайте issue здесь. | Elige una tarea, pulsa **Reservar**, ajusta los minutos en el título y abre la incidencia aquí. |
| Look up your request number in the receipt ledger. Start after confirmation. One active reservation per person. | Найдите номер своего запроса в журнале. Начните после подтверждения. У одного человека одна активная бронь. | Busca el número de tu solicitud en el registro. Empieza tras la confirmación. Una reserva activa por persona. |
| A reservation expires one hour after your time box, capped at 24 hours. Release early or record your PR before expiry. | Бронь истекает через час после сессии, максимум через 24 часа. Освободите ее раньше или привяжите свой PR до истечения. | La reserva vence una hora después de la sesión, con un máximo de 24 horas. Libérala o registra tu PR antes del vencimiento. |
| Follow the upstream project's AI and assignment rules. Check the discussion again before editing. | Соблюдайте правила проекта по ИИ и назначению исполнителей. Перед правкой проверьте обсуждение. | Respeta las reglas sobre IA y asignaciones del proyecto. Revisa la conversación antes de editar. |

Create an issue **in Repo Neighbor** with one of these exact title formats. Replace the URLs and minutes. GitHub supplies the requester identity. Only the holder can release or submit. Include the source issue URL and mandatory attribution in the PR body. Results are recorded by command issue number; the workflow closes processed requests. A failed run leaves requests available for reconciliation.

```text
rn claim https://github.com/OWNER/PROJECT/issues/123 90
rn release https://github.com/OWNER/PROJECT/issues/123
rn submit https://github.com/OWNER/PROJECT/issues/123 https://github.com/OWNER/PROJECT/pull/456
```

## How a week works

Monday at 09:15 Moscow time is the intended release. GitHub can delay scheduled jobs. Each new project needs at least two distinct tasks. We compare mentioned file paths and similar titles; the contributor must confirm the change is independent. A repository without sufficient review bandwidth waits. External PR decisions over the last 28 days set the weekly limit: round up decisions/4, clamp to 1–5, subtract current open external PRs and unsubmitted active reservations. Owner/member/collaborator PRs and recognized bot accounts are excluded. A bounded review sample with incomplete coverage yields zero slots. An open submitted PR counts only through the upstream queue. Results follow the original week after merge. The board is a snapshot; command processing checks live eligibility. The additional reconciliation runs every six hours.

## Community allocation / Распределение / Selección

[Rules, capacity, priorities and volunteer computing](../docs/allocation.md)

### Передача незавершенной работы / Handoff / Relevo

Откройте issue в Repo Neighbor с заголовком `rn handoff ISSUE_URL`. В теле укажите три строки:

1. Публичная ссылка на ветку, коммит или draft PR с вашей работой.
2. Какие проверки выполнены и с каким результатом. Если не запускали, укажите это.
3. Что именно должен сделать следующий участник.

Последний владелец брони может передать задачу и после истечения времени, пока ее не взял другой участник. Доска и квитанция следующей брони ведут на эти заметки. Пишите только публичные сведения.

**EN** — Open an issue titled `rn handoff ISSUE_URL`. Use three body lines for the public branch/commit/draft PR URL, checks and results, and the next step.
**ES** — Abre un issue con el titulo `rn handoff ISSUE_URL`. Escribe tres lineas con el enlace publico a la rama, commit o PR, las pruebas y su resultado, y el proximo paso.

### Отзыв после merge / Outcome feedback / Resultado

GitHub-пользователь, который влил PR, или владелец персонального репозитория может открыть issue с заголовком `rn feedback PR_URL`. Пример тела: `solved 120 20`. Первое поле — результат (solved, partial, unresolved), второе — оценка минут работы, которую заменило изменение, третье — минуты ревью. Указывайте целые числа от 0 до 99999. Повторная команда обновляет отзыв. Результат появится в отчете недели, когда задачу забронировали, рядом с заявкой и PR. Расчетная стоимость и вес голосов сохраняют прежнюю методику.

**EN** — After merge, the merger or personal repository owner can submit `rn feedback PR_URL` with `solved|partial|unresolved saved_minutes review_minutes`. A newer report replaces the previous one.
**ES** — Despues de integrar el PR, quien lo integro o el propietario del repositorio personal puede enviar `rn feedback PR_URL` con el resultado y dos cifras en minutos (trabajo ahorrado y revision).
