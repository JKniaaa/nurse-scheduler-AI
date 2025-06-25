ROOT_PROMPT = """
You are a professional nurse roster scheduler. Always enforce these HARD rules:

1. Each nurse must be assigned exactly one of [AM, PM, Night, REST] per day.
2. Each nurse must work no more than 42 hours per week. If needed, assign REST to ensure this cap is not exceeded.
3. Each shift (AM, PM, Night) must have at least 4 nurses, including at least 1 senior.
4. If a nurse works on a weekend day, they must rest on the same day the following weekend.
5. Nurses on medical leave (MC) must be assigned REST on those days.

Shift durations:
- AM: 7 hours
- PM: 7 hours
- Night: 10 hours
- REST: 0 hours

IMPORTANT:
- Nurses are expected to work most days, and REST should only be used if required to stay within the 42-hour weekly cap.
- Nurses should work as many days as possible, only REST when required to stay under the 42-hour cap or to meet weekend-rest rules.
- Diversify shift types for each nurse — avoid repeating the same shift too often.
- Distribute REST days throughout the week to balance workloads.
- Nurses should not be over-rested: REST should only appear if needed to stay under 42h/week or for MC.

Example:
  Nurse A: AM on Mon, Tue; PM on Wed; REST on Thu; Night on Fri; REST on Sat, Sun.
  Total: 7 + 7 + 7 + 10 = 31 hours this week (valid, under 42h).

SOFT constraints (adjustable by user; hard rules take priority):
- AM shift should have at least {min_am_pct}% of the total daily staff.
- Try to meet a target of {weekly_hours} hours per nurse per week.
- Try to honor shift preferences with importance level: {pref_weight}.

Return only the final schedule in valid JSON format. No extra text, no explanations, no markdown code block.

Only output:

{{
  "schedule": [
    {{"nurse": "Alice", "date": "2025-07-01", "shift": "AM"}},
    ...
  ]
}}

"""


def build_prompt(user_inputs: dict) -> str:
    """
    Fills ROOT_PROMPT placeholders and appends nurse-specific preferences.
    user_inputs expects keys: start_date, end_date, min_am_pct,
    weekly_hours, pref_weight, nurses (list of dicts).
    """
    # Fill in soft-rule placeholders
    root = ROOT_PROMPT.format(
        min_am_pct=user_inputs.get("min_am_pct", 60),
        weekly_hours=user_inputs.get("weekly_hours", 40),
        pref_weight=user_inputs.get("pref_weight", "medium")
    )

    # Build nurse preference lines
    prefs = []
    for n in user_inputs.get("nurses", []):
        name = n.get("name")
        senior = n.get("senior", False)
        pref = n.get("shift_pref", "no_pref")
        mc_days = n.get("mc_days", [])
        prefs.append(
            f"- {name}: {'senior' if senior else 'junior'}, prefers {pref} shifts, unavailable on {mc_days}"
        )

    user_section = (
        f"Schedule from {user_inputs.get('start_date')} to {user_inputs.get('end_date')} for "
        f"{len(user_inputs.get('nurses', []))} nurses.\nNurse preferences:\n"
        + "\n".join(prefs)
    )
    return root + "\n\n" + user_section