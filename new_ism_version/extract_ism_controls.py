import argparse
import json
import re
import zipfile
from datetime import datetime, timezone
from io import BytesIO
import requests
import pathlib

BASE_DIR = pathlib.Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "data" / "ism_controls"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CONTROL_ID_RE = re.compile(r"^ism-(\d{4})$", re.I)

REPO = "AustralianCyberSecurityCentre/ism-oscal"
GITHUB_API = f"https://api.github.com/repos/{REPO}"


def get_release(version=None):
    if version:
        version = version if version.startswith("v") else f"v{version}"
        url = f"{GITHUB_API}/releases/tags/{version}"
    else:
        url = f"{GITHUB_API}/releases/latest"

    response = requests.get(url, timeout=30)
    response.raise_for_status()

    return response.json()

def get_all_releases():
    url = f"{GITHUB_API}/releases"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()

def get_catalog_from_release(release):
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

    return data["catalog"]


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


def make_row(control, path, release, metadata, downloaded_at):
    control_id = control.get("id", "")
    match = CONTROL_ID_RE.match(control_id)

    return {
        "downloadedAt": downloaded_at,

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


def extract_controls(catalog, release, metadata, downloaded_at):
    group_stack = [(group, []) for group in catalog.get("groups", [])]
    ism_controls = []

    while group_stack:
        group, path = group_stack.pop()

        title = group.get("title")
        new_path = path + ([title] if title else [])

        for control in group.get("controls", []):
            control_id = control.get("id", "")
            control_class = control.get("class", "")

            if control_class == "ISM-control" or CONTROL_ID_RE.match(control_id):
                ism_controls.append(
                    make_row(
                        control=control,
                        path=new_path,
                        release=release,
                        metadata=metadata,
                        downloaded_at=downloaded_at,
                    )
                )

        children = group.get("groups", [])

        for child in children:
            group_stack.append((child, new_path))

    ism_controls.sort(key=lambda row: row["numericId"] or 0)

    return ism_controls


def write_jsonl(rows, output_path):
    with open(output_path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    downloaded_at = datetime.now(timezone.utc).isoformat()

    releases = get_all_releases()

    for release in releases:
        catalog = get_catalog_from_release(release)
        metadata = catalog.get("metadata", {})

        print("Release:", release.get("tag_name"))
        print("Catalog version:", metadata.get("version"))
        print("Catalog published:", metadata.get("published"))

        ism_controls = extract_controls(
            catalog=catalog,
            release=release,
            metadata=metadata,
            downloaded_at=downloaded_at,
        )

        write_jsonl(ism_controls, OUTPUT_DIR / f"ism_controls_{metadata.get("version")}.jsonl")

        print("Controls extracted:", len(ism_controls))


if __name__ == "__main__":
    main()