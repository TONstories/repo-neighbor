// Shared admission and review rules for the translation desk.
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
async function gistStatement(seed: string, origin: string) {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(seed),
  );
  const proof = Array.from(new Uint8Array(digest), (b) =>
    b.toString(16).padStart(2, "0"),
  ).join("");
  return (
    "I am signing in to " +
    origin +
    " in my own browser. Repo Neighbor verification: " +
    proof
  );
}
type Env = {
  REVIEWER_IDS?: string;
  GITHUB_CLIENT_ID?: string;
  GITHUB_CLIENT_SECRET?: string;
  CAMPAIGN_BRIDGE?: string;
};
type CampaignHold = { id: string; issue: string; repo: string; login: string; until: number };
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
export type DeskStorage = {
  sql: { exec<T>(query: string, ...values: (string | number)[]): { toArray(): T[] } };
  transactionSync(fn: () => void): void;
};

export class DeskApp {
  sql: DeskStorage["sql"];
  constructor(
    private storage: DeskStorage,
    private env: Pick<Env, "REVIEWER_IDS" | "GITHUB_CLIENT_ID" | "GITHUB_CLIENT_SECRET" | "CAMPAIGN_BRIDGE">,
    private equal: (a: Uint8Array, b: Uint8Array) => boolean,
  ) {
    this.sql = storage.sql;
    this.sql.exec(
      "CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, uid TEXT, login TEXT, expires INTEGER)",
    );
    this.sql.exec(
      "CREATE TABLE IF NOT EXISTS gist_proofs (challenge TEXT PRIMARY KEY, expires INTEGER)",
    );
    this.sql.exec(
      "CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY,user TEXT,uid TEXT,state TEXT,draft TEXT,claimed INTEGER,submitted INTEGER,reviewed INTEGER,reviewer TEXT,note TEXT,metrics TEXT)",
    );
    this.sql.exec("CREATE TABLE IF NOT EXISTS campaign_holds (id TEXT PRIMARY KEY, issue TEXT, repo TEXT, login TEXT, until INTEGER)");
    this.sql.exec("CREATE TABLE IF NOT EXISTS leases (id TEXT PRIMARY KEY, token TEXT NOT NULL)");
  }
  session(account: { id: number; login: string }, now: number) {
    const session = token();
    this.sql.exec("DELETE FROM sessions WHERE expires<=?", now);
    this.sql.exec(
      "INSERT INTO sessions VALUES(?,?,?,?)",
      session,
      String(account.id),
      account.login,
      now + 86400000,
    );
    return setCookie("rn_session", session, 86400);
  }
  campaignHolds(now: number) {
    return this.sql.exec<CampaignHold>("SELECT * FROM campaign_holds WHERE until>?", now).toArray();
  }
  async campaign(r: Request, now: number) {
    const expected = this.env.CAMPAIGN_BRIDGE;
    const provided = r.headers.get("Authorization") || "";
    const enc = new TextEncoder();
    if (!expected || !/^Bearer [a-f0-9]{64}$/.test(provided) || expected.length !== 64 ||
        !this.equal(enc.encode("Bearer " + expected), enc.encode(provided)))
      return json({ error: "Unauthorized" }, 401);
    const raw = await r.text();
    if (raw.length > 2400) return json({ error: "Too large" }, 413);
    let b;
    try { b = JSON.parse(raw); } catch { return json({ error: "Invalid JSON" }, 400); }
    if (!b || typeof b.id !== "string" || !/^\d{1,16}$/.test(b.id))
      return json({ error: "Invalid request" }, 400);
    if (b.op === "release") {
      this.sql.exec("DELETE FROM campaign_holds WHERE id=?", b.id);
      return json({ ok: true });
    }
    if (b.op === "review") {
      this.sql.exec("UPDATE campaign_holds SET until=? WHERE id=?", 4102444800000, b.id);
      return json({ ok: true });
    }
    if (b.op !== "claim" || typeof b.issue !== "string" || typeof b.repo !== "string" ||
        typeof b.login !== "string" || !/^[a-z0-9-]{1,39}$/.test(b.login) ||
        !/^[a-z0-9_.-]+\/[a-z0-9_.-]+$/.test(b.repo) ||
        b.issue.slice(0, b.issue.lastIndexOf("/")) !== "https://github.com/" + b.repo + "/issues" ||
        !/\/[1-9]\d*$/.test(b.issue) ||
        !Number.isSafeInteger(b.until) || b.until <= now || b.until > now + 86400000)
      return json({ error: "Invalid hold" }, 400);
    const campaign = this.campaignHolds(now);
    const existing = campaign.find((hold) => hold.id === b.id);
    if (existing)
      return existing.issue === b.issue && existing.login === b.login
        ? json({ ok: true }) : json({ error: "Conflicting claim ID" }, 409);
    const mobile = this.busy(now);
    if (campaign.some((hold) => hold.issue === b.issue ||
          (hold.login === b.login && hold.until < 4102444800000)) ||
        mobile.some((row) => (row.user.toLowerCase() === b.login && row.state === "held") ||
          taskById.get(row.id)?.issue.toLowerCase() === b.issue) ||
        campaign.filter((hold) => hold.repo === b.repo).length +
          mobile.filter((row) => taskById.get(row.id)?.repo.toLowerCase() === b.repo).length >= 3)
      return json({ error: "Task or review slots are occupied" }, 409);
    this.sql.exec("DELETE FROM campaign_holds WHERE until<=?", now);
    this.sql.exec("INSERT INTO campaign_holds VALUES(?,?,?,?,?)", b.id, b.issue, b.repo, b.login, b.until);
    return json({ ok: true });
  }
  busy(now: number) {
    return this.sql.exec<Row>("SELECT * FROM tasks WHERE state IN ('pending','revision') OR (state='held' AND claimed>?)", now-3600000).toArray();
  }
  async fetch(r: Request) {
    const u = new URL(r.url),
      path = u.pathname,
      now = Date.now();
    if (path === "/api/campaign" && r.method === "POST") return this.campaign(r, now);
    if (r.method === "POST" && r.headers.get("Origin") !== u.origin)
      return json({ error: "Origin mismatch" }, 403);
    const sid = cookie(r, "rn_session") || "";
    const me = this.sql
      .exec<{
        uid: string;
        login: string;
      }>(
        "SELECT uid, login FROM sessions WHERE token=? AND expires>?",
        sid,
        now,
      )
      .toArray()[0];
    const reviewer =
      !!me &&
      (this.env.REVIEWER_IDS || "")
        .split(",")
        .map((s) => s.trim())
        .includes(me.uid);
    if (path === "/api/gist-start" && r.method === "POST") {
      const seed = now + "." + token();
      const response = json({ statement: await gistStatement(seed, u.origin) });
      response.headers.append(
        "Set-Cookie",
        setCookie("__Host-rn_proof", seed, 600),
      );
      return response;
    }
    if (path === "/api/gist-finish" && r.method === "POST") {
      const seed = cookie(r, "__Host-rn_proof") || "";
      const issued = Number(seed.split(".")[0]);
      if (
        !/^\d{13}\.[a-f0-9-]{72}$/.test(seed) ||
        issued > now ||
        now - issued >= 600000
      )
        return json(
          { error: "Время подтверждения истекло. Начните вход заново." },
          403,
        );
      // The public proof is browser-bound. Never follow an address supplied by the client.
      const id = u.searchParams.get("id") || "";
      if (!/^[a-f0-9]{32}$/.test(id))
        return json({ error: "Проверьте ссылку на Gist." }, 400);
      const gh = await fetch("https://api.github.com/gists/" + id, {
        headers: {
          "User-Agent": "Repo-Neighbor",
          Accept: "application/vnd.github+json",
        },
      });
      if (!gh.ok)
        return json(
          {
            error:
              gh.status === 404
                ? "GitHub не нашел Gist. Проверьте ссылку."
                : "GitHub временно недоступен. Попробуйте позже.",
          },
          gh.status === 404 ? 404 : 503,
        );
      const gist = (await gh.json()) as {
        owner?: { id: number; login: string };
        files?: Record<string, { content?: string; truncated?: boolean }>;
      };
      const statement = await gistStatement(seed, u.origin);
      if (
        !gist.owner ||
        !Number.isSafeInteger(gist.owner.id) ||
        !/^[a-z0-9-]{1,39}$/i.test(gist.owner.login) ||
        !Object.values(gist.files || {}).some(
          (file) => !file.truncated && file.content?.trim() === statement,
        )
      )
        return json(
          {
            error:
              "В этом Gist нет строки подтверждения для текущего браузера.",
          },
          403,
        );
      const finished = Date.now();
      this.sql.exec("DELETE FROM gist_proofs WHERE expires<=?", finished);
      if (
        finished >= issued + 600000 ||
        !this.sql
          .exec(
            "INSERT OR IGNORE INTO gist_proofs VALUES(?,?) RETURNING challenge",
            statement,
            issued + 600000,
          )
          .toArray().length
      )
        return json(
          { error: "Подтверждение уже использовано или истекло." },
          403,
        );
      const response = json({ ok: true });
      response.headers.append("Set-Cookie", this.session(gist.owner, finished));
      response.headers.append(
        "Set-Cookie",
        setCookie("__Host-rn_proof", "", 0),
      );
      return response;
    }
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
      const h = new Headers({ Location: "/", "Cache-Control": "no-store" });
      h.append("Set-Cookie", this.session(account, now));
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
      const all = rows(), held = this.busy(now), campaign = this.campaignHolds(now);
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
            !campaign.some((hold) => hold.issue === t.issue.toLowerCase()) &&
            held.filter((x) => taskById.get(x.id)?.repo === t.repo).length +
              campaign.filter((hold) => hold.repo === t.repo.toLowerCase()).length < 3,
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
    if (b.lease !== undefined && (typeof b.lease !== "string" || !/^[a-f0-9]{32}$/.test(b.lease)))
      return json({ error: "Invalid reservation identifier" }, 400);
    const lease = this.sql.exec<{token: string}>("SELECT token FROM leases WHERE id=?", b.id).toArray()[0]?.token;
    const active = old?.state === "held" && old.claimed > now - 3600000;
    if (path === "/api/release") {
      if (!mine || !active || lease !== b.lease)
        return json({ id: b.id, state: old?.state });
      this.storage.transactionSync(() => {
        this.sql.exec("DELETE FROM tasks WHERE id=?", b.id);
        this.sql.exec("DELETE FROM leases WHERE id=?", b.id);
      });
      return json({ id: b.id, state: "released" });
    }
    if (path === "/api/claim") {
      if (mine && old?.state !== "held")
        return json({ id: b.id, state: old?.state });
      const busy = this.busy(now), campaign = this.campaignHolds(now);
      const task = taskById.get(b.id)!;
      if (
        campaign.some((hold) => hold.issue === task.issue.toLowerCase() ||
          (hold.login === me.login.toLowerCase() && hold.until < 4102444800000)) ||
        (active && lease !== b.lease) ||
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
        ).length + campaign.filter((hold) => hold.repo === task.repo.toLowerCase()).length >= 3
      )
        return json({ error: "Task or review slots are occupied" }, 409);
      if (!mine || !old || old.claimed <= now - 3600000)
        this.storage.transactionSync(() => {
          this.sql.exec(
            "INSERT OR REPLACE INTO tasks VALUES(?,?,?,'held','',?,0,0,'','','{}')",
            b.id, me.login, me.uid, now,
          );
          this.sql.exec("DELETE FROM leases WHERE id=?", b.id);
          if (b.lease)
            this.sql.exec("INSERT INTO leases VALUES(?,?)", b.id, b.lease);
        });
      return json({ id: b.id, state: "held" });
    }
    if (path === "/api/submit") {
      if (!old || !mine || (old.state === "held" && lease !== b.lease))
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
