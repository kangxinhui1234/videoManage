"""
FastAPI web app — AI image & video generation studio.
Run:  python server.py
"""

import os, sys, time, base64, json, threading, subprocess
from pathlib import Path

from typing import List
from fastapi import FastAPI, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from seedance import SeedanceClient   # noqa: E402
from task_store import store          # noqa: E402
from tts import cosy_speak, VOICES  # noqa: E402
from script_agent import ScriptAgent                # noqa: E402
from script_model import Script, create_script       # noqa: E402

# ═══════════════════════════════════════════════════════
# Setup
# ═══════════════════════════════════════════════════════

app = FastAPI(title="AI Studio")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

for _d in [BASE_DIR / "uploads", BASE_DIR / "output"]:
    _d.mkdir(exist_ok=True)

app.mount("/uploads", StaticFiles(directory=str(BASE_DIR / "uploads")), name="uploads")
app.mount("/output",  StaticFiles(directory=str(BASE_DIR / "output")),  name="output")
app.mount("/audio",   StaticFiles(directory=str(BASE_DIR / "output" / "audio")), name="audio")
app.mount("/scripts", StaticFiles(directory=str(BASE_DIR / "scripts")), name="scripts")

client = None  # lazy init — set SEEDANCE_API_KEY env var first


def get_client():
    global client
    if client is None:
        client = SeedanceClient()
    return client

IMAGE_MODELS  = ["gpt-image-2"]
VIDEO_MODELS  = {
    "kling-3.0-omni-1080p-ref-audio":   "可灵 3.0 (1080p + 参考图 + 音频)",
    "kling-3.0-omni-1080p-noref-audio": "可灵 3.0 (1080p + 音频，无参考图)",
    "kling-3.0-720p-audio":             "可灵 3.0 (720p + 音频，无参考图)",
    "Kling-3.0-Omni":                   "可灵 3.0 Omni (参考图，无音频 mute)",
    "Kling-2.6":                         "可灵 2.6 (参考图，无音频 mute)",
    "Kling-2.0":                         "可灵 2.0 (参考图，无音频 mute)",
    "Kling-1.6":                         "可灵 1.6 (参考图，无音频 mute)",
    "Vidu-q2-pro":                       "Vidu Q2 Pro",
    "GV-3.1-fast":                       "GV 3.1 Fast",
    "sora-2":                            "Sora 2",
    "sora-2-pro":                        "Sora 2 Pro",
}
# (value, label) — label shows aspect ratio + orientation
SIZE_PRESETS = [
    ("1280x720",   "1280x720 (16:9 横屏)"),
    ("720x1280",   "720x1280 (9:16 竖屏)"),
    ("1920x1080",  "1920x1080 (16:9 横屏)"),
    ("1080x1920",  "1080x1920 (9:16 竖屏)"),
    ("720x720",    "720x720 (1:1 方形)"),
]
SECONDS_OPTIONS = ["4", "5", "6", "8", "10", "12", "15"]
# Image sizes
ASPECT_RATIOS = {
    "1:1": "1024x1024", "3:2": "1536x1024", "4:3": "1536x1152",
    "2:3": "1024x1536", "16:9": "1920x1080", "9:16": "1080x1920",
}

# ═══════════════════════════════════════════════════════
# Background video poller
# ═══════════════════════════════════════════════════════

def _poll_video_tasks():
    while True:
        time.sleep(5)
        c = globals().get("client")
        if c is None:
            continue
        try:
            for t in store.list_all("video"):
                if t.get("status") in ("queued", "in_progress"):
                    try:
                        info = c.videos.get(t["id"])
                        s = info.get("status", t["status"])
                        upd = {"status": s}
                        if s == "completed":
                            vurl = info.get("video_url")
                            upd["video_url"] = vurl
                            if vurl:
                                try:
                                    upd["local_path"] = c.videos.download(vurl)
                                except Exception:
                                    pass
                        elif s == "failed":
                            upd["error"] = info.get("error", "unknown")
                        store.update(t["id"], upd)
                    except Exception:
                        pass
        except Exception:
            pass

_poller = threading.Thread(target=_poll_video_tasks, daemon=True)
_poller.start()

# ═══════════════════════════════════════════════════════
# Page routes
# ═══════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def index():
    return RedirectResponse("/image")

@app.get("/image", response_class=HTMLResponse)
async def page_image(req: Request):
    return templates.TemplateResponse("image.html", {
        "request": req,
        "models": IMAGE_MODELS,
        "ratios": ASPECT_RATIOS,
    })

@app.get("/video", response_class=HTMLResponse)
async def page_video(req: Request):
    recent_images = [t for t in store.list_all("image") if t.get("local_path")][:12]
    return templates.TemplateResponse("video.html", {
        "request": req,
        "models": VIDEO_MODELS,
        "sizes": SIZE_PRESETS,
        "seconds_options": SECONDS_OPTIONS,
        "recent_images": recent_images,
    })

@app.get("/edit", response_class=HTMLResponse)
async def page_edit(req: Request):
    recent_images = [t for t in store.list_all("image") if t.get("local_path")][:12]
    return templates.TemplateResponse("edit.html", {
        "request": req,
        "models": IMAGE_MODELS,
        "ratios": ASPECT_RATIOS,
        "recent_images": recent_images,
    })

@app.get("/tasks", response_class=HTMLResponse)
async def page_tasks(req: Request):
    return templates.TemplateResponse("tasks.html", {"request": req})

# ═══════════════════════════════════════════════════════
# API — Image generation
# ═══════════════════════════════════════════════════════

@app.post("/api/image/generate")
async def api_image_generate(
    model: str = Form("gpt-image-2"),
    prompt: str = Form(...),
    size: str = Form("1:1"),
    n: int = Form(1),
    ref_urls: str = Form(""),
):
    try:
        c = get_client()
        # Build kwargs with optional reference images
        kwargs = {}
        if ref_urls.strip():
            refs = [u.strip() for u in ref_urls.split(",") if u.strip()]
            if refs:
                kwargs["image"] = refs if len(refs) > 1 else refs[0]
        result = c.images.generate(prompt, size=size, n=n, **kwargs)
        urls = [d["url"] for d in result.get("data", [])]
        paths = []
        for i, url in enumerate(urls):
            try:
                ext = ".png"
                filename = f"img_{int(time.time())}_{i}{ext}"
                save_path = str(BASE_DIR / "output" / "images" / filename)
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                c.images._client.download_file(url, save_path)
                paths.append("/output/images/" + filename)
            except Exception:
                paths.append(url)  # fallback: keep URL

        task = store.make_task("image", f"img_{int(time.time())}",
                               model=model, prompt=prompt, size=size,
                               urls=urls, local_path=paths[0] if paths else "")
        store.add(task)

        return JSONResponse({"success": True, "urls": urls, "local_paths": paths})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

# ═══════════════════════════════════════════════════════
# API — Image editing (reference-based generation)
# ═══════════════════════════════════════════════════════

@app.post("/api/image/edit")
async def api_image_edit(
    prompt: str = Form(...),
    size: str = Form("1:1"),
    image_url: str = Form(""),
    image_file: UploadFile = File(None),
):
    try:
        ref_image = None
        if image_file and image_file.filename:
            data = await image_file.read()
            ref_image = base64.b64encode(data).decode("utf-8")
        elif image_url.strip():
            ref_image = image_url.strip()

        kwargs = {}
        if ref_image:
            kwargs["image"] = ref_image

        c = get_client()
        result = c.images.generate(prompt, size=size, response_format="url", **kwargs)
        urls = [d["url"] for d in result.get("data", [])]
        paths = []
        for i, url in enumerate(urls):
            try:
                filename = f"edit_{int(time.time())}_{i}.png"
                save_path = str(BASE_DIR / "output" / "images" / filename)
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                c.images._client.download_file(url, save_path)
                paths.append("/output/images/" + filename)
            except Exception:
                paths.append(url)

        task = store.make_task("image", f"edit_{int(time.time())}",
                               model="gpt-image-2", prompt=prompt, size=size,
                               urls=urls, local_path=paths[0] if paths else "",
                               edit_mode=True)
        store.add(task)

        return JSONResponse({"success": True, "urls": urls, "local_paths": paths})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

# ═══════════════════════════════════════════════════════
# API — Video generation
# ═══════════════════════════════════════════════════════

@app.post("/api/video/create")
async def api_video_create(
    model: str = Form("sora-2-pro"),
    prompt: str = Form(...),
    seconds: str = Form("5"),
    size: str = Form("1280x720"),
    generate_audio: bool = Form(False),
    # optional URLs
    image_url: str = Form(""),
    ref_urls: str = Form(""),
    # multi-file upload
    ref_files: List[UploadFile] = File([]),
):
    try:
        is_sora = model.startswith("sora-")
        kwargs = {
            "seconds": seconds.strip(),
            "size": size.strip(),
        }
        # Sora natively generates audio for text-to-video; sending generate_audio
        # triggers a different pipeline (generate action) that breaks audio.
        if generate_audio and not is_sora:
            kwargs["generate_audio"] = True

        # --- collect reference images ---
        ref_list = []
        for f in ref_files:
            if f.filename:
                data = await f.read()
                mime = f.content_type or "image/png"
                b64 = base64.b64encode(data).decode("utf-8")
                ref_list.append(f"data:{mime};base64,{b64}")
        if ref_urls.strip():
            ref_list.extend(u.strip() for u in ref_urls.split(",") if u.strip())
        elif image_url.strip():
            ref_list.append(image_url.strip())

        # send refs via correct field per model
        is_sora = model.startswith("sora-")
        if ref_list:
            if is_sora:
                # Sora uses input_reference, supports base64 data URIs natively
                kwargs["input_reference"] = ref_list if len(ref_list) > 1 else ref_list[0]
            else:
                kwargs["reference_images"] = ref_list

        c = get_client()
        result = c.videos.create(model=model, prompt=prompt, **kwargs)
        task_id = result.get("id", "")
        task = store.make_task("video", task_id,
                               model=model, prompt=prompt,
                               status=result.get("status", "queued"),
                               ref_count=len(ref_list))
        store.add(task)
        return JSONResponse({"success": True, "task_id": task_id, "task": task})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/api/video/{task_id}")
async def api_video_status(task_id: str):
    task = store.get(task_id)
    if not task:
        # try live query
        try:
            info = get_client().videos.get(task_id)
            return JSONResponse(info)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=404)
    return JSONResponse(task)

@app.get("/api/tasks")
async def api_task_list(type: str = ""):
    tasks = store.list_all(task_type=type if type else None)
    return JSONResponse(tasks)

# ═══════════════════════════════════════════════════════
# Script workspace
# ═══════════════════════════════════════════════════════

agent = None

def _get_agent():
    global agent
    if agent is None:
        agent = ScriptAgent()
    return agent


@app.get("/produce", response_class=HTMLResponse)
async def page_produce(req: Request):
    return templates.TemplateResponse("produce.html", {"request": req})

@app.get("/script", response_class=HTMLResponse)
async def page_script(req: Request):
    return templates.TemplateResponse("script.html", {"request": req})


@app.post("/api/script/chat/stream")
async def api_script_chat_stream(req: Request):
    """Streaming chat with the script agent."""
    import asyncio

    body = await req.json()
    messages = body.get("messages", [])
    script_data = body.get("script")

    a = _get_agent()
    if script_data and messages:
        a.set_context({
            "title": script_data.get("title", ""),
            "genre": script_data.get("genre", ""),
            "summary": script_data.get("summary", ""),
            "characters": [
                {"name": c.get("name",""), "description": c.get("description",""),
                 "image_prompt": c.get("image_prompt",""), "image_path": c.get("image_path","")}
                for c in script_data.get("characters", [])
            ],
            "scenes": [
                {"index": s.get("index", i), "title": s.get("title", ""),
                 "narration": s.get("narration", ""),
                 "dialogue": s.get("dialogue", []),
                 "image_prompt": s.get("image_prompt",""), "image_path": s.get("image_path","")}
                for i, s in enumerate(script_data.get("scenes", []))
            ],
        })

    last_msg = messages[-1]["content"] if messages else "你好"

    async def generate():
        full_text = ""
        try:
            for chunk_text in a.chat_stream(last_msg):
                full_text += chunk_text
                yield f"data: {json.dumps({'token': chunk_text})}\n\n"
                # Let event loop breathe
                await asyncio.sleep(0)

            # Extract and send any JSON actions from complete response
            actions = a.extract_json(full_text)
            if actions:
                yield f"data: {json.dumps({'actions': actions})}\n\n"

            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/api/script/reset")
async def api_script_reset():
    global agent
    if agent:
        agent.reset()
    return JSONResponse({"success": True})


@app.post("/api/script/save")
async def api_script_save(req: Request):
    try:
        body = await req.json()
        s = Script(data=body)
        path = s.save()
        return JSONResponse({"success": True, "path": path, "id": s.id})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/script/load")
async def api_script_load(id: str = ""):
    s = Script.load(id)
    if s:
        return JSONResponse({"script": s.to_dict()})
    return JSONResponse({"error": "not found"}, status_code=404)


@app.get("/api/script/list")
async def api_script_list():
    scripts = Script.list_all()
    return JSONResponse({"scripts": scripts})


# ═══════════════════════════════════════════════════════
# Story / TTS / Export
# ═══════════════════════════════════════════════════════

@app.get("/story", response_class=HTMLResponse)
async def page_story(req: Request):
    recent_images = [t for t in store.list_all("image") if t.get("local_path")][:20]
    return templates.TemplateResponse("story.html", {
        "request": req,
        "voices": VOICES,
        "recent_images": recent_images,
    })

@app.get("/api/audio/list")
async def api_audio_list():
    """List generated audio files sorted by time (newest first)."""
    audio_dir = BASE_DIR / "output" / "audio"
    if not audio_dir.exists():
        return JSONResponse({"files": []})
    files = sorted(
        [f for f in audio_dir.glob("*.mp3")],
        key=lambda f: f.stat().st_mtime, reverse=True
    )
    return JSONResponse({
        "files": [{"path": "/output/audio/" + f.name, "name": f.name} for f in files[:50]]
    })

@app.get("/api/tts/chars")
async def api_tts_chars():
    """Return all character voice presets for the story page."""
    return JSONResponse(VOICES)

@app.post("/api/tts")
async def api_tts(
    text: str = Form(...),
    voice: str = Form("zh-CN-XiaoxiaoNeural"),
    rate: str = Form("+0%"),
    pitch: str = Form("+0Hz"),
    style: str = Form("general"),
    engine: str = Form("cosy"),
    speed: float = Form(1.0),
):
    try:
        import re
        text = re.sub(r'https?://\S+', '', text).strip()
        if not text:
            return JSONResponse({"success": False, "error": "文本为空（可能全部是URL）"}, status_code=400)
        if engine == "cosy":
            # Pass through — produce page already sends CosyVoice format
            path = cosy_speak(text, voice, speed=speed)
        else:
            path = await edge_speak(text, voice, rate=rate, pitch=pitch, style=style)
        return JSONResponse({"success": True, "path": path, "text": text[:100]})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.post("/api/story/export")
async def api_story_export(req: Request):
    """Export story scenes (image + audio) to a single MP4 video."""
    try:
        body = await req.json()
        scenes = body.get("scenes", [])
        if not scenes:
            return JSONResponse({"success": False, "error": "无场景数据"}, status_code=400)

        output_dir = BASE_DIR / "output" / "videos"
        output_dir.mkdir(parents=True, exist_ok=True)
        out_file = output_dir / f"story_{int(time.time())}.mp4"

        # Build concat file + temp segments
        concat_lines = []
        temp_files = []
        for i, s in enumerate(scenes):
            audio_path = BASE_DIR / s["audio"].lstrip("/") if s.get("audio") else None
            if not audio_path or not os.path.exists(audio_path):
                continue

            # find usable image: local path > remote download > black
            img_path = None
            local_img = s.get("imageLocal", "")
            remote_img = s.get("image", "")
            if local_img:
                p = BASE_DIR / local_img.lstrip("/")
                if p.exists():
                    img_path = p
            if not img_path and remote_img and remote_img.startswith("/output/"):
                p = BASE_DIR / remote_img.lstrip("/")
                if p.exists():
                    img_path = p
            if not img_path and remote_img and remote_img.startswith("http"):
                # try to find a local copy in output/images
                import requests as req
                try:
                    tmp_img = output_dir / f"_img_{i}_{int(time.time())}.png"
                    r = req.get(remote_img, timeout=30, verify=False, proxies={"http":None,"https":None})
                    if r.ok:
                        tmp_img.write_bytes(r.content)
                        img_path = tmp_img
                        temp_files.append(tmp_img)
                except Exception:
                    pass

            seg_file = output_dir / f"_seg_{i}_{int(time.time())}.mp4"
            temp_files.append(seg_file)

            if img_path and img_path.exists():
                cmd = [
                    "ffmpeg", "-y", "-loop", "1", "-i", str(img_path),
                    "-i", str(audio_path),
                    "-c:v", "libx264", "-tune", "stillimage",
                    "-c:a", "aac", "-b:a", "192k",
                    "-pix_fmt", "yuv420p", "-shortest",
                    "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
                    str(seg_file)
                ]
            else:
                # Audio only → black screen
                cmd = [
                    "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=1920x1080:d=9999",
                    "-i", str(audio_path),
                    "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
                    "-pix_fmt", "yuv420p", "-shortest",
                    str(seg_file)
                ]

            subprocess.run(cmd, capture_output=True, timeout=120)

            concat_lines.append(f"file '{seg_file.as_posix()}'")

        # Concatenate all segments
        concat_file = output_dir / f"_concat_{int(time.time())}.txt"
        with open(concat_file, "w") as f:
            f.write("\n".join(concat_lines))

        final_cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy", str(out_file)
        ]
        subprocess.run(final_cmd, capture_output=True, timeout=60)

        # Cleanup temp files
        if concat_file.exists():
            os.remove(concat_file)
        for tf in temp_files:
            if tf.exists():
                os.remove(tf)

        rel = "/" + os.path.relpath(out_file, BASE_DIR).replace("\\", "/")
        return JSONResponse({"success": True, "path": rel})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.post("/api/script/export")
async def api_script_export_ep(req: Request):
    """Export episode assets as ZIP: shots/characters/scenes organized in folders."""
    import zipfile, shutil
    body = await req.json()
    episode = body.get("episode", {})
    characters = body.get("characters", [])
    scenes_data = body.get("scenes", [])
    title = body.get("title", "episode")

    if not episode or not episode.get("shots"):
        return JSONResponse({"success": False, "error": "No episode data"}, status_code=400)

    ep_idx = episode.get("index", 1)
    ep_name = f"ep{ep_idx}_{title}"
    export_dir = BASE_DIR / "output" / "exports" / ep_name
    if export_dir.exists():
        shutil.rmtree(export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)

    # Write episode script as text
    script_txt = f"{title}\n{episode.get('title','')}\n\n"
    for s in episode.get("shots", []):
        script_txt += f"--- 分镜{s['index']+1}: {s.get('title','')} ---\n"
        script_txt += f"旁白: {s.get('narration','')}\n"
        for d in s.get("dialogue", []):
            script_txt += f"{d['character']}: {d['line']}\n"
        script_txt += f"生图提示词: {s.get('image_prompt','')}\n\n"
    (export_dir / "剧本.txt").write_text(script_txt, encoding="utf-8")

    # Export each shot
    shots_dir = export_dir / "shots"
    shots_dir.mkdir(exist_ok=True)
    for s in episode.get("shots", []):
        sn = f"{s['index']+1:02d}_{s.get('title','shot')}"
        sd = shots_dir / sn
        sd.mkdir(exist_ok=True)

        # Info
        info = {
            "title": s.get("title", ""),
            "narration": s.get("narration", ""),
            "dialogue": s.get("dialogue", []),
            "image_prompt": s.get("image_prompt", ""),
            "character": s.get("character", "旁白"),
            "scene": s.get("scene", ""),
            "characters_in_shot": s.get("characters_in_shot", []),
        }
        (sd / "info.json").write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")

        # Copy shot images (images array, ordered by index for editing)
        shot_imgs = s.get("images", [])
        for si_idx, si_img in enumerate(shot_imgs):
            img = si_img.get("image_path", "") or si_img.get("image_url", "")
            if img and img.startswith("/output/"):
                src = BASE_DIR / img.lstrip("/")
                if src.exists():
                    ext = src.suffix or ".png"
                    label = si_img.get("label", f"图{si_idx+1}")
                    safe_label = label.replace("/", "_").replace("\\", "_")
                    shutil.copy(src, sd / f"{si_idx+1:02d}_{safe_label}{ext}")
        # Fallback: single image_path on shot itself
        if not shot_imgs:
            img = s.get("image_path", "") or s.get("image_url", "")
            if img and img.startswith("/output/"):
                src = BASE_DIR / img.lstrip("/")
                if src.exists():
                    ext = src.suffix or ".png"
                    shutil.copy(src, sd / f"image{ext}")

        # Copy audio
        aud = s.get("audio_path", "")
        if aud and aud.startswith("/output/"):
            src = BASE_DIR / aud.lstrip("/")
            if src.exists():
                shutil.copy(src, sd / "audio.mp3")

    # Export characters
    if characters:
        cd = export_dir / "characters"
        cd.mkdir(exist_ok=True)
        for c in characters:
            img = c.get("image_path", "") or c.get("image_url", "")
            if img and img.startswith("/output/"):
                src = BASE_DIR / img.lstrip("/")
                if src.exists():
                    ext = src.suffix or ".png"
                    shutil.copy(src, cd / f"{c['name']}{ext}")
            (cd / f"{c.get('name','char')}.txt").write_text(
                f"角色: {c.get('name','')}\n描述: {c.get('description','')}\n生图提示词: {c.get('image_prompt','')}",
                encoding="utf-8"
            )

    # Export scenes
    if scenes_data:
        sd2 = export_dir / "scenes"
        sd2.mkdir(exist_ok=True)
        for sc in scenes_data:
            img = sc.get("image_path", "") or sc.get("image_url", "")
            if img and img.startswith("/output/"):
                src = BASE_DIR / img.lstrip("/")
                if src.exists():
                    ext = src.suffix or ".png"
                    shutil.copy(src, sd2 / f"{sc['name']}{ext}")

    # Zip
    zip_path = BASE_DIR / "output" / "exports" / f"{ep_name}.zip"
    shutil.make_archive(str(zip_path.with_suffix("")), "zip", export_dir)

    # Cleanup
    shutil.rmtree(export_dir)

    rel = "/" + os.path.relpath(zip_path, BASE_DIR).replace("\\", "/")
    return JSONResponse({"success": True, "path": rel})

# ═══════════════════════════════════════════════════════
# File upload helper
# ═══════════════════════════════════════════════════════

@app.post("/api/upload")
async def api_upload(file: UploadFile = File(...)):
    data = await file.read()
    filename = f"{int(time.time())}_{file.filename}"
    save_path = BASE_DIR / "uploads" / filename
    save_path.write_bytes(data)
    b64 = base64.b64encode(data).decode("utf-8")
    return JSONResponse({
        "success": True,
        "filename": filename,
        "url": f"/uploads/{filename}",
        "base64": b64,
        "size": len(data),
    })

# ═══════════════════════════════════════════════════════
# Startup
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    print("\n  AI Studio → http://localhost:8000\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
