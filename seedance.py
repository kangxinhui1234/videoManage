"""
Seedance-2 video generation client.

Usage::

    from seedance import SeedanceClient

    client = SeedanceClient(api_key="sk-xxx")

    # --- create an asset from a public URL ---
    asset = client.assets.create("https://example.com/img.png", asset_type="image")
    client.assets.wait_active(asset["Id"])

    # --- generate a video ---
    task = client.videos.create(
        model="seedance-2.0-fast",
        prompt="A sunny beach with gentle waves",
        duration=5,
        aspect_ratio="16:9",
    )
    result = client.videos.wait_completed(task["id"])
    path = client.videos.download(result["video_url"])
    print(f"Saved to {path}")

    # --- or do everything in one call ---
    _, path = client.videos.run_and_download(
        model="seedance-2.0-pro",
        prompt="Product showcase video",
        first_image="asset://asset-xxx",
        duration=6,
    )
"""

from client import BaseClient
from asset import AssetService
from video import VideoService
from image import ImageService
import config


class SeedanceClient:
    """Unified entry point for the Seedance-2 + gpt-image-2 API."""

    def __init__(self, api_key=None, base_url=None):
        http = BaseClient(api_key=api_key, base_url=base_url)
        self.assets = AssetService(http)
        self.videos = VideoService(http)
        self.images = ImageService(http)
