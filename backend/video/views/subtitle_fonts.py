"""字幕字体：上传、列出、删除用户自己的字体文件，供首页「字幕样式」选用。

字体文件存放在 MEDIA_ROOT/fonts/。浏览器通过 /api/subtitle-fonts/file/<文件名> 取字体，
不依赖只在 DEBUG 下才有的 /media/ 静态服务。
字体名从文件自己的 name 表读取（TTF、OTF、WOFF），读不到时用文件名；WOFF2 要 brotli 解压，直接用文件名。
粗细、斜体从 OS/2 表读取，可变字体读 fvar 的 wght 轴范围，
这样同一字体的常规、粗体几个文件能被浏览器按字重正确挑选。
"""
import os
import re
import struct
import threading
import zlib
from urllib.parse import quote

from django.conf import settings
from django.http import FileResponse, JsonResponse
from django.views import View

FONT_DIR = os.path.join(settings.MEDIA_ROOT, "fonts")
MAX_FONT_BYTES = 60 * 1024 * 1024
SFNT_SIGNATURES = (b"\x00\x01\x00\x00", b"true", b"OTTO")
# 扩展名 -> (允许的文件头, CSS format(), Content-Type)
FONT_TYPES = {
    ".ttf": (SFNT_SIGNATURES, "truetype", "font/ttf"),
    ".otf": (SFNT_SIGNATURES, "opentype", "font/otf"),
    ".woff": ((b"wOFF",), "woff", "font/woff"),
    ".woff2": ((b"wOF2",), "woff2", "font/woff2"),
}
_PARSE_ERRORS = (OSError, ValueError, struct.error, zlib.error, UnicodeError)
_lock = threading.Lock()
_meta_cache = {}


def _read_tables(path, wanted):
    """Return {tag: bytes} for the wanted tables of a TTF/OTF/WOFF file. WOFF tables are inflated."""
    tables = {}
    with open(path, "rb") as f:
        signature = f.read(4)
        if signature == b"wOFF":
            f.seek(12)
            (num_tables,) = struct.unpack(">H", f.read(2))
            f.seek(44)
            entries = [struct.unpack(">4sIIII", f.read(20)) for _ in range(num_tables)]
            for tag, offset, comp_length, orig_length, _checksum in entries:
                name = tag.decode("latin-1")
                if name in wanted:
                    f.seek(offset)
                    data = f.read(comp_length)
                    tables[name] = zlib.decompress(data) if comp_length < orig_length else data
        elif signature in SFNT_SIGNATURES:
            (num_tables,) = struct.unpack(">H", f.read(2))
            f.seek(12)
            entries = [struct.unpack(">4sIII", f.read(16)) for _ in range(num_tables)]
            for tag, _checksum, offset, length in entries:
                name = tag.decode("latin-1")
                if name in wanted:
                    f.seek(offset)
                    tables[name] = f.read(length)
        else:
            raise ValueError("not a TTF, OTF or WOFF font")
    return tables


def _language_rank(platform, language):
    """name 表记录的语言优先级：简体中文、其他中文、美式英文，其余靠后。"""
    if platform == 3:
        if language == 0x0804:
            return 0
        if language == 0x1004:
            return 1
        if language in (0x0404, 0x0C04, 0x1404):
            return 2
        return 3 if language == 0x0409 else 4
    if platform == 1:
        return {33: 0, 19: 2, 0: 3}.get(language, 5)
    return 4


def _family_name(name_table):
    _format, count, string_offset = struct.unpack_from(">HHH", name_table, 0)
    candidates = []
    for i in range(count):
        platform, encoding, language, name_id, length, offset = struct.unpack_from(">HHHHHH", name_table, 6 + 12 * i)
        if name_id not in (1, 16):
            continue
        raw = name_table[string_offset + offset:string_offset + offset + length]
        # 只读 UTF-16 和 Mac Roman 记录；老字体里 GBK、Big5 等双字节编码的记录跳过，免得读出乱码
        if platform == 0 or (platform == 3 and encoding in (0, 1, 10)):
            text = raw.decode("utf-16-be", errors="replace")
        elif platform == 1 and encoding == 0:
            text = raw.decode("mac_roman", errors="replace")
        else:
            continue
        text = re.sub(r"[\x00-\x1f\x7f]", "", text).strip()[:100]
        if not text or "\ufffd" in text:
            continue
        rank = _language_rank(platform, language)
        # 有的字体在中文语言记录里填的是英文名：同一优先级下，真正写了中文的排前面
        english_in_chinese_slot = 1 if rank <= 2 and all(ord(ch) < 128 for ch in text) else 0
        # nameID 16 是排版族名，同一字体的各个字重共用；没有时才用 nameID 1
        candidates.append((0 if name_id == 16 else 1, rank, english_in_chinese_slot, i, text))
    return min(candidates)[-1] if candidates else ""


def _weight_and_style(tables):
    weight, style = "400", "normal"
    os2 = tables.get("OS/2", b"")
    if len(os2) >= 64:
        (weight_class,) = struct.unpack_from(">H", os2, 4)
        if 1 <= weight_class <= 1000:
            weight = str(weight_class)
        (fs_selection,) = struct.unpack_from(">H", os2, 62)
        if fs_selection & 1:
            style = "italic"
    fvar = tables.get("fvar", b"")
    if len(fvar) >= 16:
        _major, _minor, axes_offset, _reserved, axis_count, axis_size = struct.unpack_from(">HHHHHH", fvar, 0)
        for i in range(axis_count):
            base = axes_offset + i * axis_size
            if base + 16 > len(fvar):
                break
            tag, minimum, _default, maximum = struct.unpack_from(">4siii", fvar, base)
            if tag == b"wght":
                low, high = max(1, round(minimum / 65536)), min(1000, round(maximum / 65536))
                if low < high:
                    weight = f"{low} {high}"
                break
    return weight, style


def _font_meta(path, filename):
    stat = os.stat(path)
    key = (filename, stat.st_size, stat.st_mtime_ns)
    if key in _meta_cache:
        return _meta_cache[key]
    stem, ext = os.path.splitext(filename)
    ext = ext.lower()
    family, weight, style = "", "400", "normal"
    if ext != ".woff2":
        try:
            tables = _read_tables(path, {"name", "OS/2", "fvar"})
            family = _family_name(tables["name"]) if "name" in tables else ""
            weight, style = _weight_and_style(tables)
        except _PARSE_ERRORS:
            pass
    meta = {
        "file": filename,
        "family": family or stem,
        "weight": weight,
        "style": style,
        "format": FONT_TYPES[ext][1],
        "size": stat.st_size,
        "url": f"/api/subtitle-fonts/file/{quote(filename)}",
    }
    _meta_cache[key] = meta
    return meta


def _font_path(filename):
    """Path of an uploaded font inside FONT_DIR, or None when the name is not a plain font file name there."""
    if not filename or filename != os.path.basename(filename) or filename.startswith("."):
        return None
    if os.path.splitext(filename)[1].lower() not in FONT_TYPES:
        return None
    path = os.path.join(FONT_DIR, filename)
    if not os.path.isfile(path) or not os.path.realpath(path).startswith(os.path.realpath(FONT_DIR) + os.sep):
        return None
    return path


def _list_fonts():
    if not os.path.isdir(FONT_DIR):
        return []
    fonts = [_font_meta(path, name) for name in os.listdir(FONT_DIR) if (path := _font_path(name))]
    return sorted(fonts, key=lambda font: (font["family"].lower(), font["weight"], font["style"], font["file"]))


def _error(message, status):
    return JsonResponse({"success": False, "error": message}, status=status)


class SubtitleFontListView(View):
    """GET 列出已上传的字体；POST 上传一个字体文件，multipart 字段名 file。"""

    def get(self, request):
        return JsonResponse({"success": True, "fonts": _list_fonts()})

    def post(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            return _error("没有收到字体文件", 400)
        base = os.path.basename((upload.name or "").replace("\\", "/"))
        stem, ext = os.path.splitext(base)
        ext = ext.lower()
        if ext not in FONT_TYPES:
            return _error("只支持 TTF、OTF、WOFF、WOFF2 字体文件", 400)
        if upload.size > MAX_FONT_BYTES:
            return _error(f"字体文件太大，最多 {MAX_FONT_BYTES // (1024 * 1024)} MB", 400)
        head = upload.read(4)
        upload.seek(0)
        if head not in FONT_TYPES[ext][0]:
            return _error(f"文件内容不是有效的 {ext[1:].upper()} 字体", 400)
        stem = re.sub(r"[^\w\- ()]+", "_", stem).strip(" ._-")[:80] or "font"
        os.makedirs(FONT_DIR, exist_ok=True)
        with _lock:
            filename, counter = f"{stem}{ext}", 1
            while os.path.exists(os.path.join(FONT_DIR, filename)):
                filename, counter = f"{stem}-{counter}{ext}", counter + 1
            final_path = os.path.join(FONT_DIR, filename)
            temp_path = os.path.join(FONT_DIR, f".{filename}.uploading")
            with open(temp_path, "wb") as f:
                for chunk in upload.chunks():
                    f.write(chunk)
            if ext != ".woff2":
                try:
                    tables = _read_tables(temp_path, {"name"})
                    if "name" not in tables:
                        raise ValueError("font has no name table")
                    _family_name(tables["name"])
                except _PARSE_ERRORS:
                    os.remove(temp_path)
                    return _error("读不出字体信息，文件可能已损坏", 400)
            os.replace(temp_path, final_path)
        return JsonResponse({"success": True, "font": _font_meta(final_path, filename)}, status=201)


class SubtitleFontDetailView(View):
    """DELETE 删除一个已上传的字体文件。"""

    def delete(self, request, filename):
        path = _font_path(filename)
        if path is None:
            return _error("字体不存在", 404)
        with _lock:
            os.remove(path)
        return JsonResponse({"success": True, "file": filename})


class SubtitleFontFileView(View):
    """GET 字体文件本身，供前端 @font-face 引用。"""

    def get(self, request, filename):
        path = _font_path(filename)
        if path is None:
            return _error("字体不存在", 404)
        response = FileResponse(open(path, "rb"), content_type=FONT_TYPES[os.path.splitext(filename)[1].lower()][2])
        response["Cache-Control"] = "public, max-age=86400"
        return response
