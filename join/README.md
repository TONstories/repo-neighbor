# First contribution desk

[Open the translation desk](https://repo-neighbor-6b014c.appwrite.network/). Pick a language, read the public source and acceptance criterion, then sign in with GitHub. Reserve for one hour before disconnecting. Submit manually or download the optional model, keep the tab open and run it. The browser retains the queued translation until the signed-in account receives a receipt. Reviewers compare both texts and can request a revision. A contributor can never approve their own draft.

### Sign in with GitHub Gist

When OAuth is unavailable, choose **Войти через GitHub Gist**. Copy the statement shown on the desk, open GitHub Gist, paste it into the file contents and choose **Create secret gist**. Return to the desk with the link. The desk checks the author with GitHub, accepts the statement once within ten minutes in the originating browser and starts a one-day session. You can delete the Gist after signing in. The statement contains no password or access token. Anyone with the link can read an unlisted Gist. GitHub API throttling can temporarily delay verification.

## Hosting and maintenance

The site and API run together on Appwrite Cloud Free. The function uses Node.js 24, the included 0.5 CPU and 512 MB specification, and the private serverless TablesDB table `repo-neighbor/desk`. Its ephemeral key has only `rows.read` and `rows.write` scopes. Each mutation creates a uniquely numbered state row. Concurrent writers retry against the newest row, preserving claim exclusivity and review receipts.

For a release, use the official Appwrite CLI signed into the project recorded in `appwrite.config.json`. Run `npm ci`, `npm test`, `npm run package:appwrite`, then `appwrite functions create-deployment --function-id repo-neighbor --code .appwrite-build --entrypoint main.mjs --activate`. Keep the database and table IDs stable. Verify the active deployment, the public desk, and the campaign workflow.

Set `RN_ORIGIN` to the public site URL and `REVIEWER_IDS` to comma-separated numeric GitHub IDs. Keep `CAMPAIGN_BRIDGE` in Appwrite function secrets and its matching value in the GitHub Actions secret `RN_APPWRITE_BRIDGE`. Redeploy after changing variables. GitHub Gist sign-in is available. The optional GitHub App needs only public identity and can be registered using `python3 register_github.py` while signed in as TONstories. Appwrite Free can pause an inactive project after seven days. The operator can reactivate it from the Console. [Appwrite Free limits](https://appwrite.io/pricing)

Add agreed documentation or translation tasks to `src/tasks.json`. Use a permanent id, upstream repository, target language, public source, and the canonical GitHub issue URL when available. Preserve ids when crediting the resulting PR. For a coordinated PR, include a credit for each contributor and link their source task. Only verified upstream merges enter the USD estimate. For independent verification of a weekly frozen ballot run `campaign/verify-week YYYY-Www` from the repository root. Older seats are explicitly marked as legacy. Open a public issue to contest a snapshot, referencing the week, candidate and disputed input.

## Device verification

| System | Browser route | Physical local model test |
|---|---|---|
| iOS | Safari, keep the tab visible | Pending |
| Android | Chrome, keep the tab visible | Pending |
| macOS | Chrome or Safari with WebGPU | Apple M1 Max, macOS 27.0.1, Chrome 157.0.8103.79. Loaded Qwen and generated a Polish translation. Receipt verified against an isolated queue. |
| Windows | Edge or Chrome with hardware acceleration | Pending |
| Linux | WebGPU-capable browser and graphics driver | Pending |

The WebGPU probe checks the adapter and shader-f16. Real allocation and model execution depend on available memory. Download is voluntary, approximately 0.88 GB plus the engine. Remove the model in the page to reclaim storage. GPU resources are released after 30 idle minutes while the page is active. The manual path needs neither WebGPU nor a subscription. Public reports contain GitHub names, task identifiers, decisions and timing. Draft text is visible to its author and authorized reviewers. The pilot target is five independent submissions including iPhone and Android, with three human acceptances.
