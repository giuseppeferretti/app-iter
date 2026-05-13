"""
Cache local de sessao Supabase criptografado com Fernet.

A chave de criptografia e derivada do machine_id do Windows (UUID via registro),
fazendo o cache nao-portavel entre maquinas — copiar a pasta pra outro PC nao
da acesso liberado.

Arquivo: %APPDATA%/Iter/AppAnac/session.cache
"""
import base64
import hashlib
import json
import os
import winreg
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.core.logger import get_logger

log = get_logger()


@dataclass
class SessaoIter:
    """Sessao Supabase persistida localmente."""
    email: str
    access_token: str            # JWT curto (~1h), usado nas queries autenticadas
    refresh_token: str           # Longo (~30d), usado pra renovar access_token
    expires_at: datetime         # quando access_token expira
    proxima_revalidacao: datetime  # quando re-checar status de assinatura


def _cache_path() -> Path:
    base = Path(os.environ.get("APPDATA", Path.home() / ".iter"))
    p = base / "Iter" / "AppAnac"
    p.mkdir(parents=True, exist_ok=True)
    return p / "session.cache"


def _machine_id() -> str:
    """UUID estavel da maquina via registro do Windows."""
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            machine_guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(machine_guid)
    except OSError:
        return os.environ.get("COMPUTERNAME", "unknown") + os.environ.get("USERNAME", "")


def _fernet() -> Fernet:
    mid = _machine_id().encode("utf-8")
    chave = base64.urlsafe_b64encode(hashlib.sha256(mid).digest())
    return Fernet(chave)


def salvar_sessao(sessao: SessaoIter) -> None:
    """Serializa e criptografa a sessao no disco."""
    payload = {
        "email": sessao.email,
        "access_token": sessao.access_token,
        "refresh_token": sessao.refresh_token,
        "expires_at": sessao.expires_at.isoformat(),
        "proxima_revalidacao": sessao.proxima_revalidacao.isoformat(),
    }
    blob = _fernet().encrypt(json.dumps(payload).encode("utf-8"))
    _cache_path().write_bytes(blob)
    log.debug("Sessao Iter salva localmente.")


def ler_sessao() -> Optional[SessaoIter]:
    """Le e decripta a sessao. None se nao existir ou estiver corrompida."""
    p = _cache_path()
    if not p.exists():
        return None
    try:
        payload = json.loads(_fernet().decrypt(p.read_bytes()).decode("utf-8"))
        return SessaoIter(
            email=payload["email"],
            access_token=payload["access_token"],
            refresh_token=payload["refresh_token"],
            expires_at=datetime.fromisoformat(payload["expires_at"]),
            proxima_revalidacao=datetime.fromisoformat(payload["proxima_revalidacao"]),
        )
    except (InvalidToken, ValueError, KeyError):
        log.warning("Cache de sessao corrompido ou de outra maquina.")
        return None


def limpar_sessao() -> None:
    """Remove a sessao local (logout)."""
    p = _cache_path()
    if p.exists():
        p.unlink()
