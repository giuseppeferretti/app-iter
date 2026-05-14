"""
Preenchimento de um lancamento de CIV (Caderneta Individual de Voo) na ANAC.

Para cada linha da planilha:
  1. Aguarda o form carregar (DataRegistroVoo visivel)
  2. Descobre mapa de Função → código SACI (1x por batch, cache in-memory)
  3. Preenche todos os campos na ordem visual da tela
  4. Clica #salvar
  5. Delega ao popup_inspector pra capturar a resposta da pagina

Tecnica de preenchimento: click → fill("") → fill(valor) → press("Tab")
(disparar onblur via Tab e suficiente para campos com mascara JS).

Padrão de navegador: opera SEMPRE no navegador já aberto pelo usuário via
CDP (porta 9222) — definido em app.core.browser. Nunca sobe Chromium próprio.
"""
import threading
from typing import Any, Callable, Dict, Optional

from playwright.async_api import Page, TimeoutError as PWTimeout

from app.core import config
from app.core.logger import get_logger
from app.core.popup_inspector import (
    DialogCapture,
    aguardar_e_capturar_resposta,
)

log = get_logger()


class CanceladoPeloUsuario(Exception):
    """Levantado quando o usuário clica em Cancelar durante um lançamento.

    A tela principal trata e dá break no loop de batch sem marcar como falha.
    """


def _check_cancel(cancel_event: Optional[threading.Event]) -> None:
    """Verifica se cancelamento foi solicitado e levanta exceção rápida.
    Chamado entre cada `await` dos preenchimentos pra cortar quase imediato.
    """
    if cancel_event is not None and cancel_event.is_set():
        raise CanceladoPeloUsuario()


# ── Cache in-memory pra descobertas dinâmicas (1 batch = 1 conexão Page) ─────
# A descoberta dos `value` do select cmbFuncao e do nome real do campo
# "Sob Capota" custa uma round trip via CDP. Cacheamos por instância de Page
# usando id(page) como chave — quando começa um novo batch (novo Page),
# o cache é descartado naturalmente.
_mapa_funcao_cache: dict[int, dict[str, str]] = {}
_seletor_capota_cache: dict[int, str] = {}


async def _descobrir_mapa_funcao(page: Page) -> dict[str, str]:
    """
    Lê as <option> do select[name="cmbFuncao"] e monta dict label→value.
    Cacheia por instância de Page.
    """
    cached = _mapa_funcao_cache.get(id(page))
    if cached is not None:
        return cached

    opcoes = await page.locator('select[name="cmbFuncao"] option').evaluate_all(
        """
        els => els
            .map(el => ({label: (el.textContent || '').trim(), value: el.value}))
            .filter(o => o.label && o.value)
        """
    )
    mapa = {opt["label"].strip().lower(): opt["value"] for opt in opcoes}
    log.info(
        f"Mapa Função descoberto ({len(mapa)} opções): "
        f"{ {opt['label']: opt['value'] for opt in opcoes} }"
    )
    _mapa_funcao_cache[id(page)] = mapa
    return mapa


async def _resolver_seletor_capota(page: Page) -> Optional[str]:
    """
    Descobre qual `name` o SACI usa pro input "Sob Capota". Tenta
    txtCapota → txtSobCapota → None (campo não existe, skip).
    Cacheia por Page.
    """
    if id(page) in _seletor_capota_cache:
        cached = _seletor_capota_cache[id(page)]
        return cached if cached else None

    for candidato in ("txtCapota", "txtSobCapota", "txtSobcapota"):
        loc = page.locator(f'input[name="{candidato}"]')
        if await loc.count() > 0:
            sel = f'input[name="{candidato}"]'
            log.info(f"Campo Sob Capota encontrado: {sel}")
            _seletor_capota_cache[id(page)] = sel
            return sel

    log.warning(
        "Campo Sob Capota não encontrado no SACI (tentei txtCapota, "
        "txtSobCapota). Lançamentos com sob_capota preenchido vão pular esse campo."
    )
    _seletor_capota_cache[id(page)] = ""
    return None


async def _marcar_radio_curso_comercial(page: Page) -> bool:
    """
    Marca o radio isComandoPiloto como Sim. Tenta:
      1. Radio com value="S" (padrão SACI mais comum)
      2. Radio com value="1"
      3. Click no <label> "Sim" próximo ao name="isComandoPiloto"
    Retorna True se conseguiu marcar, False senão.
    """
    base = 'input[name="isComandoPiloto"]'
    radios = page.locator(base)
    total = await radios.count()
    if total == 0:
        log.warning("Radio isComandoPiloto não está no DOM — skip.")
        return False

    # Tenta value padrão Sim/Não comuns
    for valor in ("S", "1", "Sim", "sim", "true"):
        radio = page.locator(f'{base}[value="{valor}"]')
        if await radio.count() > 0:
            await radio.first.check()
            log.info(f"Curso comercial marcado via value=\"{valor}\"")
            return True

    # Fallback: pega o primeiro radio do par (geralmente Sim vem antes)
    log.warning(
        "value do radio isComandoPiloto desconhecido — clicando o PRIMEIRO "
        "radio (assumindo ordem Sim, Não). Confira o resultado no SACI."
    )
    try:
        await radios.first.check()
        return True
    except Exception as exc:
        log.error(f"Falha ao marcar radio isComandoPiloto: {exc}")
        return False


async def _preencher_texto(
    page: Page, seletor: str, valor: str, tab: bool = True
) -> None:
    """Padrao: click → fill("") → fill → Tab."""
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

    # 2. keyboard.type
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
    Tenta input[name="txtDestino"] primeiro. Se não existir, usa o segundo
    input[name="txtOrigem"] (workaround pra HTML mal-formado do SACI).
    """
    destino_locator = page.locator('input[name="txtDestino"]')
    if await destino_locator.count() > 0:
        seletor = 'input[name="txtDestino"]'
        await _preencher_texto(page, seletor, valor)
        log.debug(f"Destino preenchido via {seletor}")
        return seletor

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
    log.warning("Destino preenchido via FALLBACK (segundo input[name='txtOrigem']).")
    return "input[name='txtOrigem'].nth(1)"


async def lancar_voo(
    page: Page, linha: Dict[str, Any], capture: DialogCapture,
    cancel_event: Optional[threading.Event] = None,
) -> Dict[str, Any]:
    """
    Preenche o form de CIV com os dados de UMA linha da planilha e clica
    #salvar. Retorna o dict do popup_inspector com o desfecho da acao.

    Se `cancel_event` for fornecido e ficar setado durante a execução, levanta
    CanceladoPeloUsuario imediatamente — corta o lançamento em andamento sem
    esperar terminar a linha toda (UX de Cancelar mais responsiva).
    """
    log.info(
        f"Preenchendo linha {linha['linha_planilha']}: "
        f"{linha['data']} {linha['origem']}→{linha['destino']} "
        f"diurno={linha.get('diurno') or '-'} noturno={linha.get('noturno') or '-'} "
        f"mat={linha['matricula']} pousos={linha['pousos']} funcao={linha['funcao']}"
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

    _check_cancel(cancel_event)
    # ── 1. Data ─────────────────────────────────────────────────────────────
    estrategia_data = await _preencher_mascarado(
        page, "#DataRegistroVoo", linha["data"]
    )

    _check_cancel(cancel_event)
    # ── 2. Pousos ───────────────────────────────────────────────────────────
    estrategia_pousos = await _preencher_mascarado(
        page, 'input[name="txtPousos"]', linha["pousos"]
    )

    _check_cancel(cancel_event)
    # ── 3. Função (dinâmica via mapa) ───────────────────────────────────────
    mapa = await _descobrir_mapa_funcao(page)
    funcao_label = linha["funcao"]
    funcao_value = mapa.get(funcao_label.strip().lower())
    if not funcao_value:
        raise RuntimeError(
            f"Função '{funcao_label}' não encontrada no SACI. "
            f"Opções disponíveis: {list(mapa.keys())}"
        )
    await page.locator('select[name="cmbFuncao"]').first.select_option(value=funcao_value)
    log.debug(f"Função '{funcao_label}' setada (value={funcao_value})")

    # ── 3a. ANAC do aluno (só se Função de instrutor + valor preenchido) ────
    if linha.get("anac_aluno"):
        try:
            await _preencher_texto(
                page, 'input[name="CD_ANAC_INSTRUENDO"]', linha["anac_aluno"]
            )
            log.debug(f"ANAC aluno '{linha['anac_aluno']}' preenchido")
        except Exception as exc:
            log.warning(
                f"Falha ao preencher CD_ANAC_INSTRUENDO: {exc} — "
                "campo pode estar oculto/desabilitado pro Função atual."
            )

    # ── 3b. Curso comercial (radio isComandoPiloto = Sim) ───────────────────
    if linha.get("curso_comercial") is True:
        if funcao_label == config.FUNCAO_PILOTO_COMANDO:
            ok = await _marcar_radio_curso_comercial(page)
            if not ok:
                log.warning(
                    "Não consegui marcar curso_comercial=Sim. "
                    "Lançamento prossegue com default Não."
                )
        else:
            log.warning(
                f"curso_comercial=Sim ignorado: só aplicável a "
                f"{config.FUNCAO_PILOTO_COMANDO}, função atual = {funcao_label}"
            )

    # ── 3c. Observação ──────────────────────────────────────────────────────
    if linha.get("obs"):
        await _preencher_texto(
            page, 'textarea[name="txtObservacao"]', linha["obs"], tab=False
        )

    _check_cancel(cancel_event)
    # ── 4. Matrícula (onblur dispara exibeHabilitacao AJAX) ─────────────────
    await _preencher_texto(page, 'input[name="txtMatricula"]', linha["matricula"])
    await page.wait_for_timeout(config.WAIT_APOS_BLUR_MATRICULA)

    _check_cancel(cancel_event)
    # ── 5. Origem ───────────────────────────────────────────────────────────
    origem_campo = page.locator('input[name="txtOrigem"]').first
    await origem_campo.click()
    await origem_campo.fill("")
    await origem_campo.fill(linha["origem"])
    await origem_campo.press("Tab")

    _check_cancel(cancel_event)
    # ── 6. Destino (com fallback) ───────────────────────────────────────────
    seletor_destino = await _preencher_destino_com_fallback(page, linha["destino"])

    # ── 7. Diurno ───────────────────────────────────────────────────────────
    estrategia_diurno = ""
    if linha.get("diurno"):
        _check_cancel(cancel_event)
        estrategia_diurno = await _preencher_mascarado(
            page, 'input[name="txtDiurno"]', linha["diurno"]
        )

    # ── 8. Noturno ──────────────────────────────────────────────────────────
    if linha.get("noturno"):
        _check_cancel(cancel_event)
        await _preencher_mascarado(
            page, 'input[name="txtNoturno"]', linha["noturno"]
        )

    # ── 9. Navegação ────────────────────────────────────────────────────────
    if linha.get("navegacao"):
        _check_cancel(cancel_event)
        await _preencher_mascarado(
            page, 'input[name="txtNavegacao"]', linha["navegacao"]
        )

    # ── 10. Instrumento Real ────────────────────────────────────────────────
    if linha.get("instrumento"):
        _check_cancel(cancel_event)
        await _preencher_mascarado(
            page, 'input[name="txtInstrumento"]', linha["instrumento"]
        )

    # ── 11. Sob Capota (descobre seletor) ───────────────────────────────────
    if linha.get("sob_capota"):
        _check_cancel(cancel_event)
        sel_capota = await _resolver_seletor_capota(page)
        if sel_capota:
            await _preencher_mascarado(page, sel_capota, linha["sob_capota"])
        else:
            log.warning(
                f"sob_capota={linha['sob_capota']} não preenchido (campo não encontrado no SACI)"
            )

    # ── 12. Milhas de navegação ─────────────────────────────────────────────
    if linha.get("milhas_nav"):
        _check_cancel(cancel_event)
        await _preencher_mascarado(
            page, 'input[name="txtQtMilhaNavegacao"]', linha["milhas_nav"]
        )

    _check_cancel(cancel_event)

    log.info(
        f"  Campos preenchidos (data={estrategia_data}, pousos={estrategia_pousos}, "
        f"destino={seletor_destino}, diurno={estrategia_diurno}). Clicando #salvar..."
    )

    # ── 13. Submit ──────────────────────────────────────────────────────────
    await page.locator("#salvar").first.click()

    # ── 14. Capturar resposta da pagina ─────────────────────────────────────
    resposta = await aguardar_e_capturar_resposta(page, capture, url_inicial)
    resposta["seletor_destino"] = seletor_destino
    resposta["estrategia_data"] = estrategia_data
    resposta["estrategia_pousos"] = estrategia_pousos
    resposta["estrategia_diurno"] = estrategia_diurno
    resposta["funcao_value"] = funcao_value
    return resposta
