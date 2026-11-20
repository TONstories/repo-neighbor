import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/quota-for-good/scripts"))
import quota


class WorkflowTests(unittest.TestCase):
    def test_visible_credit(self):
        for body in (quota.CREDIT, (ROOT / "templates/contribution.md").read_text()):
            self.assertTrue(quota.has_credit(body))
        for body in ("", quota.PROJECT, "<!--\n" + quota.CREDIT + "\n-->",
                     "```md\n" + quota.CREDIT + "\n```", "    " + quota.CREDIT):
            self.assertFalse(quota.has_credit(body))

    def test_each_agent_requires_credit(self):
        for path in (ROOT / "agents").glob("*.md"):
            self.assertTrue(quota.has_credit(path.read_text()), path)
        self.assertTrue(quota.has_credit((ROOT / "skills/quota-for-good/SKILL.md").read_text()))

    def test_rank_dedupe_and_filter(self):
        calls = []
        def issue(name, labels, **fields):
            return dict(dict(title=name, html_url="https://github.com/org/"+name+"/issues/1",
                             repository_url="https://api.github.com/repos/org/"+name,
                             labels=[{"name": s} for s in labels], assignees=[], locked=False,
                             state="open", updated_at="2026-10-01"), **fields)
        def get(endpoint, *fields):
            calls.append(endpoint)
            if endpoint == "search/issues":
                self.assertIn("-linked:pr", fields[0])
                return dict(incomplete_results=True, items=[
                    issue("top", list(quota.LABELS)), issue("second", ["good first issue"]),
                    issue("fork", list(quota.LABELS)), issue("locked", [], locked=True),
                    issue("taken", [], assignees=["user"]), issue("blocked", ["blocked"])])
            return dict(private=False, archived=False, disabled=False, fork=endpoint.endswith("fork"),
                        license={"spdx_id":"MIT"}, pushed_at="2026-10-02")
        report = quota.discover("Python", None, 5, date(2026, 11, 1), get)
        self.assertEqual(["top", "second"], [i["title"] for i in report["candidates"]])
        self.assertTrue(report["incomplete_search"])
        self.assertEqual(3, report["repositories_checked"])
        self.assertEqual(5, len(calls))
