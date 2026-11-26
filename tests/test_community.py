import datetime as dt
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / "campaign"),
    str(ROOT / "sponsorship"),
    str(ROOT / "skills/repo-neighbor/scripts"),
]
import community as c
import sponsor
import run
from finder import assess, discover
from test_campaign import ROW, REPO, META, FILES, NOW, ISSUE, WINDOW, APPROVAL, discovery


class ElectionTests(unittest.TestCase):
    def test_weight_replacement_cutoff_and_dedup(self):
        prior = (NOW - dt.timedelta(days=15)).isoformat()
        old = dict(issue=ISSUE, user="Alice", merged_at=prior, submitted_at=prior)
        ledger = {
            "claims": [
                old,
                dict(old),
                dict(old, issue="other", merged_at=NOW.isoformat()),
            ]
        }

        def lookup(repo):
            return dict(META, nameWithOwner=repo), {}

        def submit(command, who="Alice"):
            return c.command("rn " + command, who, NOW, ledger, lookup)

        self.assertIn("Nominated", submit("nominate org/first"))
        self.assertIn("One nomination", submit("nominate org/second"))
        submit("nominate org/second", "Bob")
        submit("vote org/first")
        submit("vote org/second")
        submit("vote org/first", "Bob")
        election = ledger["elections"][c.week(NOW + dt.timedelta(days=7))]
        self.assertEqual(list(c.ranking(election)), ["org/second", "org/first"])
        self.assertEqual(election["votes"]["alice"]["weight"], 2)
        self.assertEqual(election["votes"]["bob"]["weight"], 1)
        election["closed"] = True
        self.assertIn("closed", submit("vote org/first"))

    def test_proposal_is_readable_from_ballot_after_issue_closes(self):
        ledger = {"claims": []}
        c.command("rn nominate org/tool", "Alice", NOW, ledger,
                  lambda repo: (dict(META, nameWithOwner=repo), {}), issue_number=42)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            c.reports(root, ledger, [], NOW, {})
            ballot = c.week(NOW + dt.timedelta(days=7)) + ".md"
            for page in ("README.md", ballot):
                self.assertIn(c.BASE + "/issues/42", (root / "reports" / page).read_text())
        self.assertEqual(c.proposal_link({"user": "previous contributor"}), "")

    def test_maintainer_proposal_verifies_org_permission_and_freezes_cap(self):
        fields = {"Product": "A docs app", "Roadmap": "Next release", "Weekly outcome": "Examples",
                  "Work packages": f"{ISSUE} and {ISSUE}2",
                  "Review and rules": "Reviewer checks both examples", "Review capacity": "2",
                  "Permission": "I invite Repo Neighbor to help."}
        body = "\n".join(f"### {key} / translation\n\n{value}" for key, value in fields.items())
        ledger = {"claims": []}
        def lookup(repo):
            return dict(META, nameWithOwner=repo), {}
        def submit(user, qualify):
            return c.command("rn propose " + REPO, user, NOW, ledger, lookup,
                             body=body, qualify=qualify)
        self.assertIn("upstream confirmation", submit("stranger", lambda *_: False))
        self.assertIn("Nominated", submit("maintainer", lambda *_: True))
        vote = ledger["elections"][c.week(NOW + dt.timedelta(days=7))]
        self.assertEqual(vote["nominees"][REPO.casefold()]["review_limit"], 2)

    def test_impact_unique_merged_pr(self):
        row = dict(pr="test", estimate=[30, 90])
        self.assertEqual(c.impact(c.unique_prs([row, row]).values()), ("$30–$90", 0))
        self.assertEqual(c.impact([{}]), ("$0–$0", 1))

    def test_dependency_and_overlapping_work(self):
        project = {"repo": REPO, "tasks": [dict(url=ISSUE, scope=["src/input.py"])]}
        claim = "rn claim " + ISSUE + " 90"
        self.assertIn(
            "prerequisites",
            run.transition(
                claim, "Jane", [], c.week(NOW), [project], NOW, {ISSUE: ["earlier"]}
            ),
        )
        other = dict(
            user="Bob",
            issue=ISSUE + "2",
            status="open",
            repo=REPO,
            scope=["src/input.py"],
        )
        with (
            patch.object(run, "live_issue", return_value=ROW),
            patch.object(run, "metadata", return_value=(META, FILES)),
            patch.object(run, "reviews", return_value=WINDOW),
            patch.object(run, "project_approval", return_value=APPROVAL),
        ):
            self.assertIn(
                "overlapping",
                run.transition(claim, "Jane", [other], c.week(NOW), [project], NOW),
            )

    def test_native_children_are_reserved_instead_of_parent(self):
        child = dict(
            ROW,
            url=ISSUE + "1",
            labels={"nodes": []},
            parent=dict(
                url=ISSUE,
                state="OPEN",
                locked=False,
                assignees={"totalCount": 0},
                labels=ROW["labels"],
            ),
        )
        parent = dict(
            ROW,
            subIssues={"nodes": [{"url": child["url"], "state": "OPEN"}]},
            repository={"nameWithOwner": REPO, "stargazerCount": 100},
        )
        self.assertIsNone(assess(parent, REPO, META, FILES, NOW.date()))
        with (
            patch("finder.graph", return_value={"search": {"nodes": [parent]}}),
            patch("finder.live_issues", return_value=[child]),
            patch("finder.metadata", return_value=(META, FILES)),
            patch("finder.project_approval", return_value=APPROVAL),
        ):
            picks = discover([], None, 4, NOW.date())["candidates"]
        self.assertEqual([row["url"] for row in picks], [child["url"]])

    def test_votes_reach_weekly_selector(self):
        tasks = [
            dict(url=ISSUE + str(i), title=t, scope=[], score=2, repo=REPO)
            for i, t in enumerate(["Improve docs", "Add parser tests"])
        ]
        with (
            patch.object(run, "metadata", return_value=(META, FILES)),
            patch.object(run, "graph", return_value={"search": {"nodes": []}}),
            patch.object(run, "discover", return_value=discovery(tasks)),
            patch.object(run, "reviews", return_value=WINDOW),
            patch.object(run, "project_approval", return_value=APPROVAL),
        ):
            selected = run.select(
                NOW, {"exclude": [], "override": {}, "ranked": [REPO.upper()]}, None, []
            )
        self.assertEqual([p["repo"] for p in selected], [REPO])


class DonationTests(unittest.TestCase):
    def grant(self):
        return {
            "provider": "openrouter",
            "cap_usd": "5",
            "key": secrets.token_urlsafe(),
            "model": "fixture/model",
            "project": REPO,
            "expires": "2099-01-01",
        }

    def test_caps_and_gateway_approval(self):
        g = self.grant()
        data = {
            "limit": 5,
            "limit_remaining": 2,
            "is_management_key": False,
            "limit_reset": None,
        }
        self.assertTrue(sponsor.verify_limit(g, lambda *a: {"data": data}))
        for field, val in [
            ("limit", 6),
            ("limit_reset", "monthly"),
            ("is_management_key", True),
            ("limit_remaining", 0),
        ]:
            with self.assertRaises(ValueError):
                sponsor.verify_limit(g, lambda *a: {"data": dict(data, **{field: val})})
        with self.assertRaises(ValueError):
            sponsor.verify_limit(g, lambda *a: {"data": data}, already_spent=4)
        g.update(provider="litellm", gateway="https://proxy.example")
        with tempfile.TemporaryDirectory() as d:
            v = Path(d)
            (v / "gateways.json").write_text("[]")
            with self.assertRaises(ValueError):
                sponsor.verify_limit(
                    g, lambda *a: self.fail("Network before allowlist"), v
                )
            (v / "gateways.json").write_text(json.dumps([g["gateway"]]))
            sponsor.verify_limit(
                g,
                lambda *a: {
                    "info": {
                        "models": [g["model"]],
                        "max_budget": 4,
                        "spend": 1,
                        "budget_duration": None,
                    }
                },
                v,
            )

    @unittest.skipUnless(
        shutil.which("age-keygen") and shutil.which("age"), "age CLI required"
    )
    def test_sealed_grant_and_interrupted_request(self):
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            subprocess.run(
                ["age-keygen", "-o", str(vault / ".env")],
                capture_output=True,
                check=True,
            )
            recipient = (
                sponsor.call(["age-keygen", "-y", str(vault / ".env")]).decode().strip()
            )
            g = self.grant()
            envelope = sponsor.encrypt(g, recipient)
            self.assertNotIn(g["key"], envelope)
            self.assertEqual(sponsor.decrypt(envelope, vault), g)
            gid = "f" * 32
            path = vault / (gid + ".json")
            sponsor.write(
                path, dict(active=True, envelope=envelope, pending=None, receipts=[])
            )
            with (
                patch.object(
                    sponsor,
                    "gh",
                    return_value=dict(
                        state="open",
                        title="test",
                        body="test",
                        visibility="public",
                        full_name=REPO,
                    ),
                ),
                patch.object(
                    sponsor, "verify_limit", return_value="https://example.invalid/"
                ),
                patch.object(sponsor, "provider", side_effect=TimeoutError),
            ):
                with self.assertRaises(TimeoutError):
                    sponsor.assist(
                        gid, vault, "https://github.com/" + REPO + "/issues/1"
                    )
                with self.assertRaises(ValueError):
                    sponsor.assist(
                        gid, vault, "https://github.com/" + REPO + "/issues/1"
                    )
            self.assertNotIn(g["key"], path.read_text())

    def test_pledge_cannot_be_preempted_and_import_binds_owner(self):
        import base64

        g = self.grant()
        gid = "a" * 32
        ledger = {"claims": []}
        for account in ["unrelated", "actual-donor"]:
            c.command("rn pledge " + gid, account, NOW, ledger, None)
        entries = {
            "repos/" + sponsor.PROJECT + "/contents/campaigns/ledger.json": {
                "content": base64.b64encode(json.dumps(ledger).encode()).decode()
            },
            "gists/" + gid: {
                "public": False,
                "owner": {"login": "stranger"},
                "files": {
                    "grant.age": {"size": 50, "content": "sealed-envelope-fixture"}
                },
            },
        }
        with (
            tempfile.TemporaryDirectory() as d,
            patch.object(sponsor, "gh", side_effect=lambda url: entries[url]),
            patch.object(sponsor, "decrypt", return_value=g),
            patch.object(sponsor, "verify_limit"),
        ):
            vault = Path(d)
            with self.assertRaises(ValueError):
                sponsor.accept(gid, vault)
            entries["gists/" + gid]["owner"]["login"] = "actual-donor"
            sponsor.accept(gid, vault)
            state = (vault / (gid + ".json")).read_text()
            self.assertTrue(json.loads(state)["active"])
            self.assertNotIn(g["key"], state)
            with self.assertRaises(ValueError):
                sponsor.accept(gid, vault)

    def test_cost_publication_only_aggregate_and_compare_and_swap(self):
        import base64

        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            sponsor.write(
                vault / ("e" * 32 + ".json"),
                dict(
                    envelope="ciphertext",
                    pending=None,
                    receipts=[
                        {
                            "day": "2026-11-20",
                            "week": "2026-W47",
                            "issue": ISSUE,
                            "cost_usd": "0.08",
                        }
                    ],
                ),
            )
            sent = []

            def transport(path, payload=None, method="GET"):
                if path == "user":
                    return {"login": "TONstories"}
                if payload is None:
                    return {
                        "sha": "version",
                        "content": base64.b64encode(b"{}").decode(),
                    }
                sent.append((method, payload))

            with patch.object(sponsor, "gh", side_effect=transport):
                sponsor.publish_costs(vault)
            method, payload = sent[0]
            self.assertEqual((method, payload["sha"]), ("PUT", "version"))
            self.assertEqual(
                json.loads(base64.b64decode(payload["content"])),
                {"2026-11-20/2026-W47": "0.08"},
            )
