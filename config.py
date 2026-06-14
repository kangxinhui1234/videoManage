import os

API_BASE_URL = "https://api.geeknow.ai"

# API Key — priority: env var > local file > empty
def _load_api_key():
    key = os.environ.get("SEEDANCE_API_KEY", "")
    if key:
        return key
    # read from local config file (not tracked by git)
    local_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".api_key")
    if os.path.exists(local_file):
        with open(local_file, "r") as f:
            key = f.read().strip()
            if key:
                return key
    return ""

API_KEY = _load_api_key()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
VIDEO_DIR = os.path.join(OUTPUT_DIR, "videos")
ASSET_DIR = os.path.join(OUTPUT_DIR, "assets")
IMAGE_DIR = os.path.join(OUTPUT_DIR, "images")

for _d in (OUTPUT_DIR, VIDEO_DIR, ASSET_DIR, IMAGE_DIR):
    os.makedirs(_d, exist_ok=True)

POLL_INTERVAL = 5       # seconds between status checks
POLL_MAX_RETRIES = 120  # max polling attempts (10 min at 5s interval)
