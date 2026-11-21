import assert from "node:assert/strict";
import test from "node:test";
import { build } from "esbuild";

test("separate Appwrite invocations serialize concurrent claims and preserve receipts", async () => {
  const bundle = await build({ entryPoints: ["src/appwrite.mjs"], bundle: true,
    platform: "node", write: false, format: "esm" });
  const { runDesk } = await import("data:text/javascript;base64," +
    Buffer.from(bundle.outputFiles[0].contents).toString("base64"));
  const now = Date.now(), env = { REVIEWER_IDS: "3" };
  let version = 0, collisions = 0, state = {
    sessions: [1, 2, 3].map((uid) => ({ uid: String(uid), token: "token" + uid,
      login: "user" + uid, expires: now + 60000 })),
  };
  const store = {
    async read() { return { version, state }; },
    async append(base, next) {
      if (base !== version) { collisions++; return false; }
      state = JSON.parse(next); version++; return true;
    },
  };
  const origin = "https://desk.example", id = "join-pl";
  const post = (op, uid, fields = {}) => runDesk(new Request(origin + "/api/" + op, {
    method: "POST", headers: { Origin: origin, Cookie: "rn_session=token" + uid,
      "Content-Type": "application/json" },
    body: JSON.stringify({ id, ...fields }),
  }), store, env);
  const [first, second] = await Promise.all([post("claim", 1), post("claim", 2)]);
  assert.deepEqual([first.status, second.status].sort(), [200, 409]);
  assert.equal(collisions, 1);
  const winner = first.ok ? 1 : 2;
  assert.equal((await post("submit", winner, { draft: "Reviewed draft." })).status, 200);
  assert.equal((await post("submit", winner, { draft: "Reviewed draft." })).status, 200);
  assert.equal(version, 2);
  assert.equal((await post("review", 3, { state: "accepted", note: "" })).status, 200);
  const exported = await runDesk(new Request(origin + "/api/export"), store, env);
  assert.deepEqual((await exported.json()).map((row) => [row.id, row.state]), [[id, "accepted"]]);
});
