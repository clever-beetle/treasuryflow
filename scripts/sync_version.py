"""
Utilitas sinkronisasi otomatis version.py dari riwayat commit Git.
Memastikan setiap pembaruan yang belum masuk ke _BASE_RELEASE_HISTORY
otomatis menaikkan nomor versi dan tercatat di version.py.
"""
import os
import re
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import version as ver_mod


def sync_version_file() -> str:
    state = ver_mod._resolve_version_state()
    current_ver = state["version"]
    if current_ver == ver_mod._BASE_VERSION:
        return current_ver

    ver_path = os.path.join(ROOT_DIR, "version.py")
    content = open(ver_path, "r", encoding="utf-8").read()
    content = re.sub(
        r'^_BASE_VERSION\s*=\s*"[^"]*"',
        f'_BASE_VERSION = "{state["version"]}"',
        content,
        count=1,
        flags=re.MULTILINE,
    )
    content = re.sub(
        r'^_BASE_RELEASE_DATE\s*=\s*"[^"]*"',
        f'_BASE_RELEASE_DATE = "{state["release_date"]}"',
        content,
        count=1,
        flags=re.MULTILINE,
    )
    content = re.sub(
        r'^_BASE_CODENAME\s*=\s*"[^"]*"',
        f'_BASE_CODENAME = "{state["codename"].replace(chr(34), chr(39))}"',
        content,
        count=1,
        flags=re.MULTILINE,
    )

    # Tambahkan entri baru yang belum ada di _BASE_RELEASE_HISTORY
    existing_versions = {item["version"] for item in ver_mod._BASE_RELEASE_HISTORY}
    new_entries = [item for item in state["history"] if item["version"] not in existing_versions]
    if new_entries:
        entries_str = ""
        for item in new_entries:
            title_escaped = item["title"].replace('"', "'")
            date_escaped = item["date_id"].replace('"', "'")
            hl_lines = ",\n".join(f'            "{h.replace(chr(34), chr(39))}"' for h in item.get("highlights", []))
            entries_str += (
                "    {\n"
                f'        "version": "{item["version"]}",\n'
                f'        "date_id": "{date_escaped}",\n'
                f'        "title": "{title_escaped}",\n'
                "        \"highlights\": [\n"
                f"{hl_lines},\n"
                "        ],\n"
                "    },\n"
            )
        content = content.replace(
            "_BASE_RELEASE_HISTORY = [\n",
            "_BASE_RELEASE_HISTORY = [\n" + entries_str,
            1,
        )

    with open(ver_path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return current_ver


if __name__ == "__main__":
    updated = sync_version_file()
    print(f"Synced version.py -> v{updated}")
