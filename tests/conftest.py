"""Configuración compartida de la suite."""

from __future__ import annotations

import pathlib

import pytest

from whisperkey import history


@pytest.fixture(autouse=True)
def historial_aislado(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    """Redirige el historial a un directorio temporal en TODOS los tests.

    history.py resuelve su ruta al importarse, a partir de Path.home(), así que
    cualquier test que ejerza el worker real escribía dictados de prueba en el
    historial verdadero del usuario: aparecían "hola mundo" y "integrated test
    result" mezclados con sus transcripciones. El aislamiento va acá, en un
    fixture autouse, para que no dependa de que cada test se acuerde.
    """
    directorio = tmp_path / "whisperkey-home"
    directorio.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(history, "_HISTORY_DIR", directorio)
    monkeypatch.setattr(history, "_HISTORY_FILE", directorio / "history.jsonl")
    return directorio
