import time
import logging
import threading
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

# Configure a basic logger if not already configured
logger = logging.getLogger(__name__)

class BaseTask(ABC):
    """
    Base class for all asynchronous tasks in VidGo.
    Encapsulates status tracking, progress updates, logging, and error handling.
    """

    def __init__(self, task_id: str, task_type: str):
        self.task_id = task_id
        self.task_type = task_type
        self.status = "Queued"  # Queued, Running, Completed, Failed
        self.progress = 0
        self.created_at = time.time()
        self.error_message = ""
        self.stages: Dict[str, str] = {}
        self.stage_progress: Dict[str, int] = {}
        self.stage_weights: Dict[str, float] = {}
        self._lock = threading.RLock()

    def update_status(self, status: str, progress: Optional[int] = None, error_message: str = ""):
        """Thread-safe status update."""
        with self._lock:
            self.status = status
            if progress is not None:
                self.progress = min(100, max(0, progress))
            if status == "Completed":
                self.progress = 100
            if error_message:
                self.error_message = error_message
            
            self.log(f"Status updated to {status} ({self.progress}%)")

    def update_stage(self, stage: str, status: str, progress: Optional[int] = None):
        """Update a specific stage and recalculate total progress based on weights."""
        with self._lock:
            if stage not in self.stages:
                self.stages[stage] = "Queued"
                self.stage_progress[stage] = 0
            
            self.stages[stage] = status
            
            if progress is not None:
                self.stage_progress[stage] = min(100, max(0, progress))
            elif status == "Completed":
                self.stage_progress[stage] = 100
            elif status == "Running" and self.stage_progress[stage] == 0:
                self.stage_progress[stage] = 1 # Indicate start
            
            # Recalculate total progress if weights are defined
            if self.stage_weights:
                total = sum(
                    self.stage_weights.get(s, 0) * self.stage_progress.get(s, 0)
                    for s in self.stage_progress
                )
                # Normalize total progress (assuming weights sum to roughly 1.0 or 100)
                weight_sum = sum(self.stage_weights.values())
                if weight_sum > 0:
                    if weight_sum <= 1.0:
                        self.progress = int(total * 100) # Weights are 0.4, 0.3, etc.
                    else:
                        self.progress = int(total) # Weights are 40, 30, etc.
                else:
                    self.progress = int(total) # Fallback
                
                self.log(f"Stage '{stage}' -> {status}. Total Progress: {self.progress}%")

    def fail(self, error: Exception):
        """Mark task as failed with an exception."""
        self.update_status("Failed", error_message=str(error))
        self.log(f"Task Failed: {error}", level="error")

    def log(self, message: str, level: str = "info"):
        """Unified logging method."""
        msg = f"[{self.task_type}][{self.task_id}] {message}"
        if level.lower() == "error":
            logger.error(msg)
            print(f"[ERROR] {msg}") # Fallback for immediate console visibility
        else:
            logger.info(msg)
            print(f"[INFO] {msg}")

    @abstractmethod
    def run(self):
        """Core logic of the task. Must be implemented by subclasses."""
        pass

    def to_dict(self) -> Dict[str, Any]:
        """Serialize task state for JSON API responses."""
        with self._lock:
            return {
                "task_id": self.task_id,
                "type": self.task_type,
                "status": self.status,
                "progress": self.progress,
                "created_at": self.created_at,
                "error_message": self.error_message,
                "stages": self.stages,
                "stage_progress": self.stage_progress,
                # Add subclass specific data handling here or via override
            }

# Example concrete implementation for TTS Task
class TTSTask(BaseTask):
    def __init__(self, task_id: str, video_id: int, language: str, voice: str):
        super().__init__(task_id, "TTS")
        self.video_id = video_id
        self.language = language
        self.voice = voice
        self.output_file = ""
        # Initialize specific fields seen in tts_task_status
        self.total_segments = 0
        self.completed_segments = 0

    def run(self):
        try:
            self.update_status("Running", 5)
            # ... Logic from generate_tts_audio would go here ...
            self.log("Simulating TTS generation...")
            time.sleep(1) # Simulate work
            self.update_status("Completed")
        except Exception as e:
            self.fail(e)

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "video_id": self.video_id,
            "language": self.language,
            "voice": self.voice,
            "output_file": self.output_file,
            "total_segments": self.total_segments,
            "completed_segments": self.completed_segments
        })
        return data
