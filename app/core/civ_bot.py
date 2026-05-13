"""
Preenchimento de um lancamento de CIV (Caderneta Individual de Voo) na ANAC.

Para cada linha da planilha:
  1. Aguarda o form carregar (DataRegistroVoo visivel)
  2. Preenche os 7 campos na ordem visual
  3. Clica #salvar
  4. Delega ao popup_inspector pra capturar a resposta da pagina

Tecnica de preenchimento: click → fill("") → fill(valor) → press("Tab")
(disparar onblur via Tab e suficiente para campos com mascara JS).
"""
from typing import Any, Dict

from playwright.async_api import Page, TimeoutError as PWTimeout

from app.core import config
from app.core.logger import get_logger
from app.core.popup_inspector import (
    DialogCapture,
    aguardar_e_capturar_resposta,
)

log = get_logger()


async def _preencher_texto(
    page: Page, seletor: str, valor: str, tab: bool = True
) -> None:
    """Padrao: click → fill("") → fill → Tab. Reuso de fiscal_bot.py:181-188."""
    campo = page.locator(seletor).first
    await campo.wait_for(state="visible", timeout=config.TIMEOUT_PADRAO)
    await campo.click()
    await campo.fill("")
    await campo.fill(valor)
    if tab:
        await campo.press("Tab")


async def _preencher_mascarado(
    page: Page, seletor: str, valor: str, valor_esperado: str | None = None
) -> str:
    """
    Preenchimento robusto para campos com mascara onkeypress (data, horas).
    Mascaras tipo mask() do site so disparam em keypress reais — fill() do
    Playwright nao aciona, entao o site ignora o valor.

    3 estrategias em ordem:
      1. fill direto (rapido, funciona em campos sem mascara estrita)
      2. keyboard.type digito a digito (mascara processa)
      3. evaluate setando .value + dispatch input/change/blur

    Retorna nome da estrategia que funcionou.
    """
    esperado = valor_esperado or valor
    campo = page.locator(seletor).first
    await campo.wait_for(state="visible", timeout=config.TIMEOUT_PADRAO)

    # 1. fill
    try:
        await campo.click()
        await campo.fill("")
        await campo.fill(valor)
        await campo.press("Tab")
        atual = await campo.input_value()
        if _valor_match(atual, esperado):
            log.debug(f"{seletor} preenchido via fill: {atual}")
            return "fill"
        log.debug(f"fill em {seletor} resultou em '{atual}' (esperado '{esperado}'), tentando type")
    except Exception as exc:
        log.debug(f"fill falhou em {seletor}: {exc}")

    # 2. keyboard.type (so digitos/alfanumericos — mascara monta separadores)
    try:
        await campo.click()
        await campo.fill("")
        await campo.click()
        digitos = "".join(c for c in valor if c.isalnum())
        await page.keyboard.type(digitos, delay=80)
        await campo.press("Tab")
        atual = await campo.input_value()
        if _valor_match(atual, esperado):
            log.debug(f"{seletor} preenchido via keyboard.type: {atual}")
            return "type"
        log.debug(f"type em {seletor} resultou em '{atual}', tentando JS")
    except Exception as exc:
        log.debug(f"keyboard.type falhou em {seletor}: {exc}")

    # 3. JS evaluate
    await campo.evaluate(
        """
        (el, v) => {
            el.value = v;
            el.dispatchEvent(new Event('input',  { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.dispatchEvent(new Event('blur',   { bubbles: true }));
        }
        """,
        valor,
    )
    atual = await campo.input_value()
    log.debug(f"{seletor} preenchido via JS: {atual}")
    if not _valor_match(atual, esperado):
        log.warning(
            f"Apos 3 estrategias, {seletor} continua com '{atual}' "
            f"(esperado '{esperado}')."
        )
    return "evaluate"


def _valor_match(atual: str, esperado: str) -> bool:
    """Compara valores ignorando espacos e zeros a esquerda em cada componente."""
    if not atual:
        return False
    norm = lambda s: "".join(c for c in s if c.isalnum())
    return norm(atual) == norm(esperado)


async def _preencher_destino_com_fallback(page: Page, valor: str) -> str:
    """
    Tenta input[name="txtDestino"] primeiro. Se nao existir (o HTML que o
    usuario compartilhou tinha 2 campos name="txtOrigem", provavel typo),
    usa o segundo input[name="txtOrigem"]. Retorna o seletor que foi usado
    pra log/debug.
    """
    destino_locator = page.locator('input[name="txtDestino"]')
    if await destino_locator.count() > 0:
        seletor = 'input[name="txtDestino"]'
        await _preencher_texto(page, seletor, valor)
        log.debug(f"Destino preenchido via {seletor}")
        return seletor

    # Fallback: segundo input[name="txtOrigem"]
    origens = page.locator('input[name="txtOrigem"]')
    count = await origens.count()
    if count < 2:
        raise RuntimeError(
            f"Campo destino nao encontrado: txtDestino ausente e "
            f"so {count} input[name='txtOrigem'] no DOM."
        )
    campo = origens.nth(1)
    await campo.wait_for(state="visible", timeout=config.TIMEOUT_PADRAO)
    await campo.click()
    await campo.fill("")
    await campo.fill(valor)
    await campo.press("Tab")
    log.warning(
        "Destino preenchido via FALLBACK (segundo input[name='txtOrigem']). "
        "Confirme no screenshot que o valor foi pro campo certo."
    )
    return "input[name='txtOrigem'].nth(1)"


async def lancar_voo(
    page: Page, linha: Dict[str, Any], capture: DialogCapture
) -> Dict[str, Any]:
    """
    Preenche o form de CIV com os dados de UMA linha da planilha e clica
    #salvar. Retorna o dict do popup_inspector com o desfecho da acao.
    """
    log.info(
        f"Preenchendo linha {linha['linha_planilha']}: "
        f"{linha['data']} {linha['origem']}→{linha['destino']} "
        f"{linha['horas']} mat={linha['matricula']} pousos={linha['pousos']}"
    )

    try:
        await page.wait_for_selector(
            "#DataRegistroVoo", state="visible", timeout=config.TIMEOUT_PADRAO
        )
    except PWTimeout as exc:
        raise RuntimeError(
            f"Form CIV nao carregou (campo #DataRegistroVoo nao visivel). "
            f"URL atual: {page.url}. Detalhe: {exc}"
        )

    url_inicial = page.url

    # 1. Data (mascara onkeypress — usa _preencher_mascarado)
    estrategia_data = await _preencher_mascarado(
        page, "#DataRegistroVoo", linha["data"]
    )

    # 2. Pousos (mascara onkeypress curta — usa _preencher_mascarado)
    estrategia_pousos = await _preencher_mascarado(
        page, 'input[name="txtPousos"]', linha["pousos"]
    )

    # 3. Funcao (select fixo: Piloto em Comando)
    await page.locator('select[name="cmbFuncao"]').first.select_option(
        value=config.FUNCAO_VALUE
    )

    # 3b. Observacao (textarea opcional)
    if linha.get("obs"):
        await _preencher_texto(
            page, 'textarea[name="txtObservacao"]', linha["obs"], tab=False
        )

    # 4. Matricula (onblur dispara exibeHabilitacao AJAX)
    await _preencher_texto(page, 'input[name="txtMatricula"]', linha["matricula"])
    await page.wait_for_timeout(config.WAIT_APOS_BLUR_MATRICULA)

    # 5. Origem (primeiro input txtOrigem)
    origem_campo = page.locator('input[name="txtOrigem"]').first
    await origem_campo.click()
    await origem_campo.fill("")
    await origem_campo.fill(linha["origem"])
    await origem_campo.press("Tab")

    # 6. Destino (com fallback)
    seletor_destino = await _preencher_destino_com_fallback(page, linha["destino"])

    # 7. Horas diurnas (mascara reais — usa _preencher_mascarado)
    estrategia_horas = await _preencher_mascarado(
        page, 'input[name="txtDiurno"]', linha["horas"]
    )

    # 8. Horas de navegacao (mascara reais identica ao txtDiurno, dir=rtl)
    if linha.get("horas_nav"):
        await _preencher_mascarado(
            page, 'input[name="txtNavegacao"]', linha["horas_nav"]
        )

    # 9. Milhas de navegacao (mascara mask numerico, onkeypress)
    if linha.get("milhas_nav"):
        await _preencher_mascarado(
            page, 'input[name="txtQtMilhaNavegacao"]', linha["milhas_nav"]
        )

    log.info(
        f"  Campos preenchidos (data={estrategia_data}, pousos={estrategia_pousos}, "
        f"destino={seletor_destino}, horas={estrategia_horas}). Clicando #salvar..."
    )

    # 8. Submit
    await page.locator("#salvar").first.click()

    # 9. Capturar resposta da pagina
    resposta = await aguardar_e_capturar_resposta(page, capture, url_inicial)
    resposta["seletor_destino"] = seletor_destino
    resposta["estrategia_data"] = estrategia_data
    resposta["estrategia_pousos"] = estrategia_pousos
    resposta["estrategia_horas"] = estrategia_horas
    return resposta
