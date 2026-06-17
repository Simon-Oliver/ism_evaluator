import difflib
import json
from pathlib import Path

BASE_DIR = Path(__file__).parent
DIR_PATH = BASE_DIR / "data" / "ism_controls"

files = [f for f in DIR_PATH.iterdir() if f.is_file()]
files.sort()  # Ensure files are in a consistent order
latest = files[-1]
current = [f for f in files if f.name == "ism_controls_2025.12.9.jsonl"][0]

with open(latest, "r") as f:
    latest_data = [json.loads(line) for line in f]

with open(current, "r") as f:
    current_data = [json.loads(line) for line in f]

latest_data_by_id = {control["controlId"]: control for control in latest_data}
current_data_by_id = {control["controlId"]: control for control in current_data}

latest_controls = {control["controlId"]: control for control in latest_data}
current_controls = {control["controlId"]: control for control in current_data}

deleted_controls = [control_id for control_id in current_controls if control_id not in latest_controls]
added_controls = [control_id for control_id in latest_controls if control_id not in current_controls]
changed_controls = []

common_controls = set(latest_controls) & set(current_controls)
changed_controls_output_string = ""

for control_id in sorted(common_controls):
    current_control = current_data_by_id[control_id]
    latest_control = latest_data_by_id[control_id]

    matcher = difflib.SequenceMatcher(None, current_control["statement"], latest_control["statement"])
    similarity = matcher.ratio()
    if similarity < 1:  # Only consider it changed if there's an actual difference
        changed_controls_output_string += f"""
{'=' * 40}
{control_id} | Similarity: {similarity:.2%}
{'=' * 40}
Current:
  {current_control['statement']}

Latest:
  {latest_control['statement']}
"""
        changed_controls.append(control_id)

print(f"""
ISM Control Version Comparison
==============================
Current file: {current.name}
Latest file:  {latest.name}

Deleted controls ({len(deleted_controls)})
--------------------
{chr(10).join(f"  - {control_id}" for control_id in sorted(deleted_controls)) or "  None"}

Added controls ({len(added_controls)})
------------------
{chr(10).join(f"  - {control_id}" for control_id in sorted(added_controls)) or "  None"}

Changed controls ({len(changed_controls)})
---------------------
{changed_controls_output_string or "  None"}
""")
