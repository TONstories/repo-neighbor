from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "campaign"))
import run
from finder import assess
from quota import CREDIT

NOW = datetime(2026, 11, 20, 10, tzinfo=timezone.utc)
REPO = "fixture/kit"
ISSUE = "https://github.com/fixture/kit/issues/7"
PR = "https://github.com/fixture/kit/pull/8"
META = dict(
    licenseInfo={"spdxId": "MIT"},
    primaryLanguage={"name": "Rust"},
    pushedAt="2026-11-19",
    isArchived=False,
    isDisabled=False,
    isFork=False,
    isPrivate=False,
)
FILES = {"CONTRIBUTING.md": "Run checks:\nnpm test\n", "Cargo.toml": ""}
ROW = dict(
    number=7,
    url=ISSUE,
    title="Docs: fix client.ts example",
    body="Expected result: update sdk/client.ts",
    state="OPEN",
    locked=False,
    updatedAt="2026-11-20",
    assignees={"totalCount": 0},
    labels={"nodes": [{"name": "help wanted"}]},
    comments={"nodes": []},
    closedByPullRequestsReferences={"totalCount": 0},
)
WINDOW = {"complete": True, "limit": 2, "open": ["other"], "decisions": 8}


class FinderTests(TestCase):
    def test_issue_language_and_session(self):
        item = assess(ROW, REPO, META, FILES, NOW.date(), ["TypeScript"], 60, 10)
        self.assertEqual(item["fit"], "fits")
        self.assertEqual(item["stack"], ["TypeScript"])
        self.assertIn("npm test (CONTRIBUTING.md)", item["checks"])
        self.assertIsNone(
            assess(ROW, REPO, META, FILES, NOW.date(), minutes=15, reserve=5)
        )
        self.assertIsNone(assess(ROW, REPO, META, FILES, NOW.date(), ["Rust"]))

    def test_policy_busy_unavailable(self):
        for extra in (
            {"assignees": {"totalCount": 1}},
            {"state": "CLOSED"},
            {"closedByPullRequestsReferences": {"totalCount": 1}},
            {"comments": {"nodes": [{"body": "I'm working on this"}]}},
        ):
            self.assertIsNone(assess(dict(ROW, **extra), REPO, META, FILES, NOW.date()))
        self.assertIsNone(
            assess(
                ROW,
                REPO,
                META,
                {"AI_POLICY.md": "AI contributions are not allowed."},
                NOW.date(),
            )
        )

    def test_uncertain_scope(self):
        item = assess(
            dict(ROW, title="Update example", body="Needs improvement"),
            REPO,
            META,
            {},
            NOW.date(),
        )
        self.assertEqual((item["fit"], item["minutes"]), ("investigate", None))

    def test_deduplication_and_repository_filters(self):
        from finder import discover

        row = dict(ROW, repository={"nameWithOwner": REPO})
        with (
            patch("finder.graph", return_value={"search": {"nodes": [row, row]}}),
            patch("finder.metadata", return_value=(META, FILES)),
        ):
            self.assertEqual(len(discover([], None, 5, NOW.date())["candidates"]), 1)
        for meta in (
            dict(META, isFork=True),
            dict(META, licenseInfo=None),
            dict(META, pushedAt="2020-01-01"),
        ):
            self.assertIsNone(assess(ROW, REPO, meta, FILES, NOW.date()))


class CampaignTests(TestCase):
    def setUp(self):
        self.claims = []
        self.projects = [{"repo": REPO, "tasks": [dict(url=ISSUE)]}]
        for name, value in (
            ("reviews", WINDOW),
            ("metadata", (META, FILES)),
            ("live_issue", ROW),
        ):
            mock = patch.object(run, name, return_value=value)
            mock.start()
            self.addCleanup(mock.stop)

    def send(self, verb="claim", who="alice", arg="90", now=NOW):
        return run.transition(
            f"qfg {verb} {ISSUE} {arg}".strip(),
            who,
            self.claims,
            "2026-W47",
            self.projects,
            now,
        )

    def test_collision_release_expiry_and_capacity(self):
        self.assertIn("Reserved", self.send())
        self.assertIn("taken", self.send(who="bob"))
        self.assertEqual(run.slots(WINDOW, self.claims, NOW, REPO), 0)
        self.assertIn("No matching", self.send("release", "bob", ""))
        self.assertEqual("Released.", self.send("release", arg=""))
        self.assertIn("Reserved", self.send(who="bob"))
        self.assertIn("Reserved", self.send(now=NOW + timedelta(hours=3)))
        self.assertEqual(run.slots(dict(WINDOW, complete=False), [], NOW, REPO), 0)

    def test_submit_and_late_merge(self):
        self.send()
        msg = dict(
            state="OPEN",
            body=CREDIT + "\n\n" + ISSUE,
            author={"login": "alice"},
            closingIssuesReferences={"nodes": []},
        )
        with patch.object(run, "upstream_pr", return_value=msg):
            self.assertIn("recorded", self.send("submit", arg=PR))
        self.assertEqual(run.slots(dict(WINDOW, open=[PR]), self.claims, NOW, REPO), 1)
        with patch.object(run, "upstream_pr", return_value=dict(msg, state="MERGED")):
            run.refresh_claims(self.claims, NOW + timedelta(days=8))
        board = run.render("2026-W47", [], self.claims, NOW, {}, "en")
        self.assertIn("Accepted improvements · 1", board)
        self.assertIn(PR, board)

    def test_wrong_pr_author_or_project(self):
        self.send()
        self.assertIn(
            "same repository", self.send("submit", arg=PR.replace("kit", "other"))
        )
        with patch.object(
            run, "upstream_pr", return_value={"author": {"login": "other"}}
        ):
            self.assertIn("did not match", self.send("submit", arg=PR))

    def test_week_boundary_and_editor(self):
        self.assertEqual(
            run.week_key(datetime(2026, 11, 23, 6, 14, tzinfo=timezone.utc)), "2026-W47"
        )
        self.assertEqual(
            run.week_key(datetime(2026, 11, 23, 6, 15, tzinfo=timezone.utc)), "2026-W48"
        )
        self.assertEqual(
            run.select(NOW.date(), {"exclude": [REPO], "override": {}}, self.projects),
            [],
        )
        self.assertFalse(
            run.compatible(
                [dict(title="fix x", scope=["a/x.py"])],
                dict(title="new check", scope=["a/x.py"]),
            )
        )
