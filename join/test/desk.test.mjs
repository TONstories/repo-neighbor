import assert from "node:assert/strict";
import test from "node:test";
import { DatabaseSync } from "node:sqlite";
import { build } from "esbuild";

test("identity, distinct reservations, review capacity and idempotent receipts", async () => {
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
  const desk = new Desk({ storage: { sql } }, { REVIEWER_IDS: "alice,reviewer" });
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
