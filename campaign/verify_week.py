"""Offline election replay. Usage: python3 campaign/verify_week.py WEEK"""

import argparse
import json
from pathlib import Path

import balance
import community


def verify(snapshot):
    if snapshot["version"] != 1 or snapshot["shares"] != balance.SHARES:
        raise ValueError("Unsupported allocation rules")
    chosen = list(snapshot["prior"])
    for round_ in snapshot["rounds"]:
        for vote in round_["ballot"]["votes"].values():
            if "credits" in vote and vote["weight"] != 1 + len(set(vote["credits"])):
                raise ValueError("Vote weight differs from credited tasks")
        picks = balance.allocate(
            list(round_["pool"]),
            community.ranking(round_["ballot"]),
            round_["limit"],
            round_["history"],
        )
        names = [p["repo"] for p in picks]
        if names != round_["selected"] or set(names).intersection(chosen):
            raise ValueError("Allocation mismatch")
        chosen.extend(names)
    return chosen


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="verify-week")
    parser.add_argument("week")
    args = parser.parse_args()
    folder = Path(__file__).resolve().parents[1] / "campaigns/archive" / args.week
    snapshot = json.loads((folder / "audit.json").read_text())
    if verify(snapshot) != [
        p["repo"] for p in json.loads((folder / "selection.json").read_text())
    ]:
        raise SystemExit("Published selection differs")
    print(
        f"Verified {len(snapshot['rounds'])} rounds. Legacy seats: {len(snapshot['prior'])}"
    )
