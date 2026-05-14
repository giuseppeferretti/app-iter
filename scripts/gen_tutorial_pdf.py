"""
Gera o tutorial_planilha.pdf — versão visual do TUTORIAL_PLANILHA.md.

Layout com identidade Iter (preto + bege), tipografia Helvetica (built-in
pra evitar dep de fonte externa). Otimizado pra ser anexado em e-mail.

Saída: tutorial_planilha.pdf na raiz do projeto.
Rodar: python -m scripts.gen_tutorial_pdf
"""
from pathlib import Path
from fpdf import FPDF

# ── Fonte com suporte Unicode (acento, em-dash, etc.) ────────────────────────
# Segoe UI vem com todo Windows e tem suporte completo a UTF-8.
SEGOE_REGULAR = Path(r"C:\Windows\Fonts\segoeui.ttf")
SEGOE_BOLD    = Path(r"C:\Windows\Fonts\segoeuib.ttf")
SEGOE_ITALIC  = Path(r"C:\Windows\Fonts\segoeuii.ttf")

# ── Identidade Iter ──────────────────────────────────────────────────────────
COR_BG_DARK    = (15, 15, 18)        # fundo dos blocos escuros
COR_BEGE       = (245, 236, 216)     # cor de destaque
COR_FG         = (24, 24, 28)        # texto principal
COR_MUTED      = (110, 110, 115)     # texto secundário
COR_PRIMARY    = (43, 107, 255)      # azul Iter (sutil)
COR_BORDER     = (220, 218, 210)     # bordas leves


class TutorialPDF(FPDF):
    def header(self):
        # Tarja sutil no topo (só nas páginas após a 1)
        if self.page_no() > 1:
            self.set_fill_color(*COR_BG_DARK)
            self.rect(0, 0, 210, 8, "F")
            self.set_xy(10, 2.5)
            self.set_font("Segoe", "B", 8)
            self.set_text_color(*COR_BEGE)
            self.cell(0, 4, "APP ITER  ·  TUTORIAL PLANILHA",
                      align="L")
            self.set_text_color(*COR_MUTED)
            self.set_xy(-30, 2.5)
            self.cell(20, 4, f"pg. {self.page_no()}", align="R")
            self.set_y(15)

    def footer(self):
        self.set_y(-15)
        self.set_font("Segoe", "", 8)
        self.set_text_color(*COR_MUTED)
        self.cell(0, 5,
                  "Iter · App ANAC · suporte.iter@gmail.com  ·  "
                  "github.com/giuseppeferretti/app-iter",
                  align="C")

    # ── Helpers de tipografia ────────────────────────────────────────────
    def h1(self, texto: str):
        self.ln(2)
        self.set_text_color(*COR_FG)
        self.set_font("Segoe", "B", 22)
        self.multi_cell(0, 9, texto)
        self.ln(2)

    def h2(self, texto: str):
        self.ln(4)
        self.set_text_color(*COR_FG)
        self.set_font("Segoe", "B", 14)
        self.cell(0, 7, texto, new_x="LMARGIN", new_y="NEXT")
        # underline bege sutil
        self.set_draw_color(*COR_BEGE)
        self.set_line_width(0.6)
        y = self.get_y()
        self.line(10, y, 30, y)
        self.ln(4)

    def h3(self, texto: str):
        self.ln(3)
        self.set_text_color(*COR_FG)
        self.set_font("Segoe", "B", 11)
        self.cell(0, 6, texto, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def eyebrow(self, texto: str):
        self.set_text_color(*COR_MUTED)
        self.set_font("Segoe", "B", 8)
        # tracking simulado: espaço entre palavras
        self.cell(0, 4, texto.upper(), new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def paragrafo(self, texto: str):
        self.set_text_color(*COR_FG)
        self.set_font("Segoe", "", 11)
        self.multi_cell(0, 5.5, texto)
        self.ln(2)

    def callout(self, texto: str, bg=(247, 244, 234), borda=COR_BEGE):
        """Bloco bege com destaque (alerta/dica)."""
        self.ln(1)
        x_start = self.l_margin
        y_start = self.get_y()
        self.set_fill_color(*bg)
        self.set_draw_color(*borda)
        self.set_line_width(0.3)
        largura = self.epw
        self.set_text_color(*COR_FG)
        self.set_font("Segoe", "", 10.5)
        # Calcula altura aproximada
        linhas = self._estimate_lines(texto, largura - 10)
        altura = max(8, linhas * 5 + 4)
        self.rect(x_start, y_start, largura, altura, "DF")
        self.set_xy(x_start + 5, y_start + 2)
        self.multi_cell(largura - 10, 5, texto)
        self.ln(2)

    def lista_numerada(self, items: list[str]):
        self.set_text_color(*COR_FG)
        self.set_font("Segoe", "", 10.5)
        for i, item in enumerate(items, 1):
            x = self.get_x()
            y = self.get_y()
            self.set_text_color(*COR_PRIMARY)
            self.set_font("Segoe", "B", 10.5)
            self.cell(7, 5.5, f"{i}.", new_x="RIGHT", new_y="TOP")
            self.set_text_color(*COR_FG)
            self.set_font("Segoe", "", 10.5)
            self.multi_cell(self.epw - 7, 5.5, item)
            self.ln(0.5)
        self.ln(2)

    def lista_bullet(self, items: list[str]):
        self.set_text_color(*COR_FG)
        self.set_font("Segoe", "", 10.5)
        for item in items:
            self.set_text_color(*COR_BEGE)
            self.set_font("Segoe", "B", 10.5)
            self.cell(6, 5.5, "·", new_x="RIGHT", new_y="TOP")
            self.set_text_color(*COR_FG)
            self.set_font("Segoe", "", 10.5)
            self.multi_cell(self.epw - 6, 5.5, item)
            self.ln(0.3)
        self.ln(2)

    def tabela(self, header: list[str], rows: list[list[str]],
               widths: list[float] | None = None):
        if widths is None:
            widths = [self.epw / len(header)] * len(header)

        # Header
        self.set_fill_color(*COR_BG_DARK)
        self.set_text_color(*COR_BEGE)
        self.set_font("Segoe", "B", 9.5)
        self.set_draw_color(*COR_BORDER)
        self.set_line_width(0.2)
        for w, txt in zip(widths, header):
            self.cell(w, 7, txt, border=1, align="L", fill=True)
        self.ln()

        # Rows (com wrap em caso de texto longo)
        self.set_text_color(*COR_FG)
        self.set_font("Segoe", "", 9.5)
        for row in rows:
            # Calcula altura da linha baseado no maior conteúdo
            heights = []
            for w, txt in zip(widths, row):
                lns = max(1, self._estimate_lines(str(txt), w - 2))
                heights.append(lns * 4.5)
            row_h = max(heights)
            row_h = max(row_h, 7)

            y_start = self.get_y()
            x = self.l_margin
            for w, txt in zip(widths, row):
                self.set_xy(x, y_start)
                self.multi_cell(w, 4.5, str(txt), border=1, align="L")
                x += w
            self.set_y(y_start + row_h)
        self.ln(3)

    def divider(self):
        self.ln(3)
        self.set_draw_color(*COR_BORDER)
        self.set_line_width(0.3)
        y = self.get_y()
        self.line(self.l_margin, y, 210 - self.r_margin, y)
        self.ln(4)

    def _estimate_lines(self, texto: str, largura_mm: float) -> int:
        """Estima quantas linhas de texto vão caber numa largura em mm."""
        if not texto:
            return 1
        # Aproximação: caracter avg = 2mm em font 10.5
        chars_per_line = max(10, int(largura_mm / 2.0))
        linhas = 0
        for paragrafo in texto.split("\n"):
            linhas += max(1, (len(paragrafo) // chars_per_line) + 1)
        return linhas


def main():
    pdf = TutorialPDF(orientation="P", unit="mm", format="A4")
    # Registra Segoe UI como fonte default (suporte unicode completo)
    pdf.add_font("Segoe", "", str(SEGOE_REGULAR), uni=True)
    pdf.add_font("Segoe", "B", str(SEGOE_BOLD), uni=True)
    pdf.add_font("Segoe", "I", str(SEGOE_ITALIC), uni=True)
    pdf.set_margins(left=15, top=15, right=15)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # ── CAPA / Hero ──────────────────────────────────────────────────────
    pdf.set_fill_color(*COR_BG_DARK)
    pdf.rect(0, 0, 210, 50, "F")
    pdf.set_xy(15, 12)
    pdf.set_text_color(*COR_BEGE)
    pdf.set_font("Segoe", "B", 9)
    pdf.cell(0, 5, "APP ITER", new_x="LMARGIN", new_y="NEXT")
    pdf.set_xy(15, 18)
    pdf.set_font("Segoe", "B", 24)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 11, "Tutorial da Planilha", new_x="LMARGIN", new_y="NEXT")
    pdf.set_xy(15, 32)
    pdf.set_text_color(*COR_BEGE)
    pdf.set_font("Segoe", "", 11)
    pdf.cell(0, 6, "Como preencher os lançamentos pra automação do SACI/ANAC")
    pdf.ln(20)

    # ── Intro ────────────────────────────────────────────────────────────
    pdf.set_y(60)
    pdf.eyebrow("OLA, PILOTO")
    pdf.paragrafo(
        "Aqui vai um guia direto pra preencher sua planilha de horas e o "
        "App Iter levar tudo pro SACI em poucos minutos."
    )
    pdf.callout(
        "Use sempre o modelo oficial — baixe pelo botão \"Baixar modelo\" "
        "na tela do app."
    )

    # ── Seção 1: 15 colunas ──────────────────────────────────────────────
    pdf.h2("A planilha tem 15 colunas")
    pdf.paragrafo(
        "A ordem segue exatamente a tela \"Lançar Voo\" do SACI. "
        "Cada linha = um lançamento de voo. São dois blocos:"
    )

    pdf.h3("Bloco \"Dados do vôo\" (colunas 1 a 7)")
    pdf.tabela(
        header=["Coluna", "O que é", "Formato", "Obrig?"],
        rows=[
            ["DATA", "Data do voo", "DD/MM/AAAA", "Sim"],
            ["POUSOS", "Quantos pousos", "Número 1 a 99", "Sim"],
            ["FUNCAO", "Função a bordo", "Escolha do dropdown", "Sim"],
            ["ANAC_ALUNO", "Cód. ANAC do aluno",
             "8 dígitos (só se Função = Instrutor)", "Condic."],
            ["CURSO_COMERCIAL", "Curso comercial",
             "Sim/Não (só se PIC)", "Condic."],
            ["OBSERVACOES", "Texto livre", "Qualquer anotação", "Não"],
            ["MILHAS_NAV", "Milhas náuticas", "Inteiro", "Não"],
        ],
        widths=[35, 50, 70, 25],
    )

    pdf.h3("Bloco \"Tempo de vôo\" (colunas 8 a 15)")
    pdf.tabela(
        header=["Coluna", "O que é", "Formato", "Obrig?"],
        rows=[
            ["MATRICULA", "Matrícula da aeronave", "Até 5 chars (PTBIC)", "Sim"],
            ["ORIGEM", "Aeródromo origem", "ICAO 4 letras (SBSP)", "Sim"],
            ["DESTINO", "Aeródromo destino", "ICAO 4 letras", "Sim"],
            ["DIURNO", "Horas diurnas", "HH:MM", "Pelo menos*"],
            ["NOTURNO", "Horas noturnas", "HH:MM", "Pelo menos*"],
            ["NAVEGACAO", "Horas de navegação", "HH:MM", "Não"],
            ["INSTRUMENTO", "Instrumento Real (IFR)", "HH:MM", "Não"],
            ["SOB_CAPOTA", "Instrução IFR simulada", "HH:MM", "Não"],
        ],
        widths=[35, 50, 70, 25],
    )
    pdf.set_font("Segoe", "I", 9.5)
    pdf.set_text_color(*COR_MUTED)
    pdf.cell(0, 5, "* Toda linha precisa ter DIURNO OU NOTURNO preenchido.")
    pdf.ln(8)

    pdf.divider()

    # ── Seção 2: 7 opções de FUNCAO ──────────────────────────────────────
    pdf.h2("As 7 opções de FUNCAO")
    pdf.paragrafo(
        "Mesmas opções do SACI. Escolha sempre pela seta do dropdown "
        "(não digite manualmente, pra evitar erro de grafia):"
    )
    pdf.lista_numerada([
        "Instrutor Voo  -  habilita ANAC_ALUNO",
        "Piloto em Comando  -  habilita CURSO_COMERCIAL",
        "Piloto em Instrução",
        "Instrutor de voo em solo  -  habilita ANAC_ALUNO",
        "Co-Piloto Single Pilot",
        "Co-Piloto Single Pilot com co-piloto, por questão regulamentar",
        "Co-Piloto Dual Pilot",
    ])

    pdf.divider()

    # ── Seção 3: Regras condicionais ─────────────────────────────────────
    pdf.h2("Regras condicionais")
    pdf.paragrafo(
        "O app valida tudo antes de iniciar. Se houver inconsistência, "
        "o painel lista linha por linha o que ajustar."
    )
    pdf.lista_bullet([
        "Se FUNCAO for Instrutor (Voo ou em solo): ANAC_ALUNO é obrigatório (8 dígitos).",
        "Se FUNCAO não for Instrutor: ANAC_ALUNO deve estar vazio.",
        "CURSO_COMERCIAL = Sim só funciona se FUNCAO = Piloto em Comando.",
        "Pelo menos uma de DIURNO ou NOTURNO deve estar preenchida.",
    ])

    pdf.divider()

    # ── Seção 4: Exemplo ─────────────────────────────────────────────────
    pdf.h2("Exemplo de linha completa")
    pdf.tabela(
        header=["Coluna", "Valor"],
        rows=[
            ["DATA", "12/03/2026"],
            ["POUSOS", "1"],
            ["FUNCAO", "Piloto em Comando"],
            ["ANAC_ALUNO", "(vazio)"],
            ["CURSO_COMERCIAL", "Não"],
            ["OBSERVACOES", "Translado"],
            ["MILHAS_NAV", "50"],
            ["MATRICULA", "PTBIC"],
            ["ORIGEM", "SBSP"],
            ["DESTINO", "SBKP"],
            ["DIURNO", "00:45"],
            ["NOTURNO", "00:30"],
            ["NAVEGACAO", "00:45"],
            ["INSTRUMENTO", "(vazio)"],
            ["SOB_CAPOTA", "(vazio)"],
        ],
        widths=[60, 120],
    )

    pdf.add_page()

    # ── Seção 5: Como usar o app ─────────────────────────────────────────
    pdf.h2("Como usar o App Iter")
    pdf.lista_numerada([
        "Abra o App Iter no menu Iniciar.",
        "Clique em \"Baixar modelo\" (link abaixo do dropzone) e salve.",
        "Preencha a planilha no Excel — uma linha por voo.",
        "Volte ao app e clique no dropzone pra carregar sua planilha preenchida.",
        "Confira o painel: lançamentos válidos + eventuais inconsistências.",
        "Clique INICIAR SESSÃO. Vai aparecer o modal de pré-execução.",
        "Clique \"Abrir SACI\" — o app vai usar o navegador que voce usa (Brave, Chrome, Edge, Opera) e abrir o SACI nele.",
        "Faça login no SACI normalmente. O status vira verde automaticamente.",
        "Clique \"Prosseguir\" — o app começa a lançar voo por voo na sua tela.",
        "Se precisar parar, clique CANCELAR — corta em até 1 segundo.",
    ])

    pdf.divider()

    # ── Seção 6: Dicas ───────────────────────────────────────────────────
    pdf.h2("Dicas")
    pdf.lista_bullet([
        "Formato de horas: HH:MM ou hora nativa do Excel — qualquer um serve.",
        "Voo só noturno: deixe DIURNO vazio (não digite \"00:00\").",
        "ICAO em minúsculo: o app converte pra maiúsculo automaticamente.",
        "Excel salvou data como 12032026? O app entende.",
        "MANTENHA a planilha FECHADA quando rodar o app — o Excel bloqueia o arquivo.",
    ])

    pdf.divider()

    # ── Seção 7: Suporte ─────────────────────────────────────────────────
    pdf.h2("Dúvidas")
    pdf.paragrafo(
        "Escreva pra suporte.iter@gmail.com — a gente responde direto, sem fila."
    )
    pdf.callout(
        "Bons voos.\n"
        "— Equipe Iter",
        bg=(245, 236, 216),
        borda=(212, 180, 140),
    )

    # ── Salva ────────────────────────────────────────────────────────────
    destino = Path(__file__).resolve().parent.parent / "tutorial_planilha.pdf"
    pdf.output(str(destino))
    print(f"tutorial_planilha.pdf salvo em {destino}")
    print(f"Tamanho: {destino.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
