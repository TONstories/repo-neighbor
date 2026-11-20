# Как предложить свой репозиторий в Repo Neighbor

[Подать заявку / Submit a proposal / Enviar propuesta](https://github.com/TONstories/repo-neighbor/issues/new?template=maintainer-proposal.yml) · [Голосование](../campaigns/reports/README.md)

## Русский

1. **Подготовьте задачи в своем репозитории.** Для недельного отбора нужны открытый активный репозиторий с распознанной лицензией и хотя бы две независимые подходящие задачи. Дайте на них прямые ссылки. Если вы действительно приглашаете внешних участников, отметьте задачи меткой `help wanted` или `good first issue`: по этим меткам работает поиск. Проверьте, что задачи свободны, а правила проекта допускают предложенный формат работы и указание Repo Neighbor в PR.
2. **Заполните форму от своего GitHub-аккаунта.** В заголовке замените `OWNER/REPO` на точное имя. Например, для вымышленного проекта TinyIndex заголовок будет `rn propose example/tinyindex`. В форме опишите продукт, план развития, цель недели, отдельные задачи и условия ревью. Укажите разрешение на работу с ИИ и атрибуцию. Если репозиторий принадлежит организации или вы коллаборатор, приложите ссылку на свою issue в исходном репозитории с меткой `repo-neighbor` и фразой `I invite Repo Neighbor to contribute to owner/repo` и точным именем репозитория в нижнем регистре.
3. **После отправки проверьте голосование.** В журнале результат обработки указан под номером вашей issue. Бот закрывает обработанную заявку; ее текст остается доступен по ссылке рядом с кандидатом. Отдельный голос подается командой `rn vote OWNER/REPO`. Один человек может выдвинуть один проект за раунд. Итог зависит от голосов, доступных задач, емкости ревью и [правил распределения](allocation.md). Граница недели — понедельник, 09:15 по Москве. [Журнал](../campaigns/ledger.json) · [Правила](community.md)

### Пример заполнения

**Продукт.** TinyIndex собирает поисковый индекс для документации. Сейчас автор узнает о битой ссылке только после публикации сайта.

**План развития.** Сейчас CLI строит индекс. Следующая веха — проверка ссылок при сборке. Затем добавим отчет в редактор. Для обеих следующих функций нужен одинаковый формат диагностики.

**Цель недели.** Автор запускает проверку до публикации и видит файл, строку и адрес каждой битой ссылки. Интеграция в редактор остается на следующий этап.

| Приоритет и задача | Где и в каком порядке работать | Когда работу можно принять |
| --- | --- | --- |
| P1. Добавить диагностику в CLI — ссылка на первую issue | Парсер ссылок и тесты CLI. Можно начать сразу. | На тестовом документе команда возвращает код 1 и точную строку ошибки. На исправном документе — код 0. |
| P2. Подготовить примеры документов — ссылка на вторую issue | Только каталог примеров. Можно делать параллельно с P1 по согласованному формату диагностики. | В каталоге есть рабочий пример и пример с одной битой ссылкой; ожидаемый результат описан для обоих. |

**Ревью.** «Я сопровождаю CLI и могу проверить два небольших PR на этой неделе. Правила вклада и использования ИИ — по ссылке в CONTRIBUTING.md. Перед изменением формата диагностики отметьте меня в исходной задаче». В своей заявке укажите настоящий GitHub-ник ревьюера и реальные ссылки на задачи и правила.

## English

Open the form above and replace `OWNER/REPO` in the title. Describe who uses the product, what already works, the next milestone and what depends on it. Choose one outcome for the week and say how a user can verify it. Link at least two independent open issues inviting outside help. For each give priority, affected files, dependencies and an acceptance check. Name the reviewer, their PR capacity and your contribution and AI policies. For an organization or collaborator account, link an upstream issue you authored with the required invitation and the `repo-neighbor` label. After processing, find your proposal beside the candidate on the voting board. The nomination and vote are separate actions.

## Español

Abre el formulario y sustituye `OWNER/REPO` en el título. Explica para quién es el producto, qué funciona hoy, el próximo hito y qué depende de él. Define un resultado semanal que el usuario pueda comprobar. Enlaza al menos dos incidencias independientes abiertas a la colaboración; indica prioridad, archivos, dependencias y prueba de aceptación. Identifica al revisor, cuántos PR podrá revisar y las reglas de contribución y uso de IA. Tras el registro, la propuesta queda enlazada junto al candidato. La nominación y el voto se envían por separado.
