"""
Conecta a um navegador Chromium-based (Chrome, Brave, Edge, Opera) via CDP.

NOVA filosofia (UX explícita):
  - O app NUNCA mais mata o navegador do usuário automaticamente. Forçar
    reinício destruía a sessão e gerava "abriu Chrome de novo".
  - O fluxo é EXPLÍCITO via UI: o usuário clica em "Abrir SACI" no pre-flight,
    e essa ação chama `abrir_navegador_com_cdp()`. Se o navegador já estiver
    rodando, oferece-se relançar (com confirmação) ou abre uma instância
    secundária com porta CDP num user-data-dir alternativo.
  - A função `cdp_disponivel()` é leve e usada pelo polling da UI pra detectar
    quando dá pra habilitar "Prosseguir".
  - `conectar()` continua funcionando, mas SÓ se o CDP já estiver ativo —
    senão lança erro com mensagem clara.

Public API:
  - detectar_navegador()              → escolhe o navegador a usar
  - cdp_disponivel(porta=9222)        → bool, leve, p/ polling UI
  - saci_aberto(porta=9222)           → bool, há aba no SACI já carregada?
  - abrir_navegador_com_cdp(nav)      → lança o navegador na porta CDP
  - conectar(pw)                       → conecta via CDP, retorna Browser+Page
  - desconectar(browser)              → fecha só a conexão CDP
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
    nome: str            # "Chrome", "Brave", "Edge", "Opera"
    exe: Path            # caminho do executavel
    user_data_dir: Path  # pasta do perfil real (sessao SACI)
    process_name: str    # nome do .exe para detecção via tasklist


# Pasta auxiliar pro user_data_dir CDP — sem mexer no perfil real do usuário.
# Quando o usuário tem o navegador aberto SEM CDP e nós precisamos abrir uma
# segunda instância COM CDP, usamos esse user-data-dir paralelo.
_CDP_PROFILE_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "Iter" / "AppIter" / "cdp-profile"


def _candidatos_navegadores() -> list[NavegadorInfo]:
    """Lista navegadores Chromium suportados na ordem de preferência."""
    user = Path(os.environ.get("USERPROFILE", r"C:\Users") + os.sep + os.environ.get("USERNAME", ""))
    local_app = Path(os.environ.get("LOCALAPPDATA", user / "AppData" / "Local"))
    program_files = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    program_files_x86 = Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))

    return [
        NavegadorInfo(
            nome="Brave",
            exe=program_files / "BraveSoftware/Brave-Browser/Application/brave.exe",
            user_data_dir=local_app / "BraveSoftware/Brave-Browser/User Data",
            process_name="brave.exe",
        ),
        NavegadorInfo(
            nome="Chrome",
            exe=program_files / "Google/Chrome/Application/chrome.exe",
            user_data_dir=local_app / "Google/Chrome/User Data",
            process_name="chrome.exe",
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
    Identifica via `tasklist` qual dos 4 navegadores já está rodando.
    Retorna a primeira correspondência encontrada (ordem da lista de
    preferência), ou None.
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
            return cand
    return None


def detectar_navegador() -> Optional[NavegadorInfo]:
    """
    Decide qual navegador o app vai abrir:
      1. Se algum dos 4 já está rodando, prefere ESSE (não força troca).
      2. Senão, retorna o primeiro instalado na ordem (Brave, Chrome, Edge, Opera).
      3. Fallback via registro do Windows.
    """
    rodando = _navegador_rodando()
    if rodando:
        log.info(f"Navegador rodando detectado: {rodando.nome}")
        return rodando

    for cand in _candidatos_navegadores():
        if cand.exe.exists():
            log.info(f"Navegador instalado detectado: {cand.nome} em {cand.exe}")
            return cand

    # Tentativa via registro
    reg_paths = {
        "Brave":  r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\brave.exe",
        "Chrome": r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
        "Edge":   r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
    }
    for nome, reg in reg_paths.items():
        exe = _exe_via_registro(reg)
        if exe:
            for cand in _candidatos_navegadores():
                if cand.nome == nome:
                    cand.exe = exe
                    return cand
    return None


def _ler_cdp_version(porta: int, timeout: float = 1.0) -> Optional[dict]:
    """GET /json/version. Retorna None se nao responder CDP."""
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{porta}/json/version", timeout=timeout
        ) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ConnectionError,
            json.JSONDecodeError, OSError):
        return None


def cdp_disponivel(porta: int | None = None) -> bool:
    """Check leve (~1s) usado pelo polling da UI."""
    p = porta or config.CDP_PORTA
    return _ler_cdp_version(p, timeout=0.8) is not None


def saci_aberto(porta: int | None = None) -> bool:
    """
    Retorna True se há uma aba CDP cuja URL aponta pro SACI.
    Não verifica login (a sessão é cookie-based — não dá pra detectar via
    CDP sem fazer request autenticado). UI confia que se o usuário abriu
    a URL e ela carregou, ele se autenticou.
    """
    p = porta or config.CDP_PORTA
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{p}/json", timeout=0.8
        ) as resp:
            abas = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return False
    for aba in abas:
        url = (aba.get("url") or "").lower()
        if "sistemas.anac.gov.br" in url or "saci" in url:
            return True
    return False


def abrir_navegador_com_cdp(
    navegador: NavegadorInfo | None = None,
    *,
    forcar_perfil_alternativo: bool = False,
) -> NavegadorInfo:
    """
    Abre o navegador na porta CDP com a URL do SACI já carregada.

    Lógica:
      - Se já há CDP rodando na porta → retorna o navegador atual sem fazer nada.
      - Se o navegador escolhido está rodando MAS sem CDP → abre uma SEGUNDA
        instância usando user-data-dir alternativo (não toca na instância do
        usuário). O usuário fecha a janela antiga ou trabalha nas duas.
      - Se o navegador NÃO está rodando → abre normal com o perfil real do
        usuário (preserva sessões salvas).

    `forcar_perfil_alternativo=True` força o user-data-dir paralelo mesmo se
    o navegador não estiver rodando — útil pra evitar conflitos.

    Retorna o NavegadorInfo usado.
    """
    if cdp_disponivel():
        nav = _navegador_rodando() or _candidatos_navegadores()[0]
        log.info(f"CDP já ativo na porta {config.CDP_PORTA} ({nav.nome}). OK.")
        return nav

    nav = navegador or detectar_navegador()
    if nav is None:
        raise RuntimeError(
            "Nenhum navegador compatível encontrado (Chrome, Brave, Edge ou Opera). "
            "Instale um deles e tente novamente."
        )

    ja_rodando = _navegador_rodando() is not None
    usar_perfil_alt = forcar_perfil_alternativo or ja_rodando

    if usar_perfil_alt:
        _CDP_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        user_data = _CDP_PROFILE_DIR
        log.info(
            f"Abrindo {nav.nome} em perfil alternativo (instância paralela): "
            f"{user_data}. Você vai precisar fazer login no SACI nesta janela."
        )
    else:
        user_data = nav.user_data_dir
        log.info(
            f"Abrindo {nav.nome} com perfil real (sessões/login preservados): "
            f"{user_data}"
        )

    subprocess.Popen([
        str(nav.exe),
        f"--remote-debugging-port={config.CDP_PORTA}",
        f"--user-data-dir={user_data}",
        "--no-first-run",
        "--no-default-browser-check",
        "--start-maximized",
        config.URL_CIV,
    ])
    return nav


async def aguardar_cdp_pronto(timeout_s: float = 60.0, intervalo_s: float = 0.5) -> bool:
    """Polling até CDP responder ou timeout."""
    elapsed = 0.0
    while elapsed < timeout_s:
        if cdp_disponivel():
            return True
        await asyncio.sleep(intervalo_s)
        elapsed += intervalo_s
    return False


async def conectar(pw: Playwright) -> tuple[Browser, BrowserContext, Page]:
    """
    Conecta via CDP, retorna (browser, context, page).
    Pré-condição: CDP já deve estar ativo (chamado por `abrir_navegador_com_cdp`
    antes via UI). Se não estiver, levanta erro pedindo pra abrir o navegador.
    """
    if not cdp_disponivel():
        raise RuntimeError(
            f"Nenhum navegador respondendo CDP na porta {config.CDP_PORTA}. "
            "Clique em 'Abrir SACI' na tela de pré-execução pra abrir o navegador "
            "corretamente, autentique-se no SACI e tente de novo."
        )

    cdp_url = f"http://localhost:{config.CDP_PORTA}"
    log.info(f"Conectando via CDP em {cdp_url}...")
    browser = await pw.chromium.connect_over_cdp(cdp_url)

    context = browser.contexts[0] if browser.contexts else await browser.new_context()

    # Prefere uma aba já no SACI; senão usa a última.
    page = None
    if context.pages:
        for p in context.pages:
            if "anac.gov.br" in (p.url or "").lower():
                page = p
                log.info(f"Aba SACI encontrada: {p.url!r}")
                break
        if page is None:
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
        log.info("Conexão CDP encerrada. Navegador continua aberto.")
    except Exception as exc:
        log.debug(f"Falha ao encerrar CDP: {exc}")
