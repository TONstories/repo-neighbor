import unittest
from pathlib import PurePosixPath

from finder import assess
from module_checks import hints, issue_checks
from test_campaign import META, NOW, REPO, ROW


class ModuleCheckTests(unittest.TestCase):
    def test_issue_prefers_explicit_python_test_to_generic_repository_check(self):
        row = dict(ROW, title="Fix readiness", body=(
            "Expected: validate scripts/wait.py. "
            "Run `python -m pytest test/test_wait.py -q`."
        ))
        item = assess(row, REPO, META, {"CONTRIBUTING.md": "pytest test/test_other.py"}, NOW.date())
        self.assertEqual(item["checks"][0], "python -m pytest test/test_wait.py -q (issue description)")
        self.assertEqual(issue_checks("pytest ../tests/test_wait.py\npytest tests/test_wait.py && echo bad"), [])

    def test_sibling_repository_command_does_not_mark_issue_as_fitting(self):
        row = dict(ROW, title="Fix query plan", body="Expected: edit crates/planner/src/explain.rs.")
        files = {"CONTRIBUTING.md": "cargo test --locked -p storage", "Cargo.toml": ""}
        item = assess(row, REPO, META, files, NOW.date(), minutes=180, reserve=10)
        self.assertEqual(item["fit"], "uncertain")
        self.assertTrue(any("a different module" in note for note in item["unknown"]))

    def test_issue_scoped_unittest_discovery(self):
        command = "python -m unittest discover -s tests -p test_report_results.py -v"
        self.assertEqual(issue_checks(f"Run `{command}`."), [f"{command} (issue description)"])
        self.assertEqual(issue_checks(command.replace("-s tests", "-s ../tests")), [])
        self.assertEqual(issue_checks(f"`{command} && echo bad`"), [])

    def test_js_root_hint_is_not_assumed_for_nested_file(self):
        row = dict(ROW, title="Fix UI", body="Expected: edit ui/src/widget.ts")
        item = assess(row, REPO, META, {"package.json": '{"scripts":{"test":"server-tests"}}'}, NOW.date())
        self.assertEqual(item["checks"], [])

    def test_js_hint_uses_nearest_package_and_workspace_manager(self):
        files = {
            "package.json": '{"scripts":{"test":"server-tests"}}',
            "pnpm-lock.yaml": "",
            "ui/package.json": '{"scripts":{"test":"ui-tests"}}',
            "ui/src/widget.ts": "",
        }
        focus = PurePosixPath("ui/src/widget.ts")
        self.assertEqual(hints(focus, files, [str(focus)], files.__getitem__), [{
            "cwd": "ui", "argv": ["pnpm", "test"],
            "source": "ui/package.json", "status": "unrun",
        }])
        files["ui/package.json"] = '{"scripts":{}}'
        self.assertEqual(hints(focus, files, [str(focus)], files.__getitem__), [])

    def test_js_workspace_root_script_is_not_a_module_hint(self):
        focus = PurePosixPath("packages/server/src/handler.ts")
        for workspace in (
            {"package.json": '{"workspaces":["packages/*"],"scripts":{"test":"npm test --workspace=ui"}}'},
            {"package.json": '{"scripts":{"test":"pnpm --filter ui test"}}',
             "pnpm-workspace.yaml": 'packages:\n  - "packages/*"\n'},
        ):
            with self.subTest(workspace=workspace):
                files = {**workspace, str(focus): "", "packages/ui/package.json": '{"name":"ui"}'}
                self.assertEqual(hints(focus, files, [str(focus)], files.__getitem__), [])
                files["packages/server/package.json"] = '{"scripts":{"test":"node --test"}}'
                hint, = hints(focus, files, [str(focus)], files.__getitem__)
                self.assertEqual(hint["cwd"], "packages/server")
                self.assertEqual(hint["source"], "packages/server/package.json")

    def test_python_does_not_reuse_same_named_test_in_a_sibling_module(self):
        files = dict.fromkeys(("ui/pyproject.toml", "api/pyproject.toml", "ui/src/widget.py",
                               "api/tests/test_widget.py", "ui/tests/test_widget.py"))
        focus = PurePosixPath("ui/src/widget.py")
        hint, = hints(focus, files, [str(focus)], files.__getitem__)
        self.assertEqual(hint["argv"], ["python3", "-m", "pytest", "tests/test_widget.py"])
        self.assertEqual(hint["source"], "ui/tests/test_widget.py")
        del files["ui/tests/test_widget.py"]
        self.assertEqual(hints(focus, files, [str(focus)], files.__getitem__), [])

    def test_issue_extracts_indented_pytest_command(self):
        self.assertEqual(issue_checks("    $ pytest tests/test_wait.py -q"),
                         ["pytest tests/test_wait.py -q (issue description)"])

    def test_rust_scoped_test_uses_named_package_and_required_features(self):
        from module_checks import tomllib

        if tomllib is None:
            self.skipTest("Rust manifest parsing uses tomllib")
        files = {
            "Cargo.toml": '[workspace]\nmembers = ["ui", "api"]',
            "api/Cargo.toml": '[package]\nname = "api"',
            "ui/Cargo.toml": ('[package]\nname = "ui"\n'
                              '[[test]]\nname = "render"\nrequired-features = ["pixels", "extra"]'),
            "ui/tests/render.rs": "",
        }
        focus = PurePosixPath("ui/tests/render.rs")
        self.assertEqual(hints(focus, files, [str(focus)], files.__getitem__), [{
            "argv": ["cargo", "test", "-p", "ui", "--test", "render", "--features", "pixels,extra"],
            "cwd": "ui", "source": "ui/Cargo.toml", "status": "unrun",
        }])

    def test_dotnet_hint_uses_static_project_reference_and_pinned_runner(self):
        focus = PurePosixPath("src/Widget/Rendering/Shape.cs")
        tests = "checks/Render/Rendering.Tests.csproj"
        test_project = (
            '<Project><ItemGroup><PackageReference Include="xunit.v3.mtp-v2" />'
            '<ProjectReference Include="$(MSBuildThisFileDirectory)..\\..\\src\\Widget\\Widget.csproj" />'
            '</ItemGroup></Project>'
        )
        files = {
            str(focus): "",
            "src/Widget/Widget.csproj": '<Project Sdk="Microsoft.NET.Sdk" />',
            tests: test_project,
            "checks/global.json": '{"test":{"runner":"Microsoft.Testing.Platform"}}',
            "global.json": "{}",
            "checks/Other/Widget.Tests.csproj": test_project.replace("src\\Widget", "src\\Other"),
            "checks/Pattern/Widget.Tests.csproj": test_project.replace("Widget.csproj", "*.csproj"),
        }
        self.assertEqual(hints(focus, files, [str(focus)], files.__getitem__), [{
            "argv": ["dotnet", "test", "--project", "./Render/Rendering.Tests.csproj"],
            "cwd": "checks", "source": tests, "status": "unrun",
        }])
        del files[tests]
        self.assertEqual(hints(focus, files, [str(focus)], files.__getitem__), [])

    def test_dotnet_vstest_uses_exact_test_project(self):
        project = PurePosixPath("checks/Utilities.csproj")
        files = {
            str(project): ('<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">'
                           '<PropertyGroup><IsTestProject>true</IsTestProject></PropertyGroup></Project>'),
            "checks/Support.csproj": '<Project Sdk="Microsoft.NET.Sdk" />',
            "checks/WidgetTest.cs": "",
        }
        self.assertEqual(hints(project, files, [str(project)], files.__getitem__), [{
            "argv": ["dotnet", "test", "./checks/Utilities.csproj"],
            "cwd": ".", "source": str(project), "status": "unrun",
        }])
        focus = PurePosixPath("checks/WidgetTest.cs")
        self.assertEqual(hints(focus, files, [str(focus)], files.__getitem__), [])
