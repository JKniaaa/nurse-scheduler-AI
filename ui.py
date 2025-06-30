import streamlit as st
import requests
import json
import os
import pandas as pd
from utils.button import excel_download_button
from utils.tables import make_schedule_table, nurse_summary_table

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
snr_min_am_pct    = st.slider("Senior Min AM coverage (%)", 0, 100, 60)
weekly_hours  = st.number_input("Target weekly hours per nurse", min_value=0, max_value=80, value=40)
pref_weight   = st.selectbox("Shift preference importance", ["low", "medium", "high"], index=1)

# 3. Nurse counts input
st.markdown("### Nurse Pool Configuration")
num_seniors = st.number_input("Number of Senior Nurses", min_value=0, value=15, step=1)
num_juniors = st.number_input("Number of Junior Nurses", min_value=0, value=10, step=1)

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
        "snr_min_am_pct": snr_min_am_pct,
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
                if not schedule:
                    st.error("No schedule returned.")
                    st.stop()
                
                 # --- FIX: convert if needed ---
                if schedule and isinstance(schedule[0], list):
                    schedule = [
                        {"nurse": n, "date": d, "shift": s}
                        for n, d, s in schedule
                    ]
                st.success("✅ Schedule generated!")
                pivot = make_schedule_table(schedule, nurses)
                st.dataframe(pivot.fillna(""))

                summary_df = nurse_summary_table(schedule, nurses)
                st.markdown("### Nurse Assignment Summary")
                st.dataframe(summary_df)

                # summary table
                excel_download_button(
                    pivot.reset_index(),  # nurse names as first column
                    filename="nurse_schedule.xlsx",
                    label="Download schedule as Excel"
                )

                excel_download_button(
                    summary_df,
                    filename="nurse_summary.xlsx",
                    label="Download summary as Excel"
                )

                # info
                relaxed_note = data.get("relaxed_constraints", "No relaxation")
                st.info(f"Relaxation Level Used: {relaxed_note}")
