"""
Leitura e validacao da planilha de lancamentos CIV.

Schema novo de 15 colunas — ordem espelha a tela SACI (bloco "Dados do vôo"
+ "Tempo de vôo"). Planilhas no formato antigo de 9 colunas são REJEITADAS
com mensagem clara apontando pro botão "Baixar template" do app.

Obrigatórios (sempre):
  data        — datetime, DD/MM/YYYY, YYYY-MM-DD ou serial Excel
  pousos      — 1-99
  funcao      — texto exato de FUNCOES_VALIDAS (config.py)
  matricula   — max 5 chars (ex: PTVZZ)
  origem      — ICAO 4 chars
  destino     — ICAO 4 chars

Condicionalmente obrigatórios:
  anac_aluno      — 8 dígitos. Obrigatório se funcao ∈ FUNCOES_INSTRUTOR; deve
                    estar vazio caso contrário.
  curso_comercial — "Sim"/"Não" (vazio = "Não"). Só aceita "Sim" se
                    funcao = "Piloto em Comando".

Condicionalmente: pelo menos UM de {diurno, noturno} preenchido por linha.

Opcionais (sempre):
  obs           — texto livre
  milhas_nav    — inteiro
  diurno        — HH:MM
  noturno       — HH:MM
  navegacao     — HH:MM
  instrumento   — HH:MM
  sob_capota    — HH:MM
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

# ── Schema completo ──────────────────────────────────────────────────────────
COLUNAS_OBRIGATORIAS = [
    "data", "pousos", "funcao", "matricula", "origem", "destino",
]
# Colunas que precisam estar presentes mesmo que opcionais — usadas pra
# detectar planilhas no formato antigo (9 colunas, sem funcao/noturno/etc.)
COLUNAS_NOVAS_OBRIGATORIAS_NO_HEADER = [
    "funcao", "anac_aluno", "curso_comercial",
    "diurno", "noturno", "navegacao", "instrumento", "sob_capota",
]
COLUNAS_OPCIONAIS = [
    "anac_aluno", "curso_comercial", "obs", "milhas_nav",
    "diurno", "noturno", "navegacao", "instrumento", "sob_capota",
]


@dataclass
class ErroValidacao:
    """Erro encontrado durante a validacao previa da planilha."""
    linha: int      # numero da linha no Excel (2 = primeira linha de dados)
    coluna: str     # qual campo falhou
    valor: str      # valor original que falhou
    motivo: str     # descricao do problema


def _ler_dataframe(caminho: str) -> pd.DataFrame:
    """
    Lê a planilha detectando dinamicamente a linha de cabeçalho.

    O template novo tem uma linha 1 com grupos visuais merged ("Dados do vôo",
    "Tempo de vôo") e a linha 2 com os nomes reais das colunas. Pandas por
    default usa a linha 0 como header — então precisamos procurar a linha que
    tem "DATA" na primeira célula e usar essa como header.

    Estratégia:
      1. Tenta a aba `config.SHEET_NAME` (default "Plan1") se ela existir,
         senão pega a primeira aba.
      2. Lê sem header, procura nas primeiras 5 linhas qual tem "DATA" na
         coluna 1. Usa essa como header.
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
        raw = xls.parse(sheet_name=aba_alvo, header=None, dtype=str)
    except PermissionError:
        raise PermissionError(
            f"Planilha em uso. Feche o Excel e tente novamente: {caminho}"
        )

    # Detecta a linha de cabeçalho: primeira linha onde a coluna 0 é "DATA"
    header_row = None
    for i in range(min(5, len(raw))):
        primeira = str(raw.iloc[i, 0]).strip().lower() if not pd.isna(raw.iloc[i, 0]) else ""
        if primeira == "data":
            header_row = i
            break

    if header_row is None:
        raise ValueError(
            "Não encontrei a linha de cabeçalho da planilha (esperava 'DATA' "
            "como primeira coluna). Baixe o template oficial pelo botão "
            "\"Baixar modelo\" no app."
        )

    df = xls.parse(sheet_name=aba_alvo, header=header_row, dtype=str)
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    return df


def _detectar_formato_antigo(colunas: list[str]) -> bool:
    """Retorna True se a planilha está no formato legado de 9 colunas."""
    return "horas" in colunas and "funcao" not in colunas


def _normalizar_sim_nao(valor: str) -> bool:
    """
    Converte texto pra bool. Aceita: "Sim"/"Não", "S"/"N", "1"/"0", "true"/"false".
    Vazio → False.
    """
    s = valor.strip().lower()
    if not s:
        return False
    return s in {"sim", "s", "1", "true", "yes", "y", "verdadeiro"}


def _opt(row: pd.Series, df_cols: list[str], col: str) -> str:
    """Lê valor opcional como string limpa (vazio se ausente/NaN)."""
    if col not in df_cols:
        return ""
    raw = row.get(col, "")
    if pd.isna(raw):
        return ""
    s = str(raw).strip()
    return "" if s.lower() in ("", "nan") else s


def validar_planilha(caminho: str) -> tuple[List[Dict[str, Any]], List[ErroValidacao]]:
    """
    Lê e valida a planilha. Retorna (lancamentos_validos, erros).
    UI chama isso ANTES do batch — mostra erros pro usuário.
    """
    df = _ler_dataframe(caminho)
    df_cols = list(df.columns)

    # ── Detecta formato antigo (9 colunas) e rejeita com mensagem clara ─────
    if _detectar_formato_antigo(df_cols):
        raise ValueError(
            "Formato de planilha antigo detectado (sem coluna FUNCAO). "
            "Baixe o novo template no app (botão \"Baixar modelo\") e refaça "
            "seu lançamento — o novo formato suporta Função a bordo, horas "
            "noturnas, instrumento real e sob capota."
        )

    faltando = [c for c in COLUNAS_OBRIGATORIAS if c not in df_cols]
    if faltando:
        raise ValueError(
            f"Colunas obrigatórias ausentes na planilha: {faltando}. "
            f"Encontradas: {df_cols}. Baixe o novo template no app."
        )

    lancamentos: List[Dict[str, Any]] = []
    erros: List[ErroValidacao] = []

    funcoes_validas_norm = {f.strip().lower(): f for f in config.FUNCOES_VALIDAS}

    for idx, row in df.iterrows():
        linha_num = idx + 2

        # Linha completamente vazia → fim da tabela
        if all(pd.isna(row[c]) or str(row[c]).strip() == "" for c in COLUNAS_OBRIGATORIAS):
            log.info(f"Linha {linha_num}: em branco — fim da tabela.")
            break

        registro: Dict[str, Any] = {"linha_planilha": linha_num}
        valido = True

        # ── data ────────────────────────────────────────────────────────────
        try:
            registro["data"] = normalizar_data_br(row.get("data"))
        except ValueError as exc:
            erros.append(ErroValidacao(linha_num, "data", str(row.get("data", "")), str(exc)))
            valido = False

        # ── pousos ──────────────────────────────────────────────────────────
        pousos = normalizar_codigo(row.get("pousos"))
        if not pousos or not pousos.isdigit() or not (1 <= int(pousos) <= 99):
            erros.append(ErroValidacao(linha_num, "pousos", pousos, "deve ser 1-99"))
            valido = False
        registro["pousos"] = pousos

        # ── funcao ──────────────────────────────────────────────────────────
        funcao_raw = _opt(row, df_cols, "funcao")
        funcao_match = funcoes_validas_norm.get(funcao_raw.lower())
        if not funcao_match:
            opcoes = " | ".join(config.FUNCOES_VALIDAS)
            erros.append(ErroValidacao(
                linha_num, "funcao", funcao_raw,
                f"Função inválida. Opções: {opcoes}"
            ))
            valido = False
            funcao_match = ""  # sentinela pra não quebrar validações condicionais
        registro["funcao"] = funcao_match

        # ── anac_aluno (condicional) ────────────────────────────────────────
        anac_aluno_raw = _opt(row, df_cols, "anac_aluno")
        # Excel pode salvar "12345678.0" se a coluna virou float — trim do .0
        anac_aluno = anac_aluno_raw[:-2] if anac_aluno_raw.endswith(".0") else anac_aluno_raw
        eh_instrutor = funcao_match in config.FUNCOES_INSTRUTOR
        if anac_aluno:
            if not anac_aluno.isdigit() or len(anac_aluno) > 8:
                erros.append(ErroValidacao(
                    linha_num, "anac_aluno", anac_aluno,
                    "deve ser numérico com até 8 dígitos"
                ))
                valido = False
            elif not eh_instrutor:
                erros.append(ErroValidacao(
                    linha_num, "anac_aluno", anac_aluno,
                    f"só pode ser preenchido para Funções de instrutor "
                    f"({', '.join(config.FUNCOES_INSTRUTOR)})"
                ))
                valido = False
        elif eh_instrutor:
            erros.append(ErroValidacao(
                linha_num, "anac_aluno", "",
                f"obrigatório para Função {funcao_match}"
            ))
            valido = False
        registro["anac_aluno"] = anac_aluno

        # ── curso_comercial (condicional) ───────────────────────────────────
        curso_raw = _opt(row, df_cols, "curso_comercial")
        curso_bool = _normalizar_sim_nao(curso_raw)
        if curso_bool and funcao_match != config.FUNCAO_PILOTO_COMANDO:
            erros.append(ErroValidacao(
                linha_num, "curso_comercial", curso_raw,
                f"Curso comercial só aplicável quando Função = "
                f"{config.FUNCAO_PILOTO_COMANDO}"
            ))
            valido = False
        registro["curso_comercial"] = curso_bool

        # ── matricula ───────────────────────────────────────────────────────
        matricula = normalizar_codigo(row.get("matricula")).upper()
        if not matricula or len(matricula) > 5:
            erros.append(ErroValidacao(linha_num, "matricula", matricula, "vazia ou > 5 chars"))
            valido = False
        registro["matricula"] = matricula

        # ── origem ──────────────────────────────────────────────────────────
        origem = normalizar_icao(row.get("origem"))
        if not origem or len(origem) > 4:
            erros.append(ErroValidacao(linha_num, "origem", origem, "ICAO inválido"))
            valido = False
        registro["origem"] = origem

        # ── destino ─────────────────────────────────────────────────────────
        destino = normalizar_icao(row.get("destino"))
        if not destino or len(destino) > 4:
            erros.append(ErroValidacao(linha_num, "destino", destino, "ICAO inválido"))
            valido = False
        registro["destino"] = destino

        # ── horas: diurno + noturno (pelo menos um) ─────────────────────────
        diurno_raw = _opt(row, df_cols, "diurno")
        noturno_raw = _opt(row, df_cols, "noturno")

        registro["diurno"] = ""
        if diurno_raw:
            try:
                registro["diurno"] = normalizar_hhmm(diurno_raw)
            except ValueError as exc:
                erros.append(ErroValidacao(linha_num, "diurno", diurno_raw, str(exc)))
                valido = False

        registro["noturno"] = ""
        if noturno_raw:
            try:
                registro["noturno"] = normalizar_hhmm(noturno_raw)
            except ValueError as exc:
                erros.append(ErroValidacao(linha_num, "noturno", noturno_raw, str(exc)))
                valido = False

        if not registro["diurno"] and not registro["noturno"]:
            erros.append(ErroValidacao(
                linha_num, "diurno/noturno", "",
                "pelo menos uma de Diurno ou Noturno precisa ter valor"
            ))
            valido = False

        # ── opcionais de tempo: navegacao, instrumento, sob_capota ──────────
        for col in ("navegacao", "instrumento", "sob_capota"):
            raw = _opt(row, df_cols, col)
            registro[col] = ""
            if raw:
                try:
                    registro[col] = normalizar_hhmm(raw)
                except ValueError as exc:
                    erros.append(ErroValidacao(linha_num, col, raw, str(exc)))
                    valido = False

        # ── obs (aceita tanto "OBSERVACOES" do novo template quanto "OBS" legado)
        registro["obs"] = _opt(row, df_cols, "observacoes") or _opt(row, df_cols, "obs")

        # ── milhas_nav ──────────────────────────────────────────────────────
        milhas_raw = _opt(row, df_cols, "milhas_nav")
        registro["milhas_nav"] = ""
        if milhas_raw:
            try:
                registro["milhas_nav"] = str(int(float(milhas_raw)))
            except ValueError:
                erros.append(ErroValidacao(linha_num, "milhas_nav", milhas_raw, "não é número"))
                valido = False

        if valido:
            lancamentos.append(registro)

    log.info(f"Validação: {len(lancamentos)} lançamentos válidos, {len(erros)} erro(s).")
    return lancamentos, erros


def ler_lancamentos(caminho: str) -> List[Dict[str, Any]]:
    """Atalho: valida e retorna apenas os lançamentos válidos."""
    validos, _ = validar_planilha(caminho)
    if not validos:
        raise ValueError("Planilha sem lançamentos válidos para processar.")
    return validos
