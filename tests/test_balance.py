import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase

from compute.goldbach import work, verify
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "campaign"))
import balance


class AllocationTests(TestCase):
    def test_votes_and_shares(self):
        pool = [dict(repo=f"{track}/{i}", track=track, tasks=[dict(score=1)])
                for track in balance.SHARES for i in range(20)]
        chosen = balance.allocate(pool.copy(), ["science/4"], 20, [])
        self.assertEqual(chosen[0]["repo"], "science/4")
        self.assertEqual({k: sum(p["track"] == k for p in chosen)*5 for k in balance.SHARES}, balance.SHARES)
        self.assertEqual(balance.allocate(pool, ["fun/3", "science/4"], 1, [])[0]["repo"], "fun/3")

    def test_multiple_voters_and_rollover(self):
        pool = [dict(repo=name, track=track, tasks=[dict(score=1)])
                for name, track in [("a", "fun"), ("b", "fun"), ("c", "public-good")]]
        chosen = balance.allocate(pool, ["a", "b"], 2, [])
        self.assertEqual([p["repo"] for p in chosen], ["a", "c"])
        self.assertEqual(balance.allocate(pool, ["a", "b"], 1, ["fun", "public-good"])[0]["repo"], "b")

    def test_capacity_only_verified_before_cutoff(self):
        project = dict(tasks=[dict(url="u")])
        cutoff = datetime(2026, 11, 23, 6, 15, tzinfo=timezone.utc)
        claims = [dict(issue="u", merged_at="2026-11-23T06:14:59Z")]
        self.assertEqual(balance.capacity([project], claims, cutoff, 3), 4)
        claims[0]["merged_at"] = "2026-11-23T06:16:00Z"
        self.assertEqual(balance.capacity([project], claims, cutoff, 3), 2)

    def test_distributed_certificates(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory)/str(i) for i in range(3)]
            for i, path in enumerate(paths):
                path.write_text(json.dumps(work(1001, 3, i)))
            self.assertEqual(verify(1001, 3, paths[::-1]), 499)
            for invalid in (paths[:2], paths+[paths[0]]):
                with self.assertRaises(ValueError):
                    verify(1001, 3, invalid)
            data = json.loads(paths[1].read_text())
            data["witnesses"][0] = 4
            paths[1].write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                verify(1001, 3, paths)
