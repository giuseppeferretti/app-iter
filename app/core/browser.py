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
import socket
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

# ── Estado runtime: porta CDP em uso ─────────────────────────────────────────
# Atualizada por abrir_navegador_com_cdp() e por descoberta automática.
# UI consulta via get_porta_ativa() — se ninguém setou ainda, retorna a
# primeira porta da lista de tentativas (default 9222).
_porta_ativa: Optional[int] = None


def get_porta_ativa() -> int:
    """Porta CDP atualmente em uso pelo app (ou a preferencial se nada ainda)."""
    return _porta_ativa or config.CDP_PORTAS_TENTATIVAS[0]


def _set_porta_ativa(p: int) -> None:
    global _porta_ativa
    if _porta_ativa != p:
        log.info(f"Porta CDP ativa: {p}")
        _porta_ativa = p


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


def _porta_em_uso_tcp(porta: int) -> bool:
    """True se algo já está usando essa porta TCP (não necessariamente CDP).
    Usado pra detectar conflitos com OUTROS apps/automações antes de abrir
    o navegador, pra não trombar com 'Chrome --remote-debugging-port=9222'
    de outro projeto rodando paralelo.

    Implementação: tenta fazer bind() em (127.0.0.1, porta). Se o SO recusa
    com EADDRINUSE/WSAEADDRINUSE, está em uso. Robusto contra problemas de
    backlog/listen que afetam abordagens baseadas em connect().
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", porta))
        return False  # bind teve sucesso → porta livre
    except OSError:
        return True  # EADDRINUSE ou similar → porta ocupada
    finally:
        s.close()


def _ler_abas_cdp(porta: int) -> list[dict]:
    """GET /json (lista de abas). Retorna [] em qualquer falha."""
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{porta}/json", timeout=0.8
        ) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []


def _porta_eh_nossa(porta: int) -> bool:
    """True se a porta hospeda CDP COM uma aba do SACI aberta.
    Heurística: se tem SACI carregado, assumimos que é a nossa sessão.
    """
    if _ler_cdp_version(porta, 0.5) is None:
        return False
    for aba in _ler_abas_cdp(porta):
        url = (aba.get("url") or "").lower()
        if "sistemas.anac.gov.br" in url or "saci" in url:
            return True
    return False


def descobrir_porta_cdp_nossa() -> Optional[int]:
    """
    Procura entre as portas tentativas qual tem CDP com aba do SACI aberta.
    Se achar, retorna a porta e seta como ativa. Senão None.
    """
    for p in config.CDP_PORTAS_TENTATIVAS:
        if _porta_eh_nossa(p):
            _set_porta_ativa(p)
            log.info(f"Sessão SACI já existente detectada em CDP porta {p}.")
            return p
    return None


def escolher_porta_livre() -> int:
    """
    Retorna a primeira porta da lista de tentativas que NÃO está ocupada.
    Útil quando vamos ABRIR o navegador pela primeira vez (ou substituir
    uma sessão SACI antiga). Loga warning se a preferencial está ocupada.
    """
    preferida = config.CDP_PORTAS_TENTATIVAS[0]
    for p in config.CDP_PORTAS_TENTATIVAS:
        if not _porta_em_uso_tcp(p):
            if p != preferida:
                log.warning(
                    f"Porta {preferida} já está em uso (outra automação ou "
                    f"navegador?). Usando porta backup {p}."
                )
            else:
                log.info(f"Porta CDP {p} livre.")
            return p
    raise RuntimeError(
        f"Todas as portas {config.CDP_PORTAS_TENTATIVAS} estão ocupadas. "
        "Feche alguma automação rodando e tente de novo."
    )


def cdp_disponivel(porta: int | None = None) -> bool:
    """Check leve (~1s) usado pelo polling da UI.
    Se nenhuma porta for fornecida e ainda não temos porta ativa, vasculha
    as portas tentativas — pode ter achado o SACI em alguma alternativa.
    """
    if porta is not None:
        return _ler_cdp_version(porta, timeout=0.8) is not None

    if _porta_ativa is not None:
        return _ler_cdp_version(_porta_ativa, timeout=0.8) is not None

    # Sem porta ativa ainda — varre tentativas procurando SACI nossa
    achada = descobrir_porta_cdp_nossa()
    return achada is not None


def saci_aberto(porta: int | None = None) -> bool:
    """
    True se há aba CDP carregada no SACI na porta indicada (ou na ativa).
    """
    p = porta if porta is not None else get_porta_ativa()
    return _porta_eh_nossa(p)


def abrir_navegador_com_cdp(
    navegador: NavegadorInfo | None = None,
    *,
    forcar_perfil_alternativo: bool = False,
) -> NavegadorInfo:
    """
    Abre o navegador na PRIMEIRA PORTA LIVRE da lista de tentativas com a URL
    do SACI carregada. Seleção dinâmica resolve conflito com outras automações
    que usam CDP na mesma máquina.

    Lógica:
      - Se já há CDP **nosso** (com SACI) em alguma porta → reusa, sem reabrir.
      - Senão, escolhe a primeira porta LIVRE (não ocupada por nada) e abre lá.
      - Se o navegador já está rodando sem CDP → abre uma instância paralela
        usando user-data-dir auxiliar (não toca na sua sessão original).
    """
    # 1. Já temos sessão SACI rodando em alguma porta CDP?
    porta_existente = descobrir_porta_cdp_nossa()
    if porta_existente is not None:
        nav = _navegador_rodando() or _candidatos_navegadores()[0]
        log.info(
            f"Reusando sessão SACI já existente: {nav.nome} CDP porta {porta_existente}"
        )
        return nav

    # 2. Escolhe navegador + porta livre
    nav = navegador or detectar_navegador()
    if nav is None:
        raise RuntimeError(
            "Nenhum navegador compatível encontrado (Chrome, Brave, Edge ou Opera). "
            "Instale um deles e tente novamente."
        )

    porta = escolher_porta_livre()
    _set_porta_ativa(porta)

    ja_rodando = _navegador_rodando() is not None
    usar_perfil_alt = forcar_perfil_alternativo or ja_rodando

    if usar_perfil_alt:
        _CDP_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        user_data = _CDP_PROFILE_DIR
        log.info(
            f"Abrindo {nav.nome} em perfil alternativo (porta CDP {porta}, "
            f"instância paralela): {user_data}. Você vai precisar fazer login "
            "no SACI nesta janela."
        )
    else:
        user_data = nav.user_data_dir
        log.info(
            f"Abrindo {nav.nome} com perfil real (porta CDP {porta}, "
            f"sessões/login preservados): {user_data}"
        )

    subprocess.Popen([
        str(nav.exe),
        f"--remote-debugging-port={porta}",
        f"--user-data-dir={user_data}",
        "--no-first-run",
        "--no-default-browser-check",
        "--start-maximized",
        config.URL_CIV,
    ])
    return nav


async def aguardar_cdp_pronto(timeout_s: float = 60.0, intervalo_s: float = 0.5) -> bool:
    """Polling até CDP responder ou timeout. Considera todas as portas tentativas."""
    elapsed = 0.0
    while elapsed < timeout_s:
        if cdp_disponivel():
            return True
        await asyncio.sleep(intervalo_s)
        elapsed += intervalo_s
    return False


async def conectar(pw: Playwright) -> tuple[Browser, BrowserContext, Page]:
    """
    Conecta via CDP na porta ativa do app, retorna (browser, context, page).
    Pré-condição: a UI deve ter chamado `abrir_navegador_com_cdp` antes (no
    botão "Abrir SACI"). Se nenhuma porta tiver CDP nosso, levanta erro claro.
    """
    # Pode ter aberto via UI já — ou a sessão pode estar em porta backup.
    porta = descobrir_porta_cdp_nossa() or (
        get_porta_ativa() if cdp_disponivel(get_porta_ativa()) else None
    )
    if porta is None:
        raise RuntimeError(
            f"Nenhum navegador respondendo CDP nas portas tentativas "
            f"{config.CDP_PORTAS_TENTATIVAS}. Clique em 'Abrir SACI' na tela de "
            "pré-execução pra abrir o navegador corretamente, autentique-se no "
            "SACI e tente de novo."
        )
    _set_porta_ativa(porta)

    cdp_url = f"http://localhost:{porta}"
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
