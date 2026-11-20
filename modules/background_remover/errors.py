"""Error khusus Background Remover. Semua pesan aman ditampilkan kepada pengguna."""

from __future__ import annotations

from core.tasks import UserMessageError


class BackgroundRemoverError(UserMessageError):
    pass


class ModelNotAvailableError(BackgroundRemoverError):
    pass


class ModelInvalidError(BackgroundRemoverError):
    pass


class InsufficientMemoryError(BackgroundRemoverError):
    pass


class UnsupportedImageError(BackgroundRemoverError):
    pass


class ProcessingError(BackgroundRemoverError):
    pass
