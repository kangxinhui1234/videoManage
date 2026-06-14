import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import config

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _build_session():
    s = requests.Session()
    s.verify = False
    s.trust_env = False  # skip system proxy (broken proxy causes Connection aborted)
    # Retry on read/connect timeouts and 5xx errors
    retry = Retry(
        total=2,
        backoff_factor=0.5,
        status_forcelist=[502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


class BaseClient:
    """HTTP client with Bearer auth + automatic retry."""

    def __init__(self, api_key=None, base_url=None):
        self.api_key = api_key or config.API_KEY
        if not self.api_key:
            raise ValueError(
                "API key is required. Set SEEDANCE_API_KEY env var or pass api_key="
            )
        self.base_url = (base_url or config.API_BASE_URL).rstrip("/")
        self.session = _build_session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        })
        self.session.proxies = {"http": None, "https": None}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _post(self, path, data=None):
        url = f"{self.base_url}{path}"
        # connect=15s, read=180s (long for image/video gen)
        resp = self.session.post(url, json=data, timeout=(15, 180))
        return self._parse_response(resp, url)

    def _get(self, path, params=None):
        url = f"{self.base_url}{path}"
        resp = self.session.get(url, params=params, timeout=(15, 30))
        return self._parse_response(resp, url)

    @staticmethod
    def _parse_response(resp, url):
        if not resp.ok:
            raise RuntimeError(
                f"{resp.status_code} {resp.reason} for {url}\n"
                f"{resp.text[:500]}"
            )
        if not resp.text or not resp.text.strip():
            return {}
        try:
            return resp.json()
        except Exception:
            return {"_raw": resp.text}

    # ------------------------------------------------------------------
    # File download (public URL, no auth)
    # ------------------------------------------------------------------

    def download_file(self, url, save_path):
        """Download from a public URL to a local path."""
        resp = requests.get(url, stream=True, timeout=(15, 300), verify=False, proxies={"http": None, "https": None})
        resp.raise_for_status()
        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return save_path
