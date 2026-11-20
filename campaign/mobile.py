"""Validate the public desk snapshot before joining it to ballots and reports."""

import json
import re
from datetime import datetime, timezone
from urllib.request import Request, urlopen


def normalize(rows):
    result = []
    seen = set()
    for row in rows:
        task, repo, user, state = (row[k] for k in ("id", "repo", "user", "state"))
        reviewer = row["reviewer"]
        if (
            not re.fullmatch(r"[a-z0-9-]{1,64}", task)
            or task in seen
            or not re.fullmatch(r"[\w.-]+/[\w.-]+", repo)
            or not re.fullmatch(r"[A-Za-z0-9-]{1,39}", user)
            or state not in {"pending", "accepted", "revision"}
            or state == "accepted"
            and (
                not re.fullmatch(r"[A-Za-z0-9-]{1,39}", reviewer)
                or reviewer.casefold() == user.casefold()
            )
        ):
            raise ValueError("Invalid mobile receipt")
        seen.add(task)
        issue = row.get("issue") or f"{repo}#mobile-{task}"
        if row.get("issue") and not re.fullmatch(
            "https://github.com/" + re.escape(repo) + r"/issues/[1-9]\d*", issue
        ):
            raise ValueError("Issue belongs to another project")
        item = dict(
            issue=issue, user=user, state=state, repo=repo, id=task, reviewer=reviewer
        )
        for key in ("claimed", "submitted", "reviewed"):
            value = row[key]
            if (
                type(value) is not int
                or value < 0
                or value > 4102444800000
                or (not value and (key != "reviewed" or state == "accepted"))
            ):
                raise ValueError("Invalid receipt date")
            item[key + "_at"] = (
                datetime.fromtimestamp(value / 1000, timezone.utc).isoformat() if value else None
            )
        item["metrics"] = {
            k: v
            for k, v in row["metrics"].items()
            if k in {"firstTaskMs", "loadMs", "generationMs"}
            and type(v) is int
            and 0 <= v <= 86400000
        }
        result.append(item)
    return result


def read_export():
    request = Request("https://repo-neighbor.fil-support-bot.workers.dev/api/export",
                      headers={"User-Agent": "RepoNeighbor-Campaign/1.0 (+https://github.com/TONstories/repo-neighbor)"})
    with urlopen(request, timeout=20) as response:
        return normalize(json.loads(response.read(4000000)))
