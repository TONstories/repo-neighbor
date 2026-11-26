"""Read-only contribution journey report. Run from the repository root."""

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import subprocess

from community import BASE, local_work, parse, week
from run import URL, load
from quota import has_credit

STAGES = ("claimed", "triage", "brief", "tested_patch")
SESSION_OUTCOMES = {"no_candidate", "stopped", "local_patch", "submitted"}


def github_url(value, kind):
    match = URL.fullmatch(value)
    if not match or match[2] != kind:
        raise ValueError(f"Expected GitHub {kind} URL: {value}")
    return value.casefold()


def read_pr_history(endpoint, timestamp, *fields):
    try:
        pages = json.loads(subprocess.check_output(
            ["gh", "api", "--paginate", "--slurp", endpoint],
            text=True, stderr=subprocess.PIPE, timeout=30,
        ))
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return None
    return [
        {
            **{key: event[key] for key in ("html_url", "author_association", timestamp, *fields)},
            "author": (event.get("user") or {}).get("login"),
            "author_type": (event.get("user") or {}).get("type"),
        }
        for page in pages for event in page if event.get(timestamp)
    ]


def read_pr(url, include_reviews=False):
    fields = "url,author,body,state,createdAt,closedAt,mergedAt,closingIssuesReferences"
    if include_reviews:
        fields += ",headRefOid,statusCheckRollup"
    pr = json.loads(subprocess.check_output(
        ["gh", "pr", "view", url, "--json", fields], text=True, timeout=30,
    ))
    if include_reviews:
        pr["checks_observed_at"] = datetime.now(timezone.utc).isoformat()
        match = URL.fullmatch(url)
        pr["review_history"] = read_pr_history(
            f"repos/{match[1]}/pulls/{match[3]}/reviews", "submitted_at", "state",
        )
        pr["discussion_history"] = read_pr_history(
            f"repos/{match[1]}/issues/{match[3]}/comments", "created_at",
        )
    return pr


def check_rollup(pr):
    attention = {"ACTION_REQUIRED", "CANCELLED", "ERROR", "FAILURE", "STALE", "STARTUP_FAILURE", "TIMED_OUT"}
    pending = []
    needs_attention = []
    for check in pr["statusCheckRollup"]:
        if "context" in check:
            name, url = check["context"], check.get("targetUrl")
            state = check["state"]
        else:
            name, url = check["name"], check.get("detailsUrl")
            state = check.get("conclusion") if check["status"] == "COMPLETED" else "PENDING"
        if state in {"EXPECTED", "PENDING"}:
            pending.append({"name": name, "url": url})
        elif state in attention:
            needs_attention.append({"name": name, "url": url, "state": state})
    return {
        "observed_at": pr["checks_observed_at"],
        "head": pr["headRefOid"],
        "reported": len(pr["statusCheckRollup"]),
        "pending": pending,
        "needs_attention": needs_attention,
    }


def follow_up(pr, as_of):
    submitted = parse(pr["createdAt"])
    decided_at = pr["mergedAt"] or pr["closedAt"]
    if submitted > as_of or (decided_at and parse(decided_at) > as_of):
        raise ValueError("Follow-up timestamp predates the GitHub PR snapshot")
    deadline = submitted + timedelta(days=30)
    is_open = pr["state"].lower() == "open"
    reviews = pr.get("review_history")
    discussion = pr.get("discussion_history")
    author = pr["author"]["login"].casefold()

    def independent_maintainer(event):
        return (
            event["author_association"] in {"OWNER", "MEMBER", "COLLABORATOR"}
            and event.get("author_type", "User") == "User"
            and (event.get("author") or "").casefold() not in {"", author}
        )

    maintainer_reviews = sorted({
        (r["submitted_at"], r["html_url"], r["state"])
        for r in reviews or []
        if independent_maintainer(r)
        and r["state"] in {"COMMENTED", "APPROVED", "CHANGES_REQUESTED"}
        and parse(r["submitted_at"]) <= as_of
    }, key=lambda entry: (parse(entry[0]), entry[1], entry[2]))
    maintainer_comments = sorted({
        (c["created_at"], c["html_url"])
        for c in discussion or []
        if independent_maintainer(c) and submitted <= parse(c["created_at"]) <= as_of
    }, key=lambda entry: (parse(entry[0]), entry[1]))
    return {
        "open_age_days": (as_of - submitted).days if is_open else None,
        "check_at": deadline.isoformat(),
        "check_due": is_open and as_of >= deadline,
        "decision_at": decided_at,
        "review_history_status": "available" if reviews is not None else "unknown",
        "maintainer_reviews": [
            {"at": at, "url": url, "state": state} for at, url, state in maintainer_reviews
        ],
        "discussion_history_status": "available" if discussion is not None else "unknown",
        "maintainer_comments": [{"at": at, "url": url} for at, url in maintainer_comments],
        **({"checks": check_rollup(pr)} if is_open and pr.get("checks_observed_at") else {}),
    }


def overlapping_submissions(pulls, tasks):
    by_url = {pr["url"]: pr for pr in pulls}
    overlaps = []
    for task in tasks.values():
        active = []
        prs = sorted((by_url[url] for url in task["prs"]), key=lambda pr: (parse(pr["submitted_at"]), pr["url"]))
        for pr in prs:
            opened = parse(pr["submitted_at"])
            active = [(url, decided) for url, decided in active if decided is None or opened < decided]
            if active:
                overlaps.append({"issue": task["issue"], "cohort": task["cohort"],
                                 "pr": pr["url"], "with": [url for url, _ in active]})
            decision = pr["merged_at"] or pr["closed_at"]
            active.append((pr["url"], parse(decision) if decision else None))
    return overlaps


def pilot_sessions(rows, tasks, pulls, as_of):
    verified_pulls = {github_url(pr["url"], "pull"): pr for pr in pulls}
    sessions = {}
    submissions = set()
    outcomes = Counter()
    for row in rows:
        session_id = row["id"].strip()
        start = parse(row["started_at"])
        if (not session_id or session_id in sessions or not row["source"].strip()
                or start.tzinfo is None or (as_of is not None and start > as_of)):
            raise ValueError(f"Invalid or repeated pilot session: {session_id}")

        issue = github_url(row["issue"], "issues") if row.get("issue") else None
        outcome = row.get("outcome")
        finished_at = row.get("finished_at")
        if outcome is None:
            if finished_at or row.get("reason") or row.get("pr"):
                raise ValueError(f"Unfinished pilot session has an outcome record: {session_id}")
        else:
            if outcome not in SESSION_OUTCOMES or not finished_at or not (row.get("reason") or "").strip():
                raise ValueError(f"Pilot session needs a recorded outcome and reason: {session_id}")
            end = parse(finished_at)
            if end.tzinfo is None or end < start or (as_of is not None and end > as_of):
                raise ValueError(f"Invalid finish time for pilot session: {session_id}")
            if outcome == "local_patch" and not any(
                event["stage"] == "tested_patch" and start <= parse(event["at"]) <= end
                for event in tasks.get(issue, {}).get("events", [])
            ):
                raise ValueError(f"No tested patch recorded during pilot session: {session_id}")
            if outcome == "submitted" or row.get("pr"):
                url = github_url(row["pr"], "pull") if row.get("pr") else None
                pr = verified_pulls.get(url)
                if not pr or url in submissions or issue not in pr["issues"]:
                    raise ValueError(f"No unique verified PR for pilot session: {session_id}")
                sent = parse(pr["submitted_at"])
                timely = ((outcome == "submitted" and start <= sent <= end)
                          or (outcome == "local_patch" and sent > end))
                if not timely:
                    raise ValueError(f"PR time does not match the pilot session outcome: {session_id}")
                submissions.add(url)

        sessions[session_id] = dict(row, id=session_id)
        outcomes[outcome or "in_progress"] += 1
    pr_states = Counter(verified_pulls[url]["state"] for url in submissions)
    return {
        "started": len(sessions),
        "finished": len(sessions) - outcomes["in_progress"],
        "by_outcome": dict(outcomes),
        "submitted": len(submissions),
        "open": pr_states["open"],
        "merged": pr_states["merged"],
        "closed_without_merge": pr_states["closed"],
        "entries": list(sessions.values()),
    }


def report(work, claims, supplement, lookup, *, as_of=None):
    if as_of is not None and as_of.tzinfo is None:
        raise ValueError("Follow-up timestamp must include a timezone")
    tasks = {}

    def mark(issue, at, stage, source):
        key = github_url(issue, "issues")
        stamp = parse(at)
        if stamp.tzinfo is None or stage not in STAGES:
            raise ValueError(f"Invalid stage or timestamp for {issue}")
        if as_of is not None and stamp > as_of:
            raise ValueError(f"Follow-up timestamp predates recorded work for {issue}")
        task = tasks.setdefault(key, {"issue": issue, "events": [], "prs": []})
        task["events"].append({"at": at, "stage": stage, "source": source})

    for row in work:
        mark(row["issue"], row["at"], row["stage"], f"artifact sha256:{row['artifact_sha256']}")
    for row in supplement.get("work", []):
        mark(row["issue"], row["at"], row["stage"], row["source"])
    for row in claims:
        mark(row["issue"], row["claimed_at"], "claimed", "ledger")
        tasks[github_url(row["issue"], "issues")].setdefault("claims", []).append({
            "user": row["user"], "at": row["claimed_at"], "status": row["status"],
        })

    for task in tasks.values():
        task["events"].sort(key=lambda event: parse(event["at"]))
        task["cohort"] = week(parse(task["events"][0]["at"]))
        task["stage"] = max((event["stage"] for event in task["events"]), key=STAGES.index)
        task["stop"] = None

    for issue, stop in supplement.get("stops", {}).items():
        task = tasks[github_url(issue, "issues")]
        if "at" in stop:
            at = parse(stop["at"])
            if at.tzinfo is None or at < parse(task["events"][0]["at"]):
                raise ValueError(f"Invalid stop timestamp for {issue}")
            if (as_of is not None and at > as_of) or at < parse(task["events"][-1]["at"]):
                continue
        task["stop"] = stop

    feedback_by_pr = {}
    if as_of is not None:
        for claim in claims:
            if claim.get("pr") and claim.get("feedback"):
                url = github_url(claim["pr"], "pull")
                feedback = claim["feedback"]
                previous = feedback_by_pr.get(url)
                if previous is None or feedback["issue"] > previous["issue"]:
                    feedback_by_pr[url] = feedback

    bindings = {}
    for row in [*claims, *supplement.get("pulls", [])]:
        if row.get("pr"):
            pr = github_url(row["pr"], "pull")
            issue = github_url(row["issue"], "issues")
            if issue not in tasks or issue.rsplit("/issues/", 1)[0] != pr.rsplit("/pull/", 1)[0]:
                raise ValueError(f"PR must refer to a recorded task in the same repository: {pr}")
            bindings.setdefault(pr, set()).add((issue, row["user"].casefold()))

    pulls = []
    for url, links in sorted(bindings.items()):
        pr = lookup(url)
        if github_url(pr["url"], "pull") != url or not has_credit(pr["body"]):
            raise ValueError(f"PR identity or visible attribution did not match: {url}")
        refs = {github_url(row["url"], "issues") for row in pr["closingIssuesReferences"]}
        for issue, user in sorted(links):
            if ((pr["author"] or {}).get("login", "").casefold() != user
                    or (issue not in refs and not re.search(re.escape(issue) + r"(?![\w/])", pr["body"].casefold()))):
                raise ValueError(f"PR author or linked issue did not match: {url}")
        issues = sorted({issue for issue, _ in links})
        for issue in issues:
            tasks[issue]["prs"].append(pr["url"])
        state = pr["state"].lower()
        if state not in ("open", "closed", "merged") or (state == "merged") != bool(pr["mergedAt"]):
            raise ValueError(f"Inconsistent PR state: {url}")
        first = min(issues, key=lambda key: parse(tasks[key]["events"][0]["at"]))
        pulls.append({
            "url": pr["url"], "issues": issues, "author": pr["author"]["login"],
            "cohort": tasks[first]["cohort"], "state": state, "submitted_at": pr["createdAt"],
            "closed_at": pr["closedAt"], "merged_at": pr["mergedAt"],
            "attribution": "visible Repo Neighbor credit in GitHub PR body",
        })
        if as_of is not None:
            info = follow_up(pr, as_of)
            feedback = feedback_by_pr.get(url) if state == "merged" else None
            info["outcome_feedback"] = {
                "outcome": feedback["outcome"],
                "saved_minutes": feedback.get("saved"),
                "review_minutes": feedback["review"],
                "source": f"{BASE}/issues/{feedback['issue']}",
            } if feedback else None
            pulls[-1]["follow_up"] = info

    def counts(rows, prs):
        states = Counter(pr["state"] for pr in prs)
        return {
            "tasks": len(rows), "tested_patches": sum(task["stage"] == "tested_patch" for task in rows),
            "submitted": len(prs), "open": states["open"], "merged": states["merged"],
            "closed_without_merge": states["closed"],
        }

    def not_submitted_counts(rows):
        pending = [task for task in rows if not task["prs"]]
        reasons = Counter()
        for task in pending:
            reason = (task["stop"] or {}).get("reason")
            reasons[reason if reason and reason != "local_only" else "unknown"] += 1
        return {
            "tasks": len(pending),
            "by_stage": dict(Counter(task["stage"] for task in pending)),
            "by_reason": dict(reasons),
        }

    cohorts = sorted({task["cohort"] for task in tasks.values()})
    by_cohort = {cohort: [task for task in tasks.values() if task["cohort"] == cohort] for cohort in cohorts}
    result = {
        "totals": counts(tasks.values(), pulls),
        "cohorts": {cohort: counts(
            rows,
            [pr for pr in pulls if pr["cohort"] == cohort],
        ) for cohort, rows in by_cohort.items()},
        "not_submitted": {
            "total": not_submitted_counts(tasks.values()),
            "cohorts": {cohort: not_submitted_counts(rows) for cohort, rows in by_cohort.items()},
        },
        "tasks": list(tasks.values()), "pulls": pulls,
    }
    if "sessions" in supplement:
        result["pilot_sessions"] = pilot_sessions(supplement["sessions"], tasks, pulls, as_of)
    if as_of is not None:
        overlaps = overlapping_submissions(pulls, tasks)
        scope = [("all", pulls)] + [
            (cohort, [pr for pr in pulls if pr["cohort"] == cohort]) for cohort in cohorts
        ]
        result["follow_up"] = {"as_of": as_of.isoformat(), "overlapping_submissions": overlaps, "counts": {
            label: {
                "issues_with_overlapping_submissions": len({
                    row["issue"] for row in overlaps if label == "all" or row["cohort"] == label
                }),
                "maintainer_reviewed": sum(bool(pr["follow_up"]["maintainer_reviews"]) for pr in rows),
                "with_maintainer_comment": sum(bool(pr["follow_up"]["maintainer_comments"]) for pr in rows),
                "reviewed_or_decided": sum(
                    pr["state"] != "open" or bool(pr["follow_up"]["maintainer_reviews"]) for pr in rows
                ),
                "with_outcome_feedback": sum(pr["follow_up"]["outcome_feedback"] is not None for pr in rows),
                "unknown_review_history": sum(pr["follow_up"]["review_history_status"] == "unknown" for pr in rows),
                "unknown_discussion_history": sum(pr["follow_up"]["discussion_history_status"] == "unknown" for pr in rows),
                "open_due": sum(pr["follow_up"]["check_due"] for pr in rows),
                "repositories_with_merge": len({
                    pr["url"].casefold().rsplit("/pull/", 1)[0] for pr in rows if pr["state"] == "merged"
                }),
            }
            for label, rows in scope
        }}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaigns", type=Path, default=Path("campaigns"))
    parser.add_argument("--supplement", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--live", action="store_true", help="Read each unique PR from GitHub")
    mode.add_argument("--snapshot", type=Path, help="Replay saved GitHub PR responses keyed by lowercase URL")
    parser.add_argument("--save-snapshot", type=Path, help="Save GitHub responses after a successful live report")
    parser.add_argument("--as-of", type=parse, help="Include review follow-up at an explicit ISO timestamp with timezone")
    args = parser.parse_args()
    if args.as_of is not None and args.as_of.tzinfo is None:
        parser.error("--as-of must include a timezone")
    if args.save_snapshot and not args.live:
        parser.error("--save-snapshot requires --live")

    snapshot = {} if args.live else json.loads(args.snapshot.read_text())

    def lookup(url):
        if args.live:
            snapshot[url] = read_pr(url, include_reviews=args.as_of is not None)
        return snapshot[url]

    data = report(
        local_work(args.campaigns), load(args.campaigns / "ledger.json", {"claims": []})["claims"],
        json.loads(args.supplement.read_text()), lookup, as_of=args.as_of,
    )
    if args.save_snapshot:
        args.save_snapshot.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
