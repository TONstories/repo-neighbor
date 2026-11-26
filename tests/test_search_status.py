from contextlib import redirect_stderr, redirect_stdout
import io
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

from test_campaign import APPROVAL, FILES, ISSUE, META, NOW, REPO, ROW
from finder import ApprovalCoverageIncomplete, GitHubRateLimited, assess, discover, graph, reviews
from quota import main

ROW_WITH_REPO = dict(ROW, repository={"nameWithOwner": REPO, "stargazerCount": 100})


def search_page(nodes=(), issue_count=None):
    return {"search": {"nodes": list(nodes), "issueCount": len(nodes) if issue_count is None else issue_count}}


class SearchStatusTests(unittest.TestCase):
    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", ["quota.py", "find", *args]), redirect_stdout(out), redirect_stderr(err):
            try:
                main()
            except SystemExit as exc:
                return exc.code, out.getvalue(), err.getvalue()
        return 0, out.getvalue(), err.getvalue()

    def test_cli_distinguishes_empty_and_total_api_error_in_json(self):
        with patch("finder.graph", return_value=search_page()):
            code, stdout, _ = self.cli("--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout)["search_status"], "empty")
        with patch("finder.graph", side_effect=RuntimeError("API rate limit")):
            code, stdout, _ = self.cli("--json")
        self.assertEqual(code, 1)
        report = json.loads(stdout)
        self.assertEqual(report["search_status"], "api_error")
        self.assertEqual(report["api_errors"], {"search": 2})
        self.assertEqual(report["candidates"], [])

    def test_graph_classifies_rate_limits_in_cli_and_graphql_errors(self):
        for code, stdout, stderr in (
            (1, "", "gh: You have exceeded a secondary rate limit. (HTTP 403)"),
            (1, "", "gh: Too Many Requests (HTTP 429)"),
            (0, '{"errors":[{"type":"RATE_LIMITED","message":"Budget exhausted"}]}', ""),
        ):
            response = subprocess.CompletedProcess([], code, stdout, stderr)
            with self.subTest(response=response), patch("finder.subprocess.run", return_value=response) as gh:
                with self.assertRaises(GitHubRateLimited):
                    graph("{viewer{login}}")
                gh.assert_called_once()

    def test_rate_limit_during_search_stops_followup_requests(self):
        with (
            patch("finder.graph", side_effect=[search_page([ROW_WITH_REPO]), GitHubRateLimited]) as gh,
            patch("finder.metadata") as metadata,
        ):
            result = discover(["Go"], None, 10, NOW.date(), report_errors=True)
        self.assertEqual(gh.call_count, 2)
        metadata.assert_not_called()
        self.assertEqual(result["search_status"], "partial")
        self.assertEqual(result["coverage_limits"], ["github_rate_limit"])
        self.assertEqual(result["candidates"], [])

        with patch("finder.graph", side_effect=GitHubRateLimited) as gh:
            code, stdout, _ = self.cli("--json")
        gh.assert_called_once()
        self.assertEqual(code, 1)
        result = json.loads(stdout)
        self.assertEqual(result["search_status"], "api_error")
        self.assertEqual(result["coverage_limits"], ["github_rate_limit"])

    def test_rate_limit_after_one_verified_project_preserves_only_its_cards(self):
        other_repo = "another/repo"
        second = dict(ROW_WITH_REPO, repository={"nameWithOwner": other_repo, "stargazerCount": 100})
        with (
            patch("finder.graph", return_value=search_page([ROW_WITH_REPO, second])),
            patch("finder.metadata", return_value=(META, FILES)),
            patch("finder.project_approval", side_effect=[APPROVAL, GitHubRateLimited]),
            patch("quota.reviews") as lookup,
        ):
            code, stdout, _ = self.cli("--json")
        self.assertEqual(code, 0)
        lookup.assert_not_called()
        result = json.loads(stdout)
        self.assertEqual(result["search_status"], "partial")
        self.assertEqual(result["api_errors"], {"project_approval": 1})
        candidate, = result["candidates"]
        self.assertEqual(candidate["repo"], REPO)
        self.assertEqual(candidate["review_status"], "rate_limited")
        self.assertIsNone(candidate["default_board_review_capacity"])

    def test_rate_limit_in_review_lookup_preserves_prior_estimates(self):
        rows = [dict(repo=f"r/{name}", url=f"https://github.com/r/{name}/issues/1", score=60)
                for name in ("loaded", "limited", "pending")]
        report = dict(candidates=rows, search_status="complete", incomplete_search=False)
        with (
            patch("quota.discover", return_value=report),
            patch("quota.reviews", side_effect=[
                dict(complete=True, limit=2, open=[]), GitHubRateLimited,
            ]) as lookup,
        ):
            code, stdout, _ = self.cli("--json")
        self.assertEqual(code, 0)
        self.assertEqual(lookup.call_count, 2)
        result = json.loads(stdout)
        self.assertEqual(result["search_status"], "partial")
        self.assertEqual(result["api_errors"], {"review_capacity": 1})
        self.assertEqual(result["candidates"][0]["default_board_review_capacity"], 2)
        self.assertEqual([row["review_status"] for row in result["candidates"]],
                         ["available", "rate_limited", "rate_limited"])

    def test_invitation_aliases_are_searched_within_the_existing_request_budget(self):
        invite = dict(ROW_WITH_REPO, labels={"nodes": [{"name": "help-wanted"}]})
        with (
            patch("finder.graph", side_effect=[search_page(), search_page([invite])]) as graph,
            patch("finder.metadata", return_value=(META, FILES)),
            patch("finder.project_approval", return_value=APPROVAL),
        ):
            report = discover([], REPO, 5, NOW.date(), as_of=NOW)
        qualifiers = [call.kwargs["q"] for call in graph.call_args_list]
        self.assertEqual(len(qualifiers), 2)
        self.assertIn('label:"good first issue","good-first-issue","beginner-friendly"', qualifiers[0])
        self.assertIn('label:"help wanted","help-wanted"', qualifiers[1])
        candidate, = report["candidates"]
        self.assertEqual(candidate["signals"], ["help wanted"])
        self.assertEqual(candidate["recent_approval"], APPROVAL)

    def test_invitation_aliases_preserve_ownership_rules_for_parent_and_child(self):
        parent = dict(ROW, url=f"https://github.com/{REPO}/issues/6",
                      labels={"nodes": [{"name": "Beginner-Friendly"}]})
        child = dict(ROW, parent=parent, labels={"nodes": []})
        picked = assess(child, REPO, META, FILES, NOW.date())
        self.assertEqual(picked["signals"], ["good first issue"])
        blocked = dict(child, labels={"nodes": [{"name": "claimed"}]})
        self.assertIsNone(assess(blocked, REPO, META, FILES, NOW.date()))
        parent["assignees"] = {"totalCount": 1}
        self.assertIsNone(assess(child, REPO, META, FILES, NOW.date()))

    def test_search_cap_with_no_eligible_candidates_is_partial(self):
        with patch("finder.graph", return_value=search_page([None], issue_count=38)):
            code, stdout, stderr = self.cli()
        self.assertEqual(code, 0)
        self.assertIn("No eligible issues verified in the completed portion.", stdout)
        self.assertIn("search_result_limit", stderr)

    def test_partial_api_failure_preserves_verified_candidates_and_skips_unverified(self):
        other_repo = "another/repo"
        other = dict(ROW_WITH_REPO, repository={"nameWithOwner": other_repo, "stargazerCount": 100},
                     url=f"https://github.com/{other_repo}/issues/7")
        with (
            patch("finder.graph", side_effect=[search_page([ROW_WITH_REPO, other]), RuntimeError("timeout")]),
            patch("finder.metadata", return_value=(META, FILES)),
            patch("finder.project_approval", side_effect=[APPROVAL, RuntimeError("timeout")]),
        ):
            report = discover([], None, 5, NOW.date(), report_errors=True)
        self.assertEqual(report["search_status"], "partial")
        self.assertEqual(report["api_errors"], {"project_approval": 1, "search": 1})
        self.assertEqual(report["repositories_checked"], 2)
        self.assertEqual([row["url"] for row in report["candidates"]], [ISSUE])

    def test_approval_scan_limit_is_partial(self):
        with (
            patch("finder.graph", return_value=search_page([ROW_WITH_REPO])),
            patch("finder.metadata", return_value=(META, FILES)),
            patch("finder.project_approval", side_effect=ApprovalCoverageIncomplete),
        ):
            report = discover([], None, 5, NOW.date(), report_errors=True)
        self.assertEqual(report["search_status"], "partial")
        self.assertEqual(report["coverage_limits"], ["approval_search_limit"])
        self.assertEqual(report["api_errors"], {})
        self.assertEqual(report["candidates"], [])

    def test_incomplete_subissues_cannot_falsely_qualify_parent(self):
        parent = dict(ROW_WITH_REPO, subIssues={"nodes": [{"state": "CLOSED"}], "totalCount": 2})
        with (
            patch("finder.graph", return_value=search_page([parent])),
            patch("finder.metadata", return_value=(META, FILES)),
            patch("finder.project_approval", return_value=APPROVAL),
        ):
            report = discover([], None, 5, NOW.date())
        self.assertEqual(report["coverage_limits"], ["subissue_limit"])
        self.assertEqual(report["candidates"], [])

    def test_incomplete_repository_policy_is_reported_as_partial_coverage(self):
        meta = dict(META, incomplete_policy_files=["CONTRIBUTING.md"])
        with (
            patch("finder.graph", return_value=search_page([ROW_WITH_REPO])),
            patch("finder.metadata", return_value=(meta, FILES)),
        ):
            report = discover([], None, 5, NOW.date())
        self.assertEqual(report["search_status"], "partial")
        self.assertEqual(report["coverage_limits"], ["policy_file_limit"])
        self.assertEqual(report["candidates"], [])

    def test_review_status_distinguishes_full_unknown_and_api_error(self):
        rows = [
            dict(repo=repo, url=f"https://github.com/{repo}/issues/{number}", score=60)
            for number, repo in enumerate(("r/full", "r/unknown", "r/full", "r/error", "r/available", "r/board_full"), 1)
        ]
        report = dict(candidates=rows, search_status="complete", incomplete_search=False)
        full = dict(complete=True, limit=1, open=["active"])
        unknown = dict(complete=False, limit=1, open=[])
        available = dict(complete=True, limit=1, open=[])
        board_full = dict(complete=True, limit=5, open=["a", "b", "c", "d"])
        with (
            patch("quota.discover", return_value=report),
            patch("quota.reviews", side_effect=[full, unknown, RuntimeError("API failed"), available, board_full]) as lookup,
        ):
            code, stdout, _ = self.cli("--json", "--limit", "6")
        self.assertEqual(code, 0)
        items = json.loads(stdout)["candidates"]
        self.assertEqual(items[0]["review_status"], "available")
        capacities = {
            row["repo"]: (row["review_capacity"], row["review_status"], row["default_board_review_capacity"])
            for row in items
        }
        self.assertEqual(capacities, {
            "r/full": (0, "full", 0),
            "r/unknown": (0, "unknown", None),
            "r/error": (0, "api_error", None),
            "r/available": (1, "available", 1),
            "r/board_full": (1, "available", 0),
        })
        self.assertEqual(lookup.call_count, 5)

    def test_review_pagination_mismatch_does_not_estimate_capacity(self):
        def response(**data):
            return {"repository": {"pullRequests": data}}

        pr = dict(url="https://github.com/r/project/pull/1", authorAssociation="NONE",
                  state="OPEN", author={"login": "contributor"})
        for count, rows, complete in ((1, [pr], True), (2, [pr], False), (1, [pr, pr], False)):
            with (
                self.subTest(count=count, rows=len(rows)),
                patch("finder.graph", side_effect=[
                    response(totalCount=count, nodes=rows, pageInfo={"hasNextPage": False}),
                    response(totalCount=0, nodes=[], pageInfo={"hasNextPage": False}),
                ]),
            ):
                reviews.cache_clear()
                window = reviews("r/project", NOW.date())
                self.assertEqual(window["complete"], complete)
                self.assertEqual(window["open"], [pr["url"]])
        reviews.cache_clear()

    def test_review_history_cuts_off_the_closed_window_but_keeps_old_open_prs(self):
        old_open = dict(url="https://github.com/r/project/pull/1", authorAssociation="NONE",
                        state="OPEN", updatedAt="2020-01-01", author={"login": "contributor"})
        merged = dict(old_open, url="https://github.com/r/project/pull/2", state="MERGED",
                      closedAt="2026-11-19", updatedAt="2026-11-20")
        bot = dict(merged, url="https://github.com/r/project/pull/3",
                   author={"login": "bot-without-suffix", "__typename": "Bot"})
        old = dict(merged, url="https://github.com/r/project/pull/4",
                   closedAt="2020-01-01", updatedAt="2020-01-02")

        def response(total, rows, more):
            return {"repository": {"pullRequests": {
                "totalCount": total, "nodes": rows, "pageInfo": {"hasNextPage": more},
            }}}

        reviews.cache_clear()
        self.addCleanup(reviews.cache_clear)
        with patch("finder.graph", side_effect=[
            response(1, [old_open], False), response(30, [merged, bot, old], True),
        ]) as api:
            result = reviews("r/project", NOW.date())
        self.assertTrue(result["complete"])
        self.assertEqual(result["open"], [old_open["url"]])
        self.assertEqual(result["decisions"], 1)
        self.assertIn("states:[OPEN]", api.call_args_list[0].args[0])
        self.assertIn("states:[CLOSED,MERGED]", api.call_args_list[1].args[0])

    def test_review_queue_can_be_full_while_the_decision_history_is_incomplete(self):
        row = dict(repo="r/project", url="https://github.com/r/project/issues/1", score=60)
        for opens, expected in ((2, ("unknown", None)), (3, ("unknown", 0)), (5, ("full", 0))):
            report = dict(candidates=[row], search_status="complete", incomplete_search=False)
            window = dict(complete=False, open_complete=True, limit=1, open=list(range(opens)))
            with (
                self.subTest(opens=opens),
                patch("quota.discover", return_value=report),
                patch("quota.reviews", return_value=window),
            ):
                code, stdout, _ = self.cli("--json")
            self.assertEqual(code, 0)
            candidate, = json.loads(stdout)["candidates"]
            self.assertEqual((candidate["review_status"], candidate["default_board_review_capacity"]), expected)

    def test_legacy_discovery_callers_still_fail_before_writing_partial_results(self):
        with patch("finder.graph", side_effect=RuntimeError("API rate limit")):
            with self.assertRaisesRegex(RuntimeError, "rate limit"):
                discover([], None, 5, NOW.date())
