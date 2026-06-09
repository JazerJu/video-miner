# coding=utf-8
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class SlideEntry:
    time: float
    image_path: str
    ocr_text: str = ""
    diagram_description: str = ""
    transcript: str = ""


@dataclass
class CodeSnapshot:
    time: float
    file_name: str = ""
    code: str = ""
    event: str = ""
    transcript: str = ""


@dataclass
class TerminalOutput:
    time: float
    text: str = ""
    transcript: str = ""


@dataclass
class VideoStructure:
    video_path: str
    duration: float = 0.0
    slides: list[SlideEntry] = field(default_factory=list)
    code_snapshots: list[CodeSnapshot] = field(default_factory=list)
    terminal_outputs: list[TerminalOutput] = field(default_factory=list)
    transcript: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, path: str):
        import json
        from pathlib import Path
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str) -> "VideoStructure":
        import json
        from pathlib import Path
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        data["slides"] = [SlideEntry(**s) for s in data.get("slides", [])]
        data["code_snapshots"] = [CodeSnapshot(**c) for c in data.get("code_snapshots", [])]
        data["terminal_outputs"] = [TerminalOutput(**t) for t in data.get("terminal_outputs", [])]
        return cls(**data)


def classify_scene(caption: str) -> str:
    caption_lower = caption.lower()
    code_kw = ["代码", "编辑器", "ide", "code", "editor", "vim", "vs code", "visual studio",
               "终端", "命令行", "terminal", "shell", "bash", "命令", "command"]
    slide_kw = ["幻灯片", "ppt", "slide", "标题", "标题页", "lecture", "标题栏"]
    terminal_kw = ["终端", "命令行", "terminal", "shell", "bash", "输出", "output",
                   "安装", "install", "编译", "compil"]

    if any(kw in caption_lower for kw in terminal_kw):
        return "terminal"
    if any(kw in caption_lower for kw in code_kw):
        return "code"
    if any(kw in caption_lower for kw in slide_kw):
        return "slide"
    return "other"
