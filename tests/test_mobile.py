import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "campaign"))
import balance
import community
import mobile
import verify_week


class MobileTests(unittest.TestCase):
    def test_credit_once(self):
        issue = "https://github.com/project/docs/issues/3"
        raw = dict(
            id="uk",
            repo="project/docs",
            issue=issue,
            state="accepted",
            user="alice",
            reviewer="bob",
            claimed=10,
            submitted=20,
            reviewed=30,
            metrics={},
        )
        rows = mobile.normalize([raw])
        opening = datetime.now(timezone.utc)
        claims = [
            dict(issue=issue, user="Alice", merged_at="2020-01-01T12:00:00+00:00")
        ]
        self.assertEqual(community.weight("Alice", [], opening, rows), 2)
        self.assertEqual(community.weight("Alice", claims, opening, rows), 2)
        with self.assertRaises(ValueError):
            mobile.normalize([dict(raw, reviewer="Alice")])

    def test_tampered_replay(self):
        snapshot = dict(
            version=1,
            shares=balance.SHARES,
            prior=[],
            rounds=[
                dict(
                    pool=[],
                    history=[],
                    ballot={"votes": {}, "nominees": {}},
                    limit=1,
                    selected=["invented"],
                )
            ],
        )
        with self.assertRaises(ValueError):
            verify_week.verify(snapshot)
