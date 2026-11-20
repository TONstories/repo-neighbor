// The single SQLite-backed object serializes admissions and review decisions.
import { DurableObject } from "cloudflare:workers";
import catalog from "./tasks.json";
const taskById = new Map(catalog.map((task) => [task.id, task]));
const json = (data: unknown, status = 200) =>
  Response.json(data, { status, headers: { "Cache-Control": "no-store" } });
const cookie = (r: Request, k: string) =>
  (r.headers.get("Cookie") || "")
    .split("; ")
    .find((s) => s.startsWith(k + "="))
    ?.slice(k.length + 1);
const setCookie = (key: string, v: string, age: number) =>
  key + "=" + v + "; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=" + age;
const token = () => crypto.randomUUID() + crypto.randomUUID();
type Env = {
  DESK: DurableObjectNamespace;
  ASSETS: Fetcher;
  REVIEWERS?: string;
  GITHUB_CLIENT_ID?: string;
  GITHUB_CLIENT_SECRET?: string;
};
type Row = {
  id: string;
  user: string;
  uid: string;
  state: string;
  draft: string;
  claimed: number;
  submitted: number;
  reviewed: number;
  reviewer: string;
  note: string;
  metrics: string;
};
export class Desk extends DurableObject<Env> {
  sql = this.ctx.storage.sql;
  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    this.sql.exec(
      "CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, uid TEXT, login TEXT, expires INTEGER)",
    );
    this.sql.exec(
      "CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY,user TEXT,uid TEXT,state TEXT,draft TEXT,claimed INTEGER,submitted INTEGER,reviewed INTEGER,reviewer TEXT,note TEXT,metrics TEXT)",
    );
  }
  async fetch(r: Request) {
    const u = new URL(r.url),
      path = u.pathname,
      now = Date.now();
    if (r.method === "POST" && r.headers.get("Origin") !== u.origin)
      return json({ error: "Origin mismatch" }, 403);
    const sid = cookie(r, "rn_session") || "";
    const me = this.sql
      .exec<{
        uid: string;
        login: string;
      }>("SELECT uid, login FROM sessions WHERE token=? AND expires>?", sid, now)
      .toArray()[0];
    const reviewer =
      !!me &&
      (this.env.REVIEWERS || "")
        .toLowerCase()
        .split(",")
        .map((s) => s.trim())
        .includes(me.login.toLowerCase());
    // OAuth uses identity-only scope; the browser never receives a GitHub token.
    if (path === "/auth/github") {
      if (!this.env.GITHUB_CLIENT_ID || !this.env.GITHUB_CLIENT_SECRET)
        return json({ error: "GitHub sign-in requires operator setup." }, 503);
      const state = token();
      const url = new URL("https://github.com/login/oauth/authorize");
      url.search = new URLSearchParams({
        client_id: this.env.GITHUB_CLIENT_ID,
        state,
        redirect_uri: u.origin + "/auth/callback",
        scope: "",
      }).toString();
      return new Response(null, {
        status: 302,
        headers: {
          Location: url.href,
          "Set-Cookie": setCookie("rn_state", state, 600),
          "Cache-Control": "no-store",
        },
      });
    }
    if (path === "/auth/callback") {
      const state = cookie(r, "rn_state");
      if (
        !state ||
        state !== u.searchParams.get("state") ||
        !u.searchParams.get("code")
      )
        return json({ error: "Invalid sign-in state" }, 403);
      const exchange = await fetch(
        "https://github.com/login/oauth/access_token",
        {
          method: "POST",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            client_id: this.env.GITHUB_CLIENT_ID,
            client_secret: this.env.GITHUB_CLIENT_SECRET,
            code: u.searchParams.get("code"),
            redirect_uri: u.origin + "/auth/callback",
          }),
        },
      );
      const data = (await exchange.json()) as { access_token?: string };
      if (!data.access_token)
        return json({ error: "GitHub sign-in expired" }, 401);
      const who = await fetch("https://api.github.com/user", {
        headers: {
          Authorization: "Bearer " + data.access_token,
          "User-Agent": "Repo-Neighbor",
        },
      });
      if (!who.ok) return json({ error: "GitHub identity unavailable" }, 502);
      const account = (await who.json()) as { id: number; login: string };
      const session = token();
      this.sql.exec("DELETE FROM sessions WHERE expires<=?", now);
      this.sql.exec(
        "INSERT INTO sessions VALUES(?,?,?,?)",
        session,
        String(account.id),
        account.login,
        now + 86400000,
      );
      const h = new Headers({ Location: "/", "Cache-Control": "no-store" });
      h.append("Set-Cookie", setCookie("rn_session", session, 86400));
      h.append("Set-Cookie", setCookie("rn_state", "", 0));
      return new Response(null, { status: 302, headers: h });
    }
    const rows = () =>
      this.sql.exec<Row>("SELECT * FROM tasks ORDER BY claimed").toArray();
    if (path === "/api/export" && r.method === "GET")
      return json(
        rows()
          .filter((x) => x.submitted)
          .map((x) => ({
            id: x.id,
            repo: taskById.get(x.id)?.repo,
            issue: taskById.get(x.id)?.issue,
            user: x.user,
            state: x.state,
            claimed: x.claimed,
            submitted: x.submitted,
            reviewed: x.reviewed,
            reviewer: x.reviewer,
            metrics: JSON.parse(x.metrics),
          })),
      );
    if (path === "/api/desk" && r.method === "GET") {
      const all = rows(),
        held = all.filter(
          (x) =>
            x.state === "pending" ||
            x.state === "revision" ||
            (x.state === "held" && x.claimed > now - 3600000),
        );

      return json({
        user: me?.login,
        reviewer,
        loginReady: !!this.env.GITHUB_CLIENT_SECRET,
        tasks: catalog.map((t) => ({
          ...t,
          available:
            !all.some(
              (x) =>
                x.id === t.id &&
                (x.state !== "held" || x.claimed > now - 3600000),
            ) &&
            held.filter((x) => taskById.get(x.id)?.repo === t.repo).length < 3,
        })),
        mine: all.filter((x) => x.uid === me?.uid),
        queue: reviewer ? all.filter((x) => x.state === "pending") : [],
      });
    }
    if (!me) return json({ error: "Sign in with GitHub" }, 401);
    if (r.method !== "POST") return json({ error: "Unknown route" }, 404);
    if (path === "/api/logout") {
      this.sql.exec("DELETE FROM sessions WHERE token=?", sid);
      return json({ ok: true });
    }
    if (
      !r.headers.get("Content-Type")?.startsWith("application/json") ||
      Number(r.headers.get("Content-Length") || 0) > 32000
    )
      return json({ error: "Invalid request" }, 400);
    const raw = await r.text();
    if (raw.length > 24000) return json({ error: "Draft too large" }, 413);
    let b;
    try {
      b = JSON.parse(raw);
    } catch {
      return json({ error: "Invalid JSON" }, 400);
    }
    if (!b || !catalog.some((t) => t.id === b.id))
      return json({ error: "Unknown task" }, 404);
    const all = rows(),
      old = all.find((x) => x.id === b.id),
      mine = old?.uid === me.uid;
    if (path === "/api/claim") {
      if (mine && old?.state !== "held")
        return json({ id: b.id, state: old?.state });
      const busy = all.filter(
        (x) =>
          x.state === "pending" ||
          x.state === "revision" ||
          (x.state === "held" && x.claimed > now - 3600000),
      );
      if (
        (old &&
          !mine &&
          (old.state !== "held" || old.claimed > now - 3600000)) ||
        busy.some(
          (x) => x.id !== b.id && x.uid === me.uid && x.state === "held",
        ) ||
        busy.filter(
          (x) =>
            x.id !== b.id &&
            taskById.get(x.id)?.repo === taskById.get(b.id)?.repo,
        ).length >= 3
      )
        return json({ error: "Task or review slots are occupied" }, 409);
      if (!mine || !old || old.claimed <= now - 3600000)
        this.sql.exec(
          "INSERT OR REPLACE INTO tasks VALUES(?,?,?,'held','',?,0,0,'','','{}')",
          b.id,
          me.login,
          me.uid,
          now,
        );
      return json({ id: b.id, state: "held" });
    }
    if (path === "/api/submit") {
      if (!old || !mine)
        return json(
          { error: "Reservation belongs to another participant" },
          409,
        );
      if (
        typeof b.draft !== "string" ||
        !b.draft.trim() ||
        b.draft.length > 6000
      )
        return json({ error: "Use 1–6000 characters" }, 400);
      if (old.state === "pending" || old.state === "accepted")
        return old.draft === b.draft
          ? json({ id: b.id, state: old.state })
          : json({ error: "Already submitted" }, 409);
      if (old.state === "held" && old.claimed <= now - 3600000)
        return json(
          { error: "Reservation expired. Claim the task again." },
          409,
        );
      const metrics: Record<string, number> = {};
      for (const k of ["firstTaskMs", "loadMs", "generationMs"])
        if (
          Number.isSafeInteger(b.metrics?.[k]) &&
          b.metrics[k] >= 0 &&
          b.metrics[k] <= 86400000
        )
          metrics[k] = b.metrics[k];
      this.sql.exec(
        "UPDATE tasks SET state='pending',draft=?,submitted=?,reviewed=0,reviewer='',note='',metrics=? WHERE id=?",
        b.draft,
        now,
        JSON.stringify(metrics),
        b.id,
      );
      return json({ id: b.id, state: "pending" });
    }
    if (path === "/api/review") {
      if (!reviewer || mine)
        return json({ error: "Independent project reviewer required" }, 403);
      if (
        !old ||
        old.state !== "pending" ||
        !["accepted", "revision"].includes(b.state) ||
        typeof b.note !== "string" ||
        b.note.length > 1000 ||
        (b.state === "revision" && !b.note.trim())
      )
        return json({ error: "Invalid decision" }, 409);
      this.sql.exec(
        "UPDATE tasks SET state=?,reviewer=?,reviewed=?,note=? WHERE id=?",
        b.state,
        me.login,
        now,
        b.note,
        b.id,
      );
      return json({ id: b.id, state: b.state });
    }
    return json({ error: "Unknown route" }, 404);
  }
}
export default {
  async fetch(req: Request, env: Env) {
    return env.DESK.get(env.DESK.idFromName("community-v1")).fetch(req);
  },
};
