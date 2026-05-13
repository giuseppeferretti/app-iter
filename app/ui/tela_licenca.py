"""
Tela de ativação via Supabase magic link OTP.

Layout:
  - Wordmark iTER (44px) no topo, centralizado
  - Eyebrow "Ativação"
  - Título "Entre com o e-mail da compra"
  - Parágrafo curto
  - TextField e-mail (borda azul Iter, outline-only)
  - TextField código de 6 dígitos (oculto até o e-mail ser enviado)
  - Botão "Enviar código" (vira "Validar código")
  - Texto de status (vermelho em erro, verde em sucesso)
  - TextButton "Ainda não tem assinatura? Adquirir"

Notas técnicas:
  - `webbrowser.open()` (stdlib síncrono) em vez de `page.launch_url()` —
    este último é coroutine async no Flet 0.85.
  - URL de checkout vem da env var ASAAS_CHECKOUT_URL (sandbox/produção
    intercambiáveis). Fallback é o placeholder do tutorial.
"""
import os
import webbrowser

import flet as ft

from app.licensing.verificador import enviar_otp, verificar_otp
from app.ui.componentes import (
    COR_BG, COR_FG, COR_MUTED_FG, COR_ERROR, COR_SUCCESS, COR_PRIMARY,
    botao_primario, eyebrow, iter_wordmark, titulo, texto,
)


ASAAS_CHECKOUT_URL = os.environ.get(
    "ASAAS_CHECKOUT_URL",
    "https://sandbox.asaas.com/c/SEU-LINK-AQUI",  # placeholder até configurar
)


# Estilo compartilhado dos TextFields — outline azul Iter
def _campo_iter(**kwargs) -> ft.TextField:
    """Fábrica de TextField com a identidade Iter."""
    defaults = dict(
        border=ft.InputBorder.OUTLINE,
        border_color=COR_PRIMARY,
        border_width=1.5,
        focused_border_color=COR_PRIMARY,
        focused_border_width=2,
        border_radius=10,
        cursor_color=COR_PRIMARY,
        color=COR_FG,
        text_size=14,
        label_style=ft.TextStyle(color=COR_MUTED_FG, size=13),
        hint_style=ft.TextStyle(color="#5a565a"),
        content_padding=ft.Padding(16, 14, 16, 14),
        bgcolor="#121218",  # leve fill pra contrastar com fundo da tela
        focused_bgcolor="#161620",
        text_style=ft.TextStyle(color=COR_FG, size=14, weight=ft.FontWeight.W_500),
    )
    defaults.update(kwargs)
    return ft.TextField(**defaults)


def construir(page: ft.Page, ao_ativar) -> ft.Control:
    estado = {"email": None}

    campo_email = _campo_iter(
        label="E-mail da compra",
        hint_text="voce@exemplo.com",
        width=420,
        keyboard_type=ft.KeyboardType.EMAIL,
    )
    campo_codigo = _campo_iter(
        label="Código de 6 dígitos",
        hint_text="123456",
        width=420,
        visible=False,
        keyboard_type=ft.KeyboardType.NUMBER,
        max_length=6,
    )
    mensagem = ft.Text("", color=COR_MUTED_FG, size=12, selectable=True)

    botao_ref: dict = {"control": None}

    def _set_mensagem(msg: str, cor=COR_MUTED_FG) -> None:
        mensagem.value = msg
        mensagem.color = cor

    def enviar(_):
        email = (campo_email.value or "").strip()
        if "@" not in email:
            _set_mensagem("Digite um e-mail válido.", COR_ERROR)
            page.update()
            return

        _set_mensagem("Enviando código...")
        page.update()

        resultado = enviar_otp(email)
        if not resultado["ok"]:
            _set_mensagem(resultado["motivo"], COR_ERROR)
            page.update()
            return

        estado["email"] = email
        campo_email.disabled = True
        campo_codigo.visible = True
        botao_ref["control"].content = "Validar código"
        botao_ref["control"].on_click = validar
        _set_mensagem(resultado["motivo"], COR_SUCCESS)
        page.update()

    def validar(_):
        codigo = (campo_codigo.value or "").strip()
        if len(codigo) < 6:
            _set_mensagem("O código deve ter 6 dígitos.", COR_ERROR)
            page.update()
            return

        _set_mensagem("Validando...")
        page.update()

        resultado = verificar_otp(estado["email"], codigo)
        if not resultado["ok"]:
            _set_mensagem(resultado["motivo"], COR_ERROR)
            page.update()
            return

        _set_mensagem("Sessão ativada.", COR_SUCCESS)
        page.update()
        ao_ativar(None)

    botao = botao_primario("Enviar código", enviar)
    botao_ref["control"] = botao

    link_adquirir = ft.TextButton(
        "Ainda não tem assinatura? Adquirir",
        on_click=lambda _: webbrowser.open(ASAAS_CHECKOUT_URL),
    )

    return ft.Container(
        padding=ft.Padding(40, 36, 40, 72),  # 72px bottom: respira sobre a DEV pill
        alignment=ft.Alignment.TOP_CENTER,
        expand=True,
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=18,
            controls=[
                iter_wordmark(height=44),
                ft.Container(height=4),
                eyebrow("Ativação"),
                titulo(
                    "Entre com o e-mail da compra",
                    size=26,
                    text_align=ft.TextAlign.CENTER,
                ),
                texto(
                    "Você vai receber um código de 6 dígitos para ativar este "
                    "dispositivo. Nenhuma senha é necessária.",
                    color=COR_MUTED_FG,
                    size=13,
                ),
                ft.Container(height=4),
                campo_email,
                campo_codigo,
                botao,
                mensagem,
                link_adquirir,
            ],
        ),
    )
