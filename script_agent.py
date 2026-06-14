"""AI Director Agent — generates complete scripts with scene-by-scene image prompts."""

import json
import requests
import urllib3
import config

urllib3.disable_warnings()

SYSTEM_PROMPT = """你是专业导演兼编剧。用户给你故事概念，你写出可以直接拍摄/配音的完整剧本。

关键要求：写的是「剧本」，不是「故事大纲」。每个场景必须展开为完整的叙述文本，不能只是概括。

输出格式：完整 JSON，包裹在 ```json 中。

```json
{
  "title": "剧本标题",
  "genre": "题材",
  "characters": [
    {"name":"角色名","description":"详细外观性格描述","image_prompt":"English AI image prompt, 9:16 vertical portrait, photorealistic cinematic"}
  ],
  "scenes": [
    {
      "index": 0,
      "title": "场景标题",
      "narration": "丰富的第三人称旁白——描述环境、动作、神态、氛围。不要概括，要写出可以让配音演员直接朗读的完整段落。至少150字。",
      "dialogue": [{"character":"角色名","line":"完整台词——不是短语，是人物真正会说的句子"}],
      "image_prompt": "English AI image prompt, 16:9 widescreen cinematic scene"
    }
  ]
}
```

硬性要求：
- 每个场景 narration 至少 150 个中文字，写具体画面和动作，不是概括
- 每句 dialogue 是完整句子，体现人物性格和剧情推进
- 一个短剧至少 4-8 个场景，有起承转合
- image_prompt 必须英文，描述具体画面而非抽象概念
- 旁白是核心——这是后续配音的基础，要写得像有声小说

工作方式：
- 第一轮：用 1-2 句话确认用户想要的故事类型和场景数量，然后立刻出剧本
- 不要写 summary/大纲字段，那不是剧本
- 直接输出 JSON，输出后说「剧本完成」"""


class ScriptAgent:
    def __init__(self, api_key=None):
        self.api_key = api_key or config.API_KEY
        self.base_url = config.API_BASE_URL.rstrip("/")
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]

    def _api(self, stream=False):
        body = {
            "model": "gpt-5",
            "messages": self.history,
            "max_tokens": 16000,
            "temperature": 0.8,
            "stream": stream,
        }
        return requests.post(
            f"{self.base_url}/v1/chat/completions",
            json=body,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=(15, 180),
            verify=False,
            stream=stream,
            proxies={"http": None, "https": None},
        )

    def chat_stream(self, user_message):
        self.history.append({"role": "user", "content": user_message})
        if len(self.history) > 20:
            self.history = [self.history[0]] + self.history[-19:]
        resp = self._api(stream=True)
        resp.raise_for_status()
        full = []
        for line in resp.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8", errors="replace")
            if line.startswith("data: "):
                ds = line[6:]
                if ds.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(ds)
                    content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    if content:
                        full.append(content)
                        yield content
                except json.JSONDecodeError:
                    pass
        self.history.append({"role": "assistant", "content": "".join(full)})

    @staticmethod
    def extract_json(text):
        import re
        results = []
        for m in re.finditer(r'```json\s*(.*?)\s*```', text, re.DOTALL):
            try:
                data = json.loads(m.group(1))
                results.append(data)
            except json.JSONDecodeError:
                pass
        return results

    def reset(self):
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]

    def set_context(self, ctx):
        self.history.append({"role": "user",
            "content": f"[当前剧本] {json.dumps(ctx, indent=2, ensure_ascii=False)}"})
