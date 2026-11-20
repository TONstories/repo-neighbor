import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CLI = Path(__file__).resolve().parents[1] / "skills/repo-neighbor/scripts/quota.py"


class ScanTests(unittest.TestCase):
    def test_scan_through_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def git(*args):
                subprocess.run(
                    ["git", "-C", tmp, *args], check=True, capture_output=True
                )

            git("init")
            for name in (
                "AGENTS.md",
                "tool/AGENTS.md",
                "tool/main.py",
                "tool/a[1].py",
                "tool/tests/test_api.py",
                "tool/vendor/ignore.py",
                "tool/credentials.py",
                "other/file.py",
            ):
                p = root / name
                p.parent.mkdir(exist_ok=True, parents=True)
                p.write_text("probe_symbol\n")
            git("add", ".")
            git(
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.org",
                "commit",
                "-m",
                "Fixture",
            )
            (root / "tool/untracked.py").touch()
            (root / "tool/main.py").write_text("new_worktree_value")
            cmd = [
                sys.executable,
                str(CLI),
                "scan",
                tmp,
                "--path",
                "tool",
                "--term",
                "probe_symbol",
                "--json",
            ]
            result = json.loads(subprocess.check_output(cmd))
            self.assertEqual(result["searched_source_files"], 3)
            groups = result["sections"]
            self.assertEqual(
                set(groups["Instructions and ownership"]["paths"]),
                {"AGENTS.md", "tool/AGENTS.md"},
            )
            self.assertEqual(
                groups["Tests in scope"]["paths"], ["tool/tests/test_api.py"]
            )
            self.assertEqual(
                next(
                    v["count"]
                    for k, v in groups.items()
                    if k.startswith("Literal matches")
                ),
                3,
            )
            self.assertNotEqual(
                subprocess.run(
                    cmd + ["--path", "../outside"], capture_output=True
                ).returncode,
                0,
            )
