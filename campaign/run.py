"""Publish and reconcile the Repo Neighbor board. Run from the repository root."""

import community
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "skills/repo-neighbor/scripts")
)
from finder import (
    SLUG,
    URL,
    assess,
    discover,
    graph,
    live_issue,
    live_issues,
    metadata,
    reviews,
)

HOME = "TONstories/repo-neighbor"
BASE = "https://github.com/" + HOME
DIR = Path("campaigns")
COMMAND = re.compile(
    r"(?:rn|qfg) (claim|release|submit) (https://github\.com/\S+)(?: (\S+))?", re.ASCII
)
UTC = timezone.utc


def load(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def save(path, data):
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )


def week_key(now):
    local = now.astimezone(timezone(timedelta(hours=3)))
    year, week, _ = (local - timedelta(hours=9, minutes=15)).isocalendar()
    return f"{year}-W{week:02d}"


def slots(window, claims, now, repo):
    used = sum(
        c["repo"] == repo and c["status"] == "held" and c["until"] > now.isoformat()
        for c in claims
    )
    return (
        max(0, window["limit"] - len(window["open"]) - used)
        if window["complete"]
        else 0
    )


def compatible(items, item):
    words = lambda t: set(re.findall(r"[a-z0-9]{3,}", t.lower()))
    for old in items:
        a, b = words(old["title"]), words(item["title"])
        if (
            set(old["scope"]) & set(item["scope"])
            or len(a & b) / max(1, len(a | b)) >= 0.55
        ):
            return False
    return True


def select(now, editor, existing, claims):
    today = now.date()
    excluded = {r.lower() for r in editor.get("exclude", [])}
    overrides = editor["override"]
    pins = overrides.get("pin", [])
    for name in [*pins, *excluded]:
        if not re.fullmatch(SLUG, name):
            raise ValueError("Invalid editor repository")
    if len(set(pins)) != len(pins) or len(pins) > 3:
        raise ValueError("Up to 3 unique pins")
    by_repo = {}
    preferences = list(pins)
    if existing is None:
        preferences += [
            r
            for r in editor.get("ranked", [])
            if r.lower() not in {p.lower() for p in pins} and r.lower() not in excluded
        ]
    seat_order = []
    for repo in preferences[:12]:
        rows = discover([], repo, 100, today, 180, 10)["candidates"]
        if rows:
            canonical = rows[0]["repo"]
            if canonical not in seat_order:
                seat_order.append(canonical)
            by_repo[canonical] = list(rows)
    preferences = seat_order
    if existing is None:
        for row in discover([], None, 150, today, 180, 10)["candidates"]:
            by_repo.setdefault(row["repo"], []).append(row)
    else:
        for project in existing:
            name = project["repo"]
            if name in by_repo or name.lower() in excluded:
                continue
            fresh = []
            for row in live_issues([t["url"] for t in project["tasks"]]):
                if row:
                    item = assess(row, name, *metadata(name), today, minutes=180)
                    if item:
                        fresh.append(item)
            if len(fresh) < 2 and len(project["tasks"]) >= 2:
                fresh.extend(discover([], name, 36, today, 180, 10)["candidates"])
            by_repo[name] = fresh
    result = []
    for repo, rows in by_repo.items():
        if repo.lower() in excluded:
            continue
        tasks = []
        for row in rows:
            if row["url"] not in [t["url"] for t in tasks] and compatible(tasks, row):
                tasks.append(row)
            if len(tasks) == 18:
                break
        if len(tasks) < (2 if existing is None or repo in pins else 1):
            continue
        window = reviews(repo, today)
        if existing is None and not slots(window, claims, now, repo):
            continue
        result.append(dict(repo=repo, tasks=tasks, window=window))
    result.sort(
        key=lambda p: (
            preferences.index(p["repo"])
            if p["repo"] in preferences
            else len(preferences),
            -min(5, len(p["tasks"])),
            -sum(t["score"] for t in p["tasks"][:2]),
            p["repo"],
        )
    )
    return result[:3]


def upstream_pr(url):
    match = URL.fullmatch(url)
    if not match or match[2] != "pull" or int(match[3]) > 2147483647:
        raise ValueError("Expected pull request URL")
    owner, repo = match[1].split("/")
    return graph(
        """query($o:String!,$n:String!,$i:Int!){repository(owner:$o,name:$n){
      pullRequest(number:$i){state mergedAt url body author{login} closingIssuesReferences(first:50){nodes{url}}}}}""",
        o=owner,
        n=repo,
        i=int(match[3]),
    )["repository"]["pullRequest"]


def transition(command, user, claims, week, projects, now, requires=None):
    match = COMMAND.fullmatch(command)
    if not match:
        return "Invalid command. See the campaign guide."
    op, url, arg = match.groups()
    source = URL.fullmatch(url)
    if not source or source[2] != "issues":
        return "Expected a GitHub issue URL."
    repo = source[1]
    owned = next(
        (
            c
            for c in reversed(claims)
            if c["user"] == user and c["issue"] == url and c["status"] == "held"
        ),
        None,
    )
    if op == "submit":
        if (
            not owned
            or not arg
            or not URL.fullmatch(arg)
            or (URL.fullmatch(arg)[1], URL.fullmatch(arg)[2]) != (repo, "pull")
        ):
            return "Supply your reserved issue and a PR from the same repository."
        if any(c.get("pr") == arg for c in claims):
            return "PR already recorded."
        try:
            pr = upstream_pr(arg)
        except ValueError:
            return "Invalid pull request URL."
        except RuntimeError as err:
            if "Could not resolve" in str(err):
                return "Pull request not found."
            raise
        from quota import has_credit

        if (
            not pr
            or (pr["author"] or {}).get("login") != user
            or not has_credit(pr["body"])
        ):
            return "PR author or required visible attribution did not match."
        refs = {r["url"] for r in pr["closingIssuesReferences"]["nodes"]}
        if url not in refs and not re.search(re.escape(url) + r"(?![\w/])", pr["body"]):
            return "Link the issue in the PR description."
        owned.update(
            status=pr["state"].lower(),
            pr=arg,
            submitted_at=now.isoformat(),
            merged_at=pr.get("mergedAt"),
        )
        return "PR recorded."
    if op == "release":
        if not owned or arg:
            return "No matching reservation to release."
        owned["status"] = "released"
        return "Released."
    if not arg or not arg.isdigit() or len(arg) > 4 or not 1 <= int(arg) <= 1440:
        return "Use a session length between 1 and 1440 minutes."
    active = [
        c
        for c in claims
        if c["status"] == "open"
        or (c["status"] == "held" and c["until"] > now.isoformat())
    ]
    if any(c["issue"] == url for c in active):
        return "Already taken. Choose another issue."
    if any(c["user"] == user and c["status"] == "held" for c in active):
        return "Finish or release your current reservation."
    project = next(
        (p for p in projects if any(t["url"] == url for t in p["tasks"])), None
    )
    if not project:
        return "Issue is not listed in the current campaign."
    blockers = [
        link
        for link in (requires or {}).get(url, [])
        if not any(c["issue"] == link and c["status"] == "merged" for c in claims)
    ]
    if blockers:
        return "Waiting for accepted prerequisites: " + " ".join(blockers)
    issue = live_issue(url)
    if not issue or not assess(
        issue, repo, *metadata(repo), now.date(), minutes=int(arg), reserve=0
    ):
        return "Issue is unavailable or does not fit this session."
    window = reviews(repo, now.date())
    if slots(window, claims, now, repo) < 1:
        return "Review capacity is full or unknown."
    task = next(t for t in project["tasks"] if t["url"] == url)
    if any(
        c["repo"] == repo
        and (
            c["issue"] == task.get("parent")
            or c.get("parent") == url
            or set(c.get("scope", [])) & set(task.get("scope", []))
        )
        for c in active
    ):
        return "An overlapping work package is already reserved or in review."
    until = now + timedelta(minutes=min(1440, int(arg) + 60))
    claims.append(
        dict(
            issue=url,
            repo=repo,
            user=user,
            week=week,
            status="held",
            claimed_at=now.isoformat(),
            estimate=task.get("minutes"),
            scope=task.get("scope", []),
            parent=task.get("parent"),
            until=until.isoformat(),
        )
    )
    return "Reserved until " + until.isoformat()


def inbox():
    owner, name = HOME.split("/")
    q = """query($o:String!,$n:String!,$cursor:String){repository(owner:$o,name:$n){
      issues(first:100,states:OPEN,after:$cursor,orderBy:{field:CREATED_AT,direction:ASC}){
      nodes{number title createdAt lastEditedAt author{login}} pageInfo{endCursor hasNextPage}}}}"""
    args = {"o": owner, "n": name}
    while True:
        page = graph(q, **args)["repository"]["issues"]
        yield from page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            return
        args["cursor"] = page["pageInfo"]["endCursor"]


def safe(text):
    # Third-party issue titles must render as plain text in a public board.
    return re.sub(r"([^\w\s])", r"\\\1", " ".join(text.split()))


def render(week, projects, claims, now, override, lang):
    copy = {
        "en": (
            "Projects of the week",
            "Review capacity",
            "decisions in 28 days",
            "open external PRs",
            "free slots",
            "Reserve",
            "Accepted improvements",
            "In review",
            "No eligible projects",
            "Independent tasks requested by contributors",
            "Stack",
            "Check",
            "confirm in target CI",
        ),
        "ru": (
            "Проекты недели",
            "Нагрузка на ревью",
            "решения за 28 дней",
            "открытые внешние PR",
            "свободные места",
            "Забронировать",
            "Принятые улучшения",
            "На ревью",
            "Подходящих проектов нет",
            "Независимые задачи, для которых ищут участников",
            "Стек",
            "Проверка",
            "уточните в CI проекта",
        ),
        "es": (
            "Proyectos de la semana",
            "Capacidad de revisión",
            "decisiones en 28 días",
            "PR externos abiertos",
            "plazas libres",
            "Reservar",
            "Mejoras aceptadas",
            "En revisión",
            "Sin proyectos elegibles",
            "Tareas independientes que buscan colaboradores",
            "Lenguajes",
            "Prueba",
            "consulta la CI del proyecto",
        ),
    }[lang]
    (
        title,
        capacity,
        decisions,
        opened,
        free,
        reserve,
        merged,
        pending,
        empty,
        goal,
        stack,
        check,
        unknown,
    ) = copy
    lines = [
        f"# {title} · {week}",
        "",
        "[EN](board.md) · [RU](board.ru.md) · [ES](board.es.md) · [Guide](../../guide.md)",
        "",
    ]
    weekly_goal = override.get("goal", {}).get(lang)
    if weekly_goal:
        lines.extend([weekly_goal, ""])
    for p in projects:
        repo = p["repo"]
        w = p["window"]
        note = override.get("descriptions", {}).get(repo, {})
        lines.extend(
            [
                f"## [{repo}](https://github.com/{repo})",
                "",
                note.get(lang, goal),
                "",
                f"{capacity} · {decisions}: {w['decisions']} · {opened}: {len(w['open'])} · **{free}: {slots(w, claims, now, repo)}**.",
                "",
            ]
        )
        for t in p["tasks"]:
            active = next(
                (
                    c
                    for c in reversed(claims)
                    if c["issue"] == t["url"]
                    and c["status"] in ("held", "open", "merged")
                ),
                None,
            )
            link = (
                BASE
                + "/issues/new?"
                + urlencode(
                    {
                        "title": "rn claim " + t["url"] + " 90",
                        "body": "Repo Neighbor campaign reservation.",
                    }
                )
            )
            action = (
                ("[%s](%s)" % (reserve, link))
                if not active
                and slots(w, claims, now, repo) > 0
                and week == week_key(now)
                else (
                    safe(active["user"] + " · " + active["status"]) if active else "—"
                )
            )
            lines.append(f"- [{safe(t['title'])}]({t['url']}) · {action}<br>")
            lines.append(
                f"  {stack}: {safe(', '.join(t['stack']) or '?')} · {check}: {safe(' / '.join(t['checks']) or unknown)}"
            )
        lines.append("")
    if not projects:
        lines.extend([empty, ""])
    for state, heading in (("merged", merged), ("open", pending)):
        items = [c for c in claims if c["week"] == week and c["status"] == state]
        lines.extend(
            [f"## {heading} · {len(items)}", ""]
            + [f"- [{c['pr']}]({c['pr']})" for c in items]
            + [""]
        )
    return "\n".join(lines).rstrip() + "\n"


def refresh_claims(claims, now):
    for c in claims:
        if c["status"] == "held" and c["until"] <= now.isoformat():
            c["status"] = "expired"
        if c["status"] in ("open", "closed"):
            pr = upstream_pr(c["pr"])
            if pr:
                c["status"] = pr["state"].lower()
                c["merged_at"] = pr.get("mergedAt")


def run(now):
    week = week_key(now)
    editor = load(DIR / "editor.json", {})
    override = editor["weeks"].get(week, {})
    folder = DIR / "archive" / week
    folder.mkdir(parents=True, exist_ok=True)
    board = folder / "projects.json"
    ledger = load(DIR / "ledger.json", {"claims": [], "receipts": {}})
    claims = ledger["claims"]
    refresh_claims(claims, now)
    requests = list(inbox())
    for request in requests:
        key = str(request["number"])
        title = request["title"]
        if key in ledger["receipts"] or not title.startswith(
            ("rn nominate ", "rn vote ", "rn pledge ")
        ):
            continue
        user = (request["author"] or {}).get("login")
        if user:
            at = community.parse(
                request.get("lastEditedAt")
                or request.get("createdAt")
                or now.isoformat()
            )
            ledger["receipts"][key] = community.command(
                title, user, at, ledger, metadata, issue_number=request["number"]
            )
    election = ledger.setdefault("elections", {}).setdefault(
        week, {"nominees": {}, "votes": {}}
    )
    projects = select(
        now,
        {
            "exclude": editor["exclude"] + override.get("exclude", []),
            "override": override,
            "ranked": community.ranking(election),
        },
        load(folder / "selection.json", load(board, None)),
        claims,
    )
    if not (folder / "selection.json").exists():
        save(folder / "selection.json", projects)
    if not election.get("closed"):
        election.update(closed=True, selected=[p["repo"] for p in projects])
    for request in requests:
        key = str(request["number"])
        if (
            not request["title"].startswith(("qfg ", "rn "))
            or key in ledger["receipts"]
        ):
            continue
        user = (request["author"] or {}).get("login")
        if user:
            ledger["receipts"][key] = transition(
                request["title"],
                user,
                claims,
                week,
                projects,
                now,
                override.get("requires", {}),
            )
    community.reports(DIR, ledger, projects, now, override)
    save(board, projects)
    save(DIR / "ledger.json", ledger)
    for data in sorted((DIR / "archive").glob("*/projects.json")):
        key = data.parent.name
        for lang, file in (
            ("en", "board.md"),
            ("ru", "board.ru.md"),
            ("es", "board.es.md"),
        ):
            (data.parent / file).write_text(
                render(
                    key, load(data, []), claims, now, editor["weeks"].get(key, {}), lang
                )
            )
    (DIR / "README.md").write_text(
        "# Projects of the week · Проекты недели · Proyectos de la semana\n\n"
        + " · ".join(
            f"[{lang}](archive/{week}/{file})"
            for lang, file in (
                ("English", "board.md"),
                ("Русский", "board.ru.md"),
                ("Español", "board.es.md"),
            )
        )
        + "\n\n[Community, voting and impact](reports/README.md) · [Archive](archive) · [Participation and editing](guide.md) · [Reservation receipts](ledger.json)\n"
    )


if __name__ == "__main__":
    run(datetime.now(UTC))
