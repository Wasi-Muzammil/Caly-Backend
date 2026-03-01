"""
Smart Slot Ranking Logic
========================
Rule-based scoring (0-100) for candidate meeting slots based on:
  1. Overlap coverage   — what % of participants are free          (40 pts)
  2. Morning preference — slots in 09:00-12:00 score higher       (20 pts)
  3. Earliest slot      — earlier slots score higher               (20 pts)
  4. Gap minimisation   — prefer slots close to now (urgency)     (10 pts)
  5. Priority boost     — is_priority flag adds a flat bonus       (10 pts)
"""

import datetime
from typing import List, Dict


# ─────────────────────────────────────────────
# Types
# ─────────────────────────────────────────────

Slot     = Dict   # {"start": datetime, "end": datetime}
BusyMap  = Dict   # {email: [{"start": datetime, "end": datetime}, ...]}


# ─────────────────────────────────────────────
# Core helpers
# ─────────────────────────────────────────────

def _overlaps(slot: Slot, busy: Slot) -> bool:
    """Return True if a busy block overlaps with the candidate slot."""
    return slot["start"] < busy["end"] and slot["end"] > busy["start"]


def _count_free_participants(slot: Slot, busy_map: BusyMap) -> int:
    """Count how many participants have NO busy block overlapping this slot."""
    free = 0
    for busy_blocks in busy_map.values():
        if not any(_overlaps(slot, b) for b in busy_blocks):
            free += 1
    return free


def _morning_score(slot: Slot) -> int:
    """
    Award points for slots that fall within the preferred morning window
    (09:00 – 12:00 local hour of the slot start).
    """
    hour = slot["start"].hour
    if 9 <= hour < 10:
        return 20
    if 10 <= hour < 11:
        return 18
    if 11 <= hour < 12:
        return 14
    if 8 <= hour < 9:
        return 8      # early but acceptable
    if 12 <= hour < 14:
        return 6      # just after lunch
    return 0


def _earliness_score(slot: Slot, search_start: datetime.datetime, search_end: datetime.datetime) -> int:
    """
    20 pts for the earliest possible slot, 0 for the latest.
    Linear interpolation across the search window.
    """
    total_seconds = (search_end - search_start).total_seconds()
    if total_seconds <= 0:
        return 20
    offset = (slot["start"] - search_start).total_seconds()
    ratio  = max(0.0, min(1.0, offset / total_seconds))
    return round(20 * (1 - ratio))


def _gap_score(slot: Slot) -> int:
    """
    10 pts if the slot starts within 24 hours (urgent scheduling),
    scaled down linearly to 0 pts at 7 days.
    """
    now     = datetime.datetime.utcnow()
    hours   = (slot["start"] - now).total_seconds() / 3600
    if hours < 0:
        return 0
    if hours <= 24:
        return 10
    if hours >= 168:   # 7 days
        return 0
    return round(10 * (1 - (hours - 24) / 144))


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

def generate_candidate_slots(
    start: datetime.datetime,
    end: datetime.datetime,
    duration_minutes: int,
    step_minutes: int = 30,
) -> List[Slot]:
    """
    Generate every possible slot of `duration_minutes` length between
    `start` and `end`, advancing by `step_minutes` each time.
    """
    slots   = []
    current = start
    delta   = datetime.timedelta(minutes=duration_minutes)
    step    = datetime.timedelta(minutes=step_minutes)

    while current + delta <= end:
        slots.append({"start": current, "end": current + delta})
        current += step

    return slots


def rank_slots(
    candidate_slots: List[Slot],
    busy_map: BusyMap,
    total_participants: int,
    search_start: datetime.datetime,
    search_end: datetime.datetime,
    is_priority: bool = False,
) -> List[Dict]:
    """
    Score and rank all candidate slots. Returns a sorted list (best first) of:
      {start, end, score, free_count, total_participants, all_free}
    Only slots where at least one participant is free are returned.
    """
    results = []

    for slot in candidate_slots:
        free_count = _count_free_participants(slot, busy_map)

        if free_count == 0:
            continue   # no point suggesting a slot nobody is free for

        # ── Scoring ──────────────────────────────────────────────────────
        overlap_score  = round(40 * (free_count / total_participants)) if total_participants else 0
        morning_score  = _morning_score(slot)
        earliness      = _earliness_score(slot, search_start, search_end)
        gap            = _gap_score(slot)
        priority_bonus = 10 if is_priority else 0

        total_score = overlap_score + morning_score + earliness + gap + priority_bonus
        total_score = min(100, total_score)   # cap at 100

        results.append({
            "start":              slot["start"],
            "end":                slot["end"],
            "score":              total_score,
            "free_count":         free_count,
            "total_participants": total_participants,
            "all_free":           free_count == total_participants,
        })

    # Best score first; ties broken by earliest start
    results.sort(key=lambda s: (-s["score"], s["start"]))
    return results