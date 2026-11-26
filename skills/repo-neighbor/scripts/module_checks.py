"""Discover unexecuted test hints from issue text and committed module files."""

import json
import posixpath
import re
import xml.etree.ElementTree as ET
from pathlib import PurePosixPath

try:
    import tomllib
except ImportError:  # Python 3.8–3.10 can still scan the other stacks.
    tomllib = None


PYTHON_MANIFESTS = {"pyproject.toml", "setup.py", "setup.cfg", "tox.ini"}
DOTNET_TEST_PACKAGES = {
    "microsoft.net.test.sdk", "mstest", "mstest.testframework", "nunit",
    "xunit", "xunit.v3", "xunit.v3.mtp-v2",
}


def issue_checks(body):
    # Select file-scoped Python checks, including standalone commands quoted inline.
    pattern = (
        r"(?m)(?:^\s*(?:\$ )?|`)"
        r"((?:python3? -m )?pytest(?: -[A-Za-z]+)* +"
        r"(?:[\w.-]+/)*test_[\w.-]+\.py(?:::[\w.]+)*(?: -[A-Za-z]+)*|"
        r"python3? -m unittest discover -s [\w.][\w./-]*"
        r" -p test_[\w.-]+\.py(?: -[qv])?)"
        r"(?=`|[ \t]*$)"
    )
    return [
        f"{cmd} (issue description)"
        for cmd in dict.fromkeys(re.findall(pattern, body))
        if not any(".." in PurePosixPath(arg).parts for arg in cmd.split())
    ]


def nearest_manifest(path, names, files):
    for directory in (path, *path.parents):
        for name in sorted(names):
            manifest = directory / name
            if str(manifest) in files:
                return manifest
    return None


def hints(focus, files, selected, read):
    if focus == PurePosixPath("."):
        return []
    target = str(focus) in files
    directory = focus.parent if target else focus
    suffixes = {focus.suffix} if target else {PurePosixPath(p).suffix for p in selected}
    results = []

    def add(cwd, argv, source):
        results.append({
            "cwd": str(cwd), "argv": argv, "source": str(source), "status": "unrun",
        })

    if suffixes & {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
        manifest = nearest_manifest(directory, {"package.json"}, files)
        if manifest:
            try:
                data = json.loads(read(str(manifest)))
            except (ValueError, UnicodeError):
                data = {}
            if isinstance(data, dict):
                scripts = data.get("scripts")
                test = scripts.get("test") if isinstance(scripts, dict) else None
                workspace = data.get("workspaces") or str(manifest.parent / "pnpm-workspace.yaml") in files
                if (not workspace and isinstance(test, str) and test.strip()
                    and "no test specified" not in test):
                    manager = package_manager(manifest.parent, files, read)
                    if manager:
                        add(manifest.parent, [manager, "test"], manifest)

    if ".go" in suffixes:
        manifest = nearest_manifest(directory, {"go.mod"}, files)
        tests = [p for p in files if p.endswith("_test.go") and PurePosixPath(p).parent == directory]
        if manifest and tests:
            add(directory, ["go", "test", "-count=1", "."], tests[0])

    if ".py" in suffixes and target:
        manifest = nearest_manifest(directory, PYTHON_MANIFESTS, files)
        if manifest:
            module = manifest.parent
            expected = focus.name if focus.name.startswith("test_") else f"test_{focus.stem}.py"
            tests = [
                p for p in map(PurePosixPath, files)
                if p.name == expected
                and nearest_manifest(p.parent, PYTHON_MANIFESTS, files) == manifest
            ]
            if len(tests) == 1:
                add(module, ["python3", "-m", "pytest", str(tests[0].relative_to(module))], tests[0])
    if ".rs" in suffixes and tomllib is not None:
        manifest = nearest_manifest(directory, {"Cargo.toml"}, files)
        if manifest:
            argv = rust_check(manifest, focus, read)
            if argv:
                add(manifest.parent, argv, manifest)
    if suffixes & {".cs", ".csproj"}:
        for cwd, argv, project in dotnet_checks(focus, directory, files, read):
            add(cwd, argv, project)
    return results


def dotnet_checks(focus, directory, files, read):
    projects = sorted(PurePosixPath(p) for p in files if p.endswith(".csproj"))
    if focus in projects:
        source = focus
    else:
        for ancestor in (directory, *directory.parents):
            candidates = [project for project in projects if project.parent == ancestor]
            if not candidates:
                continue
            if len(candidates) != 1:
                return
            source = candidates[0]
            break
        else:
            return

    for project in projects:
        try:
            xml = read(str(project))
            if "<!DOCTYPE" in xml:
                continue
            root = ET.fromstring(xml)
        except (ValueError, ET.ParseError):
            continue
        elements = [
            (item.tag.rsplit("}", 1)[-1], item)
            for group in root
            if not group.get("Condition")
            for item in group
            if not item.get("Condition")
        ]
        test_flags = {item.text.strip().lower() for tag, item in elements
                      if tag == "IsTestProject" and item.text}
        is_test = root.get("Sdk", "").split("/")[0] == "MSTest.Sdk" or any(
            tag == "PackageReference" and item.get("Include", "").lower() in DOTNET_TEST_PACKAGES
            for tag, item in elements
        )
        if test_flags != {"true"} and (test_flags or not is_test):
            continue
        if project != source and not any(
            tag == "ProjectReference" and dotnet_reference(project, item.get("Include", "")) == str(source)
            for tag, item in elements
        ):
            continue
        config = nearest_manifest(project.parent, {"global.json"}, files)
        cwd = config.parent if config else PurePosixPath(".")
        test_runner = "VSTest"
        if config:
            try:
                test_runner = json.loads(read(str(config))).get("test", {}).get("runner", "VSTest")
            except (ValueError, AttributeError):
                continue
        argv = ["dotnet", "test"]
        if test_runner == "Microsoft.Testing.Platform":
            argv.append("--project")
        elif test_runner != "VSTest":
            continue
        yield cwd, [*argv, f"./{project.relative_to(cwd)}"], project


def dotnet_reference(project, include):
    anchor = "$(MSBuildThisFileDirectory)"
    if include.startswith(anchor):
        include = include[len(anchor):]
    path = include.replace("\\", "/")
    if not path or path.startswith("/") or any(char in path for char in "$%@*?;:"):
        return None
    return posixpath.normpath(str(project.parent / path))


def rust_check(manifest, focus, read):
    try:
        data = tomllib.loads(read(str(manifest)))
    except (ValueError, UnicodeError):
        return None
    package = data.get("package", {})
    if not isinstance(package, dict):
        return None
    name = package.get("name")
    if not isinstance(name, str) or not re.fullmatch(r"[\w-]+", name):
        return None
    argv = ["cargo", "test", "-p", name]
    relative = focus.relative_to(manifest.parent)
    tests = data.get("test", [])
    if not isinstance(tests, list):
        return None
    for test in tests:
        if not isinstance(test, dict):
            continue
        test_name = test.get("name")
        if not isinstance(test_name, str) or not re.fullmatch(r"[\w-]+", test_name):
            continue
        if str(relative) != test.get("path", f"tests/{test_name}.rs"):
            continue
        features = test.get("required-features", [])
        if not isinstance(features, list) or not all(
            isinstance(flag, str) and re.fullmatch(r"[\w+./?-]+", flag) and not flag.startswith("-")
            for flag in features
        ):
            return None
        argv += ["--test", test_name]
        if features:
            argv += ["--features", ",".join(features)]
        return argv
    return argv


def package_manager(directory, files, read):
    locks = {"package-lock.json": "npm", "pnpm-lock.yaml": "pnpm", "yarn.lock": "yarn",
             "bun.lock": "bun", "bun.lockb": "bun"}
    for ancestor in (directory, *directory.parents):
        manifest = str(ancestor / "package.json")
        if manifest in files:
            try:
                data = json.loads(read(manifest))
            except (ValueError, UnicodeError):
                data = {}
            if isinstance(data, dict) and isinstance(data.get("packageManager"), str):
                manager = data["packageManager"].split("@", 1)[0]
                return manager if manager in locks.values() else None
        detected = {manager for lock, manager in locks.items() if str(ancestor / lock) in files}
        if detected:
            return min(detected) if len(detected) == 1 else None
    return "npm"
