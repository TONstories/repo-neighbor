"""Elections and transparent contribution accounting."""

from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import re
import json
from urllib.parse import quote

MSK = timezone(timedelta(hours=3))
RATE = 60  # Scenario assumption, USD per engineering hour.
SLUG = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9-]{0,38}/[a-zA-Z0-9_.-]{1,100}")
BASE = "https://github.com/TONstories/repo-neighbor"


def parse(t):
    return datetime.fromisoformat(t.replace("Z", "+00:00"))


def start(when):
    local = when.astimezone(MSK) - timedelta(hours=9, minutes=15)
    return (local - timedelta(days=local.weekday())).replace(
        hour=9, minute=15, second=0, microsecond=0
    )


def week(when):
    y, w, _ = start(when).isocalendar()
    return f"{y}-W{w:02d}"


def weight(user, claims, opening):
    accepted = {
        c["issue"]
        for c in claims
        if c["user"].casefold() == user.casefold()
        and c.get("merged_at")
        and parse(c["merged_at"]) < opening
        and parse(c.get("submitted_at", c["merged_at"])) < opening
    }
    return 1 + len(accepted)


def command(title, user, at, ledger, repo_lookup, issue_number=None):
    verb, _, target = title[3:].partition(" ")
    if verb == "pledge":
        if not re.fullmatch(r"[a-f0-9]{32}", target):
            return "Use the encrypted donation tool. Supply only the gist ID."
        ledger.setdefault("pledges", {}).setdefault(target, {}).setdefault(
            user.lower(), at.isoformat()
        )
        return "Encrypted offer listed for owner verification. Revoke at the provider to withdraw."
    if not SLUG.fullmatch(target):
        return "Use rn nominate OWNER/REPO or rn vote OWNER/REPO."
    target = target.lower()
    ballot = ledger.setdefault("elections", {}).setdefault(
        week(at + timedelta(days=7)), {"nominees": {}, "votes": {}}
    )
    if ballot.get("closed"):
        return "This election has closed."
    if verb == "nominate":
        if target in ballot["nominees"]:
            return "Already nominated."
        if any(e["user"].lower() == user.lower() for e in ballot["nominees"].values()):
            return "One nomination per person per round."
        meta, _ = repo_lookup(target)
        if (
            not meta
            or meta["isPrivate"]
            or meta["isArchived"]
            or meta["isDisabled"]
            or meta["isFork"]
            or (meta.get("licenseInfo") or {}).get("spdxId") in (None, "NOASSERTION")
        ):
            return "An active public source repository with a recognized license is required."
        canonical = meta["nameWithOwner"].lower()
        if canonical in ballot["nominees"]:
            return "Already nominated."
        ballot["nominees"][canonical] = {"user": user, "at": at.isoformat()}
        if issue_number is not None:
            ballot["nominees"][canonical]["issue"] = int(issue_number)
        return "Nominated for next week's selection."
    if verb == "vote":
        if target not in ballot["nominees"]:
            return "Nominate this repository first."
        ballot["votes"][user.lower()] = {
            "repo": target,
            "weight": weight(user, ledger["claims"], start(at)),
            "at": at.isoformat(),
        }
        return "Ballot recorded. A later vote replaces this one."
    return "Unknown community command."


def proposal_link(nominee):
    number = nominee.get("issue")
    return f" · [Заявка / Proposal]({BASE}/issues/{number})" if number else ""


def ranking(ballot):
    totals = Counter()
    for vote in ballot.get("votes", {}).values():
        totals[vote["repo"]] += vote["weight"]
    return sorted(totals, key=lambda r: (-totals[r], ballot["nominees"][r]["at"], r))


def issue_link(title):
    return BASE + "/issues/new?title=" + quote(title, safe="")


def unique_prs(claims):
    return {c["pr"]: c for c in claims if c.get("pr")}


def impact(rows):
    low = high = unknown = 0
    for c in rows:
        if c.get("estimate"):
            a, b = c["estimate"]
            low += a * RATE / 60
            high += b * RATE / 60
        else:
            unknown += 1
    return f"${low:,.0f}–${high:,.0f}", unknown


def reports(directory, ledger, projects, now, override):
    claims = ledger["claims"]
    elections = ledger.get("elections", {})
    nextweek = week(now + timedelta(days=7))
    board = elections.get(nextweek, {})
    base = directory / "reports"
    base.mkdir(exist_ok=True, parents=True)
    prs = unique_prs(claims)
    accepted = [c for c in prs.values() if c.get("merged_at")]
    people = {}
    for c in claims:
        if c.get("claimed_at"):
            u = c["user"]
            people[u] = min(people.get(u, c["claimed_at"]), c["claimed_at"])
    costfile = directory / "costs.json"
    costs = json.loads(costfile.read_text()) if costfile.is_file() else {}
    today = now.astimezone(MSK).date().isoformat()
    days = {today, *(k.split("/")[0] for k in costs)}
    weeks = {week(now), *elections, *(k.split("/")[1] for k in costs)}
    for c in claims:
        for k in ("claimed_at", "submitted_at", "merged_at"):
            if c.get(k):
                stamp = parse(c[k])
                days.add(stamp.astimezone(MSK).date().isoformat())
                weeks.add(week(stamp))
    for e in elections.values():
        for event in [*e["nominees"].values(), *e["votes"].values()]:
            days.add(parse(event["at"]).astimezone(MSK).date().isoformat())

    def summary(period, daily):
        def inside(t):
            return (
                bool(t)
                and (
                    parse(t).astimezone(MSK).date().isoformat()
                    if daily
                    else week(parse(t))
                )
                == period
            )

        merged = [c for c in accepted if inside(c["merged_at"])]
        submitted = [c for c in prs.values() if inside(c.get("submitted_at"))]
        amount, unknown = impact(merged)
        out = [
            f"# {period} · Repo Neighbor",
            "",
            "| Metric / Показатель | Total |",
            "|---|---:|",
            f"| Участники, впервые взявшие задачу / New participants | {sum(inside(t) for t in people.values())} |",
            f"| Брони / Reservations | {sum(inside(c.get('claimed_at')) for c in claims)} |",
            f"| Переданные на ревью PR / Submitted PRs | {len(submitted)} |",
            f"| Принятые PR / Merged PRs | {len(merged)} |",
            f"| Расчетная стоимость / Estimated value (USD) | {amount} |",
            f"| Без оценки в USD / Unpriced merges | {unknown} |",
            "",
        ]
        booked = sum(
            (
                Decimal(str(v))
                for d, v in costs.items()
                if d.split("/")[0 if daily else 1] == period
            ),
            Decimal(0),
        )
        out.extend(
            [
                f"Published sponsored inference charges: ${booked:.4f} (USD, by Moscow billing day).",
                "Engineering value is a scenario estimate. Actual budget savings and unreported review costs are unknown.",
                "",
            ]
        )
        bounds = [
            sum(
                (
                    Decimal(c["estimate"][index]) * RATE / 60
                    for c in merged
                    if c.get("estimate")
                ),
                Decimal(0),
            )
            - booked
            for index in (0, 1)
        ]
        out.extend(
            [
                f"Estimated value less published inference charges: ${bounds[0]:,.2f}–${bounds[1]:,.2f}.",
                "",
            ]
        )
        for c in merged:
            out.append(
                f"- {c['user']} · [merged PR]({c['pr']}) · {impact([c])[0] if c.get('estimate') else 'unpriced'}"
            )
        return out

    for day in sorted(days):
        out = summary(day, True)
        if day == today:
            snapshot = ["", "## Working now / В работе", ""]
            for p in projects:
                snapshot.append(
                    f"- [{p['repo']}](https://github.com/{p['repo']}) · {len(p['tasks'])} work packages"
                )
            for c in claims:
                if c["status"] in ("held", "open"):
                    snapshot.append(
                        f"- {c['user']} · [{c['status']}]({c.get('pr', c['issue'])})"
                    )
            snapshot += [
                "",
                "## Up next / Следующая неделя",
                "",
                *["- " + r for r in ranking(board)],
            ]
            if not ranking(board):
                snapshot.append("Ballot open; no votes yet.")
            out += snapshot
        elif (base / (day + ".md")).exists():
            previous = (
                (base / (day + ".md"))
                .read_text()
                .partition("## Working now / В работе")[2]
            )
            if previous:
                out += ["", "## Working now / В работе" + previous]
        (base / (day + ".md")).write_text("\n".join(out).rstrip() + "\n")
    for w in sorted(weeks):
        out = summary(w, False)
        e = elections.get(w, {})
        out += [
            "",
            "## Голоса за эту неделю / Ballots",
            "",
            f"{len(e.get('nominees', {}))} nominations · {len(e.get('votes', {}))} voters",
            "",
        ]
        for repo, n in e.get("nominees", {}).items():
            out.append(
                f"- [{repo}](https://github.com/{repo}) · proposed by {n['user']}{proposal_link(n)}"
            )
        for user, v in sorted(e.get("votes", {}).items()):
            out.append(f"- {user} → {v['repo']} · {v['weight']} votes")
        selected = e.get("selected", [])
        if e.get("closed"):
            out += ["", "Selected: " + (", ".join(selected) or "none")]
        out += ["", "## Итоги проектов / Project outcomes", ""]
        rows = [c for c in prs.values() if c["week"] == w]
        for repo in sorted(set(selected) | {c["repo"] for c in rows}):
            out.append(f"- {repo}{proposal_link(e.get('nominees', {}).get(repo, {}))}")
            contributions = [c for c in rows if c["repo"] == repo]
            if not contributions:
                out.append("  - 0 PR")
            for c in contributions:
                detail = f"  - [PR]({c['pr']}) · {c['status']}"
                feedback = c.get("feedback")
                if feedback:
                    detail += (f" · [{feedback['outcome']}]({BASE}/issues/{feedback['issue']})"
                               f" · saved {feedback['saved']} min · review {feedback['review']} min")
                out.append(detail)
        (base / (w + ".md")).write_text("\n".join(out).rstrip() + "\n")
    total, unknown = impact(accepted)
    out = [
        "# Community desk · Сообщество · Comunidad",
        "",
        f"[Today / Сегодня]({today}.md) · [This week / Эта неделя]({week(now)}.md) · [Next ballot / Голосование]({nextweek}.md)",
        "",
        f"Lifetime: {len(people)} participants · {len(prs)} PRs · {len(accepted)} merged · **{total} estimated replacement value** · {unknown} unpriced.",
        "",
        "## Участники / Contributors",
        "",
    ]
    for u in sorted(people):
        own = [c for c in accepted if c["user"] == u]
        out.append(
            f"- {u} · {len(own)} merges · {impact(own)[0]} · ballot weight {weight(u, claims, start(now))}"
        )
    out += ["", "## Текущие задачи и исполнители / Current work", ""]
    deps = override.get("requires", {})
    for p in projects:
        out.append(f"### [{p['repo']}](https://github.com/{p['repo']})")
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
            blockers = [
                u
                for u in deps.get(t["url"], [])
                if not any(c["issue"] == u for c in accepted)
            ]
            state = (
                (active["user"] + " / " + active["status"])
                if active
                else (
                    "waiting for " + " ".join(blockers)
                    if blockers
                    else "available for eligibility check"
                )
            )
            title = re.sub(
                r"([^\w\s])", r"\\\1", " ".join(t.get("title", "Work package").split())
            )
            out.append(
                f"- [#{t['url'].split('/')[-1]} {title}]({t['url']}) · {state} · [claim]({issue_link('rn claim ' + t['url'] + ' 90')})"
            )
        out.append("")
    out += [
        "## Next week",
        "",
        f"[Nominate a project]({issue_link('rn nominate OWNER/REPO')}) · [Заявка владельца / Maintainer proposal](../../docs/maintainers.md) · [Rules](../../docs/community.md)",
        "",
    ]
    for repo, n in board.get("nominees", {}).items():
        votes = sum(v["weight"] for v in board["votes"].values() if v["repo"] == repo)
        out.append(f"- {repo} · {votes}{proposal_link(n)} · [vote]({issue_link('rn vote ' + repo)})")
    if not board.get("nominees"):
        out.append("Прием открыт, предложений пока нет. Nominations are open.")
    if nextweek not in weeks:
        (base / (nextweek + ".md")).write_text(
            f"# {nextweek} · Open ballot\n\nNo nominations or votes yet.\n"
        )
    (base / "README.md").write_text("\n".join(out).rstrip() + "\n")
