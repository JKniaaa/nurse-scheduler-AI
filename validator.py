from datetime import datetime, timedelta

def validate_schedule(schedule: list, user_inputs: dict) -> None:
    """
    Raises ValueError if any hard rule is violated.
    """
    # Map nurse->list of (date, shift)
    assignments = {}
    # Track weekly hours per nurse
    hours_per_week = {}
    # Define shift hours
    SHIFT_HOURS = {"AM": 8, "PM": 8, "Night": 8}

    # Helper to parse date
    def parse(d): return datetime.fromisoformat(d)

    # Build assignments
    for entry in schedule:
        nurse = entry["nurse"]
        date = entry["date"]
        shift = entry["shift"]
        dt = parse(date)
        # MC day check
        for n in user_inputs.get("nurses", []):
            if n["name"] == nurse and date in n.get("mc_days", []):
                raise ValueError(f"Scheduled on MC day: {nurse} on {date}")
        # One shift per day
        key = (nurse, date)
        if key in assignments:
            raise ValueError(f"Multiple shifts for {nurse} on {date}")
        assignments[key] = shift
        # Hours tally
        week_start = dt - timedelta(days=dt.weekday())
        week_key = (nurse, week_start.date())
        hours_per_week[week_key] = hours_per_week.get(week_key, 0) + SHIFT_HOURS.get(shift, 0)

    # Weekly hour cap
    for (nurse, week), hrs in hours_per_week.items():
        if hrs > 42:
            raise ValueError(f"{nurse} exceeds 42h in week of {week}: {hrs}h")

    # Coverage per day/shift
    from collections import defaultdict
    cover = defaultdict(list)  # (date, shift) -> [nurse,...]
    seniors = set(n["name"] for n in user_inputs.get("nurses", []) if n.get("senior"))
    for (nurse, date), shift in assignments.items():
        cover[(date, shift)].append(nurse)
    for (date, shift), nurses in cover.items():
        if len(nurses) < 4:
            raise ValueError(f"Understaffed {shift} on {date}: {len(nurses)} nurses")
        if not any(n in seniors for n in nurses):
            raise ValueError(f"No senior on {shift} {date}")

    # Weekend rest rule
    for (nurse, date), shift in assignments.items():
        dt = parse(date)
        if dt.weekday() >= 5:
            next_week = dt + timedelta(days=7)
            rest_key = (nurse, next_week.date())
            if rest_key in assignments:
                raise ValueError(f"Weekend rest violation: {nurse} works {date} and {next_week.date()}")
