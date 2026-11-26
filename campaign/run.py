"""Publish and reconcile the Repo Neighbor board. Run from the repository root."""

import balance
import community
import time
import copy
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "skills/repo-neighbor/scripts")
)
from finder import (
    ApprovalCoverageIncomplete,
    DEFAULT_BOARD_REVIEW_LIMIT,
    GRAPH_CALLS,
    GitHubRateLimited,
    MIN_REPO_STARS,
    URL,
    assess,
    complete_issue_discussion,
    discover,
    graph,
    live_issue,
    live_issues,
    metadata,
    project_approval,
    required_actions,
    reviews,
)

HOME = "TONstories/repo-neighbor"
BASE = "https://github.com/" + HOME
DIR = Path("campaigns")
COMMAND = re.compile(
    r"(?:rn|qfg) (claim|release|submit|handoff|feedback) (https://github\.com/\S+)(?: (\S+))?", re.ASCII
)
UTC = timezone.utc
APPROVAL_UNVERIFIED = "Could not verify recent PR approval because GitHub review coverage is incomplete."


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


def qualify(source, repo, user, detail):
    if source == "maintainer":
        matches = re.findall(r"https://github[.]com/" + re.escape(repo)
                             + r"/issues/([1-9][0-9]{0,9})\b", detail, re.I)
        if len(matches) != 1 or int(matches[0]) > 2147483647:
            return False
        owner, name = repo.split("/")
        query = """query($o:String!,$n:String!,$i:Int!){repository(owner:$o,name:$n){
          issue(number:$i){author{login} authorAssociation body labels(first:30){nodes{name}}}}}"""
        issue = (graph(query, o=owner, n=name, i=int(matches[0]))["repository"] or {}).get("issue") or {}
        return ((issue.get("author") or {}).get("login", "").casefold() == user.casefold()
                and issue.get("authorAssociation") in {"OWNER", "MEMBER", "COLLABORATOR"}
                and any(label["name"].casefold() == "repo-neighbor"
                        for label in issue["labels"]["nodes"])
                and f"I invite Repo Neighbor to contribute to {repo}" in issue.get("body", ""))
    if not any(path.rsplit("/", 1)[-1] == "CONTRIBUTING.md" and content.strip()
               for path, content in detail.items()):
        return False
    candidates = discover([], repo, 10, datetime.now(UTC).date(), 180, 10)["candidates"]
    ready = [candidate for candidate in candidates if not required_actions(candidate)]
    return any(compatible([a], b) for i, a in enumerate(ready) for b in ready[i+1:])


def select(now, editor, existing, claims):
    today = now.date()
    excluded = {r.lower() for r in editor.get("exclude", [])}
    ranked = editor.get("ranked", [])
    by_repo = {}
    proposals = editor.get("proposals", {})
    previous_caps = {p["repo"].casefold(): p.get("review_limit", DEFAULT_BOARD_REVIEW_LIMIT) for p in existing or []}
    skipped = editor.setdefault("skipped", {})
    if existing is None:
        coverage = editor["discovery"] = {}

        def search(name, limit):
            report = discover([], name, limit, today, 180, 10, report_errors=True, as_of=now)
            source = name.casefold() if name else "global"
            coverage[source] = {key: report[key] for key in (
                "search_status", "coverage_limits", "api_errors", "queries_completed",
            )}
            if "github_rate_limit" in report["coverage_limits"]:
                raise GitHubRateLimited(f"GitHub API rate limit during weekly discovery ({source})")
            return report["candidates"]

        def add(name):
            if name.lower() in excluded or name.lower() in by_repo:
                return
            by_repo[name.lower()] = list(search(name, 60))

        for name in ranked:
            add(name)
        for name, proposal in proposals.items():
            if name in excluded or not proposal.get("tasks"):
                continue
            meta, files = metadata(name)
            items = [assess(issue, meta["nameWithOwner"], meta, files, today, minutes=180)
                     for issue in live_issues(proposal["tasks"][:18])] if meta else []
            by_repo[name] = [item for item in items if item]
        for name in editor.get("discovery_seeds", []):
            add(name)
        rotation = community.start(now).date().toordinal() // 7
        for tags in balance.TOPICS.values():
            tag = tags[rotation % len(tags)]
            query = "query($q:String!){search(type:REPOSITORY,first:3,query:$q){nodes{... on Repository{nameWithOwner}}}}"
            for node in graph(query, q=f"topic:{tag} stars:>={MIN_REPO_STARS} archived:false fork:false good-first-issues:>0 sort:updated")["search"]["nodes"]:
                add(node["nameWithOwner"])
        for row in search(None, 150):
            by_repo.setdefault(row["repo"].lower(), []).append(row)
    else:
        for project in existing:
            name = project["repo"]
            key = name.casefold()
            if key in by_repo or key in excluded:
                continue
            fresh = []
            for row in live_issues([t["url"] for t in project["tasks"]]):
                if row:
                    item = assess(row, name, *metadata(name), today, minutes=180)
                    if item:
                        fresh.append(item)
            by_repo[key] = fresh
    result = []
    for repo, rows in by_repo.items():
        if repo.lower() in excluded:
            skipped[repo] = "Already selected"
            continue
        if not rows:
            status = editor.get("discovery", {}).get(repo, {}).get("search_status")
            skipped[repo] = {
                "partial": "Issue search incomplete",
                "api_error": "Issue search failed",
            }.get(status, "No eligible issues")
            continue
        canonical = rows[0]["repo"]
        meta, files = metadata(canonical)
        if meta.get("incomplete_policy_files"):
            skipped[repo] = "Contribution rules could not be verified"
            continue
        try:
            approval = project_approval(canonical, meta, now)
        except ApprovalCoverageIncomplete:
            skipped[repo] = APPROVAL_UNVERIFIED
            editor.setdefault("approval_unverified", []).append(repo)
            continue
        if not approval:
            skipped[repo] = "Requires 100 GitHub stars and a verified PR approval in the last 72 hours"
            continue
        category = balance.track(meta)
        if (existing is None and editor.get("version") == 2
            and proposals.get(repo.lower(), {}).get("source") != "maintainer"
            and not any(path.rsplit("/", 1)[-1] == "CONTRIBUTING.md" and content.strip()
                        for path, content in files.items())):
            skipped[repo] = "No published contribution rules or verified maintainer proposal"
            continue
        tasks = []
        for row in sorted(rows, key=lambda candidate: bool(required_actions(candidate))):
            if category == "defensive-security" and row.get("kind") != "docs":
                continue
            if row["url"] not in [t["url"] for t in tasks] and compatible(tasks, row):
                tasks.append(row)
            if len(tasks) == 18:
                break
        if len(tasks) < (2 if existing is None else 1):
            skipped[repo] = "Insufficient independent tasks"
            continue
        if existing is None and sum(not required_actions(task) for task in tasks) < 2:
            skipped[repo] = "Insufficient independent tasks ready to reserve"
            continue
        review_limit = proposals.get(repo.casefold(), {}).get("review_limit", previous_caps.get(repo.casefold(), DEFAULT_BOARD_REVIEW_LIMIT))
        window = reviews(repo, today)
        window = dict(window, limit=min(window["limit"], review_limit))
        if existing is None and not slots(window, claims, now, repo):
            skipped[repo] = "No review capacity" if window["complete"] else "Review capacity could not be verified"
            continue
        if existing is None and editor.get("version") == 2:
            tasks = tasks[:max(2, 2 * slots(window, claims, now, repo))]
        result.append(dict(repo=canonical, tasks=tasks, window=window, stars=meta["stargazerCount"],
                           recent_approval=approval,
                           track=category, review_limit=review_limit))
    if existing is not None:
        return result
    if editor.get("version") == 2:
        editor["pool"] = [dict(repo=p["repo"], track=p["track"], tasks=[
            {"score": t["score"], "minutes": t.get("minutes")} for t in p["tasks"]]) for p in result]
        chosen, editor["reasons"] = balance.allocate_minutes(
            result, ranked, editor["limit"], editor["history"], editor["replacement"])
        return chosen
    editor["pool"] = [dict(repo=p["repo"], track=p["track"], tasks=[{"score": t["score"]} for t in p["tasks"][:2]]) for p in result]
    return balance.allocate(result, ranked, editor.get("limit", 3), editor.get("history", []))


def upstream_pr(url):
    match = URL.fullmatch(url)
    if not match or match[2] != "pull" or int(match[3]) > 2147483647:
        raise ValueError("Expected pull request URL")
    owner, repo = match[1].split("/")
    return graph(
        """query($o:String!,$n:String!,$i:Int!){repository(owner:$o,name:$n){
      pullRequest(number:$i){state mergedAt mergedBy{login} url body author{login} closingIssuesReferences(first:50){nodes{url}}}}}""",
        o=owner,
        n=repo,
        i=int(match[3]),
    )["repository"]["pullRequest"]


def transition(command, user, claims, week, projects, now, requires=None, body="", number=None):
    match = COMMAND.fullmatch(command)
    if not match:
        return "Invalid command. See the campaign guide."
    op, url, arg = match.groups()
    source = URL.fullmatch(url)
    if op == "feedback":
        row = next((c for c in claims if c.get("pr") == url and c.get("merged_at")), None)
        values = re.fullmatch(r"(solved|partial|unresolved) ([0-9]{1,5}) ([0-9]{1,5})", " ".join(body.split()))
        if not row or arg or not values or not number:
            return "Use a recorded merged PR. Body: solved|partial|unresolved saved_minutes review_minutes."
        pr = upstream_pr(url)
        merger = ((pr or {}).get("mergedBy") or {}).get("login", "")
        if user.casefold() not in {row["repo"].split("/")[0].casefold(), merger.casefold()}:
            return "Only the repository owner or the GitHub merge actor can report the outcome."
        row["feedback"] = dict(outcome=values[1], saved=int(values[2]), review=int(values[3]), by=user, issue=number)
        return "Feedback recorded."
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
    if op == "handoff":
        latest = next((c for c in reversed(claims) if c["issue"] == url), None)
        if not latest or latest["user"] != user or latest["status"] not in ("held", "expired"):
            return "Only the latest reservation holder can hand off unfinished work."
        fields = [line.strip() for line in body.splitlines() if line.strip()]
        if arg or not number or len(fields) != 3 or not re.fullmatch(
            r"https://github[.]com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/(?:pull/[0-9]+|(?:tree|commit)/[^\s]+)", fields[0]
        ):
            return "Supply three lines: public branch, commit or draft PR URL; checks and result; next step."
        latest.update(status="released", handoff=number)
        return "Handoff recorded. Reservation released."
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
    if any(c["user"].casefold() == user.casefold() and c["status"] == "held" for c in active):
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
    meta, files = metadata(repo)
    if meta.get("incomplete_policy_files"):
        return "Cannot verify the full contribution rules for this reservation."
    try:
        approval = project_approval(repo, meta, now)
    except ApprovalCoverageIncomplete:
        return APPROVAL_UNVERIFIED
    if not approval:
        return "The repository needs at least 100 GitHub stars and a verified PR approval in the last 72 hours."
    if issue:
        issue = complete_issue_discussion(issue)
        if issue is None:
            return "Cannot verify the complete issue discussion for this reservation."
    eligible = issue and assess(issue, repo, meta, files, now.date(), minutes=int(arg), reserve=0)
    if not eligible:
        return "Issue is unavailable or does not fit this session."
    if actions := required_actions(eligible):
        return "Upstream prerequisites need confirmation before reserving: " + " ".join(actions)
    window = reviews(repo, now.date())
    review_limit = project.get("review_limit", DEFAULT_BOARD_REVIEW_LIMIT)
    window = dict(window, limit=min(window["limit"], review_limit))
    if window.get("open_complete") and len(window["open"]) >= review_limit:
        return "Review capacity is full."
    if (sum(c["repo"].casefold() == repo.casefold() for c in active) >= review_limit
            or slots(window, claims, now, repo) < 1):
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
    handoff = next((c["handoff"] for c in reversed(claims) if c["issue"] == url and c.get("handoff")), None)
    return "Reserved until " + until.isoformat() + (f". Handoff: {BASE}/issues/{handoff}" if handoff else "")


def inbox():
    owner, name = HOME.split("/")
    q = """query($o:String!,$n:String!,$cursor:String){repository(owner:$o,name:$n){
      issues(first:100,states:OPEN,after:$cursor,orderBy:{field:CREATED_AT,direction:ASC}){
      nodes{number title body createdAt lastEditedAt author{login}} pageInfo{endCursor hasNextPage}}}}"""
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
            "Confirm before starting",
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
            "Подтвердите до начала работы",
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
            "Confirma antes de empezar",
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
        confirm_first,
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
        decisions_count = str(w["decisions"]) if w.get("decisions_complete", True) else f"≥{w['decisions']}"
        open_count = str(len(w["open"])) if w.get("open_complete", True) else f"≥{len(w['open'])}"
        note = override.get("descriptions", {}).get(repo, {})
        lines.extend(
            [
                f"## [{repo}](https://github.com/{repo})",
                "",
                note.get(lang, goal),
                "",
                p.get("track", "general"),
                "",
                f"{capacity} · {decisions}: {decisions_count} · {opened}: {open_count} · **{free}: {slots(w, claims, now, repo)}**.",
                "",
            ]
        )
        if approval := p.get("recent_approval"):
            lines.extend([
                f"GitHub ★ {p['stars']} · [APPROVED]({approval['review']}) · {approval['submitted_at']}",
                "",
            ])
        for t in p["tasks"]:
            actions = required_actions(t)
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
                and not actions
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
            if actions:
                lines.append(f"  <br>{confirm_first}: {safe(' '.join(actions))}")
            why, notes = {"en": ("Selection signals", "Handoff"), "ru": ("Основания отбора", "Передача работы"), "es": ("Criterios de selección", "Relevo")}[lang]
            signals = list(t.get("signals") or []) + list(t.get("evidence") or [])[:1]
            if t.get("minutes"):
                signals.append("–".join(map(str, t["minutes"])) + " min")
            if signals:
                lines.append(f"  <br>{why}: {safe(' · '.join(signals))}")
            handoff = next((c["handoff"] for c in reversed(claims) if c["issue"] == t["url"] and c.get("handoff")), None)
            if handoff:
                lines.append(f"  <br>[{notes}]({BASE}/issues/{handoff})")
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


def desk_command(secret, **data):
    request = Request("https://repo-neighbor-6b014c.appwrite.network/api/campaign",
                      data=json.dumps(data).encode(), headers={
                          "Authorization": "Bearer " + secret,
                          "Content-Type": "application/json", "User-Agent": "Repo-Neighbor-Campaign/1.0",
                      })
    try:
        with urlopen(request, timeout=15) as response:
            if json.load(response).get("ok") is not True:
                raise ValueError("Missing desk acknowledgement")
            return True
    except HTTPError as error:
        error.close()
        if error.code == 409:
            return False
        raise


def reconcile_hold(secret, claim):
    if secret and claim.get("bridge") and claim["status"] != "held":
        desk_command(secret, id=claim["bridge"], op="review" if claim["status"] == "open" else "release")


def run(now):
    week = week_key(now)
    editor = load(DIR / "editor.json", {})
    override = editor["weeks"].get(week, {})
    excluded = [*editor.get("exclude", []), *override.get("exclude", [])]
    folder = DIR / "archive" / week
    folder.mkdir(parents=True, exist_ok=True)
    board = folder / "projects.json"
    ledger = load(DIR / "ledger.json", {"claims": [], "receipts": {}})
    claims = ledger["claims"]
    bridge = os.getenv("RN_CAMPAIGN_BRIDGE")
    if os.getenv("RN_REQUIRE_BRIDGE") == "1":
        # GitHub issue numbers start at one. This checks credentials without releasing real work.
        if not bridge or not desk_command(bridge, op="release", id="0"):
            raise RuntimeError("Shared desk bridge is required for published campaign claims.")
    if os.getenv("RN_IMPORT_MOBILE") == "1":
        from mobile import read_export
        try:
            ledger["mobile"] = read_export()
            ledger.pop("mobile_stale", None)
        except (OSError, ValueError, KeyError, TypeError):
            ledger["mobile_stale"] = True
    active_before = [(c, c["status"]) for c in claims if c["status"] in ("held", "open", "closed")]
    refresh_claims(claims, now)
    for claim, old_state in active_before:
        if claim["status"] != old_state:
            reconcile_hold(bridge, claim)
    requests = list(inbox())
    for request in requests:
        key = str(request["number"])
        title = request["title"]
        if key in ledger["receipts"] or not title.startswith(
            ("rn nominate ", "rn propose ", "rn vote ", "rn pledge ")
        ):
            continue
        user = (request["author"] or {}).get("login")
        if user:
            at = community.parse(
                request.get("lastEditedAt")
                or request.get("createdAt")
                or now.isoformat()
            )
            try:
                ledger["receipts"][key] = community.command(
                    title, user, at, ledger, metadata, issue_number=request["number"],
                    body=request.get("body") or "", qualify=qualify,
                    project_check=lambda repo, meta: project_approval(repo, meta, now),
                )
            except ApprovalCoverageIncomplete:
                ledger["receipts"][key] = APPROVAL_UNVERIFIED
    election = ledger.setdefault("elections", {}).setdefault(
        week, {"nominees": {}, "votes": {}}
    )
    previous_week = week_key(now - timedelta(days=7))
    previous = load(DIR / "archive" / previous_week / "selection.json", [])
    opening = community.start(now)
    last = ledger["elections"].get(previous_week, {})
    limit = election.setdefault("capacity", balance.capacity(previous, claims, opening, last.get("capacity", 3)))
    selection_file = folder / "selection.json"
    selection = load(selection_file, load(board, []))
    unfinished = [p for p in selection if not balance.finished(p, claims, now)]
    audit_path = folder / "audit.json"
    version = 2 if week >= community.RULES_WEEK else 1
    audit = load(audit_path, dict(version=version, shares=balance.SHARES, prior=[p["repo"] for p in selection], rounds=[]))
    before_search = time.monotonic()
    first_call = len(GRAPH_CALLS)
    recheck = {"exclude": excluded}
    projects = select(now, recheck, unfinished, claims) if unfinished else []
    unverified = recheck.get("approval_unverified", [])
    occupied = len(projects) + len(unverified)
    vacancies = max(0, limit - occupied)
    if not selection or not unfinished or (vacancies and occupied < len(unfinished)):
        past = [t for k, e in ledger["elections"].items() if k <= week for t in e.get("tracks", {}).values()]
        if audit["version"] == 2:
            past = {category: 0 for category in balance.SHARES}
            for offset in range(1, 5):
                key = week_key(now - timedelta(weeks=offset))
                for project in load(DIR / "archive" / key / "selection.json", []):
                    past[project.get("track", "general")] += balance.workload(project)
            for project in selection:
                past[project.get("track", "general")] += balance.workload(project)
        options = dict(version=audit["version"], replacement=bool(selection), proposals=election["nominees"], exclude=[*excluded, *(p["repo"] for p in selection)], ranked=community.ranking(election),
                       limit=1 if selection and not unfinished else vacancies, history=past,
                       discovery_seeds=override.get("discovery_seeds", []))
        additions = select(now, options, None, claims)
        record = dict(ballot=copy.deepcopy({k: election[k] for k in ("nominees", "votes")}),
                      history=past, limit=options["limit"], pool=options["pool"],
                      skipped=options["skipped"], discovery=options["discovery"],
                      selected=[p["repo"] for p in additions])
        if audit["version"] == 2:
            record.update(replacement=options["replacement"], reasons=options["reasons"])
        if not audit["rounds"] or audit["rounds"][-1] != record:
            audit["rounds"].append(record)
        selection.extend(additions)
        projects.extend(additions)
        save(selection_file, selection)
    if unverified:
        audit["approval_unverified"] = unverified
    else:
        audit.pop("approval_unverified", None)
    save(audit_path, audit)
    calls = GRAPH_CALLS[first_call:]
    save(folder / "discovery-metrics.json", dict(seconds=round(time.monotonic()-before_search, 2),
                                               requests=len(calls), repeated=len(calls)-len(set(calls))))
    election.update(closed=True, selected=[p["repo"] for p in selection])
    tracks = election.setdefault("tracks", {})
    for p in selection:
        repo = p["repo"]
        if repo not in tracks:
            tracks[repo] = p.get("track") or balance.track(metadata(repo)[0])
    for p in projects:
        p["track"] = tracks[p["repo"]]
    for request in requests:
        key = str(request["number"])
        if (
            not request["title"].startswith(("qfg ", "rn "))
            or key in ledger["receipts"]
        ):
            continue
        user = (request["author"] or {}).get("login")
        if user:
            before = len(claims)
            previous_status = {id(c): c["status"] for c in claims}
            receipt = transition(
                request["title"], user, claims, week, projects, now,
                override.get("requires", {}), request.get("body") or "", request["number"],
            )
            if bridge and len(claims) > before:
                claim = claims[-1]
                admitted = desk_command(
                    bridge, op="claim", id=key, issue=claim["issue"].casefold(),
                    repo=claim["repo"].casefold(), login=claim["user"].casefold(),
                    until=int(community.parse(claim["until"]).timestamp() * 1000),
                )
                if admitted:
                    claim["bridge"] = key
                else:
                    claims.pop()
                    receipt = "A task or review slot is already occupied in the shared desk."
            for claim in claims[:before]:
                if claim["status"] != previous_status[id(claim)]:
                    reconcile_hold(bridge, claim)
            ledger["receipts"][key] = receipt
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
