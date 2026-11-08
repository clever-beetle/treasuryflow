import os
import subprocess

APP_VERSION = "2.8.1"
RELEASE_DATE = "2026-11-08"
RELEASE_CODENAME = "Precision & Speed"


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
        "codename": RELEASE_CODENAME,
        "display": f"v{APP_VERSION}",
        "full_display": f"v{APP_VERSION} ({BUILD_SHA})",
    }
