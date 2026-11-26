# A fast first pass through an unfamiliar repository

From the Repo Neighbor clone, point the scanner at the Git checkout you want to improve. The first command shows the project map. The second narrows it to a module and searches for a literal symbol. Replace the example paths and symbol with your own.

```sh
python3 skills/repo-neighbor/scripts/quota.py scan ../project
python3 skills/repo-neighbor/scripts/quota.py scan ../project --path src --term createRenderer
```

The map names the exact commit, applicable instruction candidates, manifests, possible entry points, CI definitions and tests. It needs only Python and Git. It reads committed files locally, so your staged, unstaged and untracked changes stay outside the snapshot. The command prints file names and counts. Use `--json` to pass the same map to another agent. The optional search checks up to 1,000 source files of at most 512 KB each, omits common generated and dependency directories, and displays the first ten paths per section. The output lists coverage. For a consumer across package boundaries, repeat the search from the root without `--path`.

| Decision | Shortcut | Evidence to keep |
|---|---|---|
| Is the issue still available? | Read its acceptance criteria, assignment, linked issues and open **and closed** PRs. Search the issue number and the symptom separately. | Issue URL, last checked time and closest existing change. |
| Where do I start reading? | Read the root and module instructions, closest manifest and the workflow for that package. Follow the public entry point to one implementation, one caller and one relevant test. | Three file paths and the command CI uses. A literal match may be a comment, alias or definition, so inspect the surrounding code. |
| Which check proves the change? | Run the smallest relevant check on the base commit. Apply the patch and rerun with the same versions. Include a neighboring case that should still fail or remain unchanged. | Base and patch outcomes, versions, exit codes and the specific assertion. |
| What do I need before submitting? | Read the contribution rules and the workflows selected by your changed paths. Check CLA eligibility before implementing and leave signing to the contributor. For catalog and schema changes, look for tests that assert the complete published list or shape. | Submission prerequisites, affected workflow jobs and the commands run locally. |
| Has upstream changed while I worked? | Reopen the issue and compare the current upstream head before submitting. For packaging problems, try both the released package and a build from the fixed commit. | Package version and commit tested separately. In [limmat #9](https://github.com/DaanRosendal/limmat/issues/9), upstream fixed the package while a local workaround was being checked. |
| Can another person resume? | Give them the commit, acceptance condition, affected paths, exact check and next unresolved question. After a publication timeout, look up the original PR by head and base before retrying. | A brief another participant can verify without rereading the chat. |

For a GitHub issue, these read-only commands check for overlapping work. Run the first two with the target repository and issue number. Replace the search phrase with a distinctive symptom and inspect matches from every state. Run the final command inside the target checkout to review the affected paths.

```sh
gh issue view 9 --repo DaanRosendal/limmat
gh pr list --repo DaanRosendal/limmat --state all --search '"limmat/style.css"' --limit 20
git diff --check
git diff --stat
```

### Русский

Запустите первую команду для всего проекта, затем подставьте во вторую имя каталога и символ из задачи. Сначала прочитайте правила для этого каталога и найдите действующий вызов функции. Проверьте исходную ошибку на базовом коммите, повторите ту же проверку с правкой и добавьте контрольный пример. Заранее прочитайте правила CLA и найдите проверки CI для затронутых файлов. Для каталогов найдите тесты, которые проверяют полный список. Перед отправкой снова откройте исходную задачу. Для передачи работы достаточно ссылки на задачу, коммита, затронутых файлов, команды проверки, ее результата и следующего шага.

### Español

Ejecuta el primer comando para ver el repositorio y el segundo para buscar un símbolo dentro de un módulo. Lee sus reglas, localiza una llamada real y la prueba correspondiente. Reproduce el problema en la revisión original y repite la misma prueba con el cambio. Comprueba primero los requisitos del CLA y revisa las tareas de CI que cubren los archivos modificados. Para catálogos, busca las pruebas que validan la lista completa. Comprueba de nuevo la incidencia antes de enviar el PR. Para el relevo comparte el commit, las rutas, el comando de prueba, el resultado y el siguiente paso.
