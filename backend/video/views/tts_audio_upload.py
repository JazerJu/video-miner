"""
TTS Audio Upload API Views
Handles uploading reference audio files to Aliyun OSS for voice cloning
"""
import os
import uuid
import time
import tempfile
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.conf import settings
import oss2
from video.views.set_setting import load_all_settings


@method_decorator(csrf_exempt, name='dispatch')
class TTSAudioUploadView(View):
    """
    POST /api/tts/audio_upload
    Upload reference audio file to Aliyun OSS for voice cloning

    Request:
    - Form data with 'audio_file' (WAV/MP3/M4A file)
    - Optional 'reference_text' (text content of the audio)

    Response:
    {
        "success": true,
        "audio_url": "https://bucket.oss-region.aliyuncs.com/path/to/audio.mp3?Expires=...",
        "reference_text": "Reference text provided or extracted"
    }

    Error response:
    {
        "error": "error message"
    }
    """

    def post(self, request):
        try:
            # Check if file was uploaded
            if 'audio_file' not in request.FILES:
                return JsonResponse(
                    {"error": "No audio file provided"},
                    status=400
                )

            audio_file = request.FILES['audio_file']

            # Get optional reference text
            reference_text = request.POST.get('reference_text', '').strip()

            # Validate file type
            allowed_extensions = ['.wav', '.mp3', '.m4a']
            file_extension = os.path.splitext(audio_file.name)[1].lower()
            if file_extension not in allowed_extensions:
                return JsonResponse(
                    {"error": f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"},
                    status=400
                )

            # Validate file size (max 10MB)
            if audio_file.size > 10 * 1024 * 1024:  # 10MB
                return JsonResponse(
                    {"error": "File size exceeds 10MB limit"},
                    status=400
                )

            # Load OSS configuration
            settings_data = load_all_settings()
            oss_settings = settings_data.get('OSS Service', {})

            oss_access_key_id = oss_settings.get('oss_access_key_id', '')
            oss_access_key_secret = oss_settings.get('oss_access_key_secret', '')
            oss_endpoint = oss_settings.get('oss_endpoint', 'oss-cn-beijing.aliyuncs.com')
            oss_bucket = oss_settings.get('oss_bucket', 'vidgo-test')
            oss_region = oss_settings.get('oss_region', 'cn-beijing')

            # Validate OSS configuration
            if not oss_access_key_id or not oss_access_key_secret:
                return JsonResponse(
                    {"error": "OSS credentials not configured"},
                    status=500
                )

            # Initialize OSS client
            auth = oss2.Auth(oss_access_key_id, oss_access_key_secret)
            bucket = oss2.Bucket(auth, f"http://{oss_endpoint}", oss_bucket)

            # Generate unique filename
            timestamp = int(time.time())
            unique_id = uuid.uuid4().hex[:12]
            object_key = f"tts_voices/{timestamp}_{unique_id}{file_extension}"

            # Upload file to OSS
            # Read file content
            audio_file.seek(0)
            file_content = audio_file.read()

            # Upload to OSS
            result = bucket.put_object(object_key, file_content)

            if result.status != 200:
                return JsonResponse(
                    {"error": f"Failed to upload to OSS: {result.status}"},
                    status=500
                )

            # Generate signed URL (valid for 1 hour)
            signed_url = bucket.sign_url('GET', object_key, expires=3600)

            return JsonResponse({
                "success": True,
                "audio_url": signed_url,
                "reference_text": reference_text,
                "object_key": object_key
            })

        except Exception as e:
            print(f"[TTS Audio Upload] Error: {e}")
            return JsonResponse(
                {"error": str(e)},
                status=500
            )