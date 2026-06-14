import time
import config


class AssetService:
    """Create and query Seedance-2 assets (images, videos, audio)."""

    def __init__(self, client):
        self._client = client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create(self, url, name=None, asset_type="image"):
        """
        Register a public URL as an asset.

        Parameters
        ----------
        url : str
            Publicly accessible URL of the asset file.
        name : str, optional
            Human-readable name (e.g. "product.png").
        asset_type : str
            One of ``"image"``, ``"video"``, ``"audio"``.

        Returns
        -------
        dict with keys Id, Name, URL, AssetType, Status.
        """
        body = {"url": url, "assetType": asset_type}
        if name:
            body["name"] = name
        result = self._client._post("/api/asset/createMedia", body)
        return result.get("Result", result)

    def get(self, asset_id):
        """
        Query asset status by raw asset ID (no ``asset://`` prefix).

        Returns dict with keys Id, Name, URL, AssetType, Status.
        """
        result = self._client._get("/api/asset/get", params={"id": asset_id})
        return result.get("Result", result)

    def wait_active(self, asset_id, interval=None, max_retries=None):
        """
        Block until the asset reaches ``Active`` status.

        Raises RuntimeError if the asset enters ``Failed``.
        Raises TimeoutError if the asset does not become active in time.
        """
        interval = interval or config.POLL_INTERVAL
        max_retries = max_retries or config.POLL_MAX_RETRIES

        for _ in range(max_retries):
            info = self.get(asset_id)
            status = info.get("Status", "")
            if status == "Active":
                return info
            if status == "Failed":
                raise RuntimeError(f"Asset {asset_id} processing failed: {info}")
            time.sleep(interval)

        raise TimeoutError(
            f"Asset {asset_id} still not Active after {max_retries * interval}s"
        )

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    @staticmethod
    def to_ref(asset_id):
        """Convert a raw asset ID to the ``asset://`` reference form."""
        return f"asset://{asset_id}"

    @staticmethod
    def from_ref(ref):
        """Strip the ``asset://`` prefix from a reference URI."""
        return ref.replace("asset://", "")
