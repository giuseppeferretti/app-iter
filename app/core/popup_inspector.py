"""
Detecta o que acontece na pagina apos clicar #salvar.

4 desfechos possiveis:
  - native_dialog   : alert/confirm JS nativo (page.on("dialog"))
  - html_modal      : modal HTML aparece (div[role=dialog], .alert, button Ok)
  - redirect        : URL muda; se contiver "login"/"autenticacao" → sessao_expirada
  - noop            : nada visivel mudou apos o timeout

Em modo de teste (config.MODO_TESTE), o dialog handler captura SEM aceitar,
deixando o popup visivel pra screenshot.
"""
import asyncio
from typing import Any, Dict, List

from playwright.async_api import Dialog, Page

from app.core import config
from app.core.logger import get_logger

log = get_logger()


SELETORES_MODAL = [
    "div[role='dialog']:visible",
    ".modal.show",
    ".modal-show",
    ".alert:visible",
    "#mensagem:visible",
    "button:has-text('Ok'):visible",
    "button:has-text('OK'):visible",
    "input[value='Ok']:visible",
    "input[value='OK']:visible",
]


class DialogCapture:
    """
    Container compartilhado com o handler de dialog.
    Sempre aceita o dialog (clica Ok) — o popup pos-save da ANAC e a
    confirmacao "Voce esta salvando o registro como rascunho. Deseja
    continuar o lancamento?", que precisa ser confirmada pra o save
    completar. Registra os eventos pra log/analise.
    """

    def __init__(self):
        self.eventos: List[Dict[str, str]] = []

    async def handler(self, dialog: Dialog) -> None:
        evento = {
            "type": dialog.type,
            "message": dialog.message,
            "default_value": dialog.default_value or "",
        }
        self.eventos.append(evento)
        log.info(
            f"Dialog capturado e aceito: type={dialog.type} message={dialog.message!r}"
        )
        try:
            await dialog.accept()
        except Exception as exc:
            log.warning(f"Falha ao aceitar dialog: {exc}")


def instalar_dialog_handler(page: Page) -> DialogCapture:
    """Instala handler de dialog na page. Sempre aceita e registra eventos."""
    capture = DialogCapture()
    page.on("dialog", capture.handler)
    return capture


async def aguardar_e_capturar_resposta(
    page: Page,
    capture: DialogCapture,
    url_origem: str,
    timeout_ms: int = config.WAIT_APOS_SALVAR_MS,
) -> Dict[str, Any]:
    """
    Apos clicar #salvar, aguarda ate um dos 4 desfechos por ate timeout_ms.

    Retorna dict com chave 'tipo' em:
      "native_dialog" | "html_modal" | "redirect" | "sessao_expirada" | "noop"
    """
    deadline = asyncio.get_event_loop().time() + (timeout_ms / 1000)

    while asyncio.get_event_loop().time() < deadline:
        # 1. Native dialog (handler ja foi disparado)
        if capture.eventos:
            return {
                "tipo": "native_dialog",
                "dialogs": list(capture.eventos),
                "url": page.url,
            }

        # 2. Redirect
        try:
            if page.url != url_origem:
                url_atual = page.url.lower()
                if any(t in url_atual for t in ("login", "autenticacao", "/sso/")):
                    return {
                        "tipo": "sessao_expirada",
                        "url": page.url,
                        "title": await _safe_title(page),
                    }
                return {
                    "tipo": "redirect",
                    "url": page.url,
                    "title": await _safe_title(page),
                }
        except Exception:
            pass

        # 3. Modal HTML
        for sel in SELETORES_MODAL:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    texto = ""
                    try:
                        texto = (await loc.inner_text())[:500]
                    except Exception:
                        pass
                    return {
                        "tipo": "html_modal",
                        "seletor": sel,
                        "texto": texto,
                        "url": page.url,
                    }
            except Exception:
                continue

        await asyncio.sleep(0.2)

    # noop: nada visivel mudou
    body_text = ""
    try:
        body_text = (await page.inner_text("body"))[:500]
    except Exception:
        pass
    return {
        "tipo": "noop",
        "url": page.url,
        "title": await _safe_title(page),
        "body_preview": body_text,
    }


async def _safe_title(page: Page) -> str:
    try:
        return await page.title()
    except Exception:
        return ""
