"""Read-only GitHub discovery. Never execute commands supplied by target repositories."""

import json
import math
import re
import subprocess
import time
from datetime import timedelta
from functools import lru_cache

SLUG = r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
URL = re.compile(r"https://github\.com/(" + SLUG + r")/(issues|pull)/([1-9][0-9]*)")
BLOCK = {"blocked", "wontfix", "duplicate", "in progress", "invalid", "claimed"}
LANGS = {
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
 subIssues(first:12){nodes{url state}} assignees(first:1){totalCount}
 labels(first:40){nodes{name}} comments(last:8){nodes{body}}
 closedByPullRequestsReferences(first:1){totalCount}"""
POLICIES = [
    "CONTRIBUTING.md",
    ".github/CONTRIBUTING.md",
    "docs/CONTRIBUTING.md",
    "AI_POLICY.md",
    "AI_POLICY",
    "AGENTS.md",
    "README.md",
]
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
META = """repositoryTopics(first:50){nodes{topic{name}}} nameWithOwner isPrivate isFork isArchived isDisabled pushedAt
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


def graph(query, **params):
    cmd = ["gh", "api", "--hostname", "github.com", "graphql", "-f", "query=" + query]
    for k, v in params.items():
        cmd += ["-F" if isinstance(v, int) else "-f", f"{k}={v}"]
    for attempt in range(3):
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
        except subprocess.TimeoutExpired:
            if attempt == 2:
                raise
            time.sleep(2**attempt)
            continue
        if (
            not res.returncode
            or not re.search(
                "TLS handshake timeout|connection reset|HTTP 50[234]", res.stderr
            )
            or attempt == 2
        ):
            break
        time.sleep(2**attempt)
    if res.returncode and res.stdout:
        partial = json.loads(res.stdout)
        errors = partial.get("errors", [])
        if (
            errors
            and all(e.get("type") == "NOT_FOUND" for e in errors)
            and partial.get("data")
        ):
            return partial["data"]
    if res.returncode:
        raise RuntimeError(res.stderr.strip() or "GitHub query failed")
    result = json.loads(res.stdout)
    if result.get("errors"):
        raise RuntimeError(str(result["errors"]))
    return result["data"]


@lru_cache(maxsize=64)
def metadata(repo):
    owner, name = repo.split("/")
    data = graph(
        "query($o:String!,$n:String!){repository(owner:$o,name:$n){" + META + "}}",
        o=owner,
        n=name,
    )["repository"]
    if not data:
        return {}, {}
    files = {
        p: (data[f"f{i}"].get("text") or "")[:90000]
        for i, p in enumerate(FILES)
        if data.get(f"f{i}")
    }
    return data, files


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


@lru_cache(maxsize=64)
def reviews(repo, today):
    owner, name = repo.split("/")
    query = """query($o:String!,$n:String!,$after:String){
      repository(owner:$o,name:$n){pullRequests(first:100,after:$after,orderBy:{field:UPDATED_AT,direction:DESC}){
      nodes{url state closedAt updatedAt authorAssociation author{login}} pageInfo{endCursor hasNextPage}}}}"""
    cutoff = (today - timedelta(days=28)).isoformat()
    decisions, opened = 0, set()
    # Old open PRs still occupy review capacity, even outside the decision window.
    open_total = graph(
        """query($o:String!,$n:String!){repository(owner:$o,name:$n){
      pullRequests(states:OPEN){totalCount}}}""",
        o=owner,
        n=name,
    )["repository"]["pullRequests"]["totalCount"]
    all_open = 0
    args = {"o": owner, "n": name}
    complete = False
    for _ in range(4):
        page = graph(query, **args)["repository"]["pullRequests"]
        for pr in page["nodes"]:
            external = pr["authorAssociation"] not in (
                "OWNER",
                "MEMBER",
                "COLLABORATOR",
            ) and not ((pr.get("author") or {}).get("login", "").endswith("[bot]"))
            if pr["state"] == "OPEN":
                all_open += 1
                if external:
                    opened.add(pr["url"])
            elif external and pr["closedAt"] and pr["closedAt"][:10] >= cutoff:
                decisions += 1
        if not page["pageInfo"]["hasNextPage"] or (
            page["nodes"][-1]["updatedAt"][:10] < cutoff and all_open == open_total
        ):
            complete = True
            break
        args["after"] = page["pageInfo"]["endCursor"]
    return {
        "decisions": decisions,
        "open": sorted(opened),
        "complete": complete,
        "limit": min(5, max(1, math.ceil(decisions / 4))),
    }


def assess(
    issue, repo, meta, files, today, languages=(), minutes=60, reserve=10, kind=None
):
    if not issue or not meta:
        return None
    labels = {n["name"].lower() for n in issue["labels"]["nodes"]}
    parent = issue.get("parent")
    if (
        parent
        and parent["url"].startswith("https://github.com/" + repo + "/issues/")
        and parent["state"] == "OPEN"
        and not parent["locked"]
        and not parent["assignees"]["totalCount"]
    ):
        labels |= {n["name"].lower() for n in parent["labels"]["nodes"]} & {
            "help wanted",
            "good first issue",
        }
    if any(
        child["state"] == "OPEN"
        for child in issue.get("subIssues", {}).get("nodes", [])
    ):
        return
    text = issue["title"] + "\n" + issue["body"]
    policy = "\n".join(files[p] for p in POLICIES if p in files)
    license_id = (meta.get("licenseInfo") or {}).get("spdxId")
    if (
        issue["state"] != "OPEN"
        or issue["locked"]
        or issue["assignees"]["totalCount"]
        or issue["closedByPullRequestsReferences"]["totalCount"]
        or labels & BLOCK
        or not labels & {"good first issue", "help wanted"}
        or any(meta[k] for k in ("isArchived", "isFork", "isDisabled", "isPrivate"))
        or not license_id
        or license_id == "NOASSERTION"
        or (meta["pushedAt"] or "")[:10] < (today - timedelta(days=90)).isoformat()
    ):
        return
    banned = r"(?:no|ban(?:ned)?|prohibit(?:ed)?|do not (?:accept|use)|don't (?:accept|use)|must not use)\s+(?:generative\s+)?(?:AI|LLM|artificial intelligence)\b|(?:AI|LLM)[^\n.]{0,55}(?:not allowed|not accepted|prohibited)"
    comments = "\n".join(c["body"] for c in issue["comments"]["nodes"])
    if re.search(banned, policy + "\n" + text, re.I) or re.search(
        r"\b(?:working on this|i(?:'ll| will) take this|i'm on it|/assignme)\b",
        comments,
        re.I,
    ):
        return
    assignment_required = re.search(
        r"(?:must|required to|need to) be assigned before|wait (?:until|for).*?assign(?:ed|ment) before",
        policy,
        re.I,
    )
    if assignment_required:
        return
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
    commands = []
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
    try:
        scripts = json.loads(files.get("package.json", "{}")).get("scripts", {})
        if scripts.get("test") and "no test specified" not in str(scripts["test"]):
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
    estimates = {"docs": (15, 45), "tests": (30, 90), "code": (45, 120)}
    low, high = estimates[category]
    known = clear or bool(evidence)
    fit = (
        "fits"
        if known and high <= minutes - reserve
        else "investigate"
        if not known
        else "uncertain"
        if low <= minutes - reserve
        else "too long"
    )
    if fit == "too long":
        return
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
    if not commands:
        unknown.append("Inspect the project's CI for its exact check.")
    if confidence != "issue":
        unknown.append("Issue stack inferred from repository files.")
    return dict(
        url=issue["url"],
        title=issue["title"],
        repo=repo,
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
        unknown=unknown,
        scope=sorted(set(re.findall(r"\b[\w.-]+(?:/[\w.-]+)+\.[A-Za-z0-9]+\b", text)))[
            :20
        ],
    )


def discover(languages, repo, limit, today, minutes=60, reserve=10, kind=None):
    base = (
        "is:public is:issue is:open archived:false no:assignee -linked:pr updated:>="
        + (today - timedelta(days=90)).isoformat()
    )
    if repo:
        base += " repo:" + repo
    filters = [""] + [f' language:"{lang}"' for lang in languages[:4]]
    query = (
        "query($q:String!){search(type:ISSUE,first:35,query:$q){nodes{... on Issue{"
        + ISSUE
        + " repository{nameWithOwner}}}}}"
    )
    grouped = {}
    for scope in filters:
        for label in ("good first issue", "help wanted"):
            rows = graph(query, q=base + scope + f' label:"{label}" sort:updated-desc')[
                "search"
            ]["nodes"]
            for row in rows:
                if row:
                    grouped.setdefault(row["repository"]["nameWithOwner"], {})[
                        row["url"]
                    ] = row
    picks = []
    for name, issues in list(grouped.items())[:24]:
        meta, files = metadata(name)
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
        for child in live_issues(children[:12]):
            if child:
                issues[child["url"]] = child
        for row in issues.values():
            item = assess(
                row, name, meta, files, today, languages, minutes, reserve, kind
            )
            if item:
                picks.append(item)
    picks.sort(key=lambda i: (-i["score"], i["url"]))
    return {
        "candidates": picks[:limit],
        "repositories_checked": min(len(grouped), 24),
        "incomplete_search": len(grouped) > 24,
        "sampled_issues": sum(map(len, grouped.values())),
    }
