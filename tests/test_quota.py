import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/quota-for-good/scripts"))
import quota


class WorkflowTests(unittest.TestCase):
    def test_visible_credit(self):
        for body in (quota.CREDIT, (ROOT / "templates/contribution.md").read_text()):
            self.assertTrue(quota.has_credit(body))
        for body in (
            "",
            quota.PROJECT,
            "<!--\n" + quota.CREDIT + "\n-->",
            "```md\n" + quota.CREDIT + "\n```",
            "    " + quota.CREDIT,
        ):
            self.assertFalse(quota.has_credit(body))

    def test_each_agent_requires_credit(self):
        for path in (ROOT / "agents").glob("*.md"):
            self.assertTrue(quota.has_credit(path.read_text()), path)
        self.assertTrue(
            quota.has_credit((ROOT / "skills/quota-for-good/SKILL.md").read_text())
        )
