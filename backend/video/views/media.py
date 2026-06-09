# This file is for serve media
from django.http import JsonResponse,HttpResponse,HttpResponseNotAllowed,HttpResponseNotFound,Http404,FileResponse
from django.http import StreamingHttpResponse
from ..models import Category, Video
from django.views import View
from django.conf import settings  # Ensure this is at the top
from django.shortcuts import get_object_or_404,render
from django.urls import reverse
from urllib.parse import unquote
from django.views.static import serve
import json 
import os
import mimetypes
import subprocess

def detect_video_codec(file_path):
    """
    Detect video codec using ffprobe to determine if it's AV1
    Returns the appropriate MIME type with codec information
    """
    try:
        # Use ffprobe to detect video codec
        result = subprocess.run([
            'ffprobe', '-v', 'quiet', '-select_streams', 'v:0',
            '-show_entries', 'stream=codec_name', '-of', 'csv=p=0', file_path
        ], capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            codec = result.stdout.strip()
            
            # Get container format
            base_mime_type, _ = mimetypes.guess_type(file_path)
            
            if codec == 'av1':
                if base_mime_type == 'video/mp4':
                    return 'video/mp4; codecs="av01.0.08M.08"'
                elif base_mime_type == 'video/webm':
                    return 'video/webm; codecs="av01.0.08M.08"'
                else:
                    # For other containers with AV1, still specify the codec
                    return f'{base_mime_type or "video/mp4"}; codecs="av01.0.08M.08"'
            elif codec == 'h264':
                if base_mime_type == 'video/mp4':
                    return 'video/mp4; codecs="avc1.42E01E, mp4a.40.2"'
                return base_mime_type or 'video/mp4'
            elif codec == 'hevc':
                if base_mime_type == 'video/mp4':
                    # Use more generic HEVC codec string for better browser compatibility
                    return 'video/mp4; codecs="hvc1"'
                return base_mime_type or 'video/mp4'
            elif codec == 'vp9':
                return 'video/webm; codecs="vp9"'
            elif codec == 'vp8':
                return 'video/webm; codecs="vp8"'
            else:
                # Unknown codec, return basic MIME type
                return base_mime_type or 'application/octet-stream'
        else:
            # ffprobe failed, fall back to basic MIME type detection
            content_type, _ = mimetypes.guess_type(file_path)
            return content_type or 'application/octet-stream'
            
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        # ffprobe not available or failed, fall back to basic MIME type detection
        content_type, _ = mimetypes.guess_type(file_path)
        return content_type or 'application/octet-stream'

class MediaActionView(View):
    def dispatch(self, request, *args, **kwargs):
        self.type = kwargs.pop('type', None)
        print(self.type)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, filename):
        if self.type == 'video':
            return self.serve_video(request, filename)
        elif self.type == 'audio':          # ← add this branch
            return self.serve_audio(request, filename)
        elif self.type == 'img':
            return self.serve_img(request, filename)
        elif self.type == 'screenshot':
            return self.serve_screenshot(request, filename)
        elif self.type == 'note_image':
            return self.serve_note_image(request, filename)
        elif self.type == 'attachments':
            return self.serve_attachments(request, filename)
        elif self.type == 'stream_video':
            return self.serve_stream_video(request, filename)
        elif self.type == 'vidunder':
            return self.serve_vidunder(request, filename)
        
        return HttpResponseNotAllowed(['GET'])
    # Memory-efficient chunked streaming for large video files
    def serve_video(self, request, filename):
        file_path = os.path.join(settings.MEDIA_ROOT, "saved_video", filename)
    
        if not os.path.exists(file_path):
            from django.http import Http404
            raise Http404("File not found")

        # Get file size and content type with codec detection
        file_size = os.path.getsize(file_path)
        content_type = detect_video_codec(file_path)
        
        # Check for time parameter in query string (e.g., ?t=90)
        time_param = request.GET.get('t')
        initial_seek_time = None
        if time_param:
            try:
                # Parse time parameter (support seconds or time format)
                if time_param.isdigit():
                    initial_seek_time = int(time_param)
                else:
                    # Could extend to support 1m30s format later
                    initial_seek_time = int(float(time_param))
                print(f"[MediaActionView] Initial seek time from query param: {initial_seek_time}s")
            except (ValueError, TypeError):
                print(f"[MediaActionView] Invalid time parameter: {time_param}")
                initial_seek_time = None
        
        # Memory limit configuration - Optimized for large files (>1GB)
        # 2MB chunks significantly reduce I/O operations: 1.5GB file = 750 I/O ops (vs 24576 with 64KB)
        CHUNK_SIZE = 2 * 1024 * 1024  # 2MB chunks for efficient streaming
        MAX_RANGE_SIZE = 100 * 1024 * 1024  # Max 100MB per range request
        
        print(f"[MediaActionView] Serving video: {filename}")
        print(f"[MediaActionView] Detected content type: {content_type}")
        print(f"[MediaActionView] File size: {file_size} bytes")

        # Handle range requests for video seeking
        range_header = request.headers.get('Range', None)
        if range_header:
            import re
            
            # Parse range header
            match = re.search(r'bytes=(\d+)-(\d*)', range_header)
            if not match:
                # Invalid range header
                response = HttpResponse(status=416)
                response['Content-Range'] = f'bytes */{file_size}'
                return response
                
            first_byte, last_byte = match.groups()
            first_byte = int(first_byte)
            last_byte = int(last_byte) if last_byte else file_size - 1
            
            if last_byte >= file_size:
                last_byte = file_size - 1
            
            if first_byte > last_byte or first_byte < 0:
                response = HttpResponse(status=416)
                response['Content-Range'] = f'bytes */{file_size}'
                return response
            
            length = last_byte - first_byte + 1
            
            # Limit range size to prevent excessive memory usage
            if length > MAX_RANGE_SIZE:
                last_byte = first_byte + MAX_RANGE_SIZE - 1
                length = MAX_RANGE_SIZE
            
            # Generator function for chunked reading
            def file_iterator():
                with open(file_path, 'rb') as f:
                    f.seek(first_byte)
                    remaining = length
                    while remaining > 0:
                        chunk_size = min(CHUNK_SIZE, remaining)
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk
            
            # Create streaming response with chunked data
            response = StreamingHttpResponse(
                file_iterator(),
                status=206,
                content_type=content_type
            )
            response['Content-Range'] = f'bytes {first_byte}-{last_byte}/{file_size}'
            response['Content-Length'] = str(length)
            response['Accept-Ranges'] = 'bytes'
            # Add CORS headers
            response['Access-Control-Allow-Origin'] = '*'
            response['Access-Control-Allow-Headers'] = 'Range'
            response['Access-Control-Expose-Headers'] = 'Content-Range, Content-Length, Accept-Ranges, X-Initial-Time'
            
            # Add initial seek time header if specified in query params
            if initial_seek_time is not None:
                response['X-Initial-Time'] = str(initial_seek_time)
            
            return response
        else:
            # Regular full file response with chunked streaming
            def file_iterator():
                with open(file_path, 'rb') as f:
                    while True:
                        chunk = f.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        yield chunk
            
            response = StreamingHttpResponse(
                file_iterator(),
                content_type=content_type
            )
            response['Content-Length'] = str(file_size)
            response['Accept-Ranges'] = 'bytes'
            # Add CORS headers
            response['Access-Control-Allow-Origin'] = '*'
            response['Access-Control-Allow-Headers'] = 'Range'
            response['Access-Control-Expose-Headers'] = 'Content-Range, Content-Length, Accept-Ranges, X-Initial-Time'
            
            # Add initial seek time header if specified in query params
            if initial_seek_time is not None:
                response['X-Initial-Time'] = str(initial_seek_time)
            
            return response

    # Memory-efficient chunked streaming for audio files  
    def serve_audio(self, request, filename):
        """
        Stream an audio file from MEDIA_ROOT/saved_audio/{filename}, with full
        Range-header support and memory-efficient chunked streaming.
        """
        file_path = os.path.join(settings.MEDIA_ROOT, "saved_audio", filename)

        if not os.path.exists(file_path):
            # Fallback: some audio files were saved into saved_video/ by mistake
            fallback = os.path.join(settings.MEDIA_ROOT, "saved_video", filename)
            if os.path.exists(fallback):
                file_path = fallback
            else:
                raise Http404("File not found")

        file_size = os.path.getsize(file_path)
        content_type, _ = mimetypes.guess_type(file_path)
        content_type = content_type or "application/octet-stream"
        
        # Memory limit configuration - Optimized for audio streaming
        CHUNK_SIZE = 512 * 1024  # 512KB chunks for efficient audio streaming
        MAX_RANGE_SIZE = 10 * 1024 * 1024  # Max 10MB per range request

        range_header = request.headers.get("Range")
        if range_header:
            import re
            m = re.match(r"bytes=(\d+)-(\d*)", range_header)
            if m:
                first_byte = int(m.group(1))
                last_byte = int(m.group(2) or file_size - 1)

                if last_byte >= file_size:
                    last_byte = file_size - 1
                    
                if first_byte > last_byte or first_byte < 0:
                    response = HttpResponse(status=416)
                    response['Content-Range'] = f'bytes */{file_size}'
                    return response

                length = last_byte - first_byte + 1
                
                # Limit range size to prevent excessive memory usage
                if length > MAX_RANGE_SIZE:
                    last_byte = first_byte + MAX_RANGE_SIZE - 1
                    length = MAX_RANGE_SIZE
                
                # Generator function for chunked reading
                def audio_iterator():
                    with open(file_path, "rb") as f:
                        f.seek(first_byte)
                        remaining = length
                        while remaining > 0:
                            chunk_size = min(CHUNK_SIZE, remaining)
                            chunk = f.read(chunk_size)
                            if not chunk:
                                break
                            remaining -= len(chunk)
                            yield chunk

                response = StreamingHttpResponse(
                    audio_iterator(),
                    status=206,
                    content_type=content_type,
                )
                response["Content-Range"] = f"bytes {first_byte}-{last_byte}/{file_size}"
                response["Accept-Ranges"] = "bytes"
                response["Content-Length"] = str(length)
                response["Access-Control-Allow-Origin"] = "*"
                response["Access-Control-Allow-Headers"] = "Range"
                response["Access-Control-Expose-Headers"] = "Content-Range, Content-Length, Accept-Ranges"
                return response

        # No Range header: send entire file with chunked streaming
        def audio_iterator():
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    yield chunk
                    
        response = StreamingHttpResponse(audio_iterator(), content_type=content_type)
        response["Content-Length"] = str(file_size)
        response["Accept-Ranges"] = "bytes"
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Headers"] = "Range"
        response["Access-Control-Expose-Headers"] = "Content-Range, Content-Length, Accept-Ranges"
        return response    

    from django.views.decorators.http import require_http_methods
    from django.utils.http import http_date
    from django.views.decorators.cache import cache_control

    def serve_stream_video(self, request, filename):
        """
        Stream HLS playlist or segment: path is '<md5>/index.m3u8' or '<md5>/<n>.ts'
        """
        # Only allow GET requests
        if request.method != 'GET':
            return HttpResponse(status=405)  # Method Not Allowed
        
        parts = filename.split('/', 1)
        if len(parts) != 2:
            raise Http404('Invalid stream_video path')
        
        digest, relpath = parts
        base = settings.MEDIA_ROOT
        hls_dir = os.path.join(base, 'stream_video', digest)
        file_path = os.path.join(hls_dir, relpath)
        
        if not file_path.startswith(hls_dir):
            raise Http404('Invalid file path')
        
        if not os.path.exists(file_path):
            raise Http404(f'File not found: {relpath}')
        
        if relpath.endswith('.m3u8'):
            content_type = 'application/vnd.apple.mpegurl'
        elif relpath.endswith('.ts'):
            content_type = 'video/MP2T'
        else:
            content_type, _ = mimetypes.guess_type(file_path)
            if not content_type:
                content_type = 'application/octet-stream'
        
        try:
            response = FileResponse(
                open(file_path, 'rb'),
                content_type=content_type,
                as_attachment=False
            )
            
            # Add CORS headers for HLS streaming
            response['Access-Control-Allow-Origin'] = '*'
            response['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
            response['Access-Control-Allow-Headers'] = 'Range, Content-Type'
            response['Access-Control-Expose-Headers'] = 'Content-Length, Content-Range'
            
            # Add caching headers
            if relpath.endswith('.ts'):
                response['Cache-Control'] = 'public, max-age=31536000'  # 1 year
            elif relpath.endswith('.m3u8'):
                response['Cache-Control'] = 'public, max-age=10'
            
            return response
            
        except IOError:
            raise Http404('Cannot read file')
    def serve_img(self,request, filename):
        file_path = os.path.join(settings.MEDIA_ROOT, "thumbnail", filename)
        if not os.path.exists(file_path):
            from django.http import Http404
            raise Http404("File not found")
        # Serve the image file
        return serve(request, os.path.basename(file_path), document_root=os.path.dirname(file_path))

    def serve_screenshot(self, request, filename):
        """
        Serve screenshot images from MEDIA_ROOT/screenshot/{filename}
        """
        file_path = os.path.join(settings.MEDIA_ROOT, "screenshot", filename)
        if not os.path.exists(file_path):
            from django.http import Http404
            raise Http404("Screenshot file not found")
        # Serve the screenshot image file
        return serve(request, os.path.basename(file_path), document_root=os.path.dirname(file_path))

    def serve_note_image(self, request, filename):
        """
        Serve note images from MEDIA_ROOT/note_image/{filename}
        """
        file_path = os.path.join(settings.MEDIA_ROOT, "note_image", filename)
        if not os.path.exists(file_path):
            from django.http import Http404
            raise Http404("Note image file not found")
        # Serve the note image file
        return serve(request, os.path.basename(file_path), document_root=os.path.dirname(file_path))

    def serve_attachments(self, request, filename):
        """
        Serve attachment files from MEDIA_ROOT/attachments/{filename}
        This provides basic file serving for the new VideoAttachment system
        """
        file_path = os.path.join(settings.MEDIA_ROOT, "attachments", filename)
        if not os.path.exists(file_path):
            from django.http import Http404
            raise Http404("Attachment file not found")
        return serve(request, os.path.basename(file_path), document_root=os.path.dirname(file_path))

    def serve_vidunder(self, request, filename):
        file_path = os.path.join(settings.MEDIA_ROOT, "vidunder", filename)
        if not os.path.exists(file_path):
            raise Http404("File not found")
        return serve(request, os.path.basename(file_path), document_root=os.path.dirname(file_path))
