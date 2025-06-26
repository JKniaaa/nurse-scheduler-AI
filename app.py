# app.py
from flask import Flask, request, jsonify
import os
import traceback
from dotenv import load_dotenv
import json
import logging
from datetime import datetime

logging.basicConfig(
    filename="backend.log",
    filemode="w",
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s"
)

# Load environment variables
load_dotenv()

# Imports
from prompts import build_prompt
from llm_client import call_llm
from validator import validate_schedule

app = Flask(__name__)

@app.route("/schedule", methods=["POST"])
def schedule():
    try:
        user_inputs = request.get_json()
        if not user_inputs:
            return jsonify({"error": "Invalid or missing JSON payload"}), 400
        
        try:
            # parse whatever was sent (e.g. “2025-6-26”), then re-serialize correctly
            sd = datetime.fromisoformat(user_inputs["start_date"]).date()
            ed = datetime.fromisoformat(user_inputs["end_date"]).date()
            user_inputs["start_date"] = sd.isoformat()
            user_inputs["end_date"]   = ed.isoformat()
        except Exception as e:
            return jsonify({"error": f"Invalid date format: {e}"}), 400

        # === Soft Constraint Relaxation Stages ===
        relaxations = [
            {"note": "Strict (no relaxation)", "append": ""},
            {"note": "Ignore shift preferences", "append": "\nYou may ignore nurse shift preferences if needed."},
            {"note": "Relax AM shift % if needed", "append": "\nYou may relax AM shift % if needed."},
            {"note": "Relax weekly hour targets", "append": "\nYou may relax weekly target hours if needed."},
            {"note": "Relax any 2 soft rules", "append": "\nYou may relax any 2 soft rules above."},
            {"note": "Relax all soft rules", "append": "\nYou may relax all soft rules if necessary."},
        ]

        last_error = None

        for stage in relaxations:
            # Build prompt with current relaxation
            prompt = build_prompt(user_inputs) + stage["append"]
            logging.info(f"\n=== Attempt: {stage['note']} ===")

            try:
                result = call_llm(prompt)
                schedule = result.get("s") or result.get("schedule")
                if not schedule:
                    raise ValueError("Missing 'schedule' in LLM response")

                # DEBUG
                # logging.info("[LLM OUTPUT]")
                # logging.info(json.dumps(schedule, indent=2))

                # Try validating the schedule
                validate_schedule(schedule, user_inputs)

                # If valid, return result with relaxation info
                return jsonify({
                    "schedule": schedule,
                    "relaxed_constraints": stage["note"]
                }), 200

            except RuntimeError as rte:
                if "rate limit" in str(rte).lower():
                    return jsonify({
                        "error": str(rte)
                    }), 429
                else:
                    raise
            except ValueError as ve:
                last_error = str(ve)
                logging.info(f"[VALIDATION ERROR] {last_error}")
                continue
            except Exception as e:
                logging.info(f"[LLM ERROR] {str(e)}")
                traceback.print_exc()
                return jsonify({"error": f"LLM failure: {str(e)}"}), 500

        # All attempts failed
        return jsonify({
            "error": f"All attempts failed. Last validation error: {last_error}",
            "relaxed_constraints": "All soft constraints attempted"
        }), 422

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
