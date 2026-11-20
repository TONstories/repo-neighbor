"""Deterministic allocation. A seat is one project's frozen weekly work package."""
from collections import Counter
from datetime import datetime

SHARES = {"public-good": 40, "fun": 20, "defensive-security": 15, "science": 15, "general": 10}
TOPICS = {
    "public-good": ("medical-imaging", "accessibility", "assistive-technology", "prosthetics", "digital-health", "oncology", "dicom"),
    "fun": ("game-development", "creative-coding", "music", "generative-art"),
    "defensive-security": ("privacy", "secrets-management", "authentication"),
    "science": ("formal-verification", "theorem-proving", "mathematics", "astronomy", "scientific-computing"),
}


def track(meta):
    topics = {n["topic"]["name"] for n in meta.get("repositoryTopics", {}).get("nodes", [])}
    return next((k for k, tags in TOPICS.items() if topics.intersection(tags)), "general")


def finished(project, claims, cutoff):
    accepted = {c["issue"] for c in claims if c.get("merged_at") and datetime.fromisoformat(c["merged_at"].replace("Z", "+00:00")) < cutoff}
    issues = {t["url"] for t in project["tasks"]}
    return bool(issues) and issues <= accepted


def capacity(previous, claims, cutoff, old_limit):
    if not previous:
        return 3
    done = sum(finished(p, claims, cutoff) for p in previous)
    if done == len(previous):
        return min(8, old_limit + 1)
    if 2 * done < len(previous):
        return max(1, old_limit - 1)
    return old_limit


def allocate(pool, ranked, limit, history):
    counts = Counter(history)
    ordered = {name.lower(): i for i, name in enumerate(ranked)}
    chosen = []
    while pool and len(chosen) < limit:
        def priority(p):
            category = p["track"]
            deficit = SHARES[category] * (sum(counts.values()) + 1) - 100 * counts[category]
            rank = ordered.get(p["repo"].lower(), len(ordered))
            voted_seat = bool(ordered) and not chosen
            return (rank if voted_seat else 0, -deficit, rank,
                    -sum(t["score"] for t in p["tasks"][:2]), p["repo"].lower())
        pick = min(pool, key=priority)
        pool.remove(pick)
        counts[pick["track"]] += 1
        chosen.append(pick)
    return chosen


def workload(project):
    # Count the frozen work package once, including tasks still awaiting a volunteer.
    return sum((lo + hi) // 2 for lo, hi in
               (task.get("minutes") or (15, 45) for task in project["tasks"]))


def allocate_minutes(pool, ranked, limit, history, replacement=False):
    remaining = list(pool)
    totals = Counter(history)
    ranks = {repo.casefold(): index for index, repo in enumerate(ranked)}
    chosen, reasons = [], []
    while remaining and len(chosen) < limit:
        first = not chosen
        has_voted = any(p["repo"].casefold() in ranks for p in remaining)
        ballot = first and has_voted
        def priority(p):
            category = p["track"]
            rank = ranks.get(p["repo"].casefold(), len(ranks))
            deficit = SHARES[category] * (sum(totals.values()) + 30) - 100 * totals[category]
            return (rank if ballot else 0, -deficit, rank,
                    -sum(t["score"] for t in p["tasks"][:2]), p["repo"].casefold())
        pick = min(remaining, key=priority)
        key = priority(pick)
        remaining.remove(pick)
        totals[pick["track"]] += workload(pick)
        chosen.append(pick)
        reasons.append(dict(repo=pick["repo"], minutes=workload(pick),
                            rule=("next-ballot" if replacement else "ballot") if ballot else "workload",
                            deficit=-key[1]))
    return chosen, reasons
