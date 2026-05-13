"""
Conecta a um navegador Chromium-based (Chrome, Brave, Edge, Opera) via CDP.

Diferenca vs versao CLI:
  - Agnostico de navegador: detecta o primeiro instalado na ordem de preferencia
  - Caminhos detectados via registro do Windows + variaveis de ambiente
  - Preserva o perfil real do usuario (sessao SACI preservada)

Comportamento:
  1. Se ja houver navegador respondendo CDP na porta padrao: anexa.
  2. Senao: fecha instancias do navegador escolhido e relanca com:
       --remote-debugging-port=9222
       --user-data-dir=<perfil real desse navegador>
       --start-maximized
       <URL_CIV>
  3. Conecta via CDP e usa a aba existente.
"""
import asyncio
import json
import os
import subprocess
import urllib.error
import urllib.request
import winreg
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from playwright.async_api import Browser, BrowserContext, Page, Playwright

from app.core import config
from app.core.logger import get_logger

log = get_logger()


@dataclass
class NavegadorInfo:
    nome: str       # "Chrome", "Brave", "Edge", "Opera"
    exe: Path       # caminho do executavel
    user_data_dir: Path  # pasta do perfil real
    process_name: str    # nome do .exe para taskkill


def _candidatos_navegadores() -> list[NavegadorInfo]:
    """Lista navegadores Chromium suportados, na ordem de preferencia."""
    user = Path(os.environ.get("USERPROFILE", r"C:\Users") + os.sep + os.environ.get("USERNAME", ""))
    local_app = Path(os.environ.get("LOCALAPPDATA", user / "AppData" / "Local"))
    program_files = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    program_files_x86 = Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))

    return [
        NavegadorInfo(
            nome="Chrome",
            exe=program_files / "Google/Chrome/Application/chrome.exe",
            user_data_dir=local_app / "Google/Chrome/User Data",
            process_name="chrome.exe",
        ),
        NavegadorInfo(
            nome="Brave",
            exe=program_files / "BraveSoftware/Brave-Browser/Application/brave.exe",
            user_data_dir=local_app / "BraveSoftware/Brave-Browser/User Data",
            process_name="brave.exe",
        ),
        NavegadorInfo(
            nome="Edge",
            exe=program_files_x86 / "Microsoft/Edge/Application/msedge.exe",
            user_data_dir=local_app / "Microsoft/Edge/User Data",
            process_name="msedge.exe",
        ),
        NavegadorInfo(
            nome="Opera",
            exe=local_app / "Programs/Opera/launcher.exe",
            user_data_dir=Path(os.environ.get("APPDATA", "")) / "Opera Software/Opera Stable",
            process_name="opera.exe",
        ),
    ]


def _exe_via_registro(reg_path: str) -> Optional[Path]:
    """Tenta encontrar o executavel registrado no Windows (HKLM)."""
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
            val, _ = winreg.QueryValueEx(key, "")
            p = Path(val)
            return p if p.exists() else None
    except (OSError, FileNotFoundError):
        return None


def _navegador_rodando() -> Optional[NavegadorInfo]:
    """
    Identifica via `tasklist` qual dos 4 navegadores ja esta rodando.
    Retorna a primeira correspondencia encontrada, ou None se nenhum
    navegador estiver aberto. Util pra preferir o navegador que o
    usuario ja usa em vez de pegar o primeiro instalado.
    """
    try:
        saida = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, check=False, timeout=5,
        ).stdout.lower()
    except Exception as exc:
        log.debug(f"tasklist falhou: {exc}")
        return None
    for cand in _candidatos_navegadores():
        if cand.process_name.lower() in saida and cand.exe.exists():
            log.info(f"Navegador rodando: {cand.nome} (process {cand.process_name})")
            return cand
    return None


def detectar_navegador() -> Optional[NavegadorInfo]:
    """Retorna o primeiro navegador instalado na ordem de preferencia."""
    # Tentativa 1: caminhos padrao
    for cand in _candidatos_navegadores():
        if cand.exe.exists():
            log.info(f"Navegador detectado: {cand.nome} em {cand.exe}")
            return cand

    # Tentativa 2: registro do Windows (App Paths)
    reg_paths = {
        "Chrome": r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
        "Brave":  r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\brave.exe",
        "Edge":   r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
    }
    for nome, reg in reg_paths.items():
        exe = _exe_via_registro(reg)
        if exe:
            log.info(f"Navegador detectado via registro: {nome} em {exe}")
            for cand in _candidatos_navegadores():
                if cand.nome == nome:
                    cand.exe = exe
                    return cand

    return None


def _ler_cdp_version(porta: int, timeout: float = 1.5) -> Optional[dict]:
    """GET /json/version. Retorna None se nao responder CDP."""
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{porta}/json/version", timeout=timeout
        ) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ConnectionError,
            json.JSONDecodeError, OSError):
        return None


async def _garantir_navegador_com_cdp() -> NavegadorInfo:
    """
    Garante que algum navegador Chromium esteja respondendo CDP em config.CDP_PORTA.
    Se nao estiver, escolhe o navegador a usar (prefere o que ja esta rodando
    pra nao reiniciar um navegador que o usuario nao usa), fecha-o e relanca
    com a flag CDP.
    """
    # Ja tem alguem respondendo? Aceita.
    if _ler_cdp_version(config.CDP_PORTA):
        log.info(f"Navegador ja respondendo CDP na porta {config.CDP_PORTA}.")
        return _navegador_rodando() or _candidatos_navegadores()[0]

    # Preferir o navegador que JA esta aberto; fallback pro primeiro instalado.
    navegador = _navegador_rodando() or detectar_navegador()
    if navegador is None:
        raise RuntimeError(
            "Nenhum navegador compativel encontrado.\n"
            "Instale um dos seguintes: Chrome, Brave, Edge ou Opera."
        )

    log.info(f"Reiniciando {navegador.nome} com debug ativo (sessao preservada)...")
    subprocess.run(
        ["taskkill", "/F", "/IM", navegador.process_name],
        capture_output=True, check=False,
    )
    await asyncio.sleep(1.5)

    subprocess.Popen([
        str(navegador.exe),
        f"--remote-debugging-port={config.CDP_PORTA}",
        f"--user-data-dir={navegador.user_data_dir}",
        "--no-first-run",
        "--start-maximized",
        config.URL_CIV,
    ])

    log.info(f"Aguardando {navegador.nome} iniciar...")
    for _ in range(30):
        await asyncio.sleep(0.5)
        if _ler_cdp_version(config.CDP_PORTA):
            log.info(f"{navegador.nome} pronto na porta {config.CDP_PORTA}.")
            return navegador

    raise RuntimeError(
        f"{navegador.nome} nao respondeu em 15s na porta {config.CDP_PORTA}."
    )


async def conectar(pw: Playwright) -> tuple[Browser, BrowserContext, Page]:
    """Garante navegador com CDP, conecta, e retorna a aba existente."""
    await _garantir_navegador_com_cdp()

    cdp_url = f"http://localhost:{config.CDP_PORTA}"
    log.info(f"Conectando via CDP em {cdp_url}...")
    browser = await pw.chromium.connect_over_cdp(cdp_url)

    context = browser.contexts[0] if browser.contexts else await browser.new_context()

    if context.pages:
        page = context.pages[-1]
        log.info(f"Usando aba existente: {page.url!r}")
    else:
        page = await context.new_page()
        log.info("Nenhuma aba aberta — criada nova aba.")

    page.set_default_timeout(config.TIMEOUT_PADRAO)
    return browser, context, page


async def desconectar(browser: Browser) -> None:
    """Encerra a conexao CDP. O navegador permanece aberto."""
    try:
        await browser.close()
        log.info("Conexao CDP encerrada. Navegador continua aberto.")
    except Exception as exc:
        log.debug(f"Falha ao encerrar CDP: {exc}")
