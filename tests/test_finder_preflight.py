import json
from unittest import TestCase
from unittest.mock import patch

from test_campaign import APPROVAL, FILES, META, NOW, REPO, ROOT, ROW
from finder import FILES as METADATA_FILES
from finder import MAX_FILE_TEXT, assess, metadata
from quota import check_issue, issue_timestamp


class LiveIssueRecheckTests(TestCase):
    def test_changed_and_blocked_after_selection(self):
        original = issue_timestamp("2026-11-20T09:00:00Z")
        row = dict(ROW, updatedAt="2026-11-20T10:00:00Z", comments={"totalCount": 0, "nodes": []})
        for delta, expected, status, reason in (
            ({}, original, "changed", "issue_updated"),
            ({"state": "CLOSED"}, original, "blocked", "issue_not_open"),
            ({"locked": True}, original, "blocked", "discussion_locked"),
            ({"assignees": {"totalCount": 1}}, original, "blocked", "issue_assigned"),
            ({"closedByPullRequestsReferences": {"totalCount": 1}}, original, "blocked", "linked_pull_request"),
            ({"comments": {"totalCount": 101, "nodes": []}}, None, "unverified", "discussion_incomplete"),
        ):
            with self.subTest(reason=reason), patch("quota.live_issue", return_value=dict(row, **delta)):
                with patch("quota.metadata") as meta:
                    result = check_issue(row["url"], expected, NOW.date())
                self.assertEqual((result["status"], result["reason"]), (status, reason))
                meta.assert_not_called()

    def test_recheck_reads_older_claims_and_allows_a_complete_unclaimed_discussion(self):
        nodes = [{"id": str(i), "body": "A suggestion."} for i in range(26)]
        row = dict(ROW, comments={"totalCount": len(nodes), "nodes": nodes[-8:]})

        def page(entries, cursor):
            return {"repository": {"issue": {
                "updatedAt": row["updatedAt"], "comments": {
                    "totalCount": len(nodes), "nodes": entries,
                    "pageInfo": {"hasNextPage": bool(cursor), "endCursor": cursor},
                },
            }}}

        for body, association, status in (
            ("I am already implementing this.", "CONTRIBUTOR", "blocked"),
            ("@alice, I'm holding this one for you.", "MEMBER", "blocked"),
            ("@alice, I'm holding this one for you.", "CONTRIBUTOR", "no_detected_blocker"),
            ("Can you explain the expected result?", "NONE", "no_detected_blocker"),
        ):
            with (
                self.subTest(status=status),
                patch("quota.live_issue", return_value=row),
                patch("quota.metadata", return_value=(META, FILES)),
                patch("quota.project_approval", return_value=APPROVAL),
                patch("finder.graph", side_effect=[
                    page([dict(nodes[0], body=body, authorAssociation=association), *nodes[1:25]], "page-2"),
                    page(nodes[25:], None),
                ]) as api,
            ):
                result = check_issue(row["url"], None, NOW.date(), as_of=NOW)
                self.assertEqual(result["status"], status)
                self.assertEqual(result["discussion_comments_checked"], 26)
                self.assertEqual(api.call_count, 2)
                self.assertEqual(api.call_args.kwargs["after"], "page-2")
                self.assertIn("authorAssociation", api.call_args.args[0])
                self.assertEqual(len(row["comments"]["nodes"]), 8)

    def test_recheck_rejects_an_inconsistent_discussion_snapshot(self):
        row = dict(ROW, comments={"totalCount": 9, "nodes": []})
        nodes = [{"id": str(i), "body": ""} for i in range(9)]
        for updated, comments in (
            ("2000-01-01T00:00:00Z", nodes),
            (row["updatedAt"], [*nodes[:8], nodes[7]]),
            (row["updatedAt"], nodes[:8]),
        ):
            page = {"repository": {"issue": {
                "updatedAt": updated, "comments": {
                    "totalCount": 9, "nodes": comments, "pageInfo": {"hasNextPage": False},
                },
            }}}
            with (
                self.subTest(updated=updated, ids=[c["id"] for c in comments]),
                patch("quota.live_issue", return_value=row),
                patch("finder.graph", return_value=page),
                patch("quota.metadata") as meta,
            ):
                result = check_issue(row["url"], None, NOW.date(), as_of=NOW)
                self.assertEqual(result["reason"], "discussion_incomplete")
                meta.assert_not_called()

    def test_reuses_current_finder_rules_and_normalizes_the_timestamp(self):
        row = dict(ROW, updatedAt="2026-11-20T10:00:00Z", comments={"totalCount": 0, "nodes": []})
        original = issue_timestamp("2026-11-20T13:00:00+03:00")
        with (
            patch("quota.live_issue", return_value=row),
            patch("quota.metadata", return_value=(META, FILES)),
            patch("quota.project_approval", return_value=APPROVAL),
        ):
            result = check_issue(row["url"], original, NOW.date(), as_of=NOW)
        self.assertEqual(result["status"], "no_detected_blocker")
        self.assertEqual(result["recent_approval"], APPROVAL)
        self.assertIn("Confirm AI and attribution policy", result["confirm"][0])

        policy = dict(FILES, **{"CONTRIBUTING.md": "Human-authored patches only."})
        with patch("quota.live_issue", return_value=row), patch("quota.metadata", return_value=(META, policy)):
            result = check_issue(row["url"], original, NOW.date())
        self.assertEqual(result["reason"], "not_eligible_under_finder_rules")

        row["comments"] = {"totalCount": 1, "nodes": [{"body": "I am already implementing this."}]}
        with patch("quota.live_issue", return_value=row), patch("quota.metadata", return_value=(META, FILES)):
            result = check_issue(row["url"], None, NOW.date())
        self.assertEqual(result["reason"], "not_eligible_under_finder_rules")

    def test_missing_recent_approval_blocks_otherwise_eligible_issue(self):
        row = dict(ROW, comments={"totalCount": 0, "nodes": []})
        with (
            patch("quota.live_issue", return_value=row),
            patch("quota.metadata", return_value=(META, FILES)),
            patch("quota.project_approval", return_value=None),
        ):
            result = check_issue(row["url"], None, NOW.date(), as_of=NOW)
        self.assertEqual((result["status"], result["reason"]), ("blocked", "no_recent_project_approval"))

    def test_failed_lookup_stays_unverified(self):
        with patch("quota.live_issue", side_effect=RuntimeError("API unavailable")):
            self.assertEqual(check_issue(ROW["url"], None, NOW.date())["status"], "unverified")

    def test_truncated_policy_stays_unverified(self):
        row = dict(ROW, comments={"totalCount": 0, "nodes": []})
        meta = dict(META, incomplete_policy_files=["CONTRIBUTING.md"])
        with patch("quota.live_issue", return_value=row), patch("quota.metadata", return_value=(meta, FILES)):
            result = check_issue(row["url"], None, NOW.date())
        self.assertEqual(result["status"], "unverified")
        self.assertEqual(result["reason"], "policy_files_incomplete")
        self.assertEqual(result["policy_files"], ["CONTRIBUTING.md"])


class FinderPreflightTests(TestCase):
    def candidate(self, row=None, contribution=None, files=None):
        policies = FILES.copy()
        if contribution is not None:
            policies["CONTRIBUTING.md"] += contribution
        if files:
            policies.update(files)
        return assess(row or ROW, REPO, META, policies, NOW.date())

    def test_direct_restrictions_and_negative_controls(self):
        for restriction, control in (
            ("Human-authored patches only.", "Human-authored patches are welcome."),
            ("Do not accept AI contributions.", "AI contributions are optional."),
            ("AI contributions are prohibited.", "AI contributions are welcome."),
            ("You must request an assignment before starting.", "You may request an assignment before starting."),
            ("You need to be assigned before editing.", "You may be assigned during review."),
            ("Wait until a maintainer assigns the issue to you before you start, so two people\n"
             "don't work on the same thing.", "A maintainer assigns the issue to you after you open a draft."),
            ("## Before you start: claim an issue", "## How to claim an issue"),
            (
                "### Claiming an issue\n\nComment on it and a maintainer assigns it to you, "
                "so two people do not write the same patch.",
                "### Claiming an issue\n\nComment on it if you would like a maintainer to assign it to you.",
            ),
        ):
            with self.subTest(restriction=restriction):
                self.assertIsNone(self.candidate(contribution=restriction))
                self.assertIsNotNone(self.candidate(contribution=control))

    def test_issue_ownership_and_negative_controls(self):
        for claim, control in (
            ("I am already implementing this.", "I am already implementing another issue."),
            ("I am fixing this.", "I am investigating related failures."),
            ("I'm taking this issue.", "I'm taking this approach in another project."),
            ("/assignme", "Does this issue require assignment?"),
            ("I'll take this.", "I'll take a look at the report."),
            ("Hi, I can pick this up. Question first: when should it ship?", "I can pick this up?"),
            ("Opened #6025 with a fix for this.", "Opened #6025 for a related issue."),
            ("I have opened PR #6025 to address this.", "Opened https://github.com/other/repo/pull/6025 with a fix for this."),
            ("I'd like to work on this issue. I'll add the Activity badge.", "I would like to understand the issue."),
            ("I'd like to work on this issue by adding a new catalog entry.", "Could I work on this issue by adding a new catalog entry?"),
        ):
            with self.subTest(claim=claim):
                self.assertIsNone(self.candidate(dict(ROW, comments={"nodes": [{"body": claim}]})))
                self.assertIsNotNone(self.candidate(dict(ROW, comments={"nodes": [{"body": control}]})))

    def test_maintainer_holds_and_releases_are_person_specific(self):
        hold = {"authorAssociation": "MEMBER", "body": "Hi @alice, I'm holding this one for you."}
        second = {"authorAssociation": "OWNER", "body": "@bob, I'm holding three issues for you."}
        release = {"authorAssociation": "COLLABORATOR", "body": "@alice, this is open. <!-- maintainer: claim-released -->"}
        quoted = dict(hold, body="> Hi @alice, I'm holding this one for you.\nThat was last week.")
        for comments, eligible in (
            ([hold], False),
            ([hold, release], True),
            ([hold, release, second], False),
            ([hold, second, release], False),
            ([hold, dict(release, authorAssociation="CONTRIBUTOR")], False),
            ([dict(hold, authorAssociation="CONTRIBUTOR")], True),
            ([quoted], True),
        ):
            with self.subTest(comments=comments):
                row = dict(ROW, comments={"nodes": comments})
                self.assertEqual(self.candidate(row) is not None, eligible)

    def test_issue_specific_assignment_and_cuda_requirements(self):
        issue = dict(ROW, body=ROW["body"] + "\nPlease comment `/claim` and wait for assignment.")
        self.assertIsNone(self.candidate(issue))
        cuda = dict(ROW, body=ROW["body"] + "\nRun the selected tests with a CUDA device.")
        item = self.candidate(cuda)
        self.assertEqual((item["fit"], item["minutes"]), ("investigate", None))

    def test_live_recheck_reports_where_assignment_is_required(self):
        row = dict(ROW, comments={"totalCount": 0, "nodes": []})
        rules = "### Claiming an issue\n\nComment on it and a maintainer assigns it to you."
        for live_row, files, source in (
            (row, {**FILES, "CONTRIBUTING.md": rules}, "CONTRIBUTING.md"),
            (dict(row, body=row["body"] + "\nPlease wait for an assignment."), FILES, "issue"),
        ):
            with (
                self.subTest(source=source),
                patch("quota.live_issue", return_value=live_row),
                patch("quota.metadata", return_value=(META, files)),
                patch("quota.project_approval") as lookup,
            ):
                result = check_issue(row["url"], None, NOW.date(), as_of=NOW)
                self.assertEqual(
                    (result["status"], result["reason"], result["source"]),
                    ("blocked", "maintainer_assignment_required", source),
                )
                lookup.assert_not_called()

    def test_issue_contributor_requirements_remain_visible_and_need_confirmation(self):
        for text, required in (
            ("This issue is reserved for a first-time OnlyRead contributor. Comment before starting.", 2),
            ("Please comment before starting. This issue is reserved for first-time OnlyRead contributors.", 2),
            ("Please leave a comment on this issue before you start.", 1),
            ("No need to comment before starting. First-time contributors are welcome.", 0),
        ):
            row = dict(ROW, body=ROW["body"] + "\n" + text, comments={"totalCount": 0, "nodes": []})
            with (
                self.subTest(text=text),
                patch("quota.live_issue", return_value=row),
                patch("quota.metadata", return_value=(META, FILES)),
                patch("quota.project_approval", return_value=APPROVAL),
            ):
                item = self.candidate(row)
                self.assertEqual(len(item["issue_requirements"]), required)
                result = check_issue(row["url"], None, NOW.date(), as_of=NOW)
                if required:
                    self.assertNotEqual(item["fit"], "fits")
                    self.assertEqual(result["status"], "requires_action")
                    self.assertEqual(result["required_actions"], item["issue_requirements"])
                else:
                    self.assertEqual(result["status"], "no_detected_blocker")

    def test_project_cla_is_visible_without_blocking_local_work(self):
        row = dict(ROW, comments={"totalCount": 0, "nodes": []})
        for policy, has_agreement in (
            ("For this reason, every\ncontributor signs the [Contributor License Agreement](CLA.md) once.", True),
            ("- Please sign the CLA before opening a pull request.", True),
            ("Contributors don't need to sign a CLA.", False),
            ("The project introduced its old contributor license agreement in 2020.", False),
        ):
            files = dict(FILES, **{"CONTRIBUTING.md": policy})
            with (
                self.subTest(policy=policy),
                patch("quota.live_issue", return_value=row),
                patch("quota.metadata", return_value=(META, files)),
                patch("quota.project_approval", return_value=APPROVAL),
            ):
                result = check_issue(row["url"], None, NOW.date(), as_of=NOW)
                self.assertEqual(result["status"], "no_detected_blocker")
                self.assertEqual(bool(result.get("submission_requirements")), has_agreement)
                if has_agreement:
                    notice, = result["submission_requirements"]
                    self.assertIn("CONTRIBUTING.md", notice)
                    self.assertIn(notice, result["confirm"])

    def test_recheck_flags_known_check_prerequisites(self):
        hardware = json.loads((ROOT / "tests/fixtures/nextgen-hardware-15.json").read_text())
        for body, expected in (
            (ROW["body"], None),
            (ROW["body"] + "\nRequired kani-gate must pass.", "Kani toolchain"),
            (ROW["body"] + "\nRun the selected tests with a CUDA device.", "physical equipment"),
            (hardware["body"], "physical equipment"),
        ):
            row = dict(ROW, body=body, comments={"totalCount": 0, "nodes": []})
            with (
                self.subTest(expected=expected, saved_hardware=body == hardware["body"]),
                patch("quota.live_issue", return_value=row),
                patch("quota.metadata", return_value=(META, FILES)),
                patch("quota.project_approval", return_value=APPROVAL),
            ):
                result = check_issue(row["url"], None, NOW.date(), as_of=NOW)
                if expected is None:
                    self.assertEqual(result["status"], "no_detected_blocker")
                    continue
                self.assertEqual(result["status"], "requires_action")
                self.assertEqual(result["reason"], "check_environment_requirements")
                self.assertTrue(any(expected in note for note in result["required_actions"]))

    def test_records_ai_conditions_and_partial_comment_coverage(self):
        issue = dict(ROW, comments={"totalCount": 9, "nodes": [{"body": "Recent discussion"}] * 8})
        item = self.candidate(issue, files={
            "CONTRIBUTOR_AI_PROMPT.md": "AI contributions require maintainer approval.",
        })
        self.assertEqual(item["fit"], "uncertain")
        self.assertTrue(any("maintainer approval" in note for note in item["unknown"]))
        self.assertTrue(any("Only recent comments" in note for note in item["unknown"]))

    def test_incomplete_discussion_alone_prevents_fits(self):
        issue = dict(ROW, comments={"totalCount": 9, "nodes": [{"body": "Recent discussion"}] * 8})
        self.assertEqual(self.candidate(issue)["fit"], "uncertain")

    def test_metadata_distinguishes_complete_long_policy_from_unreadable_policy(self):
        index = METADATA_FILES.index("CONTRIBUTING.md")
        padding = ("Guidance for contributors.\n" * (MAX_FILE_TEXT // 25 + 1))
        self.addCleanup(metadata.cache_clear)
        for blob, incomplete, candidate in (
            ({"text": padding, "isTruncated": False}, [], True),
            ({"text": padding + "Human-authored patches only.\n", "isTruncated": False}, [], False),
            ({"text": "Contributions welcome.", "isTruncated": True}, ["CONTRIBUTING.md"], False),
            ({"text": None, "isTruncated": False}, ["CONTRIBUTING.md"], False),
            (None, [], True),
        ):
            with self.subTest(incomplete=incomplete, eligible=candidate):
                metadata.cache_clear()
                response = {"repository": dict(META, nameWithOwner=REPO, **{f"f{index}": blob})}
                with patch("finder.graph", return_value=response):
                    meta, files = metadata(REPO)
                self.assertEqual(meta["incomplete_policy_files"], incomplete)
                self.assertEqual(assess(ROW, REPO, meta, files, NOW.date()) is not None, candidate)

    def test_required_initial_comment_is_visible_instead_of_a_time_promise(self):
        required = "If there is already an issue for what you want to fix, leave a comment first."
        optional = required.replace("leave a", "you may leave a")
        row = dict(ROW, body=ROW["body"] + "\n\nnpm test\n")
        item = self.candidate(row, contribution="\n" + required)
        self.assertEqual(item["fit"], "uncertain")
        self.assertIn("Comment on the issue before starting (CONTRIBUTING.md).", item["unknown"])
        self.assertEqual(self.candidate(row, contribution="\n" + optional)["fit"], "fits")

    def test_autonomous_assignment_rule_is_visible_without_excluding_human_led_work(self):
        row = dict(ROW, labels={"nodes": [{"name": "good first issue"}]})
        item = self.candidate(row, contribution=(
            "\nAI reviews are advisory and do not replace approval.\n\n"
            "**Maintainer-operated autonomous agents** are distinct from human-directed AI assistance. "
            "Before an autonomous agent implements a newcomer-reserved `good first issue`, "
            "a maintainer must authorize **that specific issue** and assign its implementer."
        ))
        self.assertEqual(item["fit"], "uncertain")
        self.assertTrue(any("issue-specific maintainer authorization and assignment" in note
                            for note in item["unknown"]))

    def test_detected_check_does_not_prove_environment_available(self):
        missing = assess(ROW, REPO, META, {}, NOW.date())
        self.assertEqual(missing["fit"], "uncertain")
        self.assertTrue(any("No check detected" in note for note in missing["unknown"]))
        item = self.candidate(dict(ROW, body=ROW["body"] + "\nRequired kani-gate must pass."))
        self.assertEqual((item["fit"], item["minutes"]), ("investigate", None))
        self.assertTrue(any("Kani toolchain" in note for note in item["unknown"]))

    def test_saved_hardware_issue_has_uncertain_effort_and_current_assignee_blocks(self):
        source = json.loads((ROOT / "tests/fixtures/nextgen-hardware-15.json").read_text())
        row = dict(ROW, title=source["title"], body=source["body"], url=source["html_url"],
                   labels={"nodes": [{"name": name} for name in source["labels"]]})
        self.assertIsNone(assess(row, REPO, dict(META, stargazerCount=10), {}, NOW.date()))
        item = assess(row, REPO, META, {}, NOW.date())
        self.assertEqual((item["fit"], item["minutes"]), ("investigate", None))
        self.assertTrue(any("physical equipment" in note for note in item["unknown"]))
        self.assertIsNone(assess(dict(row, assignees={"totalCount": 1}), REPO, META, {}, NOW.date()))
