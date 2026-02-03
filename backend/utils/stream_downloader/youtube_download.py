import yt_dlp
import os
from typing import Dict, Optional, Any


class YouTubeDownloader:
    def __init__(self):
        self.base_ydl_opts = {
            'writesubtitles': False,
            'writeautomaticsub': False,
            'ignoreerrors': True,
            'noplaylist': True,  # Only download single video, not playlist
            'quiet': True,
        }
        
        # Check proxy settings
        try:
            import configparser
            from django.conf import settings
            
            config_path = os.path.join(settings.BASE_DIR, 'config/config.ini')
            if os.path.exists(config_path):
                config = configparser.ConfigParser()
                config.read(config_path)
                use_proxy = config.get('DEFAULT', 'use_proxy', fallback='false').lower() == 'true'
                
                if not use_proxy:
                    # Force no proxy if disabled in settings
                    self.base_ydl_opts['proxy'] = ''
        except Exception as e:
            print(f"Error reading proxy settings: {e}")

    def get_video_info(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Extract video information without downloading
        
        Args:
            url: YouTube video URL
            
        Returns:
            Dictionary containing video metadata or None if failed
        """
        ydl_opts = self.base_ydl_opts.copy()
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=False)
                
                if info_dict is None:
                    print("Failed to extract video information")
                    return None
                
                # Extract key information
                video_info = {
                    'title': info_dict.get('title', ''),
                    'duration': info_dict.get('duration', 0),
                    'uploader': info_dict.get('uploader', ''),
                    'upload_date': info_dict.get('upload_date', ''),
                    'view_count': info_dict.get('view_count', 0),
                    'description': info_dict.get('description', ''),
                    'thumbnail': info_dict.get('thumbnail', ''),
                    'formats': info_dict.get('formats', []),
                    'id': info_dict.get('id', ''),
                    'webpage_url': info_dict.get('webpage_url', ''),
                    'ext': info_dict.get('ext', 'mp4'),
                }
                
                return video_info
                
        except Exception as e:
            print(f"Error extracting video info: {e}")
            return None

    def download_video(self, url: str, output_path: str, 
                      filename_template: Optional[str] = None,
                      merge_audio_video: bool = True) -> Optional[str]:
        """
        Download video from YouTube URL
        
        Args:
            url: YouTube video URL
            output_path: Directory to save the video
            filename_template: Custom filename template (optional)
            merge_audio_video: Whether to merge separate audio/video streams with ffmpeg
            
        Returns:
            Path to downloaded file or None if failed
        """
        if not os.path.exists(output_path):
            os.makedirs(output_path, exist_ok=True)
            
        # Set filename template
        if filename_template is None:
            filename_template = '%(title)s.%(ext)s'
            
        ydl_opts = self.base_ydl_opts.copy()
        ydl_opts.update({
            'outtmpl': os.path.join(output_path, filename_template),
        })
        
        # Set format based on preferences
        if merge_audio_video:
            # Try to get separate video and audio, fallback to combined
            ydl_opts['format'] = 'bestvideo[height<=720]+bestaudio/best[height<=720]'
        else:
            # Get best combined format with reasonable quality
            ydl_opts['format'] = 'best[height<=720]'
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # First get info to determine output filename
                info_dict = ydl.extract_info(url, download=False)
                
                # Generate the expected output filename
                output_filename = ydl.prepare_filename(info_dict)
                
                # Download the video
                ydl.process_info(info_dict)
                
                return output_filename
                
        except Exception as e:
            print(f"Error downloading video: {e}")
            return None

    def download_audio_only(self, url: str, output_path: str,
                           filename_template: Optional[str] = None) -> Optional[str]:
        """
        Download audio only from YouTube URL
        
        Args:
            url: YouTube video URL  
            output_path: Directory to save the audio
            filename_template: Custom filename template (optional)
            
        Returns:
            Path to downloaded audio file or None if failed
        """
        if not os.path.exists(output_path):
            os.makedirs(output_path, exist_ok=True)
            
        if filename_template is None:
            filename_template = '%(title)s.%(ext)s'
            
        ydl_opts = self.base_ydl_opts.copy()
        ydl_opts.update({
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'outtmpl': os.path.join(output_path, filename_template),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=False)
                output_filename = ydl.prepare_filename(info_dict)
                
                # Replace video extension with audio extension
                audio_filename = os.path.splitext(output_filename)[0] + '.mp3'
                
                ydl.process_info(info_dict)
                
                return audio_filename
                
        except Exception as e:
            print(f"Error downloading audio: {e}")
            return None


# Legacy function for backward compatibility
def download_youtube_video(url, output_path):
    downloader = YouTubeDownloader()
    return downloader.download_video(url, output_path)