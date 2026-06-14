import os
import time
import base64
import config


class ImageService:
    """Synchronous image generation via gpt-image-2 (POST /v1/images/generations)."""

    # Preset size mappings
    SIZES = {
        "1:1": "1024x1024",
        "4:3": "1536x1152",
        "3:2": "1536x1024",
        "2:3": "1024x1536",
        "16:9": "1920x1080",
        "9:16": "1080x1920",
    }

    _OPTIONAL_FIELDS = [
        "n", "image", "response_format", "quality", "style", "background", "watermark",
    ]

    def __init__(self, client):
        self._client = client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, prompt, size=None, response_format="url", **kwargs):
        """
        Generate images synchronously.

        Parameters
        ----------
        prompt : str
            Image generation prompt.
        size : str
            Either a preset key like ``"16:9"`` or a raw size like ``"1920x1080"``.
            Presets: 1:1 / 4:3 / 3:2 / 2:3 / 16:9 / 9:16.
        response_format : str
            ``"url"`` (default) or ``"b64_json"``.
        n : int, optional
            Number of images (default 1).
        image : str | list[str] | object, optional
            Reference image input (Base64 or Base64 array).
        quality, style, background, watermark : optional
            Forwarded to upstream as-is.

        Returns
        -------
        dict with keys ``created`` and ``data`` (list of image objects).
        """
        body = {
            "model": "gpt-image-2",
            "prompt": prompt,
            "size": self._resolve_size(size),
            "response_format": response_format,
        }
        for field in self._OPTIONAL_FIELDS:
            value = kwargs.get(field)
            if value is not None:
                body[field] = value

        return self._client._post("/v1/images/generations", body)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def generate_urls(self, prompt, size=None, n=1, **kwargs):
        """Generate images and return a list of URL strings."""
        result = self.generate(prompt, size=size, response_format="url", n=n, **kwargs)
        return [item["url"] for item in result.get("data", [])]

    def generate_b64(self, prompt, size=None, n=1, **kwargs):
        """Generate images and return a list of base64 strings."""
        result = self.generate(prompt, size=size, response_format="b64_json", n=n, **kwargs)
        return [item["b64_json"] for item in result.get("data", [])]

    def generate_and_save(self, prompt, size=None, save_dir=None, **kwargs):
        """
        Generate images (url format) and save them to local disk.

        Returns list of absolute file paths.
        """
        urls = self.generate_urls(prompt, size=size, **kwargs)
        if save_dir is None:
            save_dir = config.IMAGE_DIR
        os.makedirs(save_dir, exist_ok=True)

        paths = []
        for i, url in enumerate(urls):
            ext = ".png"
            filename = f"image_{int(time.time())}_{i}{ext}"
            save_path = os.path.join(save_dir, filename)
            self._client.download_file(url, save_path)
            paths.append(os.path.abspath(save_path))
        return paths

    @classmethod
    def _resolve_size(cls, size):
        """Resolve a preset key (e.g. '16:9') to actual dimensions, or pass through."""
        if size is None:
            return "1024x1024"
        return cls.SIZES.get(size, size)
