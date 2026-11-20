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
            run.select(NOW, {"exclude": [REPO], "override": {}}, self.projects, []),
            [],
        )
        self.assertFalse(
            run.compatible(
                [dict(title="fix x", scope=["a/x.py"])],
                dict(title="new check", scope=["a/x.py"]),
            )
        )

    def test_replay_owner_edit_and_expiration(self):
        import tempfile

        item = assess(ROW, REPO, META, FILES, NOW.date())
        other = dict(
            ROW,
            url=ISSUE + "1",
            title="Add an independent config parser",
            body="Expected: parse config/options.py",
        )
        pair = [item, assess(other, REPO, META, FILES, NOW.date())]
        requests = [
            {"number": i, "title": f"qfg claim {ISSUE} 90", "author": {"login": u}}
            for i, u in enumerate(("alice", "bob"), 1)
        ]
        with (
            tempfile.TemporaryDirectory() as path,
            patch.object(run, "DIR", Path(path)),
            patch.object(run, "discover", return_value={"candidates": pair}),
            patch.object(run, "live_issues", return_value=[ROW, other]),
            patch.object(run, "inbox", return_value=requests),
        ):
            editor = {"exclude": [], "weeks": {}}
            run.save(run.DIR / "editor.json", editor)
            run.run(NOW)
            state = run.load(run.DIR / "ledger.json", {})
            self.assertIn("Reserved", state["receipts"]["1"])
            self.assertIn("taken", state["receipts"]["2"])
            # A carried reservation exhausts this project's remaining review place.
            self.assertEqual(
                run.select(NOW, {"exclude": [], "override": {}}, None, state["claims"]),
                [],
            )
            editor["weeks"]["2026-W47"] = {
                "descriptions": {REPO: {"ru": "Проверка редактора"}}
            }
            run.save(run.DIR / "editor.json", editor)
            run.run(NOW)
            self.assertEqual(state, run.load(run.DIR / "ledger.json", {}))
            self.assertIn(
                "Проверка редактора",
                (run.DIR / "archive/2026-W47/board.ru.md").read_text(),
            )
            run.run(NOW + timedelta(hours=4))
            self.assertEqual(
                run.load(run.DIR / "ledger.json", {})["claims"][0]["status"], "expired"
            )
