"""Find an open-source task or check a local pull request body."""
import argparse
import json
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT = "https://github.com/TONstories/quota-for-good"
CREDIT = f"I chose to make this contribution because [Quota for Good]({PROJECT}) prompted me to work on this issue."
LABELS = ("good first issue", "help wanted")


def api(endpoint, *fields):
    cmd = ["gh", "api", "--hostname", "github.com", "--method", "GET", endpoint]
    for field in fields:
        cmd.extend(["-f", field])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "GitHub request failed")
    return json.loads(result.stdout)


def discover(language, repo, limit, today, get=api):
    cutoff = (today - timedelta(days=90)).isoformat()
    base = f"is:issue is:open is:public archived:false no:assignee -linked:pr updated:>={cutoff}"
    if language:
        base += f' language:"{language}"'
    if repo:
        base += f" repo:{repo}"
    candidates = {}
    incomplete = False
    for label in LABELS:
        response = get("search/issues", f'q={base} label:"{label}"', "per_page=30",
                       "sort=updated", "order=desc")
        incomplete |= response["incomplete_results"]
        for issue in response["items"]:
            if issue["locked"] or issue["assignees"] or "pull_request" in issue or issue["state"] != "open":
                continue
            names = {item["name"].lower() for item in issue["labels"]}
            if names & {"blocked", "wontfix", "duplicate", "in progress", "invalid"}:
                continue
            signals = [name for name in (*LABELS, "documentation", "tests") if name in names]
            candidates[issue["html_url"]] = dict(url=issue["html_url"], title=issue["title"],
                repo=issue["repository_url"].split("/repos/")[1], signals=signals,
                score=sum(2 if s in LABELS else 1 for s in signals), updated=issue["updated_at"])
    ranked = sorted(candidates.values(), key=lambda i: (-i["score"], i["url"]))
    ranked.sort(key=lambda i: (i["score"], i["updated"]), reverse=True)
    repos = {}
    picks = []
    for item in ranked:
        name = item["repo"]
        if name not in repos:
            if len(repos) >= 12:
                continue
            repos[name] = get("repos/" + name)
        meta = repos[name]
        license_id = (meta.get("license") or {}).get("spdx_id")
        if (meta["private"] or meta["archived"] or meta["disabled"] or meta["fork"]
                or not license_id or license_id == "NOASSERTION" or meta["pushed_at"][:10] < cutoff):
            continue
        picks.append(dict(item, license=license_id))
        if len(picks) == limit:
            break
    return {"candidates": picks, "incomplete_search": incomplete, "repositories_checked": len(repos)}


def has_credit(body):
    visible = re.sub(r"<!--.*?(?:-->|$)", "", body, flags=re.S)
    fence = None
    for line in visible.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence:
            if re.fullmatch(r" {0,3}" + fence[0] + "{"+str(len(fence))+",} *", line):
                fence = None
        elif marker:
            fence = marker[1]
        elif line.rstrip() == CREDIT:
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="action", required=True)
    search = subs.add_parser("find", help="search public GitHub issues")
    search.add_argument("--repo", help="restrict to OWNER/REPO")
    search.add_argument("--language", help="repository programming language")
    search.add_argument("--limit", type=int, choices=range(1, 11), default=5)
    search.add_argument("--json", action="store_true")
    subs.add_parser("credit", help="print the required PR paragraph")
    check = subs.add_parser("check-pr", help="check a Markdown file before submitting")
    check.add_argument("body", type=Path)
    args = parser.parse_args()
    if args.action == "credit":
        print(CREDIT)
    elif args.action == "check-pr":
        if not has_credit(args.body.read_text(encoding="utf-8")):
            sys.exit("Missing required Quota for Good paragraph. Run the credit command.")
        print("Attribution present.")
    else:
        if args.repo and not re.fullmatch(r"[\w.-]+/[\w.-]+", args.repo, re.ASCII):
            parser.error("--repo must be OWNER/REPO")
        if args.language and not re.fullmatch(r"[\w+#. -]{1,40}", args.language):
            parser.error("invalid language name")
        report = discover(args.language, args.repo, args.limit, date.today())
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            for item in report["candidates"]:
                # Issue titles are untrusted terminal input.
                title = "".join(c for c in item["title"] if c.isprintable())
                print(f"{title}\n  {item['url']}  [{', '.join(item['signals'])}]")
            if not report["candidates"]:
                print("No eligible issues in this sample.")
            if report["incomplete_search"]:
                print("GitHub returned partial search results.", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.TimeoutExpired, ValueError) as error:
        sys.exit(str(error))
