"""
Meeting Service
===============
Orchestrates multi-participant availability comparison by:
  1. Looking up each participant's Google Calendar credentials in the DB
  2. Fetching their busy blocks via the FreeBusy API
  3. Generating candidate slots and ranking them
"""

import datetime
from typing import List, Dict, Tuple

from sqlalchemy.orm import Session

from app.users.models import User
from app.calendar.service import get_calendar_service, fetch_busy_blocks
from app.meetings.ranking import generate_candidate_slots, rank_slots


def get_availability_and_rank(
    db: Session,
    participant_emails: List[str],
    duration_minutes: int,
    search_start: datetime.datetime,
    search_end: datetime.datetime,
    is_priority: bool = False,
    max_slots: int = 10,
) -> Tuple[List[Dict], List[str]]:
    """
    Core scheduling logic.

    Returns:
        ranked_slots  — top N ranked slot dicts (start, end, score, …)
        warnings      — list of human-readable warning strings
    """
    busy_map: Dict = {}
    warnings: List[str] = []

    for email in participant_emails:
        user = db.query(User).filter(User.email == email).first()

        # ── Participant not registered / not connected to Google ──────────
        if not user or not user.access_token:
            warnings.append(
                f"{email} is not registered or has not connected Google Calendar. "
                "Their availability could not be checked."
            )
            # Treat as always free (empty busy list) so they don't block all slots
            busy_map[email] = []
            continue

        # ── Fetch busy blocks from Google ─────────────────────────────────
        try:
            service, _ = get_calendar_service(
                access_token=user.access_token,
                refresh_token=user.refresh_token,
                token_expiry=user.token_expiry,
            )
            busy_map[email] = fetch_busy_blocks(service, search_start, search_end)
        except Exception as exc:
            warnings.append(f"Could not fetch calendar for {email}: {str(exc)}")
            busy_map[email] = []

    # ── Generate and rank candidates ──────────────────────────────────────
    candidates    = generate_candidate_slots(search_start, search_end, duration_minutes)
    ranked        = rank_slots(
        candidate_slots    = candidates,
        busy_map           = busy_map,
        total_participants = len(participant_emails),
        search_start       = search_start,
        search_end         = search_end,
        is_priority        = is_priority,
    )

    return ranked[:max_slots], warnings