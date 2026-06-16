import json
import re
import zipfile
from datetime import datetime, timezone
from io import BytesIO

import requests

CONTROL_ID_RE = re.compile(r"^ism-(\d{4})$", re.I)

url = "https://api.github.com/repos/AustralianCyberSecurityCentre/ism-oscal/releases/latest"

response = requests.get(url, timeout=30)
response.raise_for_status()

release = response.json()

zip_url = release["zipball_url"]

zip_response = requests.get(zip_url, timeout=30)
zip_response.raise_for_status()

with zipfile.ZipFile(BytesIO(zip_response.content), "r") as archive:
    names = archive.namelist()

    catalog_name = next(
        name for name in names
        if name.endswith("/ISM_catalog.json")
    )

    with archive.open(catalog_name) as f:
        data = json.load(f)

catalog = data.get("catalog")
metadata = catalog.get("metadata", {})

print("Release:", release["tag_name"])
print("Catalog version:", metadata.get("version"))
print("Catalog published:", metadata.get("published"))


def get_prop(control, name):
    for prop in control.get("props", []):
        if prop.get("name") == name:
            return prop.get("value")
    return None


def get_props(control, name):
    values = []

    for prop in control.get("props", []):
        if prop.get("name") == name:
            values.append(prop.get("value"))

    return values


def get_part(control, name):
    for part in control.get("parts", []):
        if part.get("name") == name:
            return part.get("prose")
    return None


def make_row(control, path):
    control_id = control.get("id", "")
    match = CONTROL_ID_RE.match(control_id)

    return {
        "downloadedAt": datetime.now(timezone.utc).isoformat(),

        "sourceRelease": release.get("tag_name"),
        "catalogVersion": metadata.get("version"),
        "catalogPublished": metadata.get("published"),
        "oscalVersion": metadata.get("oscal-version"),

        "controlId": control_id.upper(),
        "controlIdRaw": control_id,
        "numericId": int(match.group(1)) if match else None,
        "title": control.get("title"),
        "statement": get_part(control, "statement"),

        "guideline": path[0] if path else None,
        "topic": path[-1] if path else None,
        "sectionPath": path,

        "applicability": get_props(control, "applicability"),
        "revision": get_prop(control, "revision"),
        "updated": get_prop(control, "updated"),
        "sortId": get_prop(control, "sort-id"),
    }


group_stack = [(group, []) for group in catalog.get("groups", [])]
print("Group stack:", len(group_stack))

ism_controls = []

while group_stack:
    group, path = group_stack.pop()

    title = group.get("title")
    new_path = path + ([title] if title else [])

    for control in group.get("controls", []):
        control_id = control.get("id", "")
        control_class = control.get("class", "")

        if control_class == "ISM-control" or CONTROL_ID_RE.match(control_id):
            ism_controls.append(make_row(control, new_path))

    children = group.get("groups", [])

    for child in children:
        group_stack.append((child, new_path))


ism_controls.sort(key=lambda row: row["NumericId"] or 0)

with open("ism_controls.jsonl", "w", encoding="utf-8") as f:
    for control in ism_controls:
        f.write(json.dumps(control, ensure_ascii=False) + "\n")

print("Controls extracted:", len(ism_controls))
print("Wrote: ism_controls.jsonl")