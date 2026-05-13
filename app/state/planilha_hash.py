"""
Histórico de sessões executadas + idempotência por hash da planilha.

Persiste em %APPDATA%/Iter/AppAnac/planilhas_processadas.json. Cada entrada
representa UMA sessão (= uma execução completa do lote, mesmo que cancelada
ou com 0 sucessos).

Esquema atual (cada entrada):
  hash          — SHA-256 do conteúdo da planilha (idempotência)
  nome          — nome do arquivo (ex: "HR.xlsx")
  linhas        — alias legado de "sucessos" (mantido pra compat)
  identificados — total de lançamentos válidos detectados
  sucessos      — quantos foram lançados com sucesso no SACI
  falhas        — quantos falharam
  duracao_seg   — duração total do lote em segundos
  cancelado     — bool: True se o usuário interrompeu o lote
  quando        — datetime ISO 8601 (UTC) da execução

Leitor tolerante: entradas legacy (só hash/nome/linhas/quando) ganham
defaults razoáveis.
"""
import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _historico_path() -> Path:
    base = Path(os.environ.get("APPDATA", Path.home() / ".iter"))
    p = base / "Iter" / "AppAnac"
    p.mkdir(parents=True, exist_ok=True)
    return p / "planilhas_processadas.json"


def calcular_hash(caminho_planilha: str) -> str:
    """SHA-256 hex do conteúdo da planilha."""
    h = hashlib.sha256()
    with open(caminho_planilha, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class HistoricoEntrada:
    """Uma sessão registrada no histórico."""
    hash_planilha: str
    nome_arquivo: str
    quando: datetime
    identificados: int = 0
    sucessos: int = 0
    falhas: int = 0
    duracao_seg: float = 0.0
    cancelado: bool = False

    # Legacy: alguns consumidores usam "linhas_processadas" — propriedade
    # calculada baseada em sucessos pra não quebrar.
    @property
    def linhas_processadas(self) -> int:
        return self.sucessos


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _parse_quando(raw: str) -> datetime:
    """Aceita ISO com ou sem tz (entradas legacy não tinham tz)."""
    try:
        dt = datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return _agora()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _ler_historico_raw() -> List[Dict[str, Any]]:
    p = _historico_path()
    if not p.exists():
        return []
    try:
        dados = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(dados, list):
            return dados
    except (json.JSONDecodeError, OSError):
        pass
    return []


def _ler_historico() -> List[HistoricoEntrada]:
    """Lê e converte. Tolera entradas legacy (sem campos novos)."""
    entradas: List[HistoricoEntrada] = []
    for d in _ler_historico_raw():
        try:
            linhas = int(d.get("linhas", 0))
            identificados = int(d.get("identificados", linhas))
            sucessos = int(d.get("sucessos", linhas))
            entradas.append(HistoricoEntrada(
                hash_planilha=d["hash"],
                nome_arquivo=d["nome"],
                quando=_parse_quando(d["quando"]),
                identificados=identificados,
                sucessos=sucessos,
                falhas=int(d.get("falhas", 0)),
                duracao_seg=float(d.get("duracao_seg", 0.0)),
                cancelado=bool(d.get("cancelado", False)),
            ))
        except (KeyError, ValueError, TypeError):
            continue
    return entradas


def _salvar_historico(entradas: List[HistoricoEntrada]) -> None:
    dados = [
        {
            "hash": e.hash_planilha,
            "nome": e.nome_arquivo,
            "linhas": e.sucessos,        # legacy alias
            "identificados": e.identificados,
            "sucessos": e.sucessos,
            "falhas": e.falhas,
            "duracao_seg": e.duracao_seg,
            "cancelado": e.cancelado,
            "quando": e.quando.isoformat(),
        }
        for e in entradas
    ]
    _historico_path().write_text(
        json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ── API pública ──────────────────────────────────────────────────────────────


def buscar_processamento_anterior(caminho_planilha: str) -> Optional[HistoricoEntrada]:
    """Retorna a entrada de histórico se essa planilha já foi processada."""
    hash_atual = calcular_hash(caminho_planilha)
    for entrada in _ler_historico():
        if entrada.hash_planilha == hash_atual:
            return entrada
    return None


def registrar_sessao(
    caminho: str,
    identificados: int,
    sucessos: int,
    falhas: int,
    duracao_seg: float,
    cancelado: bool = False,
) -> None:
    """
    Adiciona uma sessão ao histórico. Chamada SEMPRE que o lote termina —
    inclusive quando cancelado ou com 0 sucessos. Mantém até 50 entradas
    mais recentes.
    """
    historico = _ler_historico()
    historico.append(HistoricoEntrada(
        hash_planilha=calcular_hash(caminho),
        nome_arquivo=Path(caminho).name,
        quando=_agora(),
        identificados=identificados,
        sucessos=sucessos,
        falhas=falhas,
        duracao_seg=duracao_seg,
        cancelado=cancelado,
    ))
    _salvar_historico(historico[-50:])


def registrar_processamento(caminho_planilha: str, linhas_processadas: int) -> None:
    """
    Wrapper de compatibilidade. Equivale a registrar_sessao com defaults pros
    novos campos. Mantido pra não quebrar consumidores antigos.
    """
    registrar_sessao(
        caminho=caminho_planilha,
        identificados=linhas_processadas,
        sucessos=linhas_processadas,
        falhas=0,
        duracao_seg=0.0,
        cancelado=False,
    )


def listar_sessoes(limite: int = 50) -> List[HistoricoEntrada]:
    """
    Retorna o histórico em ordem decrescente de `quando` (mais recente primeiro).
    Trunca em `limite` entradas.
    """
    entradas = _ler_historico()
    entradas.sort(key=lambda e: e.quando, reverse=True)
    return entradas[:limite]
