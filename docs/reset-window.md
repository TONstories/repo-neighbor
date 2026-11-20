# Use spare Codex time before reset

**Русский.** Участник сам включает наблюдение для одной выбранной задачи. Пока терминал открыт, Repo Neighbor спрашивает локальный Codex CLI о времени сброса и остатке доступной подписки. В выбранном окне он может один раз запустить Codex и сохранить черновик документации. Режим подходит для самостоятельной работы с публичной задачей. Для командной кампании сначала забронируйте ее на доске.

**English.** Check the included Codex allowance, then optionally arm a foreground watch for one public documentation issue. It produces a local draft for human review. For a campaign task, reserve it first.

**Español.** Consulta la cuota de Codex y activa la espera para una tarea publica de documentacion. Genera un borrador local para revision. Reserva primero la tarea si participas en una campaña.

Из корня скачанного репозитория проверьте состояние без вызова модели:

```sh
python3 skills/repo-neighbor/scripts/reset_window.py check --period weekly --before-hours 10 --reserve-percent 30
```

Для запуска сначала отключите платный перерасход у провайдера. Выберите свободную задачу по документации. Подставьте ее URL вместо примера:

```sh
python3 skills/repo-neighbor/scripts/reset_window.py watch --period weekly --before-hours 10 --reserve-percent 30 --minutes 45 --included-only --issue https://github.com/OWNER/PROJECT/issues/123
```

| Status | Что происходит |
|---|---|
| early | До сброса больше заданного времени. В режиме watch следующая проверка состоится в пределах 15 минут. Время выводится в UTC. |
| ready | Окно открыто. Проверяются актуальность и размер задачи. После повторной проверки квоты запускается один черновик. |
| reserve | В одном из показанных провайдером окон осталось не больше запаса. Наблюдение заканчивается. |
| unavailable | Провайдер не подтвердил доступность включенного использования, изменился аккаунт или нужное окно недоступно. Наблюдение заканчивается. |

Поддерживаются пятичасовое (`five-hour`), недельное (`weekly`) и месячное (`monthly`) окна, если именно такое окно возвращает провайдер. Проверка опирается на протокол Codex CLI `account/rateLimits/read`. Нужен вход по подписке и версия CLI с этим протоколом и параметрами из команды запуска в скрипте.

По умолчанию черновик появляется в `~/.repo-neighbor/drafts`. Там же остается отметка о попытке запуска для конкретного сброса. При сбое проверьте результат перед повтором. Остановить наблюдение или активный сеанс можно через Ctrl+C. При закрытом терминале и после перезагрузки требуется новый запуск. Для другого агента остается доступен ручной режим.

The reserve is sampled during the run (about every 30 seconds). A single request can cross the threshold. The time box limits local execution. Disable paid overage in the provider account before using watch. The tool does not set billing controls or infer whether your personal queue is empty. No PR or issue is posted.

### Предложить одну задачу перед сбросом

На компьютере с подключенным Codex отключите у провайдера платное превышение лимита и откройте терминал:

```sh
python3 skills/repo-neighbor/scripts/reset_window.py suggest --included-only
```

Оставьте терминал открытым. За 12 часов до подтвержденного недельного сброса программа предложит одну задачу по документации, если во всех известных окнах осталось больше 30%. Команда показывает остаток, ссылку и максимальное время работы. Введите `start`, чтобы запустить локальный клиент Codex после повторной проверки аккаунта и квоты. `later` откладывает предложение на 30 минут, `skip` пропускает сброс. При выборе `later` оставьте терминал открытым: программа сама вернется к проверке. После запуска или пропуска наблюдение завершается. Если данные провайдера неизвестны, можно вручную вызвать скилл. Прежний режим `watch` сохраняет автоматический старт для тех, кто его явно включил. Смартфон использует собственный GPU и работает в открытой вкладке.
