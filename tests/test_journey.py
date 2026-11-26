import unittest
from unittest.mock import Mock

from test_community import c  # sets the campaign and skill import paths
from journey import follow_up, pilot_sessions, report
from quota import CREDIT

ISSUE = "https://github.com/Example/Client/issues/4"
SECOND_ISSUE = "https://github.com/Example/Client/issues/5"
PR = "https://github.com/Example/Client/pull/12"
START = "2026-11-26T12:00:00Z"
END = "2026-11-26T13:00:00Z"
NEXT_WEEK = "2026-12-01T12:00:00Z"


class JourneyTest(unittest.TestCase):
    def test_same_pr_from_ledger_and_supplement_and_late_merge(self):
        claim = dict(issue=ISSUE, pr=PR, user="Alice", claimed_at=START, status="open")
        supplement = {
            "work": [
                dict(issue=ISSUE.lower(), at=START, stage="tested_patch", source="test log"),
                dict(issue=SECOND_ISSUE, at=NEXT_WEEK, stage="brief", source="brief"),
            ],
            "pulls": [
                dict(issue=ISSUE.lower(), pr=PR.lower(), user="alice"),
                dict(issue=SECOND_ISSUE, pr=PR, user="Alice"),
            ],
            "stops": {SECOND_ISSUE: {"reason": "required_check_unavailable", "source": "old check log"}},
        }
        observation = dict(
            url=PR, author={"login": "Alice"}, body=CREDIT, state="OPEN",
            createdAt=NEXT_WEEK, closedAt=None, mergedAt=None,
            closingIssuesReferences=[{"url": ISSUE}, {"url": SECOND_ISSUE}],
        )
        lookup = Mock(return_value=observation)
        first = report([], [claim], supplement, lookup)
        self.assertEqual(first, report([], [claim], supplement, lookup))
        self.assertEqual(lookup.call_count, 2)
        lookup.assert_called_with(PR.lower())
        self.assertEqual(first["totals"], dict(
            tasks=2, tested_patches=1, submitted=1, open=1, merged=0, closed_without_merge=0,
        ))
        self.assertEqual(first["cohorts"]["2026-W49"]["submitted"], 0)
        self.assertEqual(first["not_submitted"]["total"]["tasks"], 0)
        self.assertEqual(first["not_submitted"]["cohorts"]["2026-W49"]["tasks"], 0)
        self.assertEqual(first["pulls"][0]["submitted_at"], NEXT_WEEK)
        self.assertTrue(all(task["prs"] == [PR] for task in first["tasks"]))

        observation.update(state="MERGED", closedAt=NEXT_WEEK, mergedAt=NEXT_WEEK)
        merged = report([], [claim], supplement, lookup)
        self.assertEqual(merged["cohorts"]["2026-W48"]["merged"], 1)
        self.assertEqual(merged["cohorts"]["2026-W48"]["submitted"], 1)
        self.assertEqual(merged["cohorts"]["2026-W48"]["open"], 0)
        self.assertEqual(merged["cohorts"]["2026-W49"]["merged"], 0)

        observation.update(state="CLOSED", mergedAt=None)
        closed = report([], [claim], supplement, lookup)
        self.assertEqual(closed["totals"]["closed_without_merge"], 1)
        self.assertEqual(closed["totals"]["merged"], 0)

    def test_unsubmitted_counts_by_cohort_keep_missing_reasons_unknown(self):
        third = "https://github.com/Example/Client/issues/6"
        supplement = {
            "work": [
                dict(issue=ISSUE, at=START, stage="tested_patch", source="test log"),
                dict(issue=SECOND_ISSUE, at=START, stage="triage", source="issue"),
                dict(issue=third, at=NEXT_WEEK, stage="tested_patch", source="test log"),
            ],
            "stops": {
                ISSUE: {"reason": "upstream_overlap", "source": "upstream PR"},
                third: {"reason": "local_only", "source": "local report"},
            },
        }
        observed = report([], [], supplement, Mock())["not_submitted"]
        self.assertEqual(observed["total"], {
            "tasks": 3,
            "by_stage": {"tested_patch": 2, "triage": 1},
            "by_reason": {"upstream_overlap": 1, "unknown": 2},
        })
        self.assertEqual(observed["cohorts"]["2026-W49"]["by_reason"], {"unknown": 1})

    def test_rejects_unverified_pull(self):
        claim = dict(issue=ISSUE, pr=PR, user="Alice", claimed_at=START, status="open")
        observation = dict(
            url=PR, author={"login": "Alice"}, body=CREDIT, state="OPEN",
            createdAt=NEXT_WEEK, closedAt=None, mergedAt=None,
            closingIssuesReferences=[{"url": ISSUE}],
        )
        for fields in (
            {"body": f"<!--\n{CREDIT}\n-->"},
            {"author": {"login": "someone-else"}},
            {"closingIssuesReferences": [{"url": SECOND_ISSUE}]},
        ):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                report([], [claim], {}, Mock(return_value=dict(observation, **fields)))

    def test_task_stop_is_independent_of_reservation_status(self):
        stop = {"reason": "required_check_unavailable", "source": "check log"}
        work = [dict(issue=ISSUE, at=START, stage="triage", artifact_sha256="a" * 64)]
        claim = dict(issue=ISSUE.lower(), user="Alice", claimed_at=START, status="expired")
        lookup = Mock()
        result = report(work, [claim], {"stops": {ISSUE: stop}}, lookup)
        self.assertEqual(result["totals"]["tasks"], 1)
        self.assertEqual(result["tasks"][0]["stage"], "triage")
        self.assertEqual(result["tasks"][0]["stop"], stop)
        self.assertEqual(result["tasks"][0]["claims"][0]["status"], "expired")
        lookup.assert_not_called()

    def test_dated_stop_is_counted_after_its_timestamp_unless_work_resumed(self):
        stop = {"reason": "participant_withdrew", "source": "decision record", "at": END}
        work = [dict(issue=ISSUE, at=START, stage="triage", source="notes")]
        supplement = {"work": work, "stops": {ISSUE: stop}}
        for as_of, reason in ((START, "unknown"), (END, "participant_withdrew")):
            result = report([], [], supplement, Mock(), as_of=c.parse(as_of))
            self.assertEqual(result["not_submitted"]["total"]["by_reason"], {reason: 1})
        work.append(dict(issue=ISSUE, at=NEXT_WEEK, stage="tested_patch", source="rerun"))
        result = report([], [], supplement, Mock(), as_of=c.parse(NEXT_WEEK))
        self.assertEqual(result["not_submitted"]["total"]["by_reason"], {"unknown": 1})
        with self.assertRaisesRegex(ValueError, "Invalid stop timestamp"):
            report([], [], {**supplement, "stops": {ISSUE: {**stop, "at": "2026-11-25T12:00:00Z"}}}, Mock())


class PilotSessionsTest(unittest.TestCase):
    def setUp(self):
        self.started = {"id": "one", "started_at": START, "source": "participant log"}
        self.local = dict(
            self.started, issue=ISSUE, finished_at=END, outcome="local_patch", reason="Verified locally",
        )
        self.work = [dict(issue=ISSUE, at=END, stage="tested_patch", source="test log")]
        self.pull = {"url": PR, "issues": [ISSUE.lower()], "submitted_at": NEXT_WEEK, "state": "merged"}
        self.task = {ISSUE.lower(): {"events": [{"at": END, "stage": "tested_patch"}]}}

    def test_distinct_sessions_with_same_issue_and_no_candidate(self):
        same_issue = dict(self.started, id="two", issue=ISSUE)
        no_candidate = dict(
            self.started, id="three", finished_at=END, outcome="no_candidate", reason="No suitable issue",
        )
        data = report([], [], {"work": self.work, "sessions": [self.local, same_issue, no_candidate]}, Mock())
        self.assertEqual(data["totals"]["tasks"], 1)
        sessions = data["pilot_sessions"]
        self.assertEqual(sessions["started"], 3)
        self.assertEqual(sessions["finished"], 2)
        self.assertEqual(sessions["by_outcome"], {"local_patch": 1, "in_progress": 1, "no_candidate": 1})
        self.assertEqual(sessions["submitted"], 0)
        self.assertNotIn("pilot_sessions", report([], [], {}, Mock()))
        self.assertEqual(report([], [], {"sessions": []}, Mock())["pilot_sessions"]["started"], 0)

    def test_verified_late_submission_preserves_the_session_outcome(self):
        row = dict(self.local, pr=PR)
        summary = pilot_sessions([row], self.task, [self.pull], c.parse(NEXT_WEEK))
        self.assertEqual(summary["by_outcome"], {"local_patch": 1})
        self.assertEqual(summary["submitted"], 1)
        self.assertEqual(summary["merged"], 1)

        sent_in_session = dict(row, outcome="submitted", finished_at=NEXT_WEEK)
        summary = pilot_sessions([sent_in_session], self.task, [self.pull], c.parse(NEXT_WEEK))
        self.assertEqual(summary["by_outcome"], {"submitted": 1})
        self.assertEqual(summary["submitted"], 1)

    def test_invalid_sessions_do_not_inflate_progress(self):
        linked = dict(self.local, pr=PR)
        cases = [
            ([self.started, self.started], self.task, []),
            ([dict(self.started, finished_at=END)], self.task, []),
            ([dict(self.local, reason=" ")], self.task, []),
            ([dict(self.local, finished_at=START)], self.task, []),
            ([self.local], {}, []),
            ([linked], self.task, []),
            ([dict(linked, outcome="submitted")], self.task, [self.pull]),
            ([linked, dict(linked, id="two")], self.task, [self.pull]),
        ]
        for rows, tasks, prs in cases:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                pilot_sessions(rows, tasks, prs, c.parse(NEXT_WEEK))


class FollowUpTest(unittest.TestCase):
    def setUp(self):
        self.pr = dict(
            url=PR, author={"login": "Alice"}, body=CREDIT, state="OPEN",
            createdAt=START, closedAt=None, mergedAt=None,
            closingIssuesReferences=[{"url": ISSUE}],
        )
        self.claim = dict(issue=ISSUE, pr=PR, user="Alice", claimed_at=START, status="open")

    def test_30_day_boundary_and_unknown_review_history(self):
        early = follow_up(self.pr, c.parse("2026-12-26T11:59:59Z"))
        self.assertEqual(early["open_age_days"], 29)
        self.assertFalse(early["check_due"])
        self.assertEqual(early["review_history_status"], "unknown")
        self.assertEqual(early["discussion_history_status"], "unknown")
        self.assertNotIn("checks", early)
        self.pr["review_history"] = []
        report_at_due = report([], [self.claim], {}, lambda _: self.pr, as_of=c.parse("2026-12-26T12:00:00Z"))
        info = report_at_due["pulls"][0]["follow_up"]
        self.assertEqual(info["open_age_days"], 30)
        self.assertTrue(info["check_due"])
        self.assertEqual(follow_up(self.pr, c.parse("2026-12-26T15:00:00+03:00"))["open_age_days"], 30)
        self.assertEqual(info["review_history_status"], "available")
        self.assertEqual(report_at_due["follow_up"]["counts"]["2026-W48"]["open_due"], 1)

    def test_open_pr_reports_pending_and_failed_checks_at_the_observed_head(self):
        checks = [
            dict(name="cla", detailsUrl="https://example.org/cla", status="COMPLETED", conclusion="FAILURE"),
            dict(name="bats", detailsUrl="https://example.org/bats", status="QUEUED", conclusion=""),
            dict(name="optional", status="COMPLETED", conclusion="SKIPPED"),
            dict(context="review bot", state="EXPECTED"),
            dict(context="lint", state="SUCCESS"),
            dict(context="build", state="ERROR", targetUrl="https://example.org/build"),
        ]
        self.pr.update(headRefOid="a" * 40, checks_observed_at=END, statusCheckRollup=checks)
        data = report([], [self.claim], {}, lambda _: self.pr, as_of=c.parse(END))
        self.assertEqual(data["pulls"][0]["follow_up"]["checks"], {
            "observed_at": END, "head": "a" * 40, "reported": 6,
            "pending": [{"name": "bats", "url": "https://example.org/bats"}, {"name": "review bot", "url": None}],
            "needs_attention": [
                {"name": "cla", "url": "https://example.org/cla", "state": "FAILURE"},
                {"name": "build", "url": "https://example.org/build", "state": "ERROR"},
            ],
        })
        self.pr.update(state="CLOSED", closedAt=END)
        self.assertNotIn("checks", follow_up(self.pr, c.parse(END)))

    def test_maintainer_comment_remains_separate_from_formal_review(self):
        comments = [{
            "author_association": "OWNER", "author_type": "User",
            "author": "maintainer", "created_at": END, "html_url": PR + "#issuecomment-10",
        }]
        self.pr.update(review_history=[], discussion_history=comments + [
            {**comments[0], "author": self.pr["author"]["login"], "html_url": PR + "#issuecomment-11"},
            {**comments[0], "author_type": "Bot", "html_url": PR + "#issuecomment-12"},
            {**comments[0], "created_at": NEXT_WEEK, "html_url": PR + "#issuecomment-13"},
        ])
        info = follow_up(self.pr, c.parse(END))
        self.assertEqual(info["discussion_history_status"], "available")
        self.assertEqual(info["maintainer_comments"], [{"at": END, "url": comments[0]["html_url"]}])
        self.assertEqual(info["maintainer_reviews"], [])

    def test_reports_overlapping_prs_but_excludes_repeated_records_and_sequential_retry(self):
        competing = PR.replace("/12", "/13")
        retry = PR.replace("/12", "/14")
        prs = {
            PR.lower(): dict(self.pr, state="CLOSED", closedAt=END),
            competing.lower(): dict(self.pr, url=competing, createdAt="2026-11-26T12:30:00Z",
                                    closedAt=NEXT_WEEK, mergedAt=NEXT_WEEK, state="MERGED"),
            retry.lower(): dict(self.pr, url=retry, createdAt=NEXT_WEEK),
        }
        links = [dict(issue=ISSUE.lower(), pr=url, user="alice") for url in prs]
        summary = report([], [self.claim], {"pulls": links}, prs.__getitem__, as_of=c.parse(NEXT_WEEK))
        self.assertEqual(summary["totals"]["submitted"], 3)
        self.assertEqual(summary["follow_up"]["overlapping_submissions"], [{
            "issue": ISSUE, "cohort": "2026-W48", "pr": competing, "with": [PR],
        }])
        for label in ("all", "2026-W48"):
            self.assertEqual(summary["follow_up"]["counts"][label]["issues_with_overlapping_submissions"], 1)

    def test_closed_and_merged_use_original_cohort_and_visible_review_links(self):
        reply = dict(submitted_at=NEXT_WEEK, author_association="MEMBER",
                     html_url=PR + "#pullrequestreview-1", state="CHANGES_REQUESTED", author="Bob")
        self.pr.update(state="CLOSED", closedAt=NEXT_WEEK, review_history=[
            reply, reply, dict(reply, author="alice", html_url=PR + "#pullrequestreview-2"),
            dict(reply, author="Carol", author_association="NONE", html_url=PR + "#pullrequestreview-3"),
            dict(reply, author="build[bot]", author_type="Bot", html_url=PR + "#pullrequestreview-4"),
            dict(reply, author="Dana", author_type="User", submitted_at="2026-12-29T12:00:00Z",
                 html_url=PR + "#pullrequestreview-5"),
        ])
        late = c.parse("2026-12-27T12:00:00Z")
        closed = report([], [self.claim], {}, lambda _: self.pr, as_of=late)
        self.assertEqual(closed["cohorts"]["2026-W48"]["closed_without_merge"], 1)
        info = closed["pulls"][0]["follow_up"]
        self.assertEqual(info["decision_at"], NEXT_WEEK)
        self.assertIsNone(info["open_age_days"])
        self.assertFalse(info["check_due"])
        self.assertEqual([review["url"] for review in info["maintainer_reviews"]], [reply["html_url"]])
        self.assertEqual(closed["follow_up"]["counts"]["all"]["maintainer_reviewed"], 1)

        self.pr.update(state="MERGED", mergedAt=NEXT_WEEK)
        self.claim["feedback"] = dict(outcome="solved", saved=45, review=12, issue=35)
        merged = report([], [self.claim], {}, lambda _: self.pr, as_of=late)
        self.assertEqual(merged["cohorts"]["2026-W48"]["merged"], 1)
        self.assertEqual(merged["follow_up"]["counts"]["2026-W48"]["repositories_with_merge"], 1)
        self.assertEqual(merged["follow_up"]["counts"]["all"]["reviewed_or_decided"], 1)
        self.assertEqual(merged["follow_up"]["counts"]["all"]["with_outcome_feedback"], 1)
        self.assertEqual(merged["pulls"][0]["follow_up"]["outcome_feedback"], {
            "outcome": "solved", "saved_minutes": 45, "review_minutes": 12,
            "source": "https://github.com/TONstories/repo-neighbor/issues/35",
        })

    def test_refuses_to_treat_current_snapshot_as_past_observation(self):
        self.pr.update(state="CLOSED", closedAt=NEXT_WEEK)
        with self.assertRaisesRegex(ValueError, "predates"):
            follow_up(self.pr, c.parse(START))


    def test_refuses_to_count_work_that_occurs_after_the_report_cutoff(self):
        observation = c.parse(START)
        recorded_work = dict(issue=ISSUE, at=NEXT_WEEK, stage="tested_patch", source="test log")
        with self.assertRaisesRegex(ValueError, "predates recorded work"):
            report([], [self.claim], {"work": [recorded_work]}, Mock(), as_of=observation)
        later_claim = dict(self.claim, claimed_at=NEXT_WEEK)
        with self.assertRaisesRegex(ValueError, "predates recorded work"):
            report([], [later_claim], {}, Mock(), as_of=observation)
