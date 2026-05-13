"""
Continuar de onde parou: se um batch foi interrompido, oferecer retomar.

Durante o batch, a cada linha processada com sucesso, atualizamos o state.json
com o indice atual. Se o usuario fechar o app no meio, ao reabrir o app
oferece "Continuar do item N".

Arquivo: %APPDATA%/Iter/AppAnac/state.json
"""
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


def _state_path() -> Path:
    base = Path(os.environ.get("APPDATA", Path.home() / ".iter"))
    p = base / "Iter" / "AppAnac"
    p.mkdir(parents=True, exist_ok=True)
    return p / "state.json"


@dataclass
class EstadoBatch:
    caminho_planilha: str
    hash_planilha: str
    total_linhas: int
    proxima_linha: int           # indice (0-based) da proxima a processar
    atualizado_em: str           # ISO datetime


def salvar_estado(estado: EstadoBatch) -> None:
    _state_path().write_text(json.dumps(asdict(estado), indent=2), encoding="utf-8")


def ler_estado() -> Optional[EstadoBatch]:
    p = _state_path()
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return EstadoBatch(**d)
    except (json.JSONDecodeError, TypeError):
        return None


def limpar_estado() -> None:
    """Limpa apos batch finalizado com sucesso."""
    p = _state_path()
    if p.exists():
        p.unlink()
