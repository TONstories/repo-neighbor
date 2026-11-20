import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from test_community import c


class LocalWorkTest(unittest.TestCase):
    def test_brief_retains_requested_outcome(self):
        from quota import acceptance_criteria
        self.assertEqual(acceptance_criteria("Current behavior\n## Acceptance criteria\n- Expected outcome\n\n---\nFooter"), "- Expected outcome")
        self.assertEqual(acceptance_criteria("No criteria heading"), "")

    def test_report_without_pr_and_duplicate(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            row = dict(user="Alice", agent="Zcode CLI", stage="tested_patch",
                       at="2026-11-20T16:30:00Z", issue="https://github.com/test/docs/issues/1",
                       artifact_sha256="a" * 64, summary="Verified local patch")
            path = root / "local-work.json"
            path.write_text(json.dumps([row]))
            now = datetime(2026, 11, 20, 18, tzinfo=timezone.utc)
            for _ in range(2):
                c.reports(root, {"claims": []}, [], now, {})
            for period in ("2026-11-20", "2026-W47"):
                text = (root / "reports" / (period + ".md")).read_text()
                self.assertEqual(text.count("Verified local patch"), 1)
            report = (root / "reports/README.md").read_text()
            self.assertIn("1 participants · 0 PRs · 0 merged", report)
            self.assertIn("ballot weight 1", report)
            path.write_text(json.dumps([row, dict(row, user="alice")]))
            with self.assertRaises(ValueError):
                c.local_work(root)
