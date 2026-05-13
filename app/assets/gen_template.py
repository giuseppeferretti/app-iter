"""
Gera o template.xlsx oficial do App Iter.

Schema (mesmo lido por app/core/excel_reader.py):
  Obrigatórios:
    data       — DD/MM/AAAA
    pousos     — 1 a 99
    matricula  — até 5 chars (ex: PTVZZ)
    origem     — ICAO 4 chars
    destino    — ICAO 4 chars
    horas      — HH:MM ou decimal

  Opcionais:
    obs           — texto livre
    milhas_nav    — número
    horas_nav     — HH:MM ou decimal

Saída: app/assets/template.xlsx (5 linhas de exemplo realistas, 1 aba "Plan1")

Rodar: `python app/assets/gen_template.py`
"""
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


COR_HEADER_BG   = "0B0B0E"
COR_HEADER_FG   = "F5ECD8"
COR_PRIMARY     = "2B6BFF"
COR_BORDER      = "262630"
COR_LINHA_BG    = "FFFFFF"
COR_OPCIONAL_BG = "F5F2EA"

COLUNAS_OBRIGATORIAS = [
    ("DATA",       "DD/MM/AAAA"),
    ("POUSOS",     "1-99"),
    ("MATRICULA",  "Ex: PTBIC"),
    ("ORIGEM",     "ICAO 4 letras"),
    ("DESTINO",    "ICAO 4 letras"),
    ("HORAS",      "HH:MM"),
]
COLUNAS_OPCIONAIS = [
    ("OBS",        "Observação livre"),
    ("MILHAS_NAV", "Milhas náuticas"),
    ("HORAS_NAV",  "HH:MM"),
]

EXEMPLOS = [
    {
        "DATA": "12/03/2026", "POUSOS": "1", "MATRICULA": "PTBIC",
        "ORIGEM": "SBSP", "DESTINO": "SBKP", "HORAS": "00:45",
        "OBS": "Translado", "MILHAS_NAV": "", "HORAS_NAV": "",
    },
]


def _aplicar_borda(cell, cor=COR_BORDER):
    cell.border = Border(
        left=Side(style="thin", color=cor),
        right=Side(style="thin", color=cor),
        top=Side(style="thin", color=cor),
        bottom=Side(style="thin", color=cor),
    )


def main() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Plan1"

    todas_colunas = COLUNAS_OBRIGATORIAS + COLUNAS_OPCIONAIS
    nomes = [c[0] for c in todas_colunas]
    larguras = {
        "DATA": 14, "POUSOS": 9, "MATRICULA": 12, "ORIGEM": 10,
        "DESTINO": 10, "HORAS": 8, "OBS": 32, "MILHAS_NAV": 12, "HORAS_NAV": 11,
    }

    # ── Cabeçalhos (linha 1) ──────────────────────────────────────────────
    header_font = Font(
        name="Segoe UI", size=11, bold=True, color=COR_HEADER_FG,
    )
    header_fill = PatternFill(
        start_color=COR_HEADER_BG, end_color=COR_HEADER_BG, fill_type="solid",
    )
    header_fill_opcional = PatternFill(
        start_color=COR_PRIMARY, end_color=COR_PRIMARY, fill_type="solid",
    )
    align_center = Alignment(horizontal="center", vertical="center")

    n_obrig = len(COLUNAS_OBRIGATORIAS)
    for col_idx, (nome, _exemplo) in enumerate(todas_colunas, start=1):
        cell = ws.cell(row=1, column=col_idx, value=nome)
        cell.font = header_font
        cell.alignment = align_center
        if col_idx <= n_obrig:
            cell.fill = header_fill
        else:
            cell.fill = header_fill_opcional
        _aplicar_borda(cell)
        ws.column_dimensions[get_column_letter(col_idx)].width = larguras[nome]

    ws.row_dimensions[1].height = 24

    # Dicas de formato vão como comentário (tooltip) em cada cabeçalho —
    # assim o usuário vê o exemplo ao passar o mouse, mas a linha não é
    # parseada como dado e não gera "erros" na validação.
    from openpyxl.comments import Comment
    for col_idx, (_nome, exemplo) in enumerate(todas_colunas, start=1):
        cell = ws.cell(row=1, column=col_idx)
        cell.comment = Comment(f"Formato: {exemplo}", "App Iter")

    # ── Linhas 2+: exemplos reais ────────────────────────────────────────
    body_font = Font(name="Segoe UI", size=11)
    align_left = Alignment(horizontal="left", vertical="center")
    align_center_body = Alignment(horizontal="center", vertical="center")
    for r_idx, exemplo in enumerate(EXEMPLOS, start=2):
        for col_idx, nome in enumerate(nomes, start=1):
            val = exemplo.get(nome, "")
            cell = ws.cell(row=r_idx, column=col_idx, value=val)
            cell.font = body_font
            if nome == "OBS":
                cell.alignment = align_left
            else:
                cell.alignment = align_center_body
            _aplicar_borda(cell)

    # ── Congelar a primeira linha pra rolar mantendo cabeçalho ────────────
    ws.freeze_panes = "A2"

    # ── Salvar ────────────────────────────────────────────────────────────
    destino = Path(__file__).parent / "template.xlsx"
    wb.save(destino)
    print(f"template.xlsx salvo em {destino}")


if __name__ == "__main__":
    main()
