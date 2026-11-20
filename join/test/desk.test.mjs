import assert from "node:assert/strict";
import test from "node:test";
import { timingSafeEqual } from "node:crypto";
import { DatabaseSync } from "node:sqlite";
import { build } from "esbuild";

test("identity, distinct reservations, review capacity and idempotent receipts", async (t) => {
  const bundle = await build({
    entryPoints: ["src/server.ts"],
    bundle: true,
    write: false,
    format: "esm",
    plugins: [
      {
        name: "cloudflare-test",
        setup(builder) {
          builder.onResolve({ filter: /^cloudflare:workers$/ }, () => ({
            path: "workers",
            namespace: "local",
          }));
          builder.onLoad({ filter: /.*/, namespace: "local" }, () => ({
            contents:
              "export class DurableObject {constructor(ctx,env){this.ctx=ctx;this.env=env}}",
          }));
        },
      },
    ],
  });
  const { Desk } = await import(
    "data:text/javascript;base64," +
      Buffer.from(bundle.outputFiles[0].contents).toString("base64")
  );
  const db = new DatabaseSync(":memory:");
  const sql = {
    exec(query, ...params) {
      const rows = db.prepare(query).all(...params);
      return { toArray: () => rows };
    },
  };
  Object.defineProperty(crypto.subtle, "timingSafeEqual", { value: timingSafeEqual, configurable: true });
  t.after(() => delete crypto.subtle.timingSafeEqual);
  const bridgeSecret = "b".repeat(64);
  const desk = new Desk(
    { storage: { sql, transactionSync: (fn) => fn() } },
    {
      CAMPAIGN_BRIDGE: bridgeSecret,
      REVIEWER_IDS: "alice,reviewer",
      GITHUB_CLIENT_ID: "fixture-client",
      GITHUB_CLIENT_SECRET: "fixture-only",
    },
  );
  const login = await desk.fetch(
    new Request("https://desk.example/auth/github"),
  );
  assert.equal(login.status, 302);
  const state = new URL(login.headers.get("Location")).searchParams.get(
    "state",
  );
  assert.ok(state);
  const callback =
    "https://desk.example/auth/callback?code=fixture&state=" + state;
  assert.equal((await desk.fetch(new Request(callback))).status, 403);
  let gistContent = "";
  t.mock.method(globalThis, "fetch", async (url) => {
    if (String(url).startsWith("https://api.github.com/gists/"))
      return Response.json({
        owner: { id: 99, login: "gist-author" },
        files: { proof: { content: gistContent } },
      });
    if (url === "https://github.com/login/oauth/access_token")
      return Response.json({ access_token: "fixture-only" });
    assert.equal(url, "https://api.github.com/user");
    return Response.json({ id: 1234, login: "participant" });
  });
  const signed = await desk.fetch(
    new Request(callback, { headers: { Cookie: "rn_state=" + state } }),
  );
  assert.equal(signed.status, 302);
  const session = signed.headers
    .getSetCookie()
    .find((s) => s.startsWith("rn_session="))
    .split(";")[0];
  const signedDesk = await desk.fetch(
    new Request("https://desk.example/api/desk", {
      headers: { Cookie: session },
    }),
  );
  assert.equal((await signedDesk.json()).user, "participant");
  const post = (path, cookie = "") =>
    desk.fetch(
      new Request("https://desk.example/api/" + path, {
        method: "POST",
        headers: { Origin: "https://desk.example", Cookie: cookie },
      }),
    );
  const proof = await post("gist-start");
  const binding = proof.headers.getSetCookie()[0].split(";")[0];
  const statement = (await proof.json()).statement;
  const finish = "gist-finish?id=" + "a".repeat(32);
  assert.equal((await post(finish, binding)).status, 403);
  gistContent = statement;
  assert.equal((await post(finish)).status, 403);
  const other = await post("gist-start");
  assert.equal(
    (await post(finish, other.headers.getSetCookie()[0].split(";")[0])).status,
    403,
  );
  const verified = await post(finish, binding);
  assert.equal(verified.status, 200);
  const signedGist = await desk.fetch(
    new Request("https://desk.example/api/desk", {
      headers: { Cookie: verified.headers.getSetCookie()[0].split(";")[0] },
    }),
  );
  assert.equal((await signedGist.json()).user, "gist-author");
  assert.equal((await post(finish, binding)).status, 403);
  for (const login of ["alice", "bob", "reviewer", "carol"])
    sql.exec(
      "INSERT INTO sessions VALUES(?,?,?,?)",
      login,
      login,
      login,
      Date.now() + 60000,
    );
  async function request(action, user, body, origin = "https://desk.example") {
    const headers = {
      Cookie: "rn_session=" + user,
      Origin: origin,
      "Content-Type": "application/json",
    };
    return desk.fetch(
      new Request("https://desk.example/api/" + action, {
        headers,
        method: body ? "POST" : "GET",
        body: JSON.stringify(body),
      }),
    );
  }
  const tasks = (await (await request("desk", "")).json()).tasks;
  const id = tasks[0].id,
    draft = "A reviewed translation.";
  assert.equal((await request("claim", "", { id })).status, 401);
  assert.equal(
    (await request("claim", "alice", { id }, "https://other.example")).status,
    403,
  );
  const campaign = (body, secret = bridgeSecret) =>
    desk.fetch(new Request("https://desk.example/api/campaign", {
      method: "POST", headers: { Authorization: "Bearer " + secret }, body: JSON.stringify(body),
    }));
  const external = { id: "101", op: "claim", issue: "https://github.com/org/docs/issues/1",
                     repo: "org/docs", login: "alice", until: Date.now() + 60000 };
  assert.equal((await campaign(external, "invalid")).status, 401);
  assert.equal((await campaign(external)).status, 200);
  assert.equal((await campaign(external)).status, 200);
  assert.equal((await request("claim", "alice", { id })).status, 409);
  assert.equal((await campaign({ ...external, id: "102", login: "bob" })).status, 409);
  await campaign({ id: external.id, op: "release" });
  const lease = "a".repeat(32);
  assert.equal((await request("claim", "alice", { id, lease })).status, 200);
  assert.equal((await campaign(external)).status, 409);
  assert.equal((await request("claim", "alice", { id, lease })).status, 200);
  assert.equal((await request("claim", "alice", { id })).status, 409);
  assert.equal((await request("submit", "alice", { id, draft })).status, 409);
  assert.equal((await (await request("release", "alice", { id })).json()).state, "held");
  assert.equal((await (await request("release", "alice", { id, lease })).json()).state, "released");
  assert.equal((await request("claim", "alice", { id })).status, 200);
  assert.equal((await request("claim", "bob", { id })).status, 409);
  for (let i = 0; i < 2; i++)
    assert.equal((await request("submit", "alice", { id, draft })).status, 200);
  for (const [index, user] of [
    [1, "bob"],
    [2, "carol"],
  ])
    assert.equal(
      (await request("claim", user, { id: tasks[index].id })).status,
      200,
    );
  assert.equal(
    (await request("claim", "reviewer", { id: tasks[3].id })).status,
    409,
  );
  assert.equal(
    (await request("review", "alice", { id, state: "accepted", note: "" }))
      .status,
    403,
  );
  assert.equal(
    (
      await request("review", "reviewer", {
        id,
        state: "revision",
        note: "Fix the verb.",
      })
    ).status,
    200,
  );
  assert.equal(
    (await request("submit", "alice", { id, draft: "Updated." })).status,
    200,
  );
  assert.equal(
    (await request("review", "reviewer", { id, state: "accepted", note: "" }))
      .status,
    200,
  );
  const rows = await (await request("export", "")).json();
  assert.equal(rows.length, 1);
  assert.equal(rows[0].user, "alice");
  assert.equal(rows[0].reviewer, "reviewer");
  assert.equal(rows[0].draft, undefined);
  db.close();
});
