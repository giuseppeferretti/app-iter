"""
Smoke test do excel_reader.py após reforma de 15 colunas.

Cria planilhas sintéticas in-memory cobrindo:
  - cenário feliz: várias Funções, condicionais OK
  - rejeições esperadas: ANAC_ALUNO em Função não-instrutor, curso_comercial=Sim
    em Função não-Piloto-em-Comando, ANAC ausente em Instrutor, formato antigo

Rodar: python -m scripts.smoke_excel_reader
Sai 0 se tudo OK, 1 se algum cenário falhar.
"""
import sys
import tempfile
from pathlib import Path

from openpyxl import Workbook

# Path setup
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.excel_reader import validar_planilha


COLUNAS_NOVAS = [
    "DATA", "POUSOS", "FUNCAO", "ANAC_ALUNO", "CURSO_COMERCIAL",
    "OBSERVACOES", "MILHAS_NAV", "MATRICULA", "ORIGEM", "DESTINO",
    "DIURNO", "NOTURNO", "NAVEGACAO", "INSTRUMENTO", "SOB_CAPOTA",
]
COLUNAS_ANTIGAS = ["DATA", "POUSOS", "MATRICULA", "ORIGEM", "DESTINO", "HORAS",
                   "OBS", "MILHAS_NAV", "HORAS_NAV"]


def _planilha(linhas: list[dict], colunas: list[str] = COLUNAS_NOVAS) -> str:
    wb = Workbook()
    ws = wb.active
    ws.title = "Plan1"
    ws.append(colunas)
    for linha in linhas:
        ws.append([linha.get(c, "") for c in colunas])
    f = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    wb.save(f.name)
    return f.name


def _resumir(titulo, validos, erros):
    print(f"  -> {len(validos)} válidos, {len(erros)} erro(s)")
    for e in erros:
        print(f"     linha {e.linha} {e.coluna}={e.valor!r}: {e.motivo}")


def _check(label: str, ok: bool) -> bool:
    marca = "OK" if ok else "FAIL"
    print(f"  {marca} {label}")
    return ok


def main() -> int:
    falhas = 0

    # ── 1. Cenário feliz — 4 linhas variadas ────────────────────────────────
    print("\n[1] Happy path: 4 linhas válidas variadas")
    caminho = _planilha([
        # Piloto em Comando simples
        {"DATA": "12/03/2026", "POUSOS": "1", "FUNCAO": "Piloto em Comando",
         "MATRICULA": "PTBIC", "ORIGEM": "SBSP", "DESTINO": "SBKP",
         "DIURNO": "00:45"},
        # Instrutor Voo com ANAC do aluno
        {"DATA": "13/03/2026", "POUSOS": "2", "FUNCAO": "Instrutor Voo",
         "ANAC_ALUNO": "12345678", "MATRICULA": "PTABC",
         "ORIGEM": "SBJD", "DESTINO": "SBJD", "DIURNO": "01:30"},
        # Piloto em Comando dentro de curso comercial
        {"DATA": "14/03/2026", "POUSOS": "1", "FUNCAO": "Piloto em Comando",
         "CURSO_COMERCIAL": "Sim", "MATRICULA": "PTBIC",
         "ORIGEM": "SBKP", "DESTINO": "SBJD",
         "DIURNO": "01:00", "INSTRUMENTO": "00:20"},
        # Voo 100% noturno
        {"DATA": "15/03/2026", "POUSOS": "1", "FUNCAO": "Co-Piloto Dual Pilot",
         "MATRICULA": "PTDEF", "ORIGEM": "SBSP", "DESTINO": "SBRJ",
         "NOTURNO": "02:15", "NAVEGACAO": "01:30"},
    ])
    validos, erros = validar_planilha(caminho)
    _resumir("happy path", validos, erros)
    if not _check("4 linhas válidas sem erros", len(validos) == 4 and len(erros) == 0):
        falhas += 1
    if validos:
        l1 = validos[0]
        if not _check("renomeou horas->diurno",
                      l1["diurno"] == "00:45" and "horas" not in l1):
            falhas += 1
        if not _check("curso_comercial é bool",
                      validos[2]["curso_comercial"] is True
                      and validos[0]["curso_comercial"] is False):
            falhas += 1

    # ── 2. ANAC_ALUNO em Função não-instrutor -> erro ────────────────────────
    print("\n[2] ANAC_ALUNO inválido pra Piloto em Comando")
    caminho = _planilha([{
        "DATA": "12/03/2026", "POUSOS": "1", "FUNCAO": "Piloto em Comando",
        "ANAC_ALUNO": "12345678", "MATRICULA": "PTBIC",
        "ORIGEM": "SBSP", "DESTINO": "SBKP", "DIURNO": "00:45",
    }])
    validos, erros = validar_planilha(caminho)
    _resumir("anac em piloto", validos, erros)
    if not _check("rejeita ANAC_ALUNO em não-instrutor",
                  len(validos) == 0 and any(e.coluna == "anac_aluno" for e in erros)):
        falhas += 1

    # ── 3. Instrutor sem ANAC_ALUNO -> erro ──────────────────────────────────
    print("\n[3] Instrutor sem ANAC_ALUNO")
    caminho = _planilha([{
        "DATA": "12/03/2026", "POUSOS": "1", "FUNCAO": "Instrutor Voo",
        "MATRICULA": "PTBIC", "ORIGEM": "SBSP", "DESTINO": "SBKP",
        "DIURNO": "00:45",
    }])
    validos, erros = validar_planilha(caminho)
    _resumir("instrutor sem anac", validos, erros)
    if not _check("rejeita instrutor sem ANAC_ALUNO",
                  len(validos) == 0 and any(e.coluna == "anac_aluno" for e in erros)):
        falhas += 1

    # ── 4. CURSO_COMERCIAL=Sim em Função não-PC -> erro ──────────────────────
    print("\n[4] CURSO_COMERCIAL=Sim em Co-Piloto")
    caminho = _planilha([{
        "DATA": "12/03/2026", "POUSOS": "1", "FUNCAO": "Co-Piloto Dual Pilot",
        "CURSO_COMERCIAL": "Sim", "MATRICULA": "PTBIC",
        "ORIGEM": "SBSP", "DESTINO": "SBKP", "DIURNO": "00:45",
    }])
    validos, erros = validar_planilha(caminho)
    _resumir("curso em co-piloto", validos, erros)
    if not _check("rejeita curso_comercial=Sim em não-PC",
                  len(validos) == 0 and any(e.coluna == "curso_comercial" for e in erros)):
        falhas += 1

    # ── 5. Sem Diurno nem Noturno -> erro ────────────────────────────────────
    print("\n[5] Sem Diurno nem Noturno")
    caminho = _planilha([{
        "DATA": "12/03/2026", "POUSOS": "1", "FUNCAO": "Piloto em Comando",
        "MATRICULA": "PTBIC", "ORIGEM": "SBSP", "DESTINO": "SBKP",
        "NAVEGACAO": "01:00",
    }])
    validos, erros = validar_planilha(caminho)
    _resumir("sem horas", validos, erros)
    if not _check("exige pelo menos diurno OU noturno",
                  len(validos) == 0 and any("diurno/noturno" in e.coluna for e in erros)):
        falhas += 1

    # ── 6. Formato antigo (9 colunas) -> ValueError com mensagem clara ──────
    print("\n[6] Formato antigo rejeitado")
    caminho = _planilha([{
        "DATA": "12/03/2026", "POUSOS": "1", "MATRICULA": "PTBIC",
        "ORIGEM": "SBSP", "DESTINO": "SBKP", "HORAS": "00:45",
    }], colunas=COLUNAS_ANTIGAS)
    try:
        validos, erros = validar_planilha(caminho)
        print(f"  -> não levantou erro (mas devia)")
        _check("rejeita formato antigo", False)
        falhas += 1
    except ValueError as exc:
        msg = str(exc)
        ok = "antigo" in msg.lower() or "novo template" in msg.lower()
        _check(f"ValueError com mensagem clara: '{msg[:80]}...'", ok)
        if not ok:
            falhas += 1

    # ── Final ───────────────────────────────────────────────────────────────
    print(f"\n{'=' * 50}")
    if falhas == 0:
        print("TODOS os cenários passaram.")
        return 0
    else:
        print(f"{falhas} cenário(s) FALHARAM.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
