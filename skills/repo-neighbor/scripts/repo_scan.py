"""Map one committed Git tree without executing code from the checkout."""

from collections import Counter
from pathlib import PurePosixPath
import os
import re
import subprocess

MANIFESTS = set(
    """package.json pnpm-workspace.yaml pyproject.toml setup.py setup.cfg tox.ini
Cargo.toml go.mod go.work pom.xml build.gradle build.gradle.kts settings.gradle.kts
Gemfile composer.json Package.swift CMakeLists.txt Makefile mix.exs pubspec.yaml
build.sbt deno.json bun.lock yarn.lock pnpm-lock.yaml package-lock.json poetry.lock
uv.lock Cargo.lock go.sum global.json""".split()
)
SOURCE = set(
    "py js jsx ts tsx mjs cjs rs go java kt kts rb php c h cc cpp hpp cs swift sh dart ex exs scala lua r jl vue svelte".split()
)
NOISE = set(
    "vendor vendors third_party node_modules dist build target coverage .venv generated __pycache__".split()
)


def git(root, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        check=check,
        timeout=60,
        env={**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0"},
    )


def map_repo(root, focus=None, term=None):
    top = git(root, "rev-parse", "--show-toplevel").stdout.decode().rstrip("\n")
    rev = git(top, "rev-parse", "--verify", "HEAD^{commit}").stdout.decode().strip()
    tree = git(top, "ls-tree", "-rlz", "--full-tree", rev).stdout
    files = {}
    for record in tree.split(b"\0"):
        if not record:
            continue
        meta, raw = record.split(b"\t", 1)
        mode, _, _, size = meta.split()
        if mode not in (b"100644", b"100755"):
            continue
        name = raw.decode("utf-8", errors="surrogateescape")
        parts = PurePosixPath(name).parts
        if (
            NOISE.intersection(parts)
            or any(
                re.search(
                    r"(?:^|[._-])(?:secrets?|credentials?|private[-_]key)(?:$|[._-])",
                    part,
                    re.I,
                )
                or part.startswith(".env")
                for part in parts
            )
            or any(not c.isprintable() for c in name)
        ):
            continue
        files[name] = int(size)
    prefix = PurePosixPath(focus or ".")
    if prefix.is_absolute() or ".." in prefix.parts:
        raise ValueError("--path must be relative to the repository root")
    selected = [
        p
        for p in files
        if prefix == PurePosixPath(".")
        or p == str(prefix)
        or p.startswith(str(prefix) + "/")
    ]
    if not selected:
        raise ValueError("No committed files in this scope after exclusions")
    # Root policies and ancestor instructions can apply to a single target file.
    parent = prefix.parent if str(prefix) in files else prefix
    ancestors = {str(p) for p in (parent, *parent.parents)}

    def policy(path):
        name = PurePosixPath(path).name.lower()
        return name.split(".")[0] in {
            "agents",
            "claude",
            "contributing",
            "codeowners",
            "security",
            "governance",
            "ai_policy",
            "ai-policy",
            "pull_request_template",
        } or path.lower().startswith(
            (
                ".github/pull_request_template/",
                ".github/instructions/",
                ".cursor/rules/",
            )
        )

    def nearby(path):
        return (
            path in in_scope
            or str(PurePosixPath(path).parent) in ancestors
            or path.startswith(".github/")
            or path == "docs/CODEOWNERS"
        )

    in_scope = set(selected)
    sections = {
        "Instructions and ownership": [p for p in files if nearby(p) and policy(p)],
        "Read first": [
            p
            for p in files
            if nearby(p) and PurePosixPath(p).name.lower().startswith("readme")
        ],
        "Manifests and build files": [
            p
            for p in files
            if nearby(p)
            and (PurePosixPath(p).name in MANIFESTS or p.endswith(".csproj"))
        ],
        "Possible entry points": [
            p
            for p in selected
            if PurePosixPath(p).stem.lower()
            in {"main", "__main__", "cli", "app", "program", "index", "lib"}
            and PurePosixPath(p).suffix[1:].lower() in SOURCE
        ],
        "CI definitions": [
            p
            for p in files
            if p.startswith(".github/workflows/")
            or p in {".gitlab-ci.yml", "Jenkinsfile", ".circleci/config.yml"}
        ],
        "Tests in scope": [
            p
            for p in selected
            if re.search(
                r"(^|/)(tests?|spec|__tests__)/|(^|/)(test_|spec_)|[._](test|spec)\.",
                p,
                re.I,
            )
            or p.endswith("_test.go")
        ],
    }

    def rank(path):
        return (path not in in_scope, len(PurePosixPath(path).parts), path)

    result = {
        "commit": rev,
        "scope": str(prefix),
        "files": len(selected),
        "extensions": dict(
            Counter(
                PurePosixPath(p).suffix.lower()
                for p in selected
                if PurePosixPath(p).suffix
            ).most_common(8)
        ),
        "sections": {},
    }
    if term is not None:
        if not term.strip() or len(term) > 200 or "\n" in term:
            raise ValueError(
                "--term requires one literal phrase of up to 200 characters"
            )
        candidates = sorted(
            (
                p
                for p in selected
                if PurePosixPath(p).suffix[1:].lower() in SOURCE
                and files[p] <= 512000
                and not p.endswith((".min.js", ".d.ts.map"))
            ),
            key=rank,
        )
        sampled = candidates[:1000]
        matches = []
        for offset in range(0, len(sampled), 100):
            paths = sampled[offset : offset + 100]
            proc = git(
                top,
                "--literal-pathspecs",
                "grep",
                "--no-textconv",
                "-IlzF",
                "-e",
                term,
                rev,
                "--",
                *paths,
                check=False,
            )
            if proc.returncode not in {0, 1}:
                raise ValueError("Git could not search the selected source files")
            matches.extend(
                s.split(b":", 1)[1].decode() for s in proc.stdout.split(b"\0") if s
            )
        sections["Literal matches (inspect definitions and callers)"] = matches
        result["searched_source_files"] = len(sampled)
        result["eligible_source_files"] = len(candidates)
    for label, paths in sections.items():
        result["sections"][label] = {
            "count": len(paths),
            "paths": sorted(paths, key=rank)[:10],
        }
    return result


def display(result):
    print(
        f"Commit {result['commit']} | Scope {result['scope']} | {result['files']} files"
    )
    print(
        "Extensions:", ", ".join(f"{k} ({v})" for k, v in result["extensions"].items())
    )
    if "searched_source_files" in result:
        print(
            f"Literal search: {result['searched_source_files']}/{result['eligible_source_files']} eligible source files"
        )
    for label, group in result["sections"].items():
        print(f"\n{label} ({group['count']}, showing {len(group['paths'])})")
        for path in group["paths"]:
            print(" ", path)
