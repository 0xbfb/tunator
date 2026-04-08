from __future__ import annotations

from pathlib import Path

SUPPORTED_TORRC_OPTIONS = {
    "SOCKSPort",
    "ControlPort",
    "DataDirectory",
    "Log",
    "ExcludeNodes",
    "HiddenServiceDir",
    "HiddenServicePort",
}

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent
LOCAL_TOR_ROOT = BACKEND_ROOT / "vendor" / "tor"
LOCAL_TOR_ARCHIVES_DIR = LOCAL_TOR_ROOT / "archives"
LOCAL_TOR_RUNTIME_DIR = LOCAL_TOR_ROOT / "runtime"
LOCAL_TOR_STATE_DIR = LOCAL_TOR_ROOT / "state"
LOCAL_TOR_DATA_DIR = LOCAL_TOR_STATE_DIR / "data"
LOCAL_TOR_LOG_DIR = LOCAL_TOR_STATE_DIR / "logs"
LOCAL_TOR_TORRC_PATH = LOCAL_TOR_STATE_DIR / "torrc"
LOCAL_TOR_MANIFEST_PATH = LOCAL_TOR_ROOT / "manifest.json"

DEFAULT_LOG_CANDIDATES = [
    str(LOCAL_TOR_LOG_DIR / "notices.log"),
]

DEFAULT_TORRC_CANDIDATES = [
    str(LOCAL_TOR_TORRC_PATH),
]

LOCAL_TOR_ONIONS_DIR = LOCAL_TOR_STATE_DIR / "onions"
