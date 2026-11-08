import os
import subprocess

APP_VERSION = "2.8.2"
RELEASE_DATE = "2026-11-08"
RELEASE_CODENAME = "Category Hygiene & UI Polish"

_BULAN_ID = (
    "",
    "Januari",
    "Februari",
    "Maret",
    "April",
    "Mei",
    "Juni",
    "Juli",
    "Agustus",
    "September",
    "Oktober",
    "November",
    "Desember",
)


def _format_release_date_id(iso_date: str) -> str:
    try:
        y, m, d = [int(p) for p in str(iso_date)[:10].split("-")]
        if 1 <= m <= 12:
            return f"{d} {_BULAN_ID[m]} {y}"
    except Exception:
        pass
    return iso_date


def _detect_build_sha() -> str:
    env_sha = (
        os.environ.get("VERCEL_GIT_COMMIT_SHA")
        or os.environ.get("GIT_COMMIT_SHA")
        or os.environ.get("RENDER_GIT_COMMIT")
        or ""
    ).strip()
    if env_sha:
        return env_sha[:7]
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            stderr=subprocess.DEVNULL,
            timeout=1.5,
        )
        sha = out.decode("utf-8", errors="ignore").strip()
        if sha:
            return sha[:7]
    except Exception:
        pass
    return "stable"


BUILD_SHA = _detect_build_sha()


def get_version_info() -> dict:
    return {
        "version": APP_VERSION,
        "build": BUILD_SHA,
        "release_date": RELEASE_DATE,
        "release_date_id": _format_release_date_id(RELEASE_DATE),
        "codename": RELEASE_CODENAME,
        "display": f"v{APP_VERSION}",
        "full_display": f"v{APP_VERSION} ({BUILD_SHA})",
    }
