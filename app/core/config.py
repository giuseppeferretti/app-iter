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
# Lista ordenada de portas que o app tenta. A primeira disponível (não ocupada
# por outro processo, ou já hospedando uma sessão SACI nossa) é usada.
# Útil pra coexistir com OUTRAS automações que também usam CDP (ex.: o Chrome
# do usuário aberto em 9222 pra outro projeto). Se 9222 está ocupada, o app
# pula pra 9223, e assim por diante.
CDP_PORTAS_TENTATIVAS = (9222, 9223, 9224, 9225, 9226)

# Alias retrocompatível — algumas partes antigas leem `CDP_PORTA`. Reflete só
# a porta preferencial (primeira da lista). A porta REAL em uso pelo app é
# rastreada em runtime via app.core.browser.get_porta_ativa().
CDP_PORTA = CDP_PORTAS_TENTATIVAS[0]

# ── Timeouts ──────────────────────────────────────────────────────────────────
RETRY_VEZES              = 3
TIMEOUT_PADRAO           = 30_000   # ms — aguarda elementos
WAIT_APOS_BLUR_MATRICULA = 800      # ms — aguarda AJAX exibeHabilitacao()
WAIT_APOS_SALVAR_MS      = 8_000    # ms — janela maxima de espera pos-save

# ── Sheet padrao da planilha ──────────────────────────────────────────────────
SHEET_NAME = "Plan1"
