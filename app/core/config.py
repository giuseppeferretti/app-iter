"""
Constantes do core do bot ANAC. Para uso embarcado no produto comercial Iter.

Diferenças vs. versão CLI:
  - Sem PLANILHA_PATH (caminho vem da UI via filedialog)
  - Sem MODO_TESTE (UI tem botão "Testar 1 linha" que faz a mesma coisa)
"""

# ── URL e regras fixas ────────────────────────────────────────────────────────
URL_CIV       = "https://sistemas.anac.gov.br/SACI/CIV/Digital/incluirCIV.asp?idMdl=447-4788"
FUNCAO_VALUE  = "06"   # Piloto em Comando (sempre)

# ── Conexao CDP com Chromium (Chrome / Brave / Edge / Opera) ──────────────────
CDP_PORTA = 9222

# ── Timeouts ──────────────────────────────────────────────────────────────────
RETRY_VEZES              = 3
TIMEOUT_PADRAO           = 30_000   # ms — aguarda elementos
WAIT_APOS_BLUR_MATRICULA = 800      # ms — aguarda AJAX exibeHabilitacao()
WAIT_APOS_SALVAR_MS      = 8_000    # ms — janela maxima de espera pos-save

# ── Sheet padrao da planilha ──────────────────────────────────────────────────
SHEET_NAME = "Plan1"
