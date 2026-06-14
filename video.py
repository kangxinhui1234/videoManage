import os
import time
import config


class VideoService:
    """Create, poll, and download video generation tasks (Seedance-2 / Sora)."""

    # Fields accepted by POST /v1/videos beyond model + prompt.
    # Seedance: duration, aspect_ratio, first_image, reference_*, generate_audio
    # Sora:     size, seconds, input_reference, image, images, metadata
    _OPTIONAL_FIELDS = [
        # Seedance
        "duration", "aspect_ratio", "ratio",
        "first_image", "first_frame_url",
        "last_image", "last_frame_url",
        "reference_images", "reference_image_urls",
        "reference_videos", "reference_video_urls",
        "reference_audios", "audio_url",
        "generate_audio",
        # Sora
        "size", "seconds",
        "input_reference", "image", "images",
        "metadata",
    ]

    def __init__(self, client):
        self._client = client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create(self, model, prompt, **kwargs):
        """
        Submit a video generation task.

        Parameters
        ----------
        model : str
            Seedance: seedance-2.0-lite / pro / fast.
            Sora: sora-2 / sora-2-pro.
        prompt : str
            Generation prompt.
        duration : int, optional (Seedance)
            Video length in seconds (>= 1).
        aspect_ratio : str, optional (Seedance)
            16:9 / 9:16 / 1:1 / 4:3 / 3:4 / 21:9 / adaptive.
        first_image : str, optional (Seedance)
            First-frame image URL or asset:// reference.
        reference_images : list[str], optional (Seedance)
            Reference image URLs / asset refs.
        generate_audio : bool, optional (Seedance)
            Enable audio generation.
        size : str, optional (Sora)
            720x1280 / 1280x720 / 1792x1024 / 1024x1792.
        seconds : str | int, optional (Sora)
            Video seconds, typically 4 / 8 / 12.
        input_reference : str | list[str], optional (Sora)
            Reference image URL / base64 / data URI.
        image : str, optional (Sora compatible)
            Compatibility reference image field.

        Returns
        -------
        dict with keys id, status, model, created, …
        """
        body = {"model": model, "prompt": prompt}
        for field in self._OPTIONAL_FIELDS:
            value = kwargs.get(field)
            if value is not None:
                body[field] = value
        return self._client._post("/v1/videos", body)

    def get(self, task_id):
        """
        Query video task status.

        Returns dict with keys id, status, video_url (when completed), error, …
        """
        return self._client._get(f"/v1/videos/{task_id}")

    def wait_completed(self, task_id, interval=None, max_retries=None):
        """
        Block until the video task reaches ``completed``.

        Raises RuntimeError if the task enters ``failed``.
        Raises TimeoutError if the task does not complete in time.

        Returns the full task dict (includes ``video_url``).
        """
        interval = interval or config.POLL_INTERVAL
        max_retries = max_retries or config.POLL_MAX_RETRIES

        for _ in range(max_retries):
            info = self.get(task_id)
            status = info.get("status", "")
            if status == "completed":
                return info
            if status == "failed":
                raise RuntimeError(
                    f"Video task {task_id} failed: {info.get('error', 'unknown')}"
                )
            time.sleep(interval)

        raise TimeoutError(
            f"Video task {task_id} still not completed after {max_retries * interval}s"
        )

    def download(self, video_url, save_path=None):
        """
        Download the generated video to local disk.

        Returns a server-relative URL path (e.g. /output/videos/video_xxx.mp4).
        """
        if not save_path:
            filename = f"video_{int(time.time())}.mp4"
            save_path = os.path.join(config.VIDEO_DIR, filename)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        self._client.download_file(video_url, save_path)
        # Return relative URL from project root, not absolute OS path
        rel = os.path.relpath(save_path, config.BASE_DIR)
        return "/" + rel.replace("\\", "/")

    # ------------------------------------------------------------------
    # High-level convenience
    # ------------------------------------------------------------------

    def run_and_download(self, model, prompt, save_path=None, **kwargs):
        """
        Create a task, block until it finishes, then download the result.

        Returns ``(task_dict, local_path)``.
        """
        created = self.create(model, prompt, **kwargs)
        task_id = created.get("id")
        if not task_id:
            raise RuntimeError(f"No task id in response: {created}")

        completed = self.wait_completed(task_id)
        video_url = completed.get("video_url")
        if not video_url:
            raise RuntimeError(f"Task {task_id} completed but no video_url returned")

        local_path = self.download(video_url, save_path)
        return completed, local_path
