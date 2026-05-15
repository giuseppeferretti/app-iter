"""
Verificação de atualização do App Iter.

Comportamento:
  - No boot do app, roda em thread separada (não bloqueia UI)
  - Consulta a API do GitHub Releases (cache local de 12h pra não estourar
    rate limit)
  - Se a versão remota > VERSAO local, expõe `update_disponivel` com info
    pra UI mostrar dialog

API pública:
  - checar_atualizacao_em_background(versao_atual, callback)
  - comparar_versoes(a, b) -> int  (-1, 0, 1)
"""
import json
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from app.core.logger import get_logger

log = get_logger()

GITHUB_API = "https://api.github.com/repos/giuseppeferretti/app-iter/releases/latest"
DOWNLOAD_URL_TEMPLATE = (
    "https://github.com/giuseppeferretti/app-iter/releases/download/{tag}/AppIter_Setup.exe"
)
CACHE_TTL_SEG = 12 * 3600  # 12h — não sobrecarrega rate limit do GitHub


@dataclass
class InfoUpdate:
    versao_remota: str       # ex.: "0.1.3"
    tag_remota: str          # ex.: "v0.1.3"
    download_url: str
    release_url: str
    notes: str


def _cache_path() -> Path:
    base = Path(os.environ.get("APPDATA", str(Path.home() / ".iter")))
    pasta = base / "Iter" / "AppAnac" / "cache"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta / "update_check.json"


def _ler_cache() -> Optional[dict]:
    try:
        f = _cache_path()
        if not f.exists():
            return None
        with open(f, encoding="utf-8") as h:
            data = json.load(h)
        if time.time() - data.get("ts", 0) > CACHE_TTL_SEG:
            return None
        return data
    except Exception:
        return None


def _gravar_cache(payload: dict) -> None:
    try:
        with open(_cache_path(), "w", encoding="utf-8") as h:
            json.dump({"ts": time.time(), **payload}, h)
    except Exception as exc:
        log.debug(f"Falha ao gravar cache de update: {exc}")


def comparar_versoes(a: str, b: str) -> int:
    """Compara versões semver simples 'X.Y.Z' (ou 'vX.Y.Z'). Retorna -1, 0, 1."""
    def norm(v: str) -> tuple[int, ...]:
        v = v.strip().lstrip("v")
        partes: list[int] = []
        for p in v.split("."):
            digitos = "".join(c for c in p if c.isdigit())
            partes.append(int(digitos) if digitos else 0)
        # pad pra 3
        while len(partes) < 3:
            partes.append(0)
        return tuple(partes[:3])

    na, nb = norm(a), norm(b)
    if na < nb:
        return -1
    if na > nb:
        return 1
    return 0


def _buscar_latest_remoto() -> Optional[dict]:
    """GET na API do GitHub. Retorna o JSON do release ou None."""
    try:
        req = urllib.request.Request(
            GITHUB_API,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "App-Iter-Updater",
            },
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ConnectionError,
            json.JSONDecodeError, OSError) as exc:
        log.debug(f"Falha ao buscar update no GitHub: {exc}")
        return None


def _ver_update_disponivel(versao_local: str) -> Optional[InfoUpdate]:
    """Consulta cache + API. Retorna InfoUpdate se há nova versão."""
    cache = _ler_cache()
    if cache and cache.get("tag_remota"):
        tag = cache["tag_remota"]
        versao_remota = tag.lstrip("v")
        if comparar_versoes(versao_local, versao_remota) >= 0:
            return None
        return InfoUpdate(
            versao_remota=versao_remota,
            tag_remota=tag,
            download_url=cache.get("download_url", ""),
            release_url=cache.get("release_url", ""),
            notes=cache.get("notes", ""),
        )

    dados = _buscar_latest_remoto()
    if not dados:
        return None

    tag = dados.get("tag_name") or ""
    if not tag:
        return None
    versao_remota = tag.lstrip("v")
    release_url = dados.get("html_url") or ""
    notes = (dados.get("body") or "")[:500]
    download_url = DOWNLOAD_URL_TEMPLATE.format(tag=tag)

    _gravar_cache({
        "tag_remota": tag,
        "download_url": download_url,
        "release_url": release_url,
        "notes": notes,
    })

    if comparar_versoes(versao_local, versao_remota) >= 0:
        return None

    return InfoUpdate(
        versao_remota=versao_remota,
        tag_remota=tag,
        download_url=download_url,
        release_url=release_url,
        notes=notes,
    )


def checar_atualizacao_em_background(
    versao_atual: str,
    callback: Callable[[InfoUpdate], None],
    atraso_seg: float = 4.0,
) -> None:
    """Roda a checagem em thread daemon após pequeno atraso.

    `callback` é chamado SÓ se há update disponível. UI usa pra mostrar
    o dialog. Se a checagem falhar (offline, GitHub fora), silencia.
    """
    def _alvo():
        try:
            time.sleep(atraso_seg)
            info = _ver_update_disponivel(versao_atual)
            if info is not None:
                log.info(
                    f"Update disponível: {versao_atual} -> {info.versao_remota} "
                    f"({info.download_url})"
                )
                callback(info)
            else:
                log.debug(f"App Iter está atualizado (v{versao_atual}).")
        except Exception as exc:
            log.warning(f"Update check falhou: {exc}")

    threading.Thread(target=_alvo, daemon=True).start()
