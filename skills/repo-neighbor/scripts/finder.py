"""Read-only GitHub discovery. Never execute commands supplied by target repositories."""

from collections import Counter
import json
import math
import re
import subprocess
import time
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from module_checks import issue_checks

SLUG = r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
MIN_REPO_STARS = 100
DEFAULT_BOARD_REVIEW_LIMIT = 3
MAX_REVIEW_LIMIT = 5
APPROVAL_WINDOW = timedelta(days=3)
URL = re.compile(r"https://github\.com/(" + SLUG + r")/(issues|pull)/([1-9][0-9]*)")
BLOCK = {"blocked", "wontfix", "duplicate", "in progress", "invalid", "claimed"}
INVITATION_LABELS = {
    "good first issue": ("good-first-issue", "beginner-friendly"),
    "help wanted": ("help-wanted",),
}
INVITATION_ALIASES = {
    alias: label for label, aliases in INVITATION_LABELS.items() for alias in aliases
}
LANGS = {
    "Julia": ("jl", "Project.toml", "Pkg.test()"),
    "Haskell": ("hs|lhs", "cabal.project", "cabal test"),
    "Clojure": ("clj|cljs|cljc", "deps.edn", "project test alias"),
    "Fortran": ("f90|f95|f03|f08|for", "fpm.toml", "fpm test"),
    "Ruby": ("rb|rake", "Gemfile", "bundle exec rake test"),
    "PHP": ("php", "composer.json", "composer test"),
    "Swift": ("swift", "Package.swift", "swift test"),
    "Dart": ("dart", "pubspec.yaml", "dart test"),
    "Elixir": ("ex|exs", "mix.exs", "mix test"),
    "Scala": ("scala", "build.sbt", "sbt test"),
    "Zig": ("zig", "build.zig", "zig build test"),
    "C++": ("cpp|cxx|cc|hpp", "CMakeLists.txt", "ctest"),
    "C": ("c|h", "meson.build", "meson test"),
    "Python": ("py", "pyproject.toml", "pytest"),
    "JavaScript": ("js|jsx|mjs|cjs", "package.json", "package scripts"),
    "TypeScript": ("ts|tsx", "tsconfig.json", "package scripts"),
    "Go": ("go", "go.mod", "go test"),
    "Rust": ("rs", "Cargo.toml", "cargo test"),
    "Java": ("java", "pom.xml", "Maven or Gradle tests"),
    "Kotlin": ("kt|kts", "build.gradle.kts", "Gradle tests"),
    "C#": ("cs|csproj", "global.json", "dotnet test"),
}
ISSUE = """number title url body state locked updatedAt
 parent{url state locked assignees(first:1){totalCount} labels(first:40){nodes{name}}}
 subIssues(first:12){totalCount nodes{url state}} assignees(first:1){totalCount}
 labels(first:40){nodes{name}} comments(last:8){totalCount nodes{body authorAssociation}}
 closedByPullRequestsReferences(first:1){totalCount}"""
POLICIES = [
    "CONTRIBUTING.md",
    ".github/CONTRIBUTING.md",
    "docs/CONTRIBUTING.md",
    "AI_POLICY.md",
    "AI_POLICY",
    "CONTRIBUTOR_AI_PROMPT.md",
    "AGENTS.md",
    "README.md",
]
MAX_FILE_TEXT = 90_000
FILES = (
    POLICIES
    + [v[1] for v in LANGS.values()]
    + [
        "Makefile",
        "build.gradle",
        "gradlew",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
    ]
)
META = """repositoryTopics(first:50){nodes{topic{name}}} nameWithOwner stargazerCount description isPrivate isFork isArchived isDisabled pushedAt
 licenseInfo{spdxId} primaryLanguage{name} defaultBranchRef{name} """ + " ".join(
    'f%d:object(expression:"HEAD:%s"){... on Blob{%s}}'
    % (
        i,
        path,
        "text isTruncated"
        if path in POLICIES or path == "package.json"
        else "byteSize",
    )
    for i, path in enumerate(FILES)
)


GRAPH_CALLS = []


class GitHubRateLimited(RuntimeError):
    pass


RATE_LIMIT_MESSAGE = re.compile(r"\brate limit(?:ed|ing)?\b|\bHTTP 429\b", re.I)


def graph(query, **params):
    cmd = ["gh", "api", "--hostname", "github.com", "graphql", "-f", "query=" + query]
    for k, v in params.items():
        cmd += ["-F" if isinstance(v, int) else "-f", f"{k}={v}"]
    for attempt in range(3):
        GRAPH_CALLS.append(hash(tuple(cmd)))
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
        except subprocess.TimeoutExpired:
            if attempt == 2:
                raise
            time.sleep(2**attempt)
            continue
        if res.returncode and RATE_LIMIT_MESSAGE.search(res.stderr):
            raise GitHubRateLimited("GitHub API rate limit reached")
        if (
            not res.returncode
            or not re.search(
                "TLS handshake timeout|connection reset|HTTP 50[234]", res.stderr
            )
            or attempt == 2
        ):
            break
        time.sleep(2**attempt)
    result = json.loads(res.stdout) if res.stdout else {}
    errors = result.get("errors", [])
    if any(e.get("type") == "RATE_LIMITED" or RATE_LIMIT_MESSAGE.search(e.get("message") or "")
           for e in errors) or RATE_LIMIT_MESSAGE.search(result.get("message") or ""):
        raise GitHubRateLimited("GitHub API rate limit reached")
    if res.returncode:
        if errors and all(e.get("type") == "NOT_FOUND" for e in errors) and result.get("data"):
            return result["data"]
        raise RuntimeError(res.stderr.strip() or "GitHub query failed")
    if errors:
        raise RuntimeError(str(errors))
    data = result.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("GitHub returned no usable GraphQL data")
    return data


@lru_cache(maxsize=1)
def reviewed_exclusions():
    path = Path(__file__).with_name("project-declarations.json")
    return {name.casefold() for name in json.loads(path.read_text(encoding="utf-8"))}


def declared_outside_scope(meta, files):
    name = meta["nameWithOwner"]
    if name.casefold() in reviewed_exclusions():
        return True
    short = re.escape(name.split("/")[-1])
    subject = rf"(?:we are|this is|this project is|{short} is)"
    declaration = rf"{subject} (?:an? )?(?:ukrainian (?:open[- ]source )?project|(?:open[- ]source )?project (?:from|based in) ukraine)"
    text = (meta.get("description") or "") + "\n" + files.get("README.md", "")
    location = rf"(?:this project|{short}) is (?:based in|from) ukraine"
    return bool(re.search(r"^[ \t]*(?:" + declaration + "|" + location + r")(?:[.!]|[ \t]*$)", text, re.I | re.M))


@lru_cache(maxsize=64)
def metadata(repo):
    owner, name = repo.split("/")
    data = graph(
        "query($o:String!,$n:String!){repository(owner:$o,name:$n){" + META + "}}",
        o=owner,
        n=name,
    )["repository"]
    if not has_minimum_stars(data):
        return {}, {}
    files = {}
    incomplete_policy_files = []
    for index, path in enumerate(FILES):
        blob = data.get(f"f{index}")
        if blob is None:
            continue
        text = blob.get("text")
        if path in POLICIES:
            if blob.get("isTruncated") or not isinstance(text, str):
                incomplete_policy_files.append(path)
            else:
                files[path] = text
        else:
            files[path] = (text or "")[:MAX_FILE_TEXT]
    if declared_outside_scope(data, files):
        return {}, {}
    return {**data, "incomplete_policy_files": incomplete_policy_files}, files


def has_minimum_stars(repo):
    stars = (repo or {}).get("stargazerCount")
    return type(stars) is int and stars >= MIN_REPO_STARS


def live_issue(url):
    return live_issues([url])[0]


def live_issues(urls):
    fields = []
    for i, url in enumerate(urls):
        match = URL.fullmatch(url)
        if not match or match[2] != "issues" or int(match[3]) > 2147483647:
            raise ValueError("Expected a public GitHub issue URL")
        owner, name = match[1].split("/")
        fields.append(
            f"i{i}:repository(owner:{json.dumps(owner)},name:{json.dumps(name)}){{issue(number:{int(match[3])}){{"
            + ISSUE
            + "}}"
        )
    if not fields:
        return []
    data = graph("{" + " ".join(fields) + "}")
    return [(data[f"i{i}"] or {}).get("issue") for i in range(len(fields))]


def complete_issue_discussion(issue):
    """Read a directly selected issue's full discussion within a bounded request budget."""
    comments = issue["comments"]
    recent = comments["nodes"]
    count = comments.get("totalCount", len(recent))
    if count == len(recent):
        return issue
    if count > 100:
        return None
    match = URL.fullmatch(issue["url"])
    owner, name = match[1].split("/")
    query = """query($owner:String!,$name:String!,$number:Int!,$after:String){
      repository(owner:$owner,name:$name){issue(number:$number){
        updatedAt comments(first:25,after:$after){
          totalCount nodes{id body authorAssociation} pageInfo{endCursor hasNextPage}}}}}"""
    params = {"owner": owner, "name": name, "number": int(match[3])}
    nodes = []
    seen_ids = set()
    seen_cursors = set()
    for _ in range(4):
        repository = graph(query, **params)["repository"]
        current = repository["issue"] if repository else None
        if not current or current["updatedAt"] != issue["updatedAt"]:
            return None
        page = current["comments"]
        if page["totalCount"] != count or not page["nodes"]:
            return None
        for node in page["nodes"]:
            if not node or node["id"] in seen_ids:
                return None
            seen_ids.add(node["id"])
            nodes.append(node)
        info = page["pageInfo"]
        if not info["hasNextPage"]:
            def comment_fields(node):
                return (node["body"], node.get("authorAssociation"))

            if len(nodes) == count and [comment_fields(node) for node in recent] == [
                comment_fields(node) for node in nodes[count - len(recent):]
            ]:
                return dict(issue, comments={"totalCount": count, "nodes": nodes})
            return None
        cursor = info["endCursor"]
        if not cursor or cursor in seen_cursors or len(nodes) >= count:
            return None
        seen_cursors.add(cursor)
        params["after"] = cursor
    return None


def project_approval(repo, meta, as_of):
    if has_minimum_stars(meta):
        return recent_approval(meta.get("nameWithOwner", repo).casefold(), as_of)
    return None


class ApprovalCoverageIncomplete(RuntimeError):
    pass


@lru_cache(maxsize=128)
def recent_approval(repo, as_of):
    owner, name = repo.casefold().split("/")
    cutoff = as_of - APPROVAL_WINDOW
    query = """query($o:String!,$n:String!,$after:String){
      repository(owner:$o,name:$n){pullRequests(first:25,after:$after,states:[OPEN,MERGED],
        orderBy:{field:UPDATED_AT,direction:DESC}){
        nodes{url updatedAt reviewDecision author{login}
          latestOpinionatedReviews(first:20){nodes{url state submittedAt authorAssociation author{login __typename}} pageInfo{hasNextPage}}}
        pageInfo{endCursor hasNextPage}}}}"""
    args = {"o": owner, "n": name}
    reviews_truncated = False
    for _ in range(4):
        repository = graph(query, **args)["repository"]
        if repository is None:
            raise RuntimeError("GitHub repository unavailable during approval check")
        page = repository["pullRequests"]
        for pr in page["nodes"]:
            if datetime.fromisoformat(pr["updatedAt"].replace("Z", "+00:00")) < cutoff:
                if reviews_truncated:
                    raise ApprovalCoverageIncomplete("Recent PR review results exceeded the search limit")
                return None
            if pr["reviewDecision"] == "CHANGES_REQUESTED":
                continue
            author = (pr["author"] or {}).get("login", "").casefold()
            reviews_page = pr["latestOpinionatedReviews"] or {}
            reviews_truncated |= reviews_page.get("pageInfo", {}).get("hasNextPage", False)
            for review in reviews_page.get("nodes", []):
                reviewer = review["author"] or {}
                if (review["state"] != "APPROVED" or not review["submittedAt"]
                    or review["authorAssociation"] not in {"OWNER", "MEMBER", "COLLABORATOR"}
                    or reviewer.get("__typename") != "User" or not reviewer.get("login")
                    or reviewer["login"].casefold() == author):
                    continue
                submitted = datetime.fromisoformat(review["submittedAt"].replace("Z", "+00:00"))
                if cutoff <= submitted <= as_of:
                    return {"pr": pr["url"], "review": review["url"], "submitted_at": review["submittedAt"]}
        if not page["pageInfo"]["hasNextPage"]:
            if reviews_truncated:
                raise ApprovalCoverageIncomplete("Recent PR review results exceeded the search limit")
            return None
        args["after"] = page["pageInfo"]["endCursor"]
    raise ApprovalCoverageIncomplete("Recent PR results exceeded the search limit")


def review_pages(repo, states, cutoff=None):
    owner, name = repo.split("/")
    query = """query($o:String!,$n:String!,$after:String){
      repository(owner:$o,name:$n){pullRequests(first:100,after:$after,states:STATES,
        orderBy:{field:UPDATED_AT,direction:DESC}){
      totalCount nodes{url state closedAt updatedAt authorAssociation author{login __typename}}
      pageInfo{endCursor hasNextPage}}}}""".replace("STATES", "[" + ",".join(states) + "]")
    args = {"o": owner, "n": name}
    rows = {}
    cursors = set()
    total = None
    for _ in range(4):
        repository = graph(query, **args).get("repository")
        if not repository:
            raise RuntimeError(f"Cannot read GitHub review window for {repo}")
        page = repository["pullRequests"]
        if total is None:
            total = page["totalCount"]
        if total != page["totalCount"]:
            break
        for pr in page["nodes"]:
            if not pr or pr["url"] in rows or pr["state"] not in states:
                return rows.values(), False
            rows[pr["url"]] = pr
        info = page["pageInfo"]
        if not info["hasNextPage"]:
            return rows.values(), len(rows) == total
        if not page["nodes"] or len(rows) >= total:
            break
        if cutoff and page["nodes"][-1]["updatedAt"][:10] < cutoff:
            return rows.values(), True
        cursor = info["endCursor"]
        if not cursor or cursor in cursors:
            break
        cursors.add(cursor)
        args["after"] = cursor
    return rows.values(), False


def external_pr(pr):
    author = pr.get("author") or {}
    return (pr["authorAssociation"] not in {"OWNER", "MEMBER", "COLLABORATOR"}
            and author.get("__typename") != "Bot" and not author.get("login", "").endswith("[bot]"))


@lru_cache(maxsize=64)
def reviews(repo, today):
    cutoff = (today - timedelta(days=28)).isoformat()
    opened, open_complete = review_pages(repo, ("OPEN",))
    closed, decisions_complete = review_pages(repo, ("CLOSED", "MERGED"), cutoff)
    decisions = sum(bool(pr["closedAt"]) and pr["closedAt"][:10] >= cutoff and external_pr(pr) for pr in closed)
    return {
        "decisions": decisions,
        "open": sorted(pr["url"] for pr in opened if external_pr(pr)),
        "complete": open_complete and decisions_complete,
        "open_complete": open_complete,
        "decisions_complete": decisions_complete,
        "limit": min(MAX_REVIEW_LIMIT, max(1, math.ceil(decisions / 4))),
    }


def issue_labels(issue):
    labels = {node["name"].lower() for node in issue["labels"]["nodes"]}
    return {INVITATION_ALIASES.get(label, label) for label in labels}


def required_actions(card):
    return (card.get("issue_requirements") or []) + (card.get("check_requirements") or [])


def has_maintainer_hold(comments):
    holders = set()
    for comment in comments:
        if comment.get("authorAssociation") not in {"OWNER", "MEMBER", "COLLABORATOR"}:
            continue
        lines = [line for line in comment["body"].splitlines() if not line.lstrip().startswith(">")]
        text = "\n".join(lines)
        mentions = {login.casefold() for login in re.findall(r"(?<![\w@])@([a-zA-Z0-9-]+)\b", text)}
        if re.search(r"<!--\s*maintainer:\s*claim-released\s*-->", text, re.I):
            holders.difference_update(mentions)
        elif re.search(
            r"\bI(?:['’]m| am) (?:holding|reserving) (?:this (?:one|issue)|(?:\w+ )?issues) for you\b",
            text,
            re.I,
        ) and mentions:
            addressed = re.search(r"^\s*(?:hi\s+)?@([a-zA-Z0-9-]+)\b", text, re.I)
            holders.update({addressed.group(1).casefold()} if addressed else mentions)
    return bool(holders)


def assignment_requirement(issue, files):
    explicit = (
        r"(?:must|required to|need to) be assigned before|wait (?:until|for).*?assign(?:ed|ment) before"
        r"|\b(?:must|need to) (?:request|get) (?:an? )?assignment before"
        r"|\bwait for (?:an? )?assignment\b"
        r"|\bwait until (?:a |the )?maintainer assigns (?:the |this )?issue to you before\b"
        r"|\bbefore you start:[ \t]+claim (?:an? |the )?issue\b"
    )
    if re.search(explicit, issue["title"] + "\n" + issue["body"], re.I):
        return "issue"
    for path in POLICIES:
        rules = files.get(path, "")
        claim_section = re.search(
            r"^#{1,6}[ \t]+claiming (?:an? |the )?issue[ \t]*\n"
            r"((?:(?!^#{1,6}[ \t])[\s\S])*)",
            rules, re.I | re.M,
        )
        if re.search(explicit, rules, re.I) or (
            claim_section and re.search(
                r"^[ \t]*(?:please[ \t]+)?comment (?:on it|on (?:the |this )?issue)"
                r"\s+(?:and|so)\s+(?:a |the )?maintainer assigns (?:it|the issue) to you\b",
                claim_section[1], re.I | re.M,
            )
        ):
            return path
    return None


def assess(
    issue, repo, meta, files, today, languages=(), minutes=60, reserve=10, kind=None
):
    if not issue or not has_minimum_stars(meta) or meta.get("incomplete_policy_files"):
        return None
    labels = issue_labels(issue)
    parent = issue.get("parent")
    if (
        parent
        and parent["url"].startswith("https://github.com/" + repo + "/issues/")
        and parent["state"] == "OPEN"
        and not parent["locked"]
        and not parent["assignees"]["totalCount"]
    ):
        labels |= issue_labels(parent) & INVITATION_LABELS.keys()
    subissues = issue.get("subIssues", {})
    children = subissues.get("nodes", [])
    if subissues.get("totalCount", len(children)) > len(children) or any(
        child["state"] == "OPEN" for child in children
    ):
        return
    text = issue["title"] + "\n" + issue["body"]
    if re.search(
        r"\b(?:into|to) Ukrainian\b|\bUkrainian (?:translation|locali[sz]ation|locale|language support)\b"
        r"|перев(?:од|ести)[^.!?\n]{0,60}на украинский",
        text, re.I,
    ):
        return
    policy = "\n".join(files[p] for p in POLICIES if p in files)
    license_id = (meta.get("licenseInfo") or {}).get("spdxId")
    if (
        issue["state"] != "OPEN"
        or issue["locked"]
        or issue["assignees"]["totalCount"]
        or issue["closedByPullRequestsReferences"]["totalCount"]
        or labels & BLOCK
        or not labels & INVITATION_LABELS.keys()
        or any(meta[k] for k in ("isArchived", "isFork", "isDisabled", "isPrivate"))
        or not license_id
        or license_id == "NOASSERTION"
        or (meta["pushedAt"] or "")[:10] < (today - timedelta(days=90)).isoformat()
    ):
        return
    banned = (
        r"(?:no|ban(?:ned)?|prohibit(?:ed)?|do not (?:accept|use)|don't (?:accept|use)|must not use)"
        r"\s+(?:generative\s+)?(?:AI|LLM|artificial intelligence)\b"
        r"|(?:AI|LLM)[^\n.]{0,55}(?:not allowed|not accepted|prohibited)"
        r"|\bhuman[- ]authored (?:code|patches|contributions|pull requests) only\b"
    )
    ownership = (
        r"\b(?:working on this|i(?:'ll| will) take this|i'm on it)\b"
        r"|\bI (?:am|have been) (?:already )?(?:implementing|fixing|working on) (?:this|it)\b"
        r"|\bI(?:'m| am) taking this(?: issue\b|(?=[.!?]|\s*$))|(?m:^[ \t]*/assignme\b)"
        r"|\bI (?:can|will) pick (?:this|this issue) up\b(?![^\n.!?]{0,40}\?)"
        r"|\bI(?:['’]d| would) like to work on this issue(?:[.!]\s+I(?:['’]ll| will)\b| by \w+ing\b)"
    )
    repo_pull = rf"(?:#|https://github\.com/{re.escape(repo)}/pull/)[1-9][0-9]*\b"
    competing_pull = rf"(?m)^[ \t]*(?:I (?:have )?)?opened (?:PR )?{repo_pull} (?:with a fix|to fix|to address|for this)\b"
    comments = issue["comments"]
    partial_discussion = comments.get("totalCount", len(comments["nodes"])) > len(comments["nodes"])
    if re.search(banned, policy + "\n" + text, re.I) or has_maintainer_hold(comments["nodes"]) or any(
        re.search(ownership, comment["body"], re.I) or re.search(competing_pull, comment["body"], re.I)
        for comment in comments["nodes"]
    ):
        return
    if assignment_requirement(issue, files):
        return

    issue_requirements = []
    comment_before_start = (
        r"(?:^|[.!?]\s+|\n)[ \t]*(?:please[ \t]+)?"
        r"(?:comment|(?:leave|post|add)[ \t]+a[ \t]+comment)"
        r"(?:[ \t]+(?:here|on[ \t]+(?:this|the)[ \t]+issue))?"
        r"[ \t]+before[ \t]+(?:starting\b|you[ \t]+start\b)"
    )
    if re.search(comment_before_start, issue["body"], re.I):
        issue_requirements.append("Comment on this issue before starting, as requested in the issue.")
    if re.search(r"\breserved for (?:a )?first[- ]time (?:[\w-]+ )?contributors?\b", issue["body"], re.I):
        issue_requirements.append("Confirm first-time contributor eligibility, as required in the issue.")

    policy_notes = []
    submission_requirements = []
    for path in POLICIES:
        rules = files.get(path, "")
        if not submission_requirements and re.search(
            r"(?:\b(?:each|every|all)\s+contributors?\s+(?:must\s+sign|signs?)"
            r"|\b(?:contributors?|you)\s+(?:must|need to)\s+sign"
            r"|(?:^|\n)\s*(?:[-*]\s+)?(?:please\s+)?sign)"
            r"\s+(?:the\s+|an?\s+)?\[?(?:contributor licen[cs]e agreement\b|CLA\b)",
            rules, re.I,
        ):
            submission_requirements.append(
                f"Check the contributor license agreement ({path}) before submission. "
                "Only the contributor can decide whether to sign it."
            )
        if re.search(
            r"\bif there is already an issue\b[^.!?]{0,120},\s*leave a comment first\b",
            rules,
            re.I,
        ):
            issue_requirements.append(f"Comment on the issue before starting ({path}).")
        if "good first issue" in labels and re.search(
            r"\bautonomous agents?\b[^#]{0,450}\bgood first issue\b[^#]{0,180}"
            r"\bmaintainer must authorize\b[^#]{0,110}\bassign\b",
            rules,
            re.I,
        ):
            policy_notes.insert(
                0, f"Autonomous work ({path}): confirm issue-specific maintainer authorization and assignment."
            )
            continue
        for line in rules.splitlines():
            if re.search(r"\b(?:AI|LLM|AI-assisted|AI-generated)\b", line, re.I) and re.search(
                r"\b(?:approval|permission|disclos\w*|attribution|policy|must|restricted)\b", line, re.I,
            ):
                snippet = "".join(char for char in line if char.isprintable()).strip()[:200]
                policy_notes.append(f"Review AI conditions ({path}): {snippet}")
                break
    stack, evidence = [], []
    for lang, (extensions, manifest, recipe) in LANGS.items():
        match = re.search(
            r"\b[\w./-]+\.(?:"
            + extensions
            + r")\b|(?<![\w])"
            + (re.escape(lang) if lang != "C" else r"(?!)")
            + r"(?![\w])",
            text,
            re.I if lang != "Go" else 0,
        )
        if match:
            stack.append(lang)
            evidence.append(match[0])
    primary = (meta.get("primaryLanguage") or {}).get("name")
    confidence = "issue" if stack else "repository only"
    if not stack:
        stack = [lang for lang, (_, manifest, _) in LANGS.items() if manifest in files]
        if primary and primary not in stack:
            stack.append(primary)
    if languages and not {s.lower() for s in stack}.intersection(
        s.lower() for s in languages
    ):
        return
    category = (
        "docs"
        if re.search(
            r"\b(doc(s|umentation)?|typo|readme)\b",
            issue["title"] + " " + " ".join(labels),
            re.I,
        )
        else "tests"
        if re.search(r"\btests?\b", issue["title"] + " " + " ".join(labels), re.I)
        else "code"
    )
    if kind and kind != category:
        return
    commands = issue_checks(issue["body"])
    has_issue_check = bool(commands)
    scope = sorted(set(re.findall(r"\b[\w.-]+(?:/[\w.-]+)+\.[A-Za-z0-9]+\b", text)))
    sources = {p: files[p] for p in POLICIES if p in files}
    sources["issue description"] = issue["body"]
    for src, source in sources.items():
        for cmd in re.findall(
            r"(?m)^\s*(?:\$ )?((?:python[3]? -m pytest|pytest|go test|cargo test|dotnet test|npm test|pnpm test|yarn test|make test|\./gradlew test|\./mvnw test|mvn test)\b[\w ./:-]{0,64})\s*$",
            source,
        ):
            entry = f"{cmd.strip()} ({src})"
            if entry not in commands:
                commands.append(entry)
            if src == "issue description":
                has_issue_check = True
    # Root scripts are repository-wide hints. A named nested file may be in another package.
    nested_js = re.search(r"\b[\w.-]+/(?:[\w.-]+/)*[\w.-]+\.(?:js|jsx|ts|tsx|mjs|cjs)\b", text)
    try:
        scripts = json.loads(files.get("package.json", "{}")).get("scripts", {})
        if not nested_js and scripts.get("test") and "no test specified" not in str(scripts["test"]):
            manager = (
                "pnpm"
                if "pnpm-lock.yaml" in files
                else "yarn"
                if "yarn.lock" in files
                else "npm"
            )
            commands.append(f"{manager} test (package.json)")
    except (ValueError, AttributeError):
        pass
    clear = bool(
        re.search(
            r"acceptance|expected|steps to reproduce|definition of done|\[[ x]\]",
            text,
            re.I,
        )
    )
    requirements = []
    if re.search(
        r"\b(?:real[- ]world|physical|real)\b[^.!?\n]{0,100}"
        r"\b(?:hardware|fixtures|devices|GPUs?)\b"
        r"|\b(?:hardware|device) testing remains manual\b"
        r"|\b(?:requires? (?:an? )?|with an? )CUDA (?:device|GPU)\b",
        text,
        re.I,
    ):
        requirements.append("Confirm physical equipment or real hardware fixtures and manual acceptance scope.")
    if re.search(r"\bkani(?:[- ]gate| verifier)\b", text, re.I):
        requirements.append("Confirm the Kani toolchain and required gate in the contributor environment.")
    estimates = {"docs": (15, 45), "tests": (30, 90), "code": (45, 120)}
    low, high = estimates[category]
    workspace_hints_only = bool(scope and commands and not has_issue_check)
    known = (clear or bool(evidence)) and not requirements
    if not known:
        fit = "investigate"
    elif low > minutes - reserve:
        return
    elif (
        high <= minutes - reserve and commands and not workspace_hints_only
        and not issue_requirements and not policy_notes and not partial_discussion
    ):
        fit = "fits"
    else:
        fit = "uncertain"
    priority = bool(
        labels & {"priority: high", "high priority", "p1", "p0", "high-priority"}
    )
    score = (
        {"fits": 60, "uncertain": 25, "investigate": 5}[fit]
        + 10 * bool(evidence)
        + 8 * bool(commands)
        + 6 * clear
        + int(priority)
    )
    unknown = ["Confirm AI and attribution policy, current ownership and actual scope."]
    unknown.extend(issue_requirements)
    unknown.extend(requirements)
    unknown.extend(submission_requirements)
    unknown.extend(policy_notes[:3])
    if partial_discussion:
        unknown.append("Only recent comments were checked; review the full discussion for claims.")
    if workspace_hints_only or nested_js:
        unknown.append("Repository checks may target a different module. Locate the affected module with scan --path.")
    if not commands:
        unknown.append("No check detected. Inspect CI or document the manual acceptance check.")
    else:
        unknown.append("Detected checks are unrun; verify their prerequisites locally.")
    if confidence != "issue":
        unknown.append("Issue stack inferred from repository files.")
    return dict(
        url=issue["url"],
        title=issue["title"],
        repo=repo,
        stars=meta["stargazerCount"],
        updated=issue["updatedAt"],
        license=license_id,
        signals=sorted(
            labels & {"good first issue", "help wanted", "documentation", "tests"}
        ),
        score=score,
        parent=(parent or {}).get("url"),
        stack=stack,
        stack_source=confidence,
        evidence=evidence,
        kind=category,
        fit=fit,
        minutes=[low, high] if known else None,
        checks=commands[:3],
        issue_requirements=issue_requirements,
        check_requirements=requirements,
        submission_requirements=submission_requirements,
        unknown=unknown,
        scope=scope[:6],
    )


API_ERRORS = (OSError, RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError)


def discover(languages, repo, limit, today, minutes=60, reserve=10, kind=None, *, report_errors=False, as_of=None):
    as_of = as_of or datetime.now(timezone.utc)
    coverage = set()
    errors = []

    def fetch(stage, function, *args, **kwargs):
        if "github_rate_limit" in coverage:
            return None
        try:
            return function(*args, **kwargs)
        except GitHubRateLimited:
            if not report_errors:
                raise
            coverage.add("github_rate_limit")
            errors.append(stage)
            return None
        except ApprovalCoverageIncomplete:
            if not report_errors:
                raise
            coverage.add("approval_search_limit")
            return None
        except API_ERRORS:
            if not report_errors:
                raise
            errors.append(stage)
            return None

    base = (
        "is:public is:issue is:open archived:false no:assignee -linked:pr updated:>="
        + (today - timedelta(days=90)).isoformat()
    )
    if repo:
        base += " repo:" + repo
    filters = [""] + [f' language:"{lang}"' for lang in languages[:4]]
    query = (
        "query($q:String!){search(type:ISSUE,first:35,query:$q){issueCount nodes{... on Issue{"
        + ISSUE
        + " repository{nameWithOwner stargazerCount}}}}}"
    )
    grouped = {}
    queries_completed = 0
    for scope in filters:
        for label, aliases in INVITATION_LABELS.items():
            label_filter = ",".join(f'"{name}"' for name in (label, *aliases))
            response = fetch("search", graph, query, q=base + scope + f" label:{label_filter} sort:updated-desc")
            if response is None:
                continue
            queries_completed += 1
            page = response["search"]
            rows = page["nodes"]
            if page.get("issueCount", len(rows)) > len(rows):
                coverage.add("search_result_limit")
            for row in rows:
                if row and has_minimum_stars(row["repository"]):
                    grouped.setdefault(row["repository"]["nameWithOwner"], {})[
                        row["url"]
                    ] = row
    if len(grouped) > 24:
        coverage.add("repository_limit")
    if len(languages) > 4:
        coverage.add("language_query_limit")
    picks = []
    repositories_checked = 0
    for name, issues in list(grouped.items())[:24]:
        repo_data = fetch("repository_metadata", metadata, name)
        if repo_data is None:
            continue
        repositories_checked += 1
        meta, files = repo_data
        if not has_minimum_stars(meta):
            continue
        if meta.get("incomplete_policy_files"):
            coverage.add("policy_file_limit")
            continue
        approval = fetch("project_approval", project_approval, name, meta, as_of)
        if not approval:
            continue
        children = list(
            dict.fromkeys(
                child["url"]
                for row in issues.values()
                for child in row.get("subIssues", {}).get("nodes", [])
                if child["state"] == "OPEN"
                and child["url"].startswith("https://github.com/" + name + "/issues/")
                and child["url"] not in issues
            )
        )
        if len(children) > 12 or any(
            group.get("totalCount", len(group["nodes"])) > len(group["nodes"])
            for row in issues.values()
            if (group := row.get("subIssues"))
        ):
            coverage.add("subissue_limit")
        for child in fetch("subissues", live_issues, children[:12]) or []:
            if child:
                issues[child["url"]] = child
        for row in issues.values():
            item = assess(
                row, name, meta, files, today, languages, minutes, reserve, kind
            )
            if item:
                item["stars"] = meta["stargazerCount"]
                item["recent_approval"] = approval
                picks.append(item)
    picks.sort(key=lambda i: (-i["score"], i["url"]))
    if not queries_completed:
        status = "api_error"
    elif errors or coverage:
        status = "partial"
    else:
        status = "complete" if picks else "empty"
    return {
        "candidates": picks[:limit],
        "repositories_checked": repositories_checked,
        "incomplete_search": bool(coverage or errors),
        "sampled_issues": sum(map(len, grouped.values())),
        "search_status": status,
        "coverage_limits": sorted(coverage),
        "api_errors": dict(sorted(Counter(errors).items())),
        "queries_completed": queries_completed,
    }
