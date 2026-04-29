"""Jerarquía de excepciones propias de WisprLocal."""

from __future__ import annotations


class WisprError(Exception):
    """Excepción base para todos los errores de WisprLocal."""


class ModelLoadError(WisprError):
    """Error al cargar el modelo de Whisper."""


class TranscriptionError(WisprError):
    """Error durante la transcripción de audio."""


class AudioDeviceError(WisprError):
    """Error relacionado con el dispositivo de audio."""


class InjectionError(WisprError):
    """Error al inyectar texto en la aplicación activa."""
