"""Script data model — structured representation of a storytelling script."""

import json
import os
import time
import config

SCRIPTS_DIR = os.path.join(config.BASE_DIR, "scripts")
os.makedirs(SCRIPTS_DIR, exist_ok=True)


class Script:
    """A complete script with characters, scenes, and production assets."""

    def __init__(self, title="", data=None):
        if data:
            self._d = data
        else:
            self._d = {
                "id": f"script_{int(time.time())}",
                "title": title,
                "genre": "",
                "style": "",
                "summary": "",
                "created_at": int(time.time()),
                "updated_at": int(time.time()),
                "characters": [],
                "props": [],
                "scenes": [],
            }

    # ---- properties ----
    @property
    def id(self): return self._d["id"]
    @property
    def title(self): return self._d["title"]
    @title.setter
    def title(self, v): self._d["title"] = v
    @property
    def characters(self): return self._d.get("characters", [])
    @property
    def scenes(self): return self._d.get("scenes", [])
    @property
    def props(self): return self._d.get("props", [])

    def to_dict(self):
        self._d["updated_at"] = int(time.time())
        return self._d

    def save(self):
        self._d["updated_at"] = int(time.time())
        path = os.path.join(SCRIPTS_DIR, f"{self.id}.json")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._d, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
        return path

    @staticmethod
    def load(script_id):
        path = os.path.join(SCRIPTS_DIR, f"{script_id}.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return Script(data=json.load(f))
        return None

    @staticmethod
    def list_all():
        scripts = []
        for f in sorted(os.listdir(SCRIPTS_DIR), reverse=True):
            if f.endswith(".json"):
                path = os.path.join(SCRIPTS_DIR, f)
                try:
                    with open(path, "r", encoding="utf-8") as fp:
                        d = json.load(fp)
                    scripts.append({
                        "id": d.get("id", f.replace(".json", "")),
                        "title": d.get("title", ""),
                        "genre": d.get("genre", ""),
                        "scenes": len(d.get("scenes", [])),
                        "characters": len(d.get("characters", [])),
                        "updated_at": d.get("updated_at", 0),
                    })
                except Exception:
                    pass
        return scripts

    # ---- helpers ----
    def add_character(self, name, description="", voice=""):
        char = {"name": name, "description": description, "voice": voice, "image_url": "", "image_path": ""}
        self._d["characters"].append(char)
        return char

    def add_prop(self, name, description="", image_url=""):
        prop = {"name": name, "description": description, "image_url": image_url, "image_path": ""}
        self._d.setdefault("props", []).append(prop)
        return prop

    def add_scene(self, title="", narration="", dialogue=None, image_prompt=""):
        scene = {
            "index": len(self._d["scenes"]),
            "title": title,
            "narration": narration,
            "dialogue": dialogue or [],
            "image_prompt": image_prompt,
            "image_url": "",
            "image_path": "",
            "audio_path": "",
            "ambient_sound": "",
        }
        self._d["scenes"].append(scene)
        return scene

    def update_scene(self, index, **kwargs):
        for s in self._d["scenes"]:
            if s["index"] == index:
                s.update(kwargs)
                return s
        return None


def create_script(title=""):
    return Script(title=title)
