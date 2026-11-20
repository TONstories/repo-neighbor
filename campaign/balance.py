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
