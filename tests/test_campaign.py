from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "campaign"))
import run
from finder import ApprovalCoverageIncomplete, assess, project_approval, recent_approval
from quota import CREDIT

NOW = datetime(2026, 11, 20, 10, tzinfo=timezone.utc)
REPO = "fixture/kit"
ISSUE = "https://github.com/fixture/kit/issues/7"
PR = "https://github.com/fixture/kit/pull/8"
META = dict(
    stargazerCount=100,
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
APPROVAL = dict(pr=PR, review=PR + "#pullrequestreview-1", submitted_at=NOW.isoformat())


def discovery(candidates=(), *, status="complete", limits=(), errors=None):
    return dict(candidates=candidates, search_status=status, coverage_limits=list(limits),
                api_errors=errors or {}, queries_completed=0 if status == "api_error" else 2)


class FinderTests(TestCase):
    def test_minimum_stars_is_inclusive_and_requires_verified_count(self):
        from finder import metadata

        for stars in (99, None, "100"):
            with self.subTest(stars=stars):
                self.assertIsNone(assess(ROW, REPO, dict(META, stargazerCount=stars), FILES, NOW.date()))
        self.assertEqual(assess(ROW, REPO, META, FILES, NOW.date())["stars"], 100)

        with patch("finder.graph", return_value={"repository": dict(META, stargazerCount=99)}) as graph:
            try:
                self.assertEqual(metadata(REPO), ({}, {}))
                self.assertIn("stargazerCount", graph.call_args.args[0])
            finally:
                metadata.cache_clear()

    def test_project_scope_requires_a_project_declaration(self):
        from finder import declared_outside_scope
        meta = dict(nameWithOwner="example/Tool", description="Tool is a Ukrainian open-source project.")
        self.assertTrue(declared_outside_scope(meta, {}))
        meta["description"] = "Ukrainian language tools"
        self.assertFalse(declared_outside_scope(meta, {"README.md": "We support Ukraine."}))
        self.assertTrue(declared_outside_scope(meta, {"README.md": "This project is based in Canada.\nThis is a project from Ukraine."}))
        with patch("finder.reviewed_exclusions", return_value={"example/tool"}):
            self.assertTrue(declared_outside_scope(meta, {}))

    def test_translation_target(self):
        for title in ("Translate the quick start into Ukrainian", "Add Ukrainian locale"):
            self.assertIsNone(assess(dict(ROW, title=title), REPO, META, FILES, NOW.date()))

    def test_issue_language_and_session(self):
        item = assess(ROW, REPO, META, FILES, NOW.date(), ["TypeScript"], 60, 10)
        self.assertEqual(item["fit"], "uncertain")
        self.assertEqual(item["stack"], ["TypeScript"])
        self.assertIn("npm test (CONTRIBUTING.md)", item["checks"])
        self.assertIsNone(
            assess(ROW, REPO, META, FILES, NOW.date(), minutes=15, reserve=5)
        )
        self.assertIsNone(assess(ROW, REPO, META, FILES, NOW.date(), ["Rust"]))

    def test_new_language_evidence(self):
        for name, path, manifest in [
            ("Julia", "src/solver.jl", "Project.toml"),
            ("Haskell", "src/Parser.hs", "cabal.project"),
            ("Clojure", "src/check.cljc", "deps.edn"),
            ("Fortran", "src/main.F90", "fpm.toml"),
        ]:
            with self.subTest(language=name):
                item = assess(dict(ROW, title="Docs example", body=path), REPO, META, {}, NOW.date(), [name])
                self.assertIn(name, item["stack"])
                self.assertEqual(item["stack_source"], "issue")
                item = assess(dict(ROW, title="Docs example", body="Fix formatting"), REPO,
                              META, {manifest: ""}, NOW.date(), [name])
                self.assertEqual(item["stack_source"], "repository only")

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

        row = dict(ROW, repository={"nameWithOwner": REPO, "stargazerCount": 100})
        low = dict(ROW, repository={"nameWithOwner": "another/small", "stargazerCount": 99})
        with (
            patch("finder.graph", return_value={"search": {"nodes": [low, row, row]}}),
            patch("finder.metadata", return_value=(META, FILES)) as metadata,
            patch("finder.project_approval", return_value=APPROVAL),
        ):
            self.assertEqual(len(discover([], None, 5, NOW.date())["candidates"]), 1)
            metadata.assert_called_once_with(REPO)
        for meta in (
            dict(META, isFork=True),
            dict(META, licenseInfo=None),
            dict(META, pushedAt="2020-01-01"),
        ):
            self.assertIsNone(assess(ROW, REPO, meta, FILES, NOW.date()))

    def test_minimum_stars_and_recent_approval_cutoff(self):
        self.addCleanup(recent_approval.cache_clear)
        review = {
            "url": APPROVAL["review"], "state": "APPROVED",
            "authorAssociation": "MEMBER", "author": {"login": "maintainer", "__typename": "User"},
        }
        cutoff = NOW - timedelta(days=3)
        for stars, at, state, decision, passes in (
            (99, cutoff, "APPROVED", None, False),
            (100, cutoff, "APPROVED", None, True),
            (100, cutoff - timedelta(seconds=1), "APPROVED", None, False),
            (101, NOW + timedelta(seconds=1), "APPROVED", None, False),
            (101, NOW, "DISMISSED", None, False),
            (101, NOW, "APPROVED", "CHANGES_REQUESTED", False),
        ):
            recent_approval.cache_clear()
            pr = dict(
                url=PR, updatedAt=NOW.isoformat(), reviewDecision=decision, author={"login": "contributor"},
                latestOpinionatedReviews={"nodes": [dict(review, submittedAt=at.isoformat(), state=state)]},
            )
            response = {"repository": {"pullRequests": {"nodes": [pr], "pageInfo": {"hasNextPage": False}}}}
            with self.subTest(stars=stars, at=at, state=state, decision=decision), patch("finder.graph", return_value=response) as graph:
                self.assertEqual(bool(project_approval(REPO, dict(META, stargazerCount=stars), NOW)), passes)
                if stars < 100:
                    graph.assert_not_called()

    def test_bounded_approval_scan_does_not_claim_no_approval(self):
        self.addCleanup(recent_approval.cache_clear)
        for rows, another_page, expected_calls in (
            ([dict(url=PR, updatedAt=NOW.isoformat(), reviewDecision=None, author=None,
                   latestOpinionatedReviews={"nodes": [], "pageInfo": {"hasNextPage": True}})], False, 1),
            ([], True, 4),
        ):
            page = {"nodes": rows, "pageInfo": {"endCursor": "cursor", "hasNextPage": another_page}}
            with self.subTest(another_page=another_page), patch(
                "finder.graph", return_value={"repository": {"pullRequests": page}}
            ) as graph:
                with self.assertRaises(ApprovalCoverageIncomplete):
                    project_approval(REPO, META, NOW)
                self.assertEqual(graph.call_count, expected_calls)


class CampaignTests(TestCase):
    def setUp(self):
        self.claims = []
        self.projects = [{"repo": REPO, "tasks": [dict(url=ISSUE)]}]
        for name, value in (
            ("reviews", WINDOW),
            ("metadata", (META, FILES)),
            ("live_issue", ROW),
            ("project_approval", APPROVAL),
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

    def test_expired_approval_removes_project_and_prevents_new_claim(self):
        self.assertIn("Reserved", self.send())
        with (
            patch.object(run, "project_approval", return_value=None),
            patch.object(run, "live_issues", return_value=[ROW]),
        ):
            self.assertIn("Released", self.send("release", arg=""))
            self.assertIn("verified PR approval", self.send(who="bob"))
            self.assertEqual(run.select(NOW, {}, self.projects, []), [])

    def test_incomplete_approval_prevents_claim_without_making_it_a_capacity_failure(self):
        with (
            patch.object(run, "project_approval", side_effect=ApprovalCoverageIncomplete),
            patch.object(run, "reviews") as reviews,
        ):
            self.assertEqual(self.send(), run.APPROVAL_UNVERIFIED)
        self.assertEqual(self.claims, [])
        reviews.assert_not_called()

    def test_weekly_recheck_keeps_allocation_during_incomplete_approval_coverage(self):
        import tempfile

        limited = "fixture/limited"
        limited_url = "https://github.com/fixture/limited/issues/7"
        visible = {"repo": REPO, "tasks": [dict(url=ISSUE)], "track": "general"}
        hidden = {"repo": limited, "tasks": [dict(url=limited_url)], "track": "general"}

        def approval(repo, meta, now):
            if repo == limited:
                raise ApprovalCoverageIncomplete
            return APPROVAL

        requests = [{"number": 1, "title": f"rn nominate {limited}", "author": {"login": "bob"}}]
        with (
            tempfile.TemporaryDirectory() as path,
            patch.object(run, "DIR", Path(path)),
            patch.object(run, "metadata", side_effect=lambda repo: (dict(META, nameWithOwner=repo), FILES)),
            patch.object(run, "live_issues", side_effect=lambda urls: [dict(ROW, url=url) for url in urls]),
            patch.object(run, "project_approval", side_effect=approval) as approvals,
            patch.object(run, "discover") as search,
            patch.object(run, "inbox", return_value=requests),
        ):
            folder = run.DIR / "archive" / run.week_key(NOW)
            folder.mkdir(parents=True)
            run.save(run.DIR / "editor.json", {"weeks": {}})
            run.save(folder / "selection.json", [hidden, visible])
            run.run(NOW)
            self.assertEqual([p["repo"] for p in run.load(folder / "projects.json", [])], [REPO])
            self.assertEqual(run.load(folder / "selection.json", []), [hidden, visible])
            self.assertEqual(run.load(folder / "audit.json", {})["approval_unverified"], [limited])
            self.assertEqual(run.load(run.DIR / "ledger.json", {})["receipts"]["1"], run.APPROVAL_UNVERIFIED)
            approvals.side_effect = None
            approvals.return_value = APPROVAL
            run.run(NOW)
            self.assertEqual([p["repo"] for p in run.load(folder / "projects.json", [])], [limited, REPO])
            self.assertNotIn("approval_unverified", run.load(folder / "audit.json", {}))
            search.assert_not_called()

    def test_reservation_checks_complete_discussion_before_claiming(self):
        completed = dict(ROW, comments={"nodes": [{"body": "I am already implementing this."}]})
        with patch.object(run, "complete_issue_discussion", side_effect=[None, completed]) as complete:
            self.assertIn("Cannot verify the complete issue discussion", self.send())
            self.assertIn("Issue is unavailable", self.send())
        self.assertEqual(complete.call_count, 2)
        self.assertEqual(self.claims, [])

    def test_board_and_live_claim_treat_prerequisites_as_pending(self):
        for body, contribution, notice in (
            ("Comment before starting.", "", "Comment on this issue before starting"),
            ("This issue is reserved for a first-time contributor.", "", "first-time contributor"),
            ("Run the Kani verifier.", "", "Kani toolchain"),
            ("", "If there is already an issue open, leave a comment first.", "Comment on the issue before starting"),
        ):
            row = dict(ROW, body=ROW["body"] + "\n" + body)
            files = {**FILES, "CONTRIBUTING.md": FILES["CONTRIBUTING.md"] + "\n" + contribution}
            task = assess(row, REPO, META, files, NOW.date(), minutes=180)
            projects = [{"repo": REPO, "window": WINDOW, "tasks": [task]}]
            with (
                self.subTest(notice=notice),
                patch.object(run, "live_issue", return_value=row),
                patch.object(run, "metadata", return_value=(META, files)),
            ):
                receipt = self.send()
                self.assertIn("prerequisites need confirmation", receipt)
                self.assertIn(notice, receipt)
                self.assertEqual(self.claims, [])
                board = run.render("2026-W47", projects, [], NOW, {}, "en")
                self.assertIn("Confirm before starting", board)
                self.assertNotIn("/issues/new?", board)
        ready = [{"repo": REPO, "window": WINDOW, "tasks": [assess(ROW, REPO, META, FILES, NOW.date())]}]
        self.assertIn("/issues/new?", run.render("2026-W47", ready, [], NOW, {}, "en"))
        self.assertIn("Reserved", self.send())
        self.assertIn("Released", self.send("release", arg=""))

    def test_live_claim_refuses_incomplete_contribution_rules(self):
        incomplete = dict(META, incomplete_policy_files=["CONTRIBUTING.md"])
        with patch.object(run, "metadata", return_value=(incomplete, FILES)):
            self.assertIn("Cannot verify the full contribution rules", self.send())
        self.assertEqual(self.claims, [])

    def test_new_project_needs_two_independent_reservable_tasks(self):
        variants = (
            ROW,
            dict(ROW, url=ISSUE + "1", title="Fix the config parser",
                 body="Expected: parse config/options.py.\nComment before starting."),
            dict(ROW, url=ISSUE + "2", title="Update migration loader",
                 body="Expected: recognize config/migrate.py."),
        )
        rows = [assess(row, REPO, META, FILES, NOW.date()) for row in variants]
        editor = {"version": 2, "discovery_seeds": [REPO], "history": {},
                  "replacement": False, "limit": 1}
        with (
            patch.object(run, "graph", return_value={"search": {"nodes": []}}),
            patch.object(run, "discover") as discover,
        ):
            discover.return_value = discovery(rows[:2])
            self.assertEqual(run.select(NOW, editor, None, []), [])
            self.assertEqual(editor["skipped"][REPO], "Insufficient independent tasks ready to reserve")
            discover.return_value = discovery(rows)
            projects = run.select(NOW, {**editor, "skipped": {}}, None, [])
            self.assertEqual([task["url"] for task in projects[0]["tasks"]], [ISSUE, ISSUE + "2"])

    def test_selection_distinguishes_unverified_sources_and_preserves_verified_candidates(self):
        other = dict(ROW, url=ISSUE + "1", title="Update migration loader",
                     body="Expected: recognize config/migrate.py.")
        pair = [assess(row, REPO, META, FILES, NOW.date()) for row in (ROW, other)]
        global_report = discovery(pair, status="partial", limits=["search_result_limit"])
        editor = {"discovery_seeds": ["fixture/partial", "fixture/error", "fixture/empty"]}
        with (
            patch.object(run, "graph", return_value={"search": {"nodes": []}}),
            patch.object(run, "discover", side_effect=[
                discovery(status="partial", limits=["approval_search_limit"]),
                discovery(status="api_error", errors={"search": 2}),
                discovery(status="empty"),
                global_report,
            ]) as search,
        ):
            projects = run.select(NOW, editor, None, [])
        self.assertEqual([project["repo"] for project in projects], [REPO])
        self.assertTrue(all(call.kwargs["report_errors"] for call in search.call_args_list))
        self.assertEqual(editor["discovery"]["global"]["coverage_limits"], ["search_result_limit"])
        self.assertEqual(editor["discovery"]["fixture/error"]["api_errors"], {"search": 2})
        self.assertEqual(editor["skipped"], {
            "fixture/partial": "Issue search incomplete",
            "fixture/error": "Issue search failed",
            "fixture/empty": "No eligible issues",
        })
        with (
            patch.object(run, "graph", return_value={"search": {"nodes": []}}),
            patch.object(run, "discover", return_value=global_report),
            patch.object(run, "reviews", return_value=dict(WINDOW, complete=False)),
        ):
            editor = {}
            self.assertEqual(run.select(NOW, editor, None, []), [])
            self.assertEqual(editor["skipped"][REPO], "Review capacity could not be verified")

    def test_weekly_discovery_stops_additional_queries_on_rate_limit(self):
        limited = discovery(status="api_error", limits=["github_rate_limit"], errors={"search": 1})
        with (
            patch.object(run, "graph") as graph,
            patch.object(run, "discover", return_value=limited) as search,
        ):
            with self.assertRaisesRegex(run.GitHubRateLimited, "fixture/limited"):
                run.select(NOW, {"discovery_seeds": ["fixture/limited", REPO]}, None, [])
            search.assert_called_once()
            graph.assert_not_called()

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
            patch.object(run, "graph", return_value={"search": {"nodes": []}}),
            patch.object(run, "discover", return_value=discovery(pair)),
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
            archive = run.DIR / "archive/2026-W47"
            selection = run.load(archive / "selection.json", [])
            self.assertEqual([row["repo"] for row in selection], [REPO])
            audit = run.load(archive / "audit.json", {})
            self.assertEqual(audit["rounds"][0]["discovery"]["global"]["search_status"], "complete")
            editor["weeks"]["2026-W47"]["exclude"] = [REPO.upper()]
            run.save(run.DIR / "editor.json", editor)
            run.run(NOW)
            self.assertEqual(run.load(archive / "projects.json", None), [])
            self.assertEqual(run.load(archive / "selection.json", []), selection)
            self.assertEqual(run.load(run.DIR / "ledger.json", {})["claims"], state["claims"])
            run.run(NOW + timedelta(hours=4))
            self.assertEqual(
                run.load(run.DIR / "ledger.json", {})["claims"][0]["status"], "expired"
            )


class CommunityFollowupTests(TestCase):
    def test_handoff_validates_before_release(self):
        row = dict(user="dev", issue=ISSUE, status="expired")
        args = ([row], "2026-W47", [], NOW)
        command = "rn handoff " + ISSUE
        notes = PR + "\nTests pass\nReview the examples"
        run.transition(command, "other", *args, body=notes, number=4)
        run.transition(command, "dev", *args, body=PR, number=4)
        self.assertEqual(row["status"], "expired")
        run.transition(command, "dev", *args, body=notes, number=4)
        self.assertEqual((row["status"], row["handoff"]), ("released", 4))

    @patch.object(run, "upstream_pr", return_value={"mergedBy": {"login": "Editor"}})
    def test_feedback_checks_identity_and_amounts(self, lookup):
        row = dict(repo=REPO, pr=PR, merged_at=NOW.isoformat())
        args = ([row], "2026-W47", [], NOW)
        command = "rn feedback " + PR
        run.transition(command, "dev", *args, body="solved 60 5", number=5)
        run.transition(command, "editor", *args, body="solved -3 5", number=5)
        self.assertNotIn("feedback", row)
        run.transition(command, "editor", *args, body="partial 60 10", number=5)
        self.assertEqual(row["feedback"], dict(outcome="partial", saved=60, review=10, by="editor", issue=5))
