import pandas as pd

def make_schedule_table(schedule, nurses):
    df = pd.DataFrame(schedule)
    pivot = df.pivot(index="nurse", columns="date", values="shift")
    # Sort nurses: seniors first, then juniors
    senior_names = [n["name"] for n in nurses if n["senior"]]
    junior_names = [n["name"] for n in nurses if not n["senior"]]
    nurse_order = senior_names + junior_names
    pivot = pivot.reindex(nurse_order)
    pivot = pivot.reindex(sorted(pivot.columns), axis=1)
    return pivot


def nurse_summary_table(schedule, nurses):
    # Build lookup for preferences and MC days (just count for MC)
    nurse_prefs = {n["name"]: n.get("shift_pref", "none") for n in nurses}
    nurse_mc_count = {n["name"]: len(n.get("mc_days", [])) for n in nurses}

    # Determine total days and number of complete weeks
    all_dates = sorted({e["date"] for e in schedule})
    num_days = len(all_dates)
    num_complete_weeks = num_days // 7

    # Prepare summary rows
    summary = []
    for nurse in nurse_prefs:
        entries = [e for e in schedule if e["nurse"] == nurse]
        counts = {"AM": 0, "PM": 0, "Night": 0, "REST": 0, "MC": 0}
        met, unmet, unmet_details = 0, 0, []
        pref = nurse_prefs[nurse]

        # Build DataFrame for this nurse's entries
        df = pd.DataFrame(entries)
        week_hours = {}
        if not df.empty:
            df = df.sort_values("date")
            df["date"] = pd.to_datetime(df["date"])
            # Assign week number (1-based)
            df["week"] = ((df["date"] - df["date"].min()).dt.days // 7) + 1
            shift_hours = {"AM": 7, "PM": 7, "Night": 10, "REST": 0, "MC": 0}
            df["hours"] = df["shift"].map(shift_hours)
            for w in range(1, num_complete_weeks + 1):
                week_df = df[df["week"] == w]
                if len(week_df) == 7:
                    week_hours[w] = week_df["hours"].sum()
                else:
                    week_hours[w] = ""
        # Count shifts and preferences
        for e in entries:
            shift = e["shift"]
            counts[shift] = counts.get(shift, 0) + 1
            if shift == pref:
                met += 1
            elif shift not in ("REST", "MC") and pref != "none":
                unmet += 1
                unmet_details.append(f"{e['date']}→{shift}")
        row = {
            "Nurse": nurse,
            "MC": counts["MC"],
            "AM": counts["AM"],
            "PM": counts["PM"],
            "Night": counts["Night"],
            "REST": counts["REST"],
        }
        # Insert week columns here (between REST and Pref met)
        for w in range(1, num_complete_weeks + 1):
            row[f"Week {w} hours"] = week_hours.get(w, "")
        # Continue with the rest of the columns
        row.update({
            "Pref met": met,
            "Pref unmet": unmet,
            "Unmet details": "; ".join(unmet_details)
        })
        summary.append(row)
    return pd.DataFrame(summary)