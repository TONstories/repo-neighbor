import "./style.css";
import catalog from "./tasks.json";
type Task = (typeof catalog)[number] & { available: boolean };
type Entry = {
  id: string;
  user: string;
  draft: string;
  state: string;
  note: string;
  claimed: number;
};
type Desk = {
  tasks: Task[];
  user?: string;
  loginReady: boolean;
  mine: Entry[];
  queue: Entry[];
  reviewer: boolean;
};
const el = <T extends HTMLElement>(id: string) =>
  document.getElementById(id) as T;
const tasks = el<HTMLSelectElement>("tasks"),
  draft = el<HTMLTextAreaElement>("draft"),
  notice = el("notice");
const model = "Qwen2.5-1.5B-Instruct-q4f16_1-MLC";
let desk: Desk = {
  tasks: catalog.map((t) => ({ ...t, available: true })),
  mine: [],
  queue: [],
  reviewer: false,
  loginReady: false,
};
let idleTimer: ReturnType<typeof setTimeout>;
function idle() {
  clearTimeout(idleTimer);
  idleTimer = setTimeout(async () => {
    if (busy) {
      idle();
      return;
    }
    if (engine) {
      await engine.unload();
      engine = undefined;
      el("progress").textContent = "Модель выгружена после 30 минут простоя.";
      select();
    }
  }, 1800000);
}
let engine: import("@mlc-ai/web-llm").MLCEngine | undefined,
  compatible = false,
  busy = false;
const metrics: Record<string, number> = {};
const os = el<HTMLSelectElement>("platform");
const guides: Record<string, string> = {
  iOS: "Откройте эту страницу в актуальном Safari. Оставьте вкладку на экране во время загрузки и перевода.",
  Android:
    "Откройте страницу в актуальном Chrome. Если браузер предлагает экономию памяти, оставьте вкладку активной.",
  Windows:
    "Откройте страницу в актуальном Edge или Chrome. Для WebGPU включите аппаратное ускорение браузера.",
  macOS:
    "Используйте актуальный Safari или Chrome с аппаратным ускорением. Оставьте вкладку открытой до квитанции.",
  Linux:
    "Используйте браузер с поддержкой WebGPU и рабочий драйвер GPU. Если адаптер недоступен, выберите ручной ввод.",
};
os.value = /Android/i.test(navigator.userAgent)
  ? "Android"
  : /iPhone|iPad/i.test(navigator.userAgent) ||
      (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)
    ? "iOS"
    : /Mac/i.test(navigator.platform)
      ? "macOS"
      : /Win/i.test(navigator.platform)
        ? "Windows"
        : "Linux";
function guide() {
  el("guide").textContent =
    guides[os.value] +
    " Нажмите «Загрузить модель», дождитесь готовности, затем «Выполнить и отправить». Для освобождения памяти нажмите «Удалить модель».";
}
os.onchange = guide;
guide();
const stateNames: Record<string, string> = {
  held: "Забронировано",
  pending: "На проверке",
  revision: "Нужна правка",
  accepted: "Принято",
};
async function api(path: string, body?: unknown) {
  const res = await fetch(
    "/api/" + path,
    body === undefined
      ? { cache: "no-store" }
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.error || "Ошибка сервера " + res.status);
  }
  return res.json();
}
const current = () => desk.tasks.find((t) => t.id === tasks.value);
const key = (id: string) => "rn-draft:" + (desk.user || "guest") + ":" + id;
function select() {
  el("recover").hidden =
    !desk.user || !localStorage.getItem("rn-outbox-v1:" + desk.user);
  const t = current();
  el("target").textContent = t ? "Перевести на " + t.lang : "Все места заняты";
  el("source").textContent =
    t?.source || "Вернитесь после проверки текущих работ.";
  draft.value = t
    ? (localStorage.getItem(key(t.id)) ??
      desk.mine.find((m) => m.id === t.id)?.draft ??
      "")
    : "";
  el<HTMLButtonElement>("generate").disabled = busy || !engine || !t;
  el<HTMLButtonElement>("send").disabled = busy || !t;
}
tasks.onchange = select;
draft.oninput = () => {
  if (tasks.value) localStorage.setItem(key(tasks.value), draft.value);
};
function node(tag: string, text: string) {
  const n = document.createElement(tag);
  n.textContent = text;
  return n;
}
function act(fn: () => Promise<void>) {
  return async () => {
    if (busy) return;
    busy = true;
    tasks.disabled = true;
    draft.disabled = true;
    try {
      await fn();
    } catch (e) {
      notice.textContent = String(e);
    } finally {
      busy = false;
      tasks.disabled = false;
      draft.disabled = false;
      select();
    }
  };
}
function entries(id: string, rows: Entry[], review = false) {
  const parent = el(id);
  parent.replaceChildren();
  for (const r of rows) {
    const card = node("article", "");
    card.append(
      node("h3", r.id + " · " + stateNames[r.state]),
      node("p", r.user),
      node("blockquote", desk.tasks.find((t) => t.id === r.id)?.source || ""),
      node("pre", r.draft),
      node("p", r.note),
    );
    if (review) {
      const note = document.createElement("input");
      note.placeholder = "Комментарий к решению";
      card.append(note);
      for (const [v, label] of [
        ["accepted", "Принять"],
        ["revision", "Нужна правка"],
      ]) {
        const b = node("button", label);
        b.onclick = act(async () => {
          await api("review", { id: r.id, state: v, note: note.value });
          await refresh();
        });
        card.append(b);
      }
    }
    parent.append(card);
  }
  if (!rows.length)
    parent.append(
      node(
        "p",
        review
          ? "Очередь пуста."
          : "Здесь появятся ваши задания и результаты проверки.",
      ),
    );
}
function render() {
  const last = tasks.value;
  tasks.replaceChildren();
  for (const t of desk.tasks.filter(
    (t) =>
      t.available ||
      desk.mine.some(
        (m) => m.id === t.id && ["held", "revision"].includes(m.state),
      ),
  ))
    tasks.add(new Option(t.lang + " · " + t.title, t.id));
  if ([...tasks.options].some((o) => o.value === last)) tasks.value = last;
  select();
  const a = el("account");
  a.replaceChildren();
  if (desk.user) {
    const b = node("button", desk.user + " · Выйти");
    b.onclick = act(async () => {
      await api("logout", {});
      localStorage.removeItem("rn-reservation");
      await refresh();
    });
    a.append(b);
  } else {
    const l = document.createElement("a");
    l.className = "login";
    l.href = "/auth/github";
    l.textContent = "Войти через GitHub";
    if (desk.loginReady) a.append(l);
    else a.append(node("span", "Вход настраивается"));
  }
  entries("history", desk.mine);
  el("review").hidden = !desk.reviewer;
  entries("queue", desk.queue, true);
}
async function refresh() {
  desk = await api("desk");
  const mine = desk.mine.find(
    (r) => r.state === "held" && r.claimed > Date.now() - 3600000,
  );
  if (mine)
    localStorage.setItem(
      "rn-reservation",
      JSON.stringify({ user: desk.user, id: mine.id, claimed: mine.claimed }),
    );
  else localStorage.removeItem("rn-reservation");
  render();
}
async function reserve(id: string) {
  if (navigator.onLine) {
    await api("claim", { id });
    await refresh();
    return;
  }
  const lease = JSON.parse(localStorage.getItem("rn-reservation") || "null");
  if (
    !lease ||
    lease.id !== id ||
    lease.user !== desk.user ||
    lease.claimed <= Date.now() - 3600000
  )
    throw Error("Чтобы взять задачу, подключитесь к сети.");
}
el("recover").onclick = act(async () => {
  const raw = localStorage.getItem(pendingKey());
  if (!raw) return;
  const job = JSON.parse(raw);
  localStorage.setItem(key(job.id), job.draft);
  const blob = URL.createObjectURL(
    new Blob([job.draft], { type: "text/plain" }),
  );
  const a = document.createElement("a");
  a.href = blob;
  a.download = job.id + ".txt";
  a.click();
  setTimeout(() => URL.revokeObjectURL(blob), 60000);
  localStorage.removeItem(pendingKey());
  notice.textContent = "Текст сохранен. Автоматическая отправка отменена.";
});
el("reserve").onclick = act(async () => {
  const t = current();
  if (t) {
    await reserve(t.id);
    notice.textContent = "Задача закреплена. Можно продолжить без сети.";
  }
});
const pendingKey = () => "rn-outbox-v1:" + desk.user;
async function flush() {
  const raw = localStorage.getItem(pendingKey());
  if (!raw) return;
  const job = JSON.parse(raw);
  if (job.user !== desk.user) return;
  await api("claim", { id: job.id });
  const receipt = await api("submit", job);
  localStorage.removeItem(pendingKey());
  localStorage.removeItem(key(job.id));
  notice.textContent =
    "Квитанция " + receipt.id + " · " + stateNames[receipt.state];
  await refresh();
}
async function send(useModel: boolean) {
  if (!desk.user) {
    notice.textContent = "Войдите через GitHub и вернитесь к задаче.";
    return;
  }
  if (localStorage.getItem(pendingKey())) {
    await flush();
    if (localStorage.getItem(pendingKey()))
      throw Error("В браузере сохранена отправка другого аккаунта.");
    return;
  }
  const t = current();
  if (!t || (!useModel && !draft.value.trim()))
    throw Error("Добавьте текст перевода.");
  if (useModel) {
    if (!engine) throw Error("Сначала загрузите модель.");
    await reserve(t.id);
    const start = performance.now();
    const reply = await engine.chat.completions.create({
      messages: [
        {
          role: "system",
          content:
            "Translate only the supplied public source into the indicated language. Preserve commands and numbers. Output only the translation.",
        },
        {
          role: "user",
          content: JSON.stringify({ language: t.lang, source: t.source }),
        },
      ],
      max_tokens: 384,
      temperature: 0,
    });
    draft.value = reply.choices[0]?.message.content?.trim() || "";
    metrics.generationMs = Math.round(performance.now() - start);
    idle();
  }
  if (!draft.value.trim())
    throw Error("Пустой ответ модели. Попробуйте вручную.");
  localStorage.setItem(key(t.id), draft.value);
  localStorage.setItem(
    pendingKey(),
    JSON.stringify({ id: t.id, user: desk.user, draft: draft.value, metrics }),
  );
  try {
    await flush();
  } catch (e) {
    throw Error(
      "Черновик сохранен. При восстановлении сети отправка повторится. " + e,
    );
  }
}
el("send").onclick = act(() => send(false));
el("generate").onclick = act(() => send(true));
window.addEventListener(
  "online",
  act(async () => {
    await refresh();
    await flush();
  }),
);
el("load").onclick = act(async () => {
  if (!compatible) throw Error("WebGPU недоступен.");
  const start = performance.now();
  el("progress").textContent = "Подготовка загрузки…";
  const lib = await import("@mlc-ai/web-llm");
  engine = await lib.CreateMLCEngine(
    model,
    { initProgressCallback: (p) => (el("progress").textContent = p.text) },
    { context_window_size: 1024 },
  );
  idle();
  metrics.loadMs = Math.round(performance.now() - start);
  el("progress").textContent = "Модель готова";
});
el("remove").onclick = act(async () => {
  if (engine) await engine.unload();
  engine = undefined;
  const lib = await import("@mlc-ai/web-llm");
  await lib.deleteModelAllInfoInCache(model);
  el("progress").textContent = "Модель удалена";
});
async function init() {
  render();
  try {
    const gpu = (
      navigator as Navigator & {
        gpu?: { requestAdapter(): Promise<{ features: Set<string> } | null> };
      }
    ).gpu;
    compatible = !!(await gpu?.requestAdapter())?.features.has("shader-f16");
  } catch {}
  el<HTMLButtonElement>("load").disabled = !compatible;
  el("device").textContent = compatible
    ? "Адаптер поддерживает WebGPU и shader-f16. Доступная память проверяется при загрузке."
    : "Совместимый GPU недоступен. Можно выполнить задачу вручную.";
  if (navigator.onLine) {
    await refresh();
  } else {
    const lease = JSON.parse(localStorage.getItem("rn-reservation") || "null");
    if (lease && lease.claimed > Date.now() - 3600000) {
      desk.user = lease.user;
      desk.tasks = desk.tasks.filter((t) => t.id === lease.id);
      render();
    }
  }
  metrics.firstTaskMs = Math.round(performance.now());
  if (navigator.onLine) await flush();
}
if ("serviceWorker" in navigator && location.protocol === "https:")
  navigator.serviceWorker.register("/sw.js").catch(() => {});
init().catch((e) => (notice.textContent = String(e)));
