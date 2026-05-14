"""
Constantes do core do bot ANAC. Para uso embarcado no produto comercial Iter.

Diferenças vs. versão CLI:
  - Sem PLANILHA_PATH (caminho vem da UI via filedialog)
  - Sem MODO_TESTE (UI tem botão "Testar 1 linha" que faz a mesma coisa)
"""

# ── URL e regras fixas ────────────────────────────────────────────────────────
URL_CIV       = "https://sistemas.anac.gov.br/SACI/CIV/Digital/incluirCIV.asp?idMdl=447-4788"

# ── Funções a bordo (dropdown SACI cmbFuncao) ─────────────────────────────────
# Labels EXATOS do <select> SACI. O civ_bot descobre dinamicamente o `value`
# de cada label ao abrir a tela (uma vez por batch) — não hardcoda códigos.
FUNCOES_VALIDAS: tuple[str, ...] = (
    "Instrutor Voo",
    "Piloto em Comando",
    "Piloto em Instrução",
    "Instrutor de voo em solo",
    "Co-Piloto Single Pilot",
    "Co-Piloto Single Pilot com co-piloto, por questão regulamentar",
    "Co-Piloto Dual Pilot",
)

# Funções de instrução — habilitam o input CD_ANAC_INSTRUENDO no SACI.
FUNCOES_INSTRUTOR: frozenset[str] = frozenset({
    "Instrutor Voo",
    "Instrutor de voo em solo",
})

# Label específico que habilita o radio "isComandoPiloto" (curso comercial).
FUNCAO_PILOTO_COMANDO: str = "Piloto em Comando"

# ── Conexao CDP com Chromium (Chrome / Brave / Edge / Opera) ──────────────────
CDP_PORTA = 9222

# ── Timeouts ──────────────────────────────────────────────────────────────────
RETRY_VEZES              = 3
TIMEOUT_PADRAO           = 30_000   # ms — aguarda elementos
WAIT_APOS_BLUR_MATRICULA = 800      # ms — aguarda AJAX exibeHabilitacao()
WAIT_APOS_SALVAR_MS      = 8_000    # ms — janela maxima de espera pos-save

# ── Sheet padrao da planilha ──────────────────────────────────────────────────
SHEET_NAME = "Plan1"
