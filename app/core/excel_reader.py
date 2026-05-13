"""
Leitura e validacao da planilha de lancamentos CIV.

Diferencas vs versao CLI:
  - `caminho` recebido como parametro (UI fornece via filedialog)
  - Funcao `validar_planilha(caminho)` que valida TUDO antes de iniciar o batch
    e retorna lista de erros — UI mostra antes do usuario clicar Iniciar

Schema obrigatorio (uma linha = um lancamento CIV):
  data       — datetime, DD/MM/YYYY, YYYY-MM-DD ou serial Excel
  pousos     — 1-99
  matricula  — max 5 chars (ex: PTVZZ)
  origem     — ICAO 4 chars
  destino    — ICAO 4 chars
  horas      — HH:MM ou decimal

Opcionais:
  obs           — texto livre
  milhas_nav    — inteiro
  horas_nav     — HH:MM ou decimal
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from app.core import config
from app.core.logger import get_logger
from app.core.utils import (
    normalizar_codigo,
    normalizar_data_br,
    normalizar_hhmm,
    normalizar_icao,
)

log = get_logger()

COLUNAS_OBRIGATORIAS = ["data", "pousos", "matricula", "origem", "destino", "horas"]
COLUNAS_OPCIONAIS    = ["obs", "milhas_nav", "horas_nav"]


@dataclass
class ErroValidacao:
    """Erro encontrado durante a validacao previa da planilha."""
    linha: int      # numero da linha no Excel (2 = primeira linha de dados)
    coluna: str     # qual campo falhou
    valor: str      # valor original que falhou
    motivo: str     # descricao do problema


def _ler_dataframe(caminho: str) -> pd.DataFrame:
    """
    Lê a planilha sem amarrar o nome da aba.

    Estratégia:
      1. Tenta a aba `config.SHEET_NAME` (default "Plan1") se ela existir.
      2. Caso contrário, usa a primeira aba do arquivo — qualquer nome.

    Isso permite que o usuário renomeie a aba como quiser (ex.: "Voos",
    "CIV Março", "Sheet1") sem que o app reclame.
    """
    path = Path(caminho)
    if not path.exists():
        raise FileNotFoundError(f"Planilha não encontrada: {caminho}")

    try:
        xls = pd.ExcelFile(path, engine="openpyxl")
    except PermissionError:
        raise PermissionError(
            f"Planilha em uso. Feche o Excel e tente novamente: {caminho}"
        )

    nomes = xls.sheet_names
    if not nomes:
        raise ValueError("Planilha não contém nenhuma aba.")

    aba_alvo = config.SHEET_NAME if config.SHEET_NAME in nomes else nomes[0]
    log.info(
        f"Lendo aba '{aba_alvo}' ({len(nomes)} aba(s) disponível(is): {nomes})."
    )

    try:
        df = xls.parse(sheet_name=aba_alvo, dtype=str)
    except PermissionError:
        raise PermissionError(
            f"Planilha em uso. Feche o Excel e tente novamente: {caminho}"
        )

    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    return df


def validar_planilha(caminho: str) -> tuple[List[Dict[str, Any]], List[ErroValidacao]]:
    """
    Le e valida a planilha. Retorna (lancamentos_validos, erros).

    UI chama isso ANTES do batch — mostra erros pro usuario.
    """
    df = _ler_dataframe(caminho)

    faltando = [c for c in COLUNAS_OBRIGATORIAS if c not in df.columns]
    if faltando:
        raise ValueError(
            f"Colunas obrigatorias ausentes na planilha: {faltando}. "
            f"Encontradas: {list(df.columns)}"
        )

    lancamentos: List[Dict[str, Any]] = []
    erros: List[ErroValidacao] = []

    for idx, row in df.iterrows():
        linha_num = idx + 2

        # Linha completamente vazia → fim da tabela
        if all(pd.isna(row[c]) or str(row[c]).strip() == "" for c in COLUNAS_OBRIGATORIAS):
            log.info(f"Linha {linha_num}: em branco — fim da tabela.")
            break

        registro: Dict[str, Any] = {"linha_planilha": linha_num}
        valido = True

        # data
        try:
            registro["data"] = normalizar_data_br(row.get("data"))
        except ValueError as exc:
            erros.append(ErroValidacao(linha_num, "data", str(row.get("data", "")), str(exc)))
            valido = False

        # pousos
        pousos = normalizar_codigo(row.get("pousos"))
        if not pousos or not pousos.isdigit() or not (1 <= int(pousos) <= 99):
            erros.append(ErroValidacao(linha_num, "pousos", pousos, "deve ser 1-99"))
            valido = False
        registro["pousos"] = pousos

        # matricula
        matricula = normalizar_codigo(row.get("matricula")).upper()
        if not matricula or len(matricula) > 5:
            erros.append(ErroValidacao(linha_num, "matricula", matricula, "vazia ou > 5 chars"))
            valido = False
        registro["matricula"] = matricula

        # origem
        origem = normalizar_icao(row.get("origem"))
        if not origem or len(origem) > 4:
            erros.append(ErroValidacao(linha_num, "origem", origem, "ICAO invalido"))
            valido = False
        registro["origem"] = origem

        # destino
        destino = normalizar_icao(row.get("destino"))
        if not destino or len(destino) > 4:
            erros.append(ErroValidacao(linha_num, "destino", destino, "ICAO invalido"))
            valido = False
        registro["destino"] = destino

        # horas
        try:
            registro["horas"] = normalizar_hhmm(row.get("horas"))
        except ValueError as exc:
            erros.append(ErroValidacao(linha_num, "horas", str(row.get("horas", "")), str(exc)))
            valido = False

        # Opcionais
        def _opt(col: str) -> str:
            raw = row.get(col, "") if col in df.columns else ""
            return "" if pd.isna(raw) or str(raw).strip() in ("", "nan") else str(raw).strip()

        registro["obs"] = _opt("obs")

        milhas_nav_raw = _opt("milhas_nav")
        registro["milhas_nav"] = ""
        if milhas_nav_raw:
            try:
                registro["milhas_nav"] = str(int(float(milhas_nav_raw)))
            except ValueError:
                erros.append(ErroValidacao(linha_num, "milhas_nav", milhas_nav_raw, "nao e numero"))

        horas_nav_raw = _opt("horas_nav")
        registro["horas_nav"] = ""
        if horas_nav_raw:
            try:
                registro["horas_nav"] = normalizar_hhmm(horas_nav_raw)
            except ValueError as exc:
                erros.append(ErroValidacao(linha_num, "horas_nav", horas_nav_raw, str(exc)))

        if valido:
            lancamentos.append(registro)

    log.info(f"Validacao: {len(lancamentos)} lancamentos validos, {len(erros)} erro(s).")
    return lancamentos, erros


def ler_lancamentos(caminho: str) -> List[Dict[str, Any]]:
    """Atalho: valida e retorna apenas os lancamentos validos."""
    validos, _ = validar_planilha(caminho)
    if not validos:
        raise ValueError("Planilha sem lancamentos validos para processar.")
    return validos
