"""Custom exceptions for TTS services."""


class TTSServiceError(Exception):
    """Base exception for TTS service errors."""

    pass


class TTSModelNotFoundError(TTSServiceError):
    """Raised when Piper model files are missing."""

    def __init__(self, model_path: str) -> None:
        super().__init__(f"TTS model not found: {model_path}")
        self.model_path = model_path


class TTSSynthesisError(TTSServiceError):
    """Raised when synthesis fails."""

    pass


class TTSConnectionError(TTSServiceError):
    """Raised when unable to connect to TTS service (Edge TTS)."""

    pass


class TTSResamplingError(TTSServiceError):
    """Raised when audio resampling fails."""

    pass
