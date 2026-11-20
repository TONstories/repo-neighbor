"""Volunteer work units for finite Goldbach checks. Python standard library only."""
import argparse
import json
from math import isqrt
from pathlib import Path


def primes(limit):
    flags = bytearray([1]) * (limit + 1)
    flags[:2] = b"\0\0"
    for p in range(2, isqrt(limit) + 1):
        if flags[p]:
            flags[p*p::p] = bytes((limit - p*p) // p + 1)
    return flags


def segment(limit, parts, index):
    if not (4 <= limit <= 1_000_000 and 1 <= parts <= min(1024, limit // 2 - 1)
            and 0 <= index < parts):
        raise ValueError("Require limit 4..1000000, nonempty parts 1..1024 and a zero-based index")
    count = limit // 2 - 1
    return range(4 + 2*(count*index//parts), 4 + 2*(count*(index+1)//parts), 2)


def work(limit, parts, index):
    numbers = segment(limit, parts, index)
    flags = primes(numbers[-1])
    witnesses = [next((p for p in range(2, n//2+1) if flags[p] and flags[n-p]), 0) for n in numbers]
    return dict(version=1, limit=limit, parts=parts, index=index, witnesses=witnesses)


def verify(limit, parts, paths):
    segment(limit, parts, 0)
    flags = primes(limit)
    seen = set()
    for path in paths:
        if path.stat().st_size > 8_000_000:
            raise ValueError("Oversized shard")
        data = json.loads(path.read_text())
        i = data["index"]
        if type(i) is not int or i in seen or (data["version"], data["limit"], data["parts"]) != (1, limit, parts):
            raise ValueError("Duplicate or foreign shard")
        numbers = segment(limit, parts, i)
        values = data["witnesses"]
        if not isinstance(values, list) or len(numbers) != len(values):
            raise ValueError("Incomplete shard")
        for n, p in zip(numbers, values):
            if type(p) is not int or not 2 <= p <= n//2 or not (flags[p] and flags[n-p]):
                raise ValueError(f"No valid prime witness for {n}")
        seen.add(i)
    if len(seen) != parts:
        raise ValueError("Missing shards")
    return limit//2 - 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["work", "verify"])
    parser.add_argument("limit", type=int)
    parser.add_argument("parts", type=int)
    parser.add_argument("inputs", nargs="+")
    args = parser.parse_args()
    try:
        if args.operation == "work":
            if len(args.inputs) != 1:
                raise ValueError("Supply one shard index")
            print(json.dumps(work(args.limit, args.parts, int(args.inputs[0]))))
        else:
            print(f"Verified even numbers: {verify(args.limit, args.parts, map(Path, args.inputs))}")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"{exc}\n")
