import { timingSafeEqual } from "node:crypto";
import { DatabaseSync } from "node:sqlite";
import { readFile } from "node:fs/promises";
import { DeskApp } from "./desk.ts";

const tables = ["tasks", "leases", "campaign_holds", "sessions", "gist_proofs"];
const contentTypes = {
  html: "text/html; charset=utf-8",
  js: "text/javascript; charset=utf-8",
  css: "text/css; charset=utf-8",
  json: "application/json",
  svg: "image/svg+xml",
  webmanifest: "application/manifest+json",
};

export function loadDesk(snapshot, env) {
  const db = new DatabaseSync(":memory:");
  const app = new DeskApp({
    sql: { exec(query, ...args) {
      const rows = db.prepare(query).all(...args);
      return { toArray: () => rows };
    } },
    transactionSync(fn) {
      db.exec("BEGIN");
      try { fn(); db.exec("COMMIT"); }
      catch (error) { db.exec("ROLLBACK"); throw error; }
    },
  }, env, timingSafeEqual);
  for (const table of tables) {
    const rows = snapshot[table] || [];
    // Column names come from the local schema, never from a remote snapshot.
    const columns = db.prepare("PRAGMA table_info(" + table + ")").all().map((c) => c.name);
    const insert = db.prepare("INSERT INTO " + table + " VALUES (" + columns.map(() => "?").join(",") + ")");
    for (const row of rows) insert.run(...columns.map((key) => row[key]));
  }
  return {
    app,
    dump: () => Object.fromEntries(tables.map((table) =>
      [table, db.prepare("SELECT * FROM " + table + " ORDER BY rowid").all()])),
    close: () => db.close(),
  };
}

export async function runDesk(request, store, env) {
  for (let attempt = 0; attempt < 3; attempt++) {
    const latest = await store.read();
    const desk = loadDesk(latest.state, env);
    try {
      const before = JSON.stringify(desk.dump());
      const response = await desk.app.fetch(request.clone());
      const after = JSON.stringify(desk.dump());
      if (before === after || await store.append(latest.version, after)) return response;
    } finally {
      desk.close();
    }
  }
  return Response.json({ error: "Please retry this request." }, { status: 503 });
}

function appwriteStore(key, env) {
  const rows = env.APPWRITE_FUNCTION_API_ENDPOINT + "/tablesdb/repo-neighbor/tables/desk/rows";
  const call = (url, method = "GET", body) => fetch(url, {
    method,
    headers: {
      "X-Appwrite-Project": env.APPWRITE_FUNCTION_PROJECT_ID,
      "X-Appwrite-Key": key,
      "Content-Type": "application/json",
    },
    body: body && JSON.stringify(body),
    signal: AbortSignal.timeout(7000),
  });
  return {
    async read() {
      const queries = new URLSearchParams();
      for (const query of [
        { method: "orderDesc", attribute: "$sequence", values: [] },
        { method: "limit", values: [1] },
      ]) queries.append("queries[]", JSON.stringify(query));
      const response = await call(rows + "?" + queries);
      if (!response.ok) throw new Error("Database read failed");
      const row = (await response.json()).rows[0];
      return row ? { version: Number(row.$id.slice(1)), state: JSON.parse(row.state) }
                 : { version: 0, state: {} };
    },
    async append(version, state) {
      // Only one invocation can create this ID. A conflict retries the business rules on fresh state.
      const response = await call(rows, "POST", { rowId: "v" + (version + 1), data: { state } });
      if (response.status === 409) return false;
      if (!response.ok) throw new Error("Database write failed");
      // Keep several committed states for rollback. A cleanup failure leaves the new state intact.
      if (version > 3) await call(rows + "/v" + (version - 3), "DELETE").catch(() => {});
      return true;
    },
  };
}

const securityHeaders = {
  "referrer-policy": "no-referrer",
  "x-content-type-options": "nosniff",
  "x-frame-options": "DENY",
};

export default async function main({ req, res, error }) {
  const path = req.path;
  try {
    if (!path.startsWith("/api/") && !path.startsWith("/auth/")) {
      const file = path === "/" || path === "/index.html" ? "index.html" : path.slice(1);
      const ext = file.split(".").at(-1);
      if (!/^(?:assets\/)?[a-zA-Z0-9_.-]+$/.test(file) || !Object.hasOwn(contentTypes, ext) ||
          !["GET", "HEAD"].includes(req.method))
        return res.text("Not found", 404);
      const content = await readFile(new URL("./dist/" + file, import.meta.url), "utf8")
        .catch((err) => { if (err.code !== "ENOENT") throw err; return null; });
      if (content === null) return res.text("Not found", 404);
      return res.text(req.method === "HEAD" ? "" : content, 200, {
        "Content-Type": contentTypes[ext],
        "Cache-Control": file.startsWith("assets/") ? "public,max-age=31536000,immutable" : "no-cache",
        ...securityHeaders,
      });
    }
    const origin = process.env.RN_ORIGIN;
    const url = new URL(origin);
    url.pathname = path;
    url.search = req.queryString || "";
    const request = new Request(url, {
      method: req.method,
      headers: req.headers,
      body: ["GET", "HEAD"].includes(req.method) ? undefined : req.bodyText,
    });
    // The proof is cleared by its short expiry and the replay table. Return one cookie per
    // response because the Appwrite runtime represents response headers as single strings.
    const response = await runDesk(request, appwriteStore(req.headers["x-appwrite-key"], process.env), process.env);
    const headers = { ...securityHeaders, ...Object.fromEntries(response.headers) };
    const cookies = response.headers.getSetCookie();
    if (cookies.length) headers["set-cookie"] = cookies[0];
    return res.text(await response.text(), response.status, headers);
  } catch {
    error("Repo Neighbor could not serve this request");
    return res.text("Desk temporarily unavailable", 503, { "Cache-Control": "no-store" });
  }
}
