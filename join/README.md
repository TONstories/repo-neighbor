# First contribution desk

[Open the translation desk](https://repo-neighbor.fil-support-bot.workers.dev/). Pick a language, read the public source and acceptance criterion, then sign in with GitHub. Reserve for one hour before disconnecting. Submit manually or download the optional model, keep the tab open and run it. The browser retains the queued translation until the signed-in account receives a receipt. Reviewers compare both texts and can request a revision. A contributor can never approve their own draft.

### Sign in with GitHub Gist

When OAuth is unavailable, choose **Войти через GitHub Gist**. Copy the statement shown on the desk, open GitHub Gist, paste it into the file contents and choose **Create secret gist**. Return to the desk with the link. The desk checks the author with GitHub, accepts the statement once within ten minutes in the originating browser and starts a one-day session. You can delete the Gist after signing in. The statement contains no password or access token. Anyone with the link can read an unlisted Gist. GitHub API throttling can temporarily delay verification.

## Hosting and maintenance

The static application and the SQLite-backed Durable Object run on one Workers Free deployment. Use Node 24+ and a Cloudflare CLI signed into the intended free account. From this directory run `npm ci`, `npm test`, `npm run build`, then `wrangler deploy`. Review the target account and Worker name before deploying. Keep the Worker and class migration names stable to retain receipts. Set the immutable numeric GitHub reviewer IDs in `wrangler.jsonc` through a reviewed repository change. The GitHub App needs only public identity, no repository write permissions or webhooks. To enable the optional OAuth shortcut, register once using `python3 register_github.py` while signed in as TONstories. Registration passes the client credentials directly to Worker secrets. Never put credentials in issues or source control.

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
