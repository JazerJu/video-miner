from django.shortcuts import render
from django.http import HttpResponse, FileResponse
from django.conf import settings
from django.views.static import serve
import os

def favicon(request):
    static_dir = settings.STATIC_ROOT if hasattr(settings, 'STATIC_ROOT') and settings.STATIC_ROOT and os.path.exists(settings.STATIC_ROOT) else settings.STATICFILES_DIRS[0]
    favicon_path = os.path.join(static_dir, 'favicon.ico')
    if os.path.exists(favicon_path):
        return FileResponse(open(favicon_path, 'rb'), content_type='image/x-icon')
    return HttpResponse(status=404)

def index(request):
    """
    服务前端 Vue 应用的主入口
    """
    # 读取构建后的 index.html 文件
    # 判断使用哪个静态文件目录：
    # 1. 优先使用 STATIC_ROOT（生产环境中collectstatic后的目录）
    # 2. 如果 STATIC_ROOT 不存在或为空，则使用 STATICFILES_DIRS 的第一个目录（开发环境）
    static_dir = settings.STATIC_ROOT if hasattr(settings, 'STATIC_ROOT') and settings.STATIC_ROOT and os.path.exists(settings.STATIC_ROOT) else settings.STATICFILES_DIRS[0]
    # 构建 index.html 文件的完整路径
    # 这是 Vue.js 构建后生成的主 HTML 文件
    index_path = os.path.join(static_dir, 'index.html')
    
    # 使用 try-except 处理文件可能不存在的情况
    try:
        # 以 UTF-8 编码打开 index.html 文件（避免中文乱码）
        with open(index_path, 'r', encoding='utf-8') as f:
            # 读取整个 HTML 文件内容到内存中
            html_content = f.read()
        # 返回 HTML 内容，设置正确的 Content-Type 头
        return HttpResponse(html_content, content_type='text/html')
    except FileNotFoundError:
        # 如果文件不存在，返回 404 错误页面
        # 同时提供给开发者的提示信息
        return HttpResponse(
            '<h1>Frontend not found</h1><p>Please run: npm run build and copy files to static/</p>', 
            status=404
        )

def frontend_assets(request, path):
    """
    服务前端静态资源 (CSS, JS, 图片等)
    """
    # 同样的逻辑：优先使用 STATIC_ROOT，否则使用 STATICFILES_DIRS[0]
    static_dir = settings.STATIC_ROOT if hasattr(settings, 'STATIC_ROOT') and settings.STATIC_ROOT and os.path.exists(settings.STATIC_ROOT) else settings.STATICFILES_DIRS[0]
    
    # 构建静态资源文件的完整路径
    # path 参数来自 URL，如: 'js/app.123abc.js' 或 'css/style.456def.css'
    file_path = os.path.join(static_dir, 'assets', path)
    
    # 检查请求的文件是否存在于服务器上
    if os.path.exists(file_path):
        # 使用 Django 的 serve 函数来服务静态文件
        # serve 会自动设置正确的 Content-Type 和缓存头
        return serve(request, path, document_root=os.path.join(static_dir, 'assets'))
    else:
        # 如果请求的资源不存在，返回 404 错误
        return HttpResponse('Asset not found', status=404)