# Community rules · Правила сообщества · Reglas

[Maintainer proposal / Заявка владельца / Propuesta](maintainers.md)

[Live desk: nominate, vote, claim and see results](../campaigns/reports/README.md)

| Goal | Command in a new issue title in Repo Neighbor |
| --- | --- |
| Propose a public repository for next week | `rn nominate OWNER/REPO` |
| Cast your whole ballot or change your choice | `rn vote OWNER/REPO` |
| Reserve one work package for 90 minutes | `rn claim ISSUE_URL 90` |
| Hand back unfinished work | `rn release ISSUE_URL` |
| Record your PR for review and impact accounting | `rn submit ISSUE_URL PR_URL` |

**Русский.** Один участник может предложить один проект за раунд. Базовый вес голоса равен одному. Каждая отдельная задача, по которой участник зарегистрировал PR и получил merge до открытия раунда, добавляет один голос. Все голоса участника идут одному кандидату. До закрытия можно изменить выбор. Окно длится с понедельника 09:15 по Москве до следующего понедельника 09:15. Донаты не увеличивают вес. В журнале видно, кто голосовал, за какой проект и с каким весом.

**English.** One nomination and one replaceable ballot per GitHub account per round. Weight equals one plus distinct upstream issues with a registered, merged contribution by the voter before the round opened. Multiple PRs on a single issue count once. Votes target the next campaign week. Equal scores favor the earlier nomination, then repository name. Eligible votes lead selection. Remaining places follow the public [allocation rules](allocation.md). There is no payment for votes.

**Español.** Cada cuenta puede proponer un repositorio y elegir un proyecto por ronda. Su voto vale uno más el número de tareas distintas con un PR registrado y aceptado antes de abrir la ronda. Se puede cambiar la elección. Los proyectos más votados pasan por los mismos controles de capacidad y elegibilidad. Las donaciones no compran votos.

### Вклад с телефона / Mobile contributions / Contribuciones móviles

Независимая приемка перевода до открытия раунда также добавляет автору один голос. Если тот же перевод вошел в PR по той же задаче, зачет остается один. Координатор указывает исходную задачу и автора в PR. В денежной оценке учитываются только принятые исходным проектом PR с известной оценкой.

An independently accepted desk task adds one credit before the next ballot opens. Set its canonical issue in the task catalog to link later PRs to the same work. Receipts preserve the original contributor. Each new ballot records the credited tasks. Replay the weekly allocation offline with `campaign/verify-week YYYY-Www`. Contest an input by opening an issue with the week, task and proposed correction.

Una traducción aceptada por otra persona aporta un crédito. La misma tarea conserva un único crédito cuando se integra en un PR. La valoración en dólares se calcula al incorporar el PR al proyecto de origen.

## Divide a goal into reviewable work

Use a project-week as the shared goal and upstream issue URLs as work-package IDs. For a larger issue the finder inspects GitHub sub-issues; it offers eligible open children instead of assigning the parent to several people. Each child has its own owner, scope, acceptance criteria and PR. For projects asking for one atomic PR, keep the issue with one contributor. Active claims and open reviews block duplicate tasks and known file overlaps; an expired reservation frees capacity. Coordinate unlisted file overlap with the maintainer before editing.

Editors can declare ordering in the week's `requires` map in [editor.json](../campaigns/editor.json). Keys are task URLs, values are prerequisite task URLs. A dependent task can be claimed after those prerequisites have a registered merged PR. Keep dependencies acyclic. The live desk lists active owners, blockers, available work and next week's candidates.

## Measuring engineering value in USD

At reservation time Repo Neighbor freezes the issue's estimated minutes. At verified merge it counts the PR once. The pilot uses a transparent **$60 per engineering hour assumption**. A 30–90 minute task contributes **$30–$90** estimated replacement value. Unpriced work is reported separately. Self-reported hours, lines changed, API donations and open PRs produce no accepted dollar value. A heavy rewrite still needs human review of this coarse estimate.

Daily reports use Moscow calendar days. Weekly reports use the campaign boundary above and attribute merges by the upstream merge timestamp. A new participant is a person receiving their first confirmed reservation. Reports show actual submitted and merged PRs, vote weights, the estimated range and separately published sponsored inference charges. Real payroll savings would require the project's counterfactual budget and review costs.

### Local work before a PR

A contributor can document triage, a verification brief or a tested local patch even when the project closes the issue independently. Propose a receipt in [local-work.json](../campaigns/local-work.json) with the GitHub login, issue URL, timestamp, stage, short factual result and SHA-256 of the reviewed artifact. Keep private session logs and credentials on the contributor's machine. The daily and weekly reports count the contributor on their first recorded activity and list the stage reached. Re-running the same stage on the same issue preserves one receipt. Merged PRs, accepted desk submissions, vote credits and USD estimates retain their existing evidence requirements.
