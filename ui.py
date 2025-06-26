import streamlit as st
import requests
import json
import os
import pandas as pd

# If you want to call your Flask service:
FLASK_URL = os.getenv("FLASK_URL", "http://localhost:5000/schedule")

st.title("🩺 Nurse Roster Scheduler")

st.markdown("Configure your nurse pool and soft-rule parameters, then hit **Generate**.")

# 1. Date range
col1, col2 = st.columns(2)
start_date = col1.date_input("Start date")
end_date   = col2.date_input("End date")

# 2. Soft-rules
min_am_pct    = st.slider("Min AM coverage (%)", 0, 100, 60)
weekly_hours  = st.number_input("Target weekly hours per nurse", min_value=0, max_value=80, value=40)
pref_weight   = st.selectbox("Shift preference importance", ["low", "medium", "high"], index=1)

# 3. Nurse counts input
st.markdown("### Nurse Pool Configuration")
num_seniors = st.number_input("Number of Senior Nurses", min_value=0, value=2, step=1)
num_juniors = st.number_input("Number of Junior Nurses", min_value=0, value=3, step=1)

# 4. Optional preferences template
st.markdown("### Default Preferences")
st.info("All nurses default to no specific shift preference and no MC days.")

# 5. On-click: call the API
if st.button("Generate Schedule"):
    # Generate nurse list programmatically
    nurses = []
    for i in range(num_seniors):
        nurses.append({
            "name": f"S{i:02d}",  # e.g., S00, S01
            "senior": True,
            "shift_pref": "none",
            "mc_days": []
        })
    for i in range(num_juniors):
        nurses.append({
            "name": f"J{i:02d}",  # e.g., J00, J01
            "senior": False,
            "shift_pref": "none",
            "mc_days": []
        })


    payload = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "min_am_pct": min_am_pct,
        "weekly_hours": weekly_hours,
        "pref_weight": pref_weight,
        "nurses": nurses,
    }
    with st.spinner("Calling scheduler…"):
        try:
            resp = requests.post(FLASK_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            st.error(f"Request failed: {e}")
        else:
            if data.get("error"):
                st.error(data["error"])
            else:
                # 6. Display schedule
                schedule = data["schedule"]
                st.success("✅ Schedule generated!")
                df = pd.DataFrame(schedule)
                pivot = df.pivot(index="nurse", columns="date", values="shift")

                # Sort nurses: seniors first, then juniors
                senior_names = [n["name"] for n in nurses if n["senior"]]
                junior_names = [n["name"] for n in nurses if not n["senior"]]
                nurse_order = senior_names + junior_names
                pivot = pivot.reindex(nurse_order)

                pivot = pivot.reindex(sorted(pivot.columns), axis=1)
                st.dataframe(pivot.fillna(""))

                # info
                relaxed_note = data.get("relaxed_constraints", "No relaxation")
                st.info(f"Relaxation Level Used: {relaxed_note}")
