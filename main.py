"""
Seedance-2 video + gpt-image-2 image generation demo.

Set your API key before running:
    set SEEDANCE_API_KEY=sk-xxx   (Windows cmd)
    $env:SEEDANCE_API_KEY="sk-xxx" (PowerShell)
    export SEEDANCE_API_KEY="sk-xxx" (bash)
"""

from seedance import SeedanceClient


# ═══════════════════════════════════════════════════════════════
# Video demos (async: submit → poll → download)
# ═══════════════════════════════════════════════════════════════

def demo_text_to_video():
    """Pure text-to-video generation."""
    client = SeedanceClient()
    _, path = client.videos.run_and_download(
        model="seedance-2.0-fast",
        prompt="清晨海边，航拍镜头掠过浪花，阳光穿过薄雾",
        duration=5,
        aspect_ratio="16:9",
    )
    print(f"Video saved to: {path}")


def demo_first_frame_to_video():
    """Generate video from a static first-frame image."""
    client = SeedanceClient()

    asset = client.assets.create(
        url="https://example.com/assets/person-first-frame.png",
        name="first-frame.png",
        asset_type="image",
    )
    print(f"Asset created: {asset['Id']}")
    client.assets.wait_active(asset["Id"])

    task = client.videos.create(
        model="seedance-2.0-pro",
        prompt="让人物自然抬头，微笑，看向镜头",
        duration=6,
        aspect_ratio="9:16",
        first_image=client.assets.to_ref(asset["Id"]),
    )
    print(f"Video task created: {task['id']}")

    result = client.videos.wait_completed(task["id"])
    path = client.videos.download(result["video_url"])
    print(f"Video saved to: {path}")


def demo_with_references():
    """Generate video with multiple reference assets."""
    client = SeedanceClient()

    img = client.assets.create("https://example.com/product.png", asset_type="image")
    vid = client.assets.create("https://example.com/motion.mp4", asset_type="video")
    audio = client.assets.create("https://example.com/music.mp3", asset_type="audio")

    for a in [img, vid, audio]:
        client.assets.wait_active(a["Id"])

    _, path = client.videos.run_and_download(
        model="seedance-2.0-pro",
        prompt="参考产品图和镜头运动生成一条广告感短视频",
        duration=6,
        aspect_ratio="adaptive",
        reference_images=[client.assets.to_ref(img["Id"])],
        reference_videos=[client.assets.to_ref(vid["Id"])],
        reference_audios=[client.assets.to_ref(audio["Id"])],
        generate_audio=True,
    )
    print(f"Video saved to: {path}")


# ═══════════════════════════════════════════════════════════════
# Image demos (synchronous: return immediately)
# ═══════════════════════════════════════════════════════════════

def demo_text_to_image():
    """Text-to-image, save to local disk."""
    client = SeedanceClient()
    paths = client.images.generate_and_save(
        prompt="一只橘猫坐在窗台上，阳光透过白纱窗帘",
        size="1:1",
        n=1,
    )
    print(f"Image saved to: {paths[0]}")


def demo_image_urls():
    """Text-to-image, return URLs only."""
    client = SeedanceClient()
    urls = client.images.generate_urls(
        prompt="现代办公室，极简设计，柔和自然光",
        size="16:9",
        n=2,
    )
    for u in urls:
        print(f"Image URL: {u}")


def demo_image_b64():
    """Text-to-image, return base64 data."""
    client = SeedanceClient()
    b64_list = client.images.generate_b64(
        prompt="赛博朋克城市夜景，霓虹灯，雨",
        size="9:16",
        n=1,
    )
    print(f"Base64 length: {len(b64_list[0])}")


def demo_image_with_reference():
    """Text-to-image with a reference image (base64)."""
    client = SeedanceClient()

    # First generate a reference image
    ref_urls = client.images.generate_urls(
        prompt="浅蓝色渐变背景，干净简约",
        size="1:1",
    )
    # Then generate a variant using the reference
    result = client.images.generate(
        prompt="浅蓝色渐变背景，加上几何线条点缀",
        size="1:1",
        image=ref_urls[0],  # some channels accept a URL as reference
    )
    print(f"Generated with reference: {result['data'][0].get('url')}")


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    demos = {
        # video
        "text":          demo_text_to_video,
        "firstframe":    demo_first_frame_to_video,
        "reference":     demo_with_references,
        # image
        "img":           demo_text_to_image,
        "img-urls":      demo_image_urls,
        "img-b64":       demo_image_b64,
        "img-ref":       demo_image_with_reference,
    }

    if len(sys.argv) > 1:
        name = sys.argv[1]
        if name in demos:
            demos[name]()
        else:
            print(f"Unknown demo '{name}'. Choose: {', '.join(demos)}")
    else:
        print("Usage: python main.py <demo>")
        print(f"Available demos:")
        print("  Video:  text | firstframe | reference")
        print("  Image:  img | img-urls | img-b64 | img-ref")
