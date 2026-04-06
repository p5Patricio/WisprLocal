"""AppState: estado compartido entre threads."""

from __future__ import annotations

import gc
import queue
import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AppState:
    ptt_active: bool = False
    toggle_active: bool = False
    model: Any = None
    is_loading: bool = False
    audio_queue: queue.Queue = field(default_factory=queue.Queue)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def is_recording(self) -> bool:
        return self.ptt_active or self.toggle_active

    def set_model(self, model: Any) -> None:
        with self.lock:
            self.model = model

    def clear_model(self) -> None:
        import torch

        with self.lock:
            self.model = None
        gc.collect()
        torch.cuda.empty_cache()
        torch.cuda.synchronize()
