"""
yt-dlp 包管理接口：安装内核、安装依赖（含 EJS）、检测升级。
供前端"媒体认证"设置页调用。
"""

import importlib.util
import subprocess
import sys

from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt


def _run_pip(args: list[str], timeout: int = 300) -> tuple[bool, str]:
    """统一 pip 调用，返回 (success, output)"""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "pip 操作超时"
    except Exception as e:
        return False, str(e)


def _get_yt_dlp_version() -> str:
    """获取当前 yt-dlp 版本号"""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip() or "未知"
    except Exception:
        return "未安装"


def _get_yt_dlp_ejs_version() -> str:
    """获取 yt-dlp-ejs 版本"""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", "yt-dlp-ejs"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.startswith("Version:"):
                    return line.split(":", 1)[1].strip()
        return "未安装"
    except Exception:
        return "未安装"


def _check_node_available() -> bool:
    """检查 Node.js 是否可用"""
    try:
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def _check_node_version() -> str:
    """获取 Node.js 版本"""
    try:
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() or "未安装"
    except Exception:
        return "未安装"


def _is_yt_dlp_ejs_importable() -> bool:
    """检查 yt-dlp-ejs 模块是否可导入"""
    return importlib.util.find_spec("yt_dlp_ejs") is not None


@method_decorator(csrf_exempt, name="dispatch")
class YtDlpStatusView(View):
    http_method_names = ["get"]

    def get(self, request, *args, **kwargs):
        try:
            return JsonResponse(
                {
                    "success": True,
                    "data": {
                        "yt_dlp_version": _get_yt_dlp_version(),
                        "ejs_version": _get_yt_dlp_ejs_version(),
                        "node_available": _check_node_available(),
                        "node_version": _check_node_version(),
                        "node_required_version": ">=20.0.0",
                    },
                }
            )
        except Exception as exc:
            return JsonResponse({"success": False, "error": str(exc)}, status=500)


@method_decorator(csrf_exempt, name="dispatch")
class YtDlpInstallDepsView(View):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        try:
            success, output = _run_pip(["install", "yt-dlp[default]"])
            yt_dlp_version = _get_yt_dlp_version()
            ejs_installed = _is_yt_dlp_ejs_importable()

            return JsonResponse(
                {
                    "success": success and ejs_installed,
                    "yt_dlp_version": yt_dlp_version,
                    "ejs_installed": ejs_installed,
                    "detail": output,
                },
                status=200 if success and ejs_installed else 500,
            )
        except Exception as exc:
            return JsonResponse(
                {
                    "success": False,
                    "yt_dlp_version": _get_yt_dlp_version(),
                    "ejs_installed": _is_yt_dlp_ejs_importable(),
                    "detail": str(exc),
                },
                status=500,
            )


@method_decorator(csrf_exempt, name="dispatch")
class YtDlpUpgradeView(View):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        current_version = _get_yt_dlp_version()

        try:
            success, output = _run_pip(["install", "-U", "yt-dlp[default]"])
            new_version = _get_yt_dlp_version()
            upgraded = (
                success
                and current_version not in {"未安装", "未知"}
                and new_version not in {"未安装", "未知"}
                and current_version != new_version
            )

            return JsonResponse(
                {
                    "success": success,
                    "current_version": current_version,
                    "new_version": new_version,
                    "upgraded": upgraded,
                    "detail": output,
                },
                status=200 if success else 500,
            )
        except Exception as exc:
            return JsonResponse(
                {
                    "success": False,
                    "current_version": current_version,
                    "new_version": _get_yt_dlp_version(),
                    "upgraded": False,
                    "detail": str(exc),
                },
                status=500,
            )
