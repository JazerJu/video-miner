"""
WebSocket consumers for real-time features
"""
import json
import asyncio
import io
import wave
import numpy as np
import time
from pathlib import Path
from django.conf import settings
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.exceptions import StopConsumer
import tempfile
import os
import ffmpeg
from pydub import AudioSegment

class HypothesisBuffer:
    """
    Hypothesis buffer implementation for smooth real-time transcription
    """
    def __init__(self):
        self.commited_in_buffer = []
        self.buffer = []
        self.new = []
        self.last_commited_time = 0
        self.last_commited_word = None

    def insert(self, new_entries, offset):
        """Insert new entries and manage buffer state"""
        # Add offset to timestamps
        new_entries = [(a + offset, b + offset, t) for a, b, t in new_entries]
        self.new = [(a, b, t) for a, b, t in new_entries if a > self.last_commited_time - 0.1]

        if len(self.new) >= 1:
            a, b, t = self.new[0]
            if abs(a - self.last_commited_time) < 1:
                if self.commited_in_buffer:
                    # Search for consecutive words that are identical
                    cn = len(self.commited_in_buffer)
                    nn = len(self.new)
                    for i in range(1, min(min(cn, nn), 5) + 1):
                        c = " ".join([self.commited_in_buffer[-j][2] for j in range(1, i + 1)][::-1])
                        tail = " ".join([self.new[j - 1][2] for j in range(1, i + 1)])
                        if c == tail:
                            # Remove duplicate words
                            for j in range(i):
                                if self.new:
                                    self.new.pop(0)
                            break

    def flush(self):
        """Return committed chunk"""
        commit = []
        while self.new and self.buffer:
            na, nb, nt = self.new[0]
            ba, bb, bt = self.buffer[0]

            if nt == bt:
                commit.append((na, nb, nt))
                self.last_commited_word = nt
                self.last_commited_time = nb
                self.buffer.pop(0)
                self.new.pop(0)
            else:
                break

        self.buffer = self.new.copy()
        self.new = []
        self.commited_in_buffer.extend(commit)
        return commit

    def complete(self):
        """Return remaining buffer"""
        return self.buffer


class RealtimeTranscriptionConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time audio transcription
    """
    async def connect(self):
        """Handle WebSocket connection"""
        await self.accept()

        # Initialize state
        self.audio_buffer = bytearray()
        self.hypothesis_buffer = HypothesisBuffer()
        self.is_processing = False
        self.language = 'zh'  # Default language
        self.temp_audio_file = None
        self.recording_start_time = None
        self.full_audio_buffer = bytearray()  # Buffer for complete audio recording
        self.session_id = None  # Unique session identifier

        # Continuous ffmpeg processing state
        self.ffmpeg_process = None
        self.ffmpeg_reader_task = None

        # Audio chunk timing
        self.chunk_count = 0
        self.chunk_duration_seconds = 1.0  # Each chunk is 1 second

        # Sentence buffer for combining transcription fragments
        self.sentence_buffer = ""
        self.sentence_start_time = None
        self.sentence_end_time = None
        self.last_transcription_text = ""  # Track last transcription to avoid duplicates
        self.sentence_start_chunk = 0  # Track when sentence started
        self.continuous_wav_buffer = bytearray()
        self.wav_chunk_ready = asyncio.Event()

        # 节流机制：防止过度频繁的转录请求
        self.last_transcription_time = 0
        self.min_transcription_interval = 2.0  # 降低到2秒间隔，提高实时性

        # 调试计数器
        self.debug_chunk_counter = 0

        print(f"[WebSocket] Client connected: {self.scope['path']}")

    async def start_continuous_ffmpeg(self):
        """Start continuous ffmpeg process for real-time audio conversion"""
        try:
            # Start ffmpeg process that reads various formats and outputs raw PCM
            cmd = [
                'ffmpeg',
                '-hide_banner',
                '-loglevel', 'error',
                '-fflags', '+nobuffer+genpts',
                '-flags', 'low_delay',
                '-probesize', '32k',
                '-analyzeduration', '0',
                '-i', 'pipe:0',  # Read from stdin (auto-detect format)
                '-vn',  # No video
                '-ac', '1',  # Mono
                '-ar', '16000',  # 16kHz sample rate
                '-acodec', 'pcm_s16le',  # 16-bit PCM
                '-f', 's16le',  # Raw PCM format (no container)
                'pipe:1'  # Write to stdout
            ]

            print(f"[WebSocket] Starting continuous ffmpeg: {' '.join(cmd)}")

            self.ffmpeg_process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Start reading PCM output from ffmpeg
            self.ffmpeg_reader_task = asyncio.create_task(self.read_continuous_pcm())

            print(f"[WebSocket] Continuous ffmpeg started (PID: {self.ffmpeg_process.pid})")

            # Monitor stderr for errors
            asyncio.create_task(self.monitor_ffmpeg_stderr())

        except Exception as e:
            print(f"[WebSocket] Failed to start continuous ffmpeg: {e}")
            await self.send_json({
                'type': 'error',
                'message': f'Failed to start audio processing: {e}'
            })

    async def read_continuous_pcm(self):
        """Read continuous raw PCM output from ffmpeg and process small frames"""
        try:
            # PCM constants
            SAMPLE_RATE = 16000
            BYTES_PER_SAMPLE = 2  # s16le
            CHANNELS = 1
            BYTES_PER_SEC = SAMPLE_RATE * BYTES_PER_SAMPLE * CHANNELS

            # Process 100ms frames = 3200 bytes
            FRAME_MS = 100
            FRAME_BYTES = BYTES_PER_SEC * FRAME_MS // 1000  # 3200 bytes for 100ms

            print(f"[WebSocket] PCM frame size: {FRAME_BYTES} bytes ({FRAME_MS}ms)")

            while self.ffmpeg_process and self.ffmpeg_process.returncode is None:
                try:
                    # Read small chunks to reduce latency
                    data = await asyncio.wait_for(
                        self.ffmpeg_process.stdout.read(FRAME_BYTES),
                        timeout=0.5  # Short timeout for responsiveness
                    )

                    if not data:
                        print("[WebSocket] FFmpeg stdout closed")
                        break

                    # Append to buffer
                    self.continuous_wav_buffer.extend(data)

                    # Process complete frames
                    while len(self.continuous_wav_buffer) >= FRAME_BYTES:
                        frame = bytes(self.continuous_wav_buffer[:FRAME_BYTES])
                        self.continuous_wav_buffer = self.continuous_wav_buffer[FRAME_BYTES:]

                        # Store frame for VAD processing
                        if not hasattr(self, 'pcm_frames'):
                            self.pcm_frames = bytearray()
                        self.pcm_frames.extend(frame)

                        # Signal processing every 5 seconds (50 frames) - 减少过度分割
                        if len(self.pcm_frames) >= FRAME_BYTES * 50:
                            print(f"[WebSocket] PCM buffer ready: {len(self.pcm_frames)} bytes (5s)")
                            self.wav_chunk_ready.set()

                except asyncio.TimeoutError:
                    # No data available, continue
                    continue
                except Exception as e:
                    print(f"[WebSocket] Error reading PCM from ffmpeg: {e}")
                    break

            print("[WebSocket] Continuous PCM reader stopped")

        except Exception as e:
            print(f"[WebSocket] Error in continuous PCM reader: {e}")

    async def monitor_ffmpeg_stderr(self):
        """Monitor ffmpeg stderr for errors"""
        try:
            while self.ffmpeg_process and self.ffmpeg_process.returncode is None:
                try:
                    # Read stderr from ffmpeg
                    stderr_line = await asyncio.wait_for(
                        self.ffmpeg_process.stderr.readline(),
                        timeout=1.0
                    )

                    if stderr_line:
                        stderr_text = stderr_line.decode('utf-8', errors='replace').strip()
                        if stderr_text:
                            print(f"[WebSocket] FFmpeg stderr: {stderr_text}")
                    else:
                        # ffmpeg process might have ended
                        break

                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    print(f"[WebSocket] Error monitoring ffmpeg stderr: {e}")
                    break

            print(f"[WebSocket] FFmpeg process ended with return code: {self.ffmpeg_process.returncode if self.ffmpeg_process else 'Unknown'}")

        except Exception as e:
            print(f"[WebSocket] Error in ffmpeg stderr monitor: {e}")

    async def process_continuous_wav_chunks(self):
        """Process continuous WAV chunks for transcription"""
        while True:
            try:
                # Wait for WAV chunk to be ready
                await self.wav_chunk_ready.wait()

                if not self.continuous_wav_buffer:
                    self.wav_chunk_ready.clear()
                    continue

                # Take PCM data for processing (5s chunks)
                if hasattr(self, 'pcm_frames') and self.pcm_frames:
                    chunk_data = bytes(self.pcm_frames)
                    self.pcm_frames.clear()

                    # Clear the event
                    self.wav_chunk_ready.clear()

                    # Transcribe PCM chunk
                    await self.transcribe_pcm_chunk(chunk_data)

            except Exception as e:
                print(f"[WebSocket] Error processing continuous WAV chunk: {e}")
                self.wav_chunk_ready.clear()

    async def transcribe_pcm_chunk(self, pcm_data):
        """Transcribe a PCM chunk using VAD-enhanced transcription"""
        if self.is_processing:
            return

        # 防止处理太小的音频块
        if len(pcm_data) < 8000:  # 小于0.25秒的音频跳过
            return

        # 节流检查：避免过于频繁的转录请求
        current_time = time.time()
        if current_time - self.last_transcription_time < self.min_transcription_interval:
            print(f"[WebSocket] Skipping transcription - too frequent (last: {current_time - self.last_transcription_time:.1f}s ago)")
            return

        self.last_transcription_time = current_time
        self.is_processing = True

        try:
            # Create temporary WAV file for VAD/transcription and debugging
            wav_file_path = tempfile.NamedTemporaryFile(suffix='.wav', delete=False).name
            with wave.open(wav_file_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # pcm_s16le (16-bit)
                wf.setframerate(16000)
                wf.writeframes(pcm_data)

            # Also save to debug directory for inspection
            if self.session_id:
                try:
                    work_dir = getattr(settings, 'WORK_DIR', 'work_dir')
                    work_dir_path = Path(work_dir)
                    work_dir_path.mkdir(exist_ok=True)

                    audio_debug_dir = work_dir_path / 'audio_debug'
                    audio_debug_dir.mkdir(exist_ok=True)

                    chunk_counter = getattr(self, 'debug_chunk_counter', 0)
                    debug_wav_path = audio_debug_dir / f"{self.session_id}_chunk_{chunk_counter:03d}.wav"

                    # Copy the WAV file to debug location
                    import shutil
                    shutil.copy2(wav_file_path, debug_wav_path)

                    self.debug_chunk_counter = chunk_counter + 1
                    print(f"[WebSocket] Debug WAV saved: {debug_wav_path}")
                except Exception as e:
                    print(f"[WebSocket] Failed to save debug WAV: {e}")

            print(f"[WebSocket] Processing PCM chunk: {len(pcm_data)} bytes -> {wav_file_path}")

            # 调试：检查PCM数据的前几个字节
            header_preview = pcm_data[:20].hex()
            print(f"[WebSocket] PCM header: {header_preview}")

            # 调试：检查音频文件信息
            try:
                duration = os.path.getsize(wav_file_path) / (16000 * 2 * 1)  # 简单计算：大小 / (采样率 * 字节数 * 声道数)
                print(f"[WebSocket] WAV duration estimate: {duration:.2f}s")
            except:
                pass

            # Transcribe using VAD-enhanced real-time transcription
            def real_progress_callback(message):
                print(f"[WebSocket] Transcription progress: {message}")
                # Send progress to client
                asyncio.create_task(self.send_json({
                    'type': 'progress',
                    'message': message
                }))

            # Force Chinese language for better results
            transcription_language = 'zh' if self.language == 'zh' else 'en'

            from asr_utils.transcription_engine import transcribe_with_engine
            from asr_utils.transcription_engine import load_transcription_settings

            transcription_settings = load_transcription_settings()
            engine_settings = transcription_settings.get("Transcription Engine", {})
            primary_engine = engine_settings.get("primary_engine", "funasr_gguf")

            srt_content = transcribe_with_engine(
                engine_type=primary_engine,
                audio_file_path=wav_file_path,
                progress_cb=real_progress_callback,
                language=transcription_language,
            )

            if srt_content:
                entries = self.parse_srt_entries(srt_content)
                print(f"[WebSocket] Simple chunks transcription successful: {len(entries)} entries")

                # Send transcription results to client
                if entries:
                    await self.send_json({
                        'type': 'transcription',
                        'entries': entries
                    })
            else:
                print(f"[WebSocket] Simple chunks transcription returned empty result")

        except Exception as e:
            print(f"[WebSocket] Error transcribing PCM chunk: {e}")
            import traceback
            print(f"[WebSocket] Traceback: {traceback.format_exc()}")

            await self.send_json({
                'type': 'error',
                'message': 'Error transcribing audio'
            })
        finally:
            self.is_processing = False
            # Clean up temporary file
            try:
                os.unlink(wav_file_path)
            except:
                pass

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        print(f"[WebSocket] Client disconnected: {self.scope['path']}")

        # Stop continuous ffmpeg process
        if self.ffmpeg_process:
            try:
                self.ffmpeg_process.terminate()
                await self.ffmpeg_process.wait()
                print("[WebSocket] FFmpeg process terminated")
            except Exception as e:
                print(f"[WebSocket] Error terminating FFmpeg: {e}")

        if self.ffmpeg_reader_task:
            self.ffmpeg_reader_task.cancel()
            try:
                await self.ffmpeg_reader_task
            except asyncio.CancelledError:
                pass

        # Save audio if there's data when client disconnects
        if self.full_audio_buffer and self.session_id:
            try:
                work_dir = getattr(settings, 'WORK_DIR', 'work_dir')
                work_dir_path = Path(work_dir)
                work_dir_path.mkdir(exist_ok=True)

                # Create audio debug directory
                audio_debug_dir = work_dir_path / 'audio_debug'
                audio_debug_dir.mkdir(exist_ok=True)

                # Save complete WebM recording
                full_webm_path = audio_debug_dir / f"{self.session_id}_disconnect_recording.webm"
                with open(full_webm_path, 'wb') as f:
                    f.write(bytes(self.full_audio_buffer))

                # Also save converted WAV for debugging
                full_wav_path = audio_debug_dir / f"{self.session_id}_disconnect_recording.wav"
                try:
                    wav_data = self.convert_webm_to_wav(str(full_webm_path))
                    with open(full_wav_path, 'wb') as f:
                        f.write(wav_data)
                    print(f"[WebSocket] Disconnect audio saved: {full_webm_path} -> {full_wav_path}")
                    print(f"[WebSocket] WebM size: {len(self.full_audio_buffer)} bytes")
                except Exception as e:
                    print(f"[WebSocket] Error converting disconnect audio: {e}")
                    # Still save the WebM file
                    print(f"[WebSocket] WebM audio saved on disconnect: {full_webm_path}")

            except Exception as e:
                print(f"[WebSocket] Error saving full audio on disconnect: {e}")

        # Clean up temporary files
        for suffix in ['.wav', '.webm']:
            temp_file = self.temp_audio_file.replace('.wav', suffix) if self.temp_audio_file else None
            if temp_file and os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except Exception as e:
                    print(f"[WebSocket] Error cleaning up temp file {temp_file}: {e}")

        raise StopConsumer()

    async def receive(self, text_data=None, bytes_data=None):
        """Handle incoming WebSocket data"""
        try:
            if text_data:
                # Handle text messages (control commands)
                await self.receive_text(text_data)
            elif bytes_data:
                # Handle WebM/Opus audio data
                self.full_audio_buffer.extend(bytes_data)  # Save all audio for debugging
                print(f"[WebSocket] Received {len(bytes_data)} bytes of WebM audio data")

                # Feed WebM data to continuous ffmpeg process
                if self.ffmpeg_process and self.ffmpeg_process.stdin:
                    try:
                        self.ffmpeg_process.stdin.write(bytes_data)
                        await self.ffmpeg_process.stdin.drain()
                    except Exception as e:
                        print(f"[WebSocket] Error feeding data to ffmpeg: {e}")
                        # Try to restart ffmpeg process
                        await self.restart_continuous_ffmpeg()
                else:
                    print(f"[WebSocket] FFmpeg process not available, data lost")

        except Exception as e:
            print(f"[WebSocket] Error receiving data: {e}")
            import traceback
            print(f"[WebSocket] Traceback: {traceback.format_exc()}")
            await self.send_json({
                'type': 'error',
                'message': 'Error processing data'
            })

    async def restart_continuous_ffmpeg(self):
        """Restart continuous ffmpeg process if it died"""
        print("[WebSocket] Restarting continuous ffmpeg...")

        # Clean up existing process
        if self.ffmpeg_process:
            try:
                self.ffmpeg_process.terminate()
                await self.ffmpeg_process.wait()
            except:
                pass

        if self.ffmpeg_reader_task:
            self.ffmpeg_reader_task.cancel()
            try:
                await self.ffmpeg_reader_task
            except asyncio.CancelledError:
                pass

        # Reset buffers
        self.continuous_wav_buffer.clear()
        self.wav_chunk_ready.clear()

        # Start new process
        await self.start_continuous_ffmpeg()

    async def receive_text(self, text_data):
        """Handle incoming text messages (control commands)"""
        try:
            data = json.loads(text_data)

            if data.get('type') == 'start':
                # Start new recording session
                self.language = data.get('language', 'zh')
                self.recording_start_time = asyncio.get_event_loop().time()
                self.audio_buffer.clear()
                self.hypothesis_buffer = HypothesisBuffer()
                self.full_audio_buffer.clear()  # Clear full audio buffer
                self.session_id = f"realtime_{int(time.time() * 1000)}"  # Unique session ID
                self.chunk_count = 0  # Reset chunk count for new session
                self.sentence_buffer = ""  # Reset sentence buffer
                self.sentence_start_time = None  # Reset sentence start time
                self.sentence_end_time = None  # Reset sentence end time
                self.last_transcription_text = ""  # Reset last transcription text
                self.sentence_start_chunk = 0  # Reset sentence start chunk

                # Create temporary file for audio processing
                self.temp_audio_file = tempfile.NamedTemporaryFile(
                    suffix='.wav',
                    delete=False
                ).name

                # Start continuous ffmpeg processing
                await self.start_continuous_ffmpeg()

                # Start continuous WAV chunk processing task
                # Launch separate task to process buffered WAV data into transcription chunks
                asyncio.create_task(self.process_continuous_wav_chunks())

                print(f"[WebSocket] Recording session started: {self.session_id}")
                await self.send_json({
                    'type': 'started',
                    'language': self.language,
                    'message': 'Recording started'
                })

            elif data.get('type') == 'stop':
                # Stop recording and process remaining audio
                await self.stop_recording()

            elif data.get('type') == 'language_change':
                # Change language
                self.language = data.get('language', 'zh')
                await self.send_json({
                    'type': 'language_changed',
                    'language': self.language
                })

        except Exception as e:
            print(f"[WebSocket] Error receiving text: {e}")
            await self.send_json({
                'type': 'error',
                'message': 'Error processing command'
            })

    
    async def stop_recording(self):
        """Stop recording and process remaining audio"""
        # Process any remaining PCM data
        if hasattr(self, 'pcm_frames') and self.pcm_frames:
            remaining_pcm = bytes(self.pcm_frames)
            if len(remaining_pcm) >= 8000:  # Only process if enough data
                await self.transcribe_pcm_chunk(remaining_pcm)
            self.pcm_frames.clear()

        # Send any remaining incomplete sentence
        remaining_sentences = self.get_remaining_sentence()
        if remaining_sentences:
            await self.send_json({
                'type': 'transcription',
                'entries': remaining_sentences
            })

        # Save complete audio recording to work_dir for debugging
        if self.full_audio_buffer and self.session_id:
            try:
                work_dir = getattr(settings, 'WORK_DIR', 'work_dir')
                work_dir_path = Path(work_dir)
                work_dir_path.mkdir(exist_ok=True)

                # Create audio debug directory
                audio_debug_dir = work_dir_path / 'audio_debug'
                audio_debug_dir.mkdir(exist_ok=True)

                # Save complete WebM recording
                full_webm_path = audio_debug_dir / f"{self.session_id}_disconnect_recording.webm"
                with open(full_webm_path, 'wb') as f:
                    f.write(bytes(self.full_audio_buffer))

                # Also save converted WAV for debugging
                full_wav_path = audio_debug_dir / f"{self.session_id}_disconnect_recording.wav"
                try:
                    wav_data = self.convert_webm_to_wav(str(full_webm_path))
                    with open(full_wav_path, 'wb') as f:
                        f.write(wav_data)
                    print(f"[WebSocket] Disconnect audio saved: {full_webm_path} -> {full_wav_path}")
                    print(f"[WebSocket] WebM size: {len(self.full_audio_buffer)} bytes")
                except Exception as e:
                    print(f"[WebSocket] Error converting disconnect audio: {e}")
                    # Still save the WebM file
                    print(f"[WebSocket] WebM audio saved on disconnect: {full_webm_path}")

            except Exception as e:
                print(f"[WebSocket] Error saving full audio on disconnect: {e}")

        await self.send_json({
            'type': 'stopped',
            'message': 'Recording stopped'
        })

    def convert_webm_to_wav(self, webm_file_path):
        """Convert WebM/Opus audio to WAV format using pydub with format detection"""
        try:
            print(f"[WebSocket] Converting audio to WAV: {webm_file_path}")

            # Try different audio formats since browser might send various formats
            formats_to_try = ["webm", "ogg", "mp4", "wav", "opus"]
            audio = None
            used_format = None

            for fmt in formats_to_try:
                try:
                    audio = AudioSegment.from_file(webm_file_path, format=fmt)
                    used_format = fmt
                    print(f"[WebSocket] Successfully loaded as {fmt} format")
                    break
                except Exception as fmt_error:
                    print(f"[WebSocket] Failed to load as {fmt}: {str(fmt_error)[:50]}")
                    continue

            if audio is None:
                raise Exception("Could not determine audio format")

            # Convert to mono and set sample rate to 16kHz for Whisper
            audio = audio.set_channels(1)
            audio = audio.set_frame_rate(16000)

            # Export to WAV in memory
            wav_buffer = io.BytesIO()
            audio.export(wav_buffer, format="wav", parameters=["-ac", "1", "-ar", "16000"])

            wav_buffer.seek(0)
            wav_data = wav_buffer.read()

            print(f"[WebSocket] Audio conversion successful ({used_format} -> WAV). Size: {len(wav_data)} bytes")
            return wav_data

        except Exception as e:
            print(f"[WebSocket] Error converting audio: {e}")
            # Fallback: try with ffmpeg directly and suppress verbose output
            try:
                print(f"[WebSocket] Trying ffmpeg fallback...")
                process = (
                    ffmpeg
                    .input(webm_file_path)
                    .output('pipe:', format='wav', ac=1, ar=16000, loglevel='error')
                    .run_async(pipe_stdout=True, pipe_stderr=True)
                )

                out, _ = process.communicate()
                if process.returncode == 0 and out:
                    print(f"[WebSocket] FFmpeg fallback successful. Size: {len(out)} bytes")
                    return out
                else:
                    raise Exception("FFmpeg fallback returned empty or failed")

            except Exception:
                print(f"[WebSocket] All conversion methods failed")
                raise Exception(f"Audio conversion failed: {e}")

    def convert_to_wav(self, raw_audio_data):
        """Convert raw audio data to WAV format (deprecated, kept for compatibility)"""
        # This function is no longer used since we're using WebM format
        # Keeping it for backward compatibility
        sample_rate = 16000
        channels = 1
        sample_width = 2

        # Create WAV file in memory
        wav_buffer = io.BytesIO()

        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(sample_width)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(raw_audio_data)

        wav_buffer.seek(0)
        return wav_buffer.read()

    def transcribe_audio(self, audio_file_path):
        """Transcribe audio file using real-time engine with sentence segmentation"""
        print(f"[WebSocket] transcribe_audio called with: {audio_file_path}")

        # Check if file exists
        import os
        if not os.path.exists(audio_file_path):
            print(f"[WebSocket] ERROR: Audio file does not exist: {audio_file_path}")
            return None

        print(f"[WebSocket] Audio file size: {os.path.getsize(audio_file_path)} bytes")

        try:
            from asr_utils.transcription_engine import transcribe_with_engine
            from asr_utils.transcription_engine import load_transcription_settings

            def real_progress_callback(message):
                print(f"[WebSocket] Transcription progress: {message}")

            # Force Chinese language for better results
            transcription_language = 'zh' if self.language == 'zh' else 'en'
            print(f"[WebSocket] Using language: {transcription_language}")

            transcription_settings = load_transcription_settings()
            engine_settings = transcription_settings.get("Transcription Engine", {})
            primary_engine = engine_settings.get("primary_engine", "funasr_gguf")
            print(f"[WebSocket] Using transcription engine: {primary_engine}")

            print(f"[WebSocket] Starting transcription...")
            srt_content = transcribe_with_engine(
                engine_type=primary_engine,
                audio_file_path=audio_file_path,
                progress_cb=real_progress_callback,
                language=transcription_language,
            )
            print(f"[WebSocket] transcribe_with_engine returned, length: {len(srt_content) if srt_content else 0}")

            if srt_content:
                print(f"[WebSocket] Transcription successful, {len(srt_content)} characters")
                print(f"[WebSocket] First 100 chars: {srt_content[:100]}")
            else:
                print(f"[WebSocket] Transcription returned empty result")

            return srt_content
        except Exception as e:
            print(f"[WebSocket] Transcription error: {e}")
            import traceback
            print(f"[WebSocket] Traceback: {traceback.format_exc()}")
            return None

    def parse_srt_entries(self, srt_content):
        """Parse SRT content and return entry list"""
        entries = []

        try:
            print(f"[WebSocket] Parsing SRT content ({len(srt_content)} characters)")
            lines = srt_content.strip().split('\n')
            print(f"[WebSocket] SRT has {len(lines)} lines")

            i = 0
            entry_count = 0

            while i < len(lines):
                if lines[i].strip().isdigit():
                    # Entry number
                    index = int(lines[i].strip())
                    i += 1

                    if i < len(lines) and '-->' in lines[i]:
                        # Timestamp line
                        timestamp_line = lines[i].strip()
                        start_time, end_time = timestamp_line.split(' --> ')
                        i += 1

                        # Collect text lines
                        text_lines = []
                        while i < len(lines) and lines[i].strip():
                            text_lines.append(lines[i].strip())
                            i += 1

                        if text_lines:
                            text = ' '.join(text_lines)
                            entries.append({
                                'index': index,
                                'start': start_time,
                                'end': end_time,
                                'text': text
                            })
                            entry_count += 1
                            print(f"[WebSocket] Parsed entry {entry_count}: [{start_time}] {text}")

                i += 1

            print(f"[WebSocket] SRT parsing complete: {entry_count} entries extracted")

        except Exception as e:
            print(f"[WebSocket] Error parsing SRT: {e}")
            import traceback
            print(f"[WebSocket] SRT traceback: {traceback.format_exc()}")

        return entries

    def parse_srt_entries_with_offset(self, srt_content):
        """Parse SRT content and add time offset to entries"""
        entries = self.parse_srt_entries(srt_content)

        if not entries:
            return entries

        # Calculate time offset in seconds (use current chunk count before increment)
        offset_seconds = self.chunk_count * self.chunk_duration_seconds

        print(f"[WebSocket] Applying {offset_seconds}s offset to {len(entries)} entries (chunk #{self.chunk_count})")

        # Function to convert SRT timestamp to seconds and back
        def srt_timestamp_to_seconds(timestamp):
            """Convert SRT timestamp HH:MM:SS,mmm to seconds"""
            time_part, ms_part = timestamp.split(',')
            h, m, s = map(int, time_part.split(':'))
            ms = int(ms_part)
            return h * 3600 + m * 60 + s + ms / 1000.0

        def seconds_to_srt_timestamp(seconds):
            """Convert seconds to SRT timestamp HH:MM:SS,mmm"""
            h = int(seconds // 3600)
            seconds %= 3600
            m = int(seconds // 60)
            seconds %= 60
            s = int(seconds)
            ms = int((seconds - s) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        # Apply offset to each entry
        for entry in entries:
            # Convert timestamps to seconds
            start_seconds = srt_timestamp_to_seconds(entry['start'])
            end_seconds = srt_timestamp_to_seconds(entry['end'])

            # Add offset
            start_seconds += offset_seconds
            end_seconds += offset_seconds

            # Convert back to SRT format
            entry['start'] = seconds_to_srt_timestamp(start_seconds)
            entry['end'] = seconds_to_srt_timestamp(end_seconds)

            print(f"[WebSocket] Adjusted entry timing: {entry['start']} - {entry['end']}")

        return entries

    def is_sentence_complete(self, text):
        """Check if text forms a complete sentence"""
        # Chinese sentence ending punctuation
        chinese_endings = {'。', '！', '？', '；', '…'}
        # English sentence ending punctuation
        english_endings = {'.', '!', '?', ';'}

        # Remove whitespace and check last character
        text_stripped = text.strip()
        if not text_stripped:
            return False

        last_char = text_stripped[-1]
        return last_char in chinese_endings or last_char in english_endings

    def add_to_sentence_buffer(self, text, start_time, end_time):
        """Add transcription text to sentence buffer and return complete sentences"""
        if not text.strip():
            return []

        # Initialize sentence start time if this is the first fragment
        if self.sentence_start_time is None:
            self.sentence_start_time = start_time
            self.sentence_start_chunk = self.chunk_count

        # Smart duplicate detection: only skip if it's the same AND from the same chunk
        current_chunk = self.chunk_count
        text_stripped = text.strip()
        last_text_stripped = self.last_transcription_text.strip()

        if (text_stripped == last_text_stripped and
            hasattr(self, 'last_transcription_chunk') and
            current_chunk == self.last_transcription_chunk):
            print(f"[WebSocket] Skipping duplicate transcription (same chunk {current_chunk}): '{text}'")
            return []

        self.last_transcription_text = text
        self.last_transcription_chunk = current_chunk

        # Add text to buffer
        self.sentence_buffer += text

        # Update end time to always use the latest timestamp
        self.sentence_end_time = end_time

        # Force sentence completion conditions:
        # 1. Has ending punctuation
        # 2. Buffer is too long (> 50 characters)
        # 3. Time window is too long (> 10 seconds)
        # 4. Too many chunks (> 15 chunks)
        buffer_length = len(self.sentence_buffer.strip())
        time_duration = (self.chunk_count - self.sentence_start_chunk) * self.chunk_duration_seconds
        chunk_duration = self.chunk_count - self.sentence_start_chunk

        should_complete = (
            self.is_sentence_complete(self.sentence_buffer) or
            buffer_length > 50 or
            time_duration > 10 or
            chunk_duration > 15
        )

        complete_sentences = []
        if should_complete:
            # Create complete sentence entry with correct timestamps
            sentence_text = self.sentence_buffer.strip()
            complete_sentences.append({
                'index': 1,  # Will be updated by sender
                'start': self.sentence_start_time,
                'end': self.sentence_end_time,
                'text': sentence_text
            })

            reason = "punctuation" if self.is_sentence_complete(self.sentence_buffer) else \
                    f"length({buffer_length})" if buffer_length > 50 else \
                    f"time({time_duration:.1f}s)" if time_duration > 10 else \
                    f"chunks({chunk_duration})"

            print(f"[WebSocket] Sentence completed ({reason}): '{sentence_text}' [{self.sentence_start_time} - {self.sentence_end_time}]")

            # Reset buffer for next sentence
            self.sentence_buffer = ""
            self.sentence_start_time = None
            self.sentence_end_time = None
            self.sentence_start_chunk = 0
        else:
            print(f"[WebSocket] Added to buffer: '{text}' (buffer: '{self.sentence_buffer}', length: {buffer_length}, time: {time_duration:.1f}s)")

        return complete_sentences

    def get_remaining_sentence(self):
        """Get any remaining incomplete sentence from buffer"""
        if self.sentence_buffer.strip():
            remaining_sentence = {
                'index': 1,
                'start': self.sentence_start_time or "00:00:00,000",
                'end': self.sentence_end_time or self.format_timestamp(self.chunk_count * self.chunk_duration_seconds),
                'text': self.sentence_buffer.strip()
            }

            print(f"[WebSocket] Final incomplete sentence: {remaining_sentence['text']} [{remaining_sentence['start']} - {remaining_sentence['end']}]")
            return [remaining_sentence]
        return []

    def format_timestamp(self, seconds):
        """Format seconds as SRT timestamp"""
        h = int(seconds // 3600)
        seconds %= 3600
        m = int(seconds // 60)
        seconds %= 60
        s = int(seconds)
        ms = int((seconds - s) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    async def send_json(self, data):
        """Send JSON data to WebSocket client"""
        await self.send(text_data=json.dumps(data))
