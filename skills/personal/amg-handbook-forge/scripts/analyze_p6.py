#!/usr/bin/env python3
"""P6 delta-gate read-out.

Reads a workflow journal and reports, IN THE ORDER THE FORGE SPEC TRUSTS THEM:
  1. best-of picks per arm   (most robust — the handbook's real job)
  2. raw per-criterion votes per arm
  3. majority rate           (panel-sensitive at k=6; directional only)

Independently reconstructs the id->arm key from the script's deterministic
shuffle rather than trusting a returned key, and cross-checks the two if the
workflow result is available. Also re-runs the on-domain and handbook-read
guards, because attempt 2 of this gate produced a complete, clean-looking
verdict over a pool where both arms were identical.

Usage: python3 analyze_p6.py <journal.jsonl> [domain-keyword ...]
                             [--arms <armA-marker> <armB-marker>]

By default the arms are identified by the standard delta-gate markers: the
baseline arm reports handbook_read="N/A" and the handbook arm reports the file's
heading (matched on "field handbook"). For an ABLATION where BOTH arms read a
handbook, pass --arms with the two literal markers the script asks for, e.g.
    --arms WITH-REPELLER NO-REPELLER
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

PERM = [7, 2, 11, 5, 0, 9, 3, 8, 1, 10, 4, 6]  # must match the gate script
K = 6
CRITERIA = ("engages_frontier", "avoids_crowded", "challenges_assumption", "groundbreaking")


def load(journal: Path) -> tuple[list[dict], list[dict]]:
    ideas, verdicts = [], []
    for line in journal.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("type") != "result":
            continue
        v = e.get("value") or e.get("result") or {}
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except json.JSONDecodeError:
                continue
        if not isinstance(v, dict):
            continue
        if "direction" in v:
            ideas.append(v)
        elif "best_of" in v:
            verdicts.append(v)
    return ideas, verdicts


def main() -> int:
    argv = sys.argv[1:]
    arm_a, arm_b, arm_names = "N/A", "field handbook", ("base", "hb")
    if "--arms" in argv:
        i = argv.index("--arms")
        arm_a, arm_b = argv[i + 1], argv[i + 2]
        arm_names = (arm_a.lower(), arm_b.lower())
        argv = argv[:i] + argv[i + 3 :]
    journal = Path(argv[0])
    keywords = [k.lower() for k in argv[1:]]
    ideas, verdicts = load(journal)

    print(f"ideations: {len(ideas)}   checkers: {len(verdicts)}")
    if len(ideas) != 2 * K:
        print(f"ABORT: expected {2 * K} ideations, got {len(ideas)} — arm key would be wrong")
        return 1

    # --- guard 1: the handbook arm must actually have read the handbook ---
    # NOTE: the journal stores results in COMPLETION order, not submission order, so
    # position cannot identify the arm. handbook_read is self-identifying, so count it.
    reads = [str(i.get("handbook_read", "")).strip() for i in ideas]
    n_missing = sum(1 for r in reads if "HANDBOOK_MISSING" in r)
    if arm_a == "N/A" and arm_b == "field handbook":
        # Default delta-gate mode. Agents are told to echo the file's first heading,
        # but they paraphrase it, quote the generated-by banner, or decorate it. Only
        # the BASELINE marker is exact, so define the handbook arm by exclusion:
        # anything that is neither the baseline marker nor MISSING read *something*.
        n_a = sum(1 for r in reads if r == arm_a)
        n_b = sum(1 for r in reads if r != arm_a and "HANDBOOK_MISSING" not in r and r)
    else:  # ablation mode: both arms echo an explicit literal marker, so match strictly
        n_a = sum(1 for r in reads if arm_a.lower() in r.lower())
        n_b = sum(1 for r in reads if arm_b.lower() in r.lower())
    print(f"guard arm-marker: {n_a} '{arm_a}' · {n_b} '{arm_b}' · {n_missing} MISSING")
    if n_missing:
        print(f"ABORT: {n_missing} agents reported HANDBOOK_MISSING — this is an A/A, not an A/B")
        return 1
    if n_a != K or n_b != K:
        print(f"ABORT: expected {K} of each arm, got {n_a}/{n_b} — arms are not balanced")
        return 1

    # --- guard 2: on-domain check ---
    if keywords:
        off = [i for i in ideas if not any(k in i["direction"].lower() for k in keywords)]
        print(f"guard on-domain: {len(ideas) - len(off)}/{len(ideas)} mention {keywords}")
        if len(off) > len(ideas) // 2:
            print("ABORT: majority of ideas look off-domain — check before trusting numbers")
            return 1

    # --- reconstruct the key from the deterministic shuffle ---
    # entries[0..K-1] = base, entries[K..2K-1] = hb ; pool[n] = entries[PERM[n]]
    key = {f"P{n + 1}": (arm_names[0] if PERM[n] < K else arm_names[1]) for n in range(2 * K)}
    print("arm key:", " ".join(f"{k}={v}" for k, v in key.items()))

    # --- 1. best-of picks (primary) ---
    picks = Counter(key.get(v["best_of"], "?") for v in verdicts)
    unmapped = picks["?"]
    print(
        f"\n1. BEST-OF PICKS   {arm_names[1]} {picks[arm_names[1]]} : {picks[arm_names[0]]} {arm_names[0]}"
        f"{f'  (unmapped: {unmapped})' if unmapped else ''}"
    )
    for v in verdicts:
        print(
            f"     {v['best_of']:>3} ({key.get(v['best_of'], '?')}) — {v['best_of_reason'][:110]}"
        )

    # --- 2. raw per-criterion votes (primary) ---
    print("\n2. RAW VOTES (yes-votes summed over checkers x ideas)")
    print(f"   {'criterion':<24} {arm_names[1][:6]:>6} {arm_names[0][:6]:>7}   margin")
    tot = {arm_names[1]: 0, arm_names[0]: 0}
    for c in CRITERIA:
        n = {arm_names[1]: 0, arm_names[0]: 0}
        for v in verdicts:
            for r in v["ratings"]:
                arm = key.get(r["id"])
                if arm and r.get(c):
                    n[arm] += 1
        tot[arm_names[1]] += n[arm_names[1]]
        tot[arm_names[0]] += n[arm_names[0]]
        d = n[arm_names[1]] - n[arm_names[0]]
        print(f"   {c:<24} {n[arm_names[1]]:>6} {n[arm_names[0]]:>7}   {d:+d}")
    print(
        f"   {'TOTAL':<24} {tot[arm_names[1]]:>6} {tot[arm_names[0]]:>7}   {tot[arm_names[1]] - tot[arm_names[0]]:+d}"
    )

    # --- 3. majority rate (secondary, panel-sensitive) ---
    print("\n3. MAJORITY RATE (secondary — panel-sensitive at k=6, directional only)")
    for c in CRITERIA:
        rate = {arm_names[1]: 0, arm_names[0]: 0}
        for pid, arm in key.items():
            yes = sum(1 for v in verdicts for r in v["ratings"] if r["id"] == pid and r.get(c))
            if yes * 2 > len(verdicts):
                rate[arm] += 1
        print(
            f"   {c:<24} {arm_names[1]} {rate[arm_names[1]]}/{K}   {arm_names[0]} {rate[arm_names[0]]}/{K}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
