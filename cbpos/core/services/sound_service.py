"""
Sound feedback service for POS operations.

Generates simple WAV tones programmatically (no external audio files needed).
Respects the ``enable_sounds`` config setting.
"""

import atexit
import io
import logging
import math
import struct
import tempfile
import wave
from pathlib import Path
from typing import Dict, Optional

from cbpos.core.services.config_service import ConfigService

logger = logging.getLogger(__name__)

# Tone definitions: (frequency_hz, duration_ms, volume 0-1)
_TONE_DEFS: Dict[str, list] = {
    "scan_success": [(1200, 80, 0.4)],
    "scan_error": [(400, 150, 0.4), (300, 200, 0.4)],
    "payment_complete": [(800, 100, 0.35), (1000, 100, 0.35), (1200, 150, 0.35)],
    "error": [(350, 250, 0.4)],
}

_SAMPLE_RATE = 22050


def _generate_wav(tones: list) -> bytes:
    """Generate a WAV file in memory from a list of (freq, duration_ms, volume) tuples."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(_SAMPLE_RATE)

        for freq, duration_ms, volume in tones:
            num_samples = int(_SAMPLE_RATE * duration_ms / 1000)
            for i in range(num_samples):
                t = i / _SAMPLE_RATE
                value = volume * 32767 * math.sin(2 * math.pi * freq * t)
                wf.writeframes(struct.pack("<h", int(value)))

    return buf.getvalue()


class SoundService:
    """Plays short audio feedback sounds using QSoundEffect."""

    _cache: Dict[str, object] = {}
    _temp_dir: Optional[Path] = None
    _initialized: bool = False

    @classmethod
    def _ensure_init(cls) -> bool:
        """Lazily initialize sound files and QSoundEffect instances."""
        if cls._initialized:
            return bool(cls._cache)

        cls._initialized = True
        try:
            from PyQt6.QtMultimedia import QSoundEffect
            from PyQt6.QtCore import QUrl
        except ImportError:
            logger.debug("QSoundEffect not available — sounds disabled")
            return False

        try:
            cls._temp_dir = Path(tempfile.mkdtemp(prefix="cbpos_sounds_"))
            atexit.register(cls.shutdown)

            for name, tones in _TONE_DEFS.items():
                wav_path = cls._temp_dir / f"{name}.wav"
                wav_path.write_bytes(_generate_wav(tones))

                effect = QSoundEffect()
                effect.setSource(QUrl.fromLocalFile(str(wav_path)))
                effect.setLoopCount(1)
                effect.setVolume(0.7)
                cls._cache[name] = effect

            return True
        except Exception:
            logger.debug("Failed to initialize sounds", exc_info=True)
            return False

    @classmethod
    def shutdown(cls) -> None:
        """Remove the temporary sound directory and release resources."""
        cls._cache.clear()
        if cls._temp_dir and cls._temp_dir.exists():
            import shutil

            try:
                shutil.rmtree(cls._temp_dir)
                logger.debug("Cleaned up sound temp directory: %s", cls._temp_dir)
            except Exception:
                logger.warning("Failed to clean up sound temp dir", exc_info=True)
        cls._temp_dir = None
        cls._initialized = False

    @classmethod
    def play(cls, sound_name: str) -> None:
        """Play a named sound if sounds are enabled.

        Args:
            sound_name: One of ``scan_success``, ``scan_error``,
                        ``payment_complete``, ``error``.
        """
        if not ConfigService.get("enable_sounds"):
            return

        if not cls._ensure_init():
            return

        effect = cls._cache.get(sound_name)
        if effect is not None:
            try:
                effect.play()
            except Exception:
                logger.debug("Could not play sound %s", sound_name, exc_info=True)
