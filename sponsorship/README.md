# Donate capped inference · Пожертвовать вычисления · Donar inferencia

**Preferred donation: a dedicated, revocable inference grant with a provider-enforced USD cap.** Only use credentials that the provider and account owner permit Repo Neighbor to use. Keep personal keys, organization administrator keys, billing tokens, auto top-up and renewable budgets out of this workflow. The donor controls revocation at the provider.

**По-русски.** Создайте отдельный ключ только для разрешенной модели и работы над выбранным проектом. Задайте у провайдера жесткий лимит расходов и отключите его сброс. Введите ключ в скрытом запросе локальной команды ниже. В GitHub передаются зашифрованный конверт и его идентификатор. Не вставляйте ключ в issue, чат, письмо, PR или командную строку.

**Español.** Crea una credencial de inferencia delegable y revocable. Define en el proveedor un límite en USD sin renovación. Introduce la clave en el terminal cuando se solicite. Solo se transmite un sobre cifrado y su identificador. El donante puede revocar la clave directamente en el proveedor.

## Send a grant

Install Python 3, age and authenticated GitHub CLI. Review the code and the [public encryption recipient](recipient.txt) in the official repository. Verify the recipient through an independent owner channel if the clone or account is in doubt. The tool checks the cap, encrypts on your machine, creates an **unlisted GitHub Gist containing ciphertext only** and opens an issue with its ID. Anyone knowing the ID may see ciphertext. GitHub also sees your account and submission time. If issue creation fails, submit `rn pledge GIST_ID` here. Never create a gist with the raw credential.

```sh
python3 sponsorship/sponsor.py offer --provider openrouter --project OWNER/REPO --model FAMILY/MODEL --cap 5 --expires YYYY-MM-DD --authorized
```

OpenRouter supports many model families through one inference adapter. Choose a dedicated prepaid workspace without BYOK upstream billing. The grant specifies exactly one model and beneficiary repository. For an organization running **LiteLLM Proxy**, use `--provider litellm --gateway https://your-approved-gateway.example` with a model-limited virtual key and lifetime USD budget. The owner independently approves the HTTPS gateway and its budgeting setup before accepting. Only these two billing adapters are implemented. [OpenRouter key metadata](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-api-key) · [Provider terms](https://openrouter.ai/terms) · [LiteLLM virtual keys](https://docs.litellm.ai/docs/proxy/virtual_keys)

## Owner workflow on macOS or Linux

The owner keeps the age identity in an owner-only directory, outside this project, under `~/.codex/secrets/repo-neighbor/.env`. File mode 0600, directory mode 0700. Back up the identity in the owner's secret manager. The checked-in recipient is public. The GitHub workflow has no decryption identity and never calls a donated model.

1. Inspect the verified donor's offer. Run `python3 sponsorship/sponsor.py accept GIST_ID`. The tool checks that the unlisted gist owner matches the GitHub pledge, decrypts in memory, verifies scope, expiration and provider cap, and retains an encrypted copy in the owner vault. For LiteLLM, approve the literal HTTPS origin in owner-only `gateways.json` (a JSON array) after validating the operator and budget controls.
2. Run `python3 sponsorship/sponsor.py assist GIST_ID ISSUE_URL` to produce a bounded implementation brief about a public, open issue in the authorized repository. This command spends grant funds. The provider receives public issue text. There are no model tools or upstream write permissions. The response is for a contributor to review.
3. The local journal records actual usage after a request. A timeout or missing cost receipt leaves a pending entry and blocks the next use. Verify the exact charge in the provider dashboard, then run `reconcile GIST_ID --verified-cost USD`. Never guess.
4. Run `costs` to export **aggregates only**, review them and update `campaigns/costs.json`. No key, gist ID, donor identity or prompt belongs in that file. Run `revoke GIST_ID` to disable local use; the donor can revoke the provider key immediately regardless of the local state.

All operator subcommands use the same `python3 sponsorship/sponsor.py` prefix. No funded key is needed for the repository tests. [age encryption format and recipient model](https://github.com/FiloSottile/age)
