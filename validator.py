# validator.py
from datetime import datetime, timedelta
from collections import defaultdict
import logging

def validate_schedule(schedule: list, user_inputs: dict) -> None:
    """
    Raises ValueError if any hard rule is violated.
    """
    # If schedule is a list of lists, convert to dicts for compatibility
    if schedule and isinstance(schedule[0], list):
        schedule = [
            {"nurse": n, "date": d, "shift": s}
            for n, d, s in schedule
        ]
    # Map nurse->list of (date, shift)
    assignments = {}
    # Track weekly hours per nurse
    hours_per_week = {}
    # Define **working** shift hours
    SHIFT_HOURS = {"AM": 7, "PM": 7, "Night": 10}

    schedule_start = datetime.fromisoformat(user_inputs["start_date"]).date()
    schedule_end = datetime.fromisoformat(user_inputs["end_date"]).date()

    # Helper to parse date
    def parse(d: str) -> datetime:
        try:
            return datetime.fromisoformat(d)
        except Exception:
            raise ValueError(f"Invalid date in schedule: {d}")

    # Build assignments and schedule_by_nurse
    schedule_by_nurse = defaultdict(list)
    for entry in schedule:
        nurse = entry["nurse"]
        date = entry["date"]
        shift = entry["shift"]
        dt = parse(date)
        # MC day check
        for n in user_inputs.get("nurses", []):
            if n["name"] == nurse and date in n.get("mc_days", []):
                if shift != "MC":
                    raise ValueError(f"Scheduled on MC day: {nurse} on {date}")
        # One shift per day
        key = (nurse, date)
        if key in assignments:
            raise ValueError(f"Multiple shifts for {nurse} on {date}")
        assignments[key] = shift
        # Hours tally
        week_num = ((dt.date() - schedule_start).days // 7) + 1
        week_key = (nurse, week_num)
        hours_per_week[week_key] = hours_per_week.get(week_key, 0) + SHIFT_HOURS.get(shift, 0)
        # Build schedule_by_nurse for REST check
        schedule_by_nurse[nurse].append(shift.upper())

    # Weekly hour cap (only for full weeks)
    for (nurse, week), hrs in hours_per_week.items():
        # Count number of days scheduled for this nurse in this week
        days_in_week = sum(
            1 for entry in schedule
            if entry["nurse"] == nurse and
               ((parse(entry["date"]).date() - schedule_start).days // 7) + 1 == week
        )
        if days_in_week == 7:
            if hrs >= 48:
                logging.warning(f"{nurse} exceeds 42h in full week of {week}: {hrs}h")

    # Coverage per day/shift
    cover = defaultdict(list)  # (date, shift) -> [nurse,...]
    seniors = set(n["name"] for n in user_inputs.get("nurses", []) if n.get("senior"))
    for (nurse, date), shift in assignments.items():
        if shift in SHIFT_HOURS:
            cover[(date, shift)].append(nurse)
    for (date, shift), nurses in cover.items():
        if len(nurses) < 4:
            logging.warning(f"Understaffed {shift} on {date}: {len(nurses)} nurses")
        if not any(n in seniors for n in nurses):
            logging.warning(f"No senior on {shift} {date}")

    # Weekend rest rule
    for (nurse, date), shift in assignments.items():
        dt = parse(date)
        if dt.weekday() >= 5:
            next_week = dt + timedelta(days=7)
            rest_key = (nurse, next_week.date())
            if rest_key in assignments:
                logging.warning(f"Weekend rest violation: {nurse} works {date} and {next_week.date()}")

    # No nurse may be assigned REST for all days
    num_days = (datetime.fromisoformat(user_inputs["end_date"]).date() -
                datetime.fromisoformat(user_inputs["start_date"]).date()).days + 1
    for nurse, shifts in schedule_by_nurse.items():
        if all(s == "REST" for s in shifts):
            logging.warning(f"Nurse {nurse} has REST for all {num_days} days")
        

    # After building schedule_by_nurse and hours_per_week
    for nurse, shifts in schedule_by_nurse.items():
        # Check for >2 consecutive REST days
        rest_streak = 0
        for s in shifts:
            if s == "REST":
                rest_streak += 1
                if rest_streak > 2:
                    logging.warning(f"{nurse} has more than 2 consecutive REST days")
            else:
                rest_streak = 0

    # At least 1 REST per week
    for (nurse, week), hrs in hours_per_week.items():
        # Find all shifts for this nurse/week
        week_shifts = [
            entry["shift"].upper()
            for entry in schedule
            if entry["nurse"] == nurse and
            ((parse(entry["date"]).date() - schedule_start).days // 7) + 1 == week
        ]
        if "REST" not in week_shifts:
            logging.warning(f"{nurse} has no REST day in week of {week}")
        

    # For each nurse, check Night → AM
    for nurse, shifts in schedule_by_nurse.items():
        for i in range(len(shifts) - 1):
            if shifts[i] == "NIGHT" and shifts[i + 1] == "AM":
                logging.warning(f"{nurse} has Night followed by AM on day {i+2}")
                