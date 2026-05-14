"""
Smoke test da seleção dinâmica de porta CDP.

Para evitar conflito com Chrome/outras automações no ambiente real do dev,
monkeypatcheia `config.CDP_PORTAS_TENTATIVAS` pra uma faixa alta isolada
(20222..20226) durante os testes.

Rodar: python -m scripts.smoke_porta_cdp
"""
import http.server
import socket
import socketserver
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core import browser, config

# Portas isoladas pra teste (longe das 9222 reais usadas pelo Chrome)
PORTAS_TESTE = (20222, 20223, 20224, 20225, 20226)


class _MockCdpHandler(http.server.BaseHTTPRequestHandler):
    abas_payload = "[]"

    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path == "/json/version":
            body = b'{"Browser":"Chrome/Mock","Protocol-Version":"1.3"}'
        elif self.path == "/json":
            body = self.__class__.abas_payload.encode("utf-8")
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _abrir_porta_ocupada(porta: int) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", porta))
    s.listen(1)
    return s


def _iniciar_mock_cdp(porta: int, com_saci: bool = False) -> socketserver.TCPServer:
    if com_saci:
        _MockCdpHandler.abas_payload = (
            '[{"url":"https://sistemas.anac.gov.br/SACI/CIV/Digital/incluirCIV.asp"}]'
        )
    else:
        _MockCdpHandler.abas_payload = '[{"url":"https://google.com"}]'
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", porta), _MockCdpHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    time.sleep(0.15)
    return httpd


def _check(label: str, ok: bool) -> int:
    print(f"  {'OK' if ok else 'FAIL'}  {label}")
    return 0 if ok else 1


def _reset_state():
    browser._porta_ativa = None


def main() -> int:
    # Monkeypatch das portas tentativas pra faixa isolada de teste
    original = config.CDP_PORTAS_TENTATIVAS
    config.CDP_PORTAS_TENTATIVAS = PORTAS_TESTE
    try:
        return _rodar_testes()
    finally:
        config.CDP_PORTAS_TENTATIVAS = original


def _rodar_testes() -> int:
    falhas = 0

    # ── 1. Nenhuma porta ocupada → escolhe a primeira ──────────────────────
    print(f"\n[1] Nenhuma porta ocupada -> escolhe {PORTAS_TESTE[0]}")
    _reset_state()
    porta = browser.escolher_porta_livre()
    falhas += _check(f"porta escolhida = {porta}", porta == PORTAS_TESTE[0])

    # ── 2. Porta[0] ocupada → escolhe Porta[1] ─────────────────────────────
    print(f"\n[2] {PORTAS_TESTE[0]} ocupada por outro processo -> {PORTAS_TESTE[1]}")
    _reset_state()
    s = _abrir_porta_ocupada(PORTAS_TESTE[0])
    try:
        falhas += _check(f"_porta_em_uso_tcp({PORTAS_TESTE[0]}) = True",
                         browser._porta_em_uso_tcp(PORTAS_TESTE[0]))
        falhas += _check(f"_porta_em_uso_tcp({PORTAS_TESTE[1]}) = False",
                         not browser._porta_em_uso_tcp(PORTAS_TESTE[1]))
        porta = browser.escolher_porta_livre()
        falhas += _check(f"escolher_porta_livre() = {porta}",
                         porta == PORTAS_TESTE[1])
    finally:
        s.close()

    # ── 3. Porta[0] e Porta[1] ocupadas → escolhe Porta[2] ─────────────────
    print(f"\n[3] {PORTAS_TESTE[0]} e {PORTAS_TESTE[1]} ocupadas -> {PORTAS_TESTE[2]}")
    _reset_state()
    s1 = _abrir_porta_ocupada(PORTAS_TESTE[0])
    s2 = _abrir_porta_ocupada(PORTAS_TESTE[1])
    try:
        porta = browser.escolher_porta_livre()
        falhas += _check(f"escolher_porta_livre() = {porta}",
                         porta == PORTAS_TESTE[2])
    finally:
        s1.close()
        s2.close()

    # ── 4. Mock CDP com SACI em Porta[1] → descoberta acha ─────────────────
    print(f"\n[4] Mock CDP COM SACI em {PORTAS_TESTE[1]} -> descobre essa porta")
    _reset_state()
    mock = _iniciar_mock_cdp(PORTAS_TESTE[1], com_saci=True)
    try:
        falhas += _check(f"cdp_disponivel({PORTAS_TESTE[1]}) = True",
                         browser.cdp_disponivel(PORTAS_TESTE[1]))
        falhas += _check(f"cdp_disponivel({PORTAS_TESTE[0]}) = False",
                         not browser.cdp_disponivel(PORTAS_TESTE[0]))
        achada = browser.descobrir_porta_cdp_nossa()
        falhas += _check(f"descobrir_porta_cdp_nossa() = {achada}",
                         achada == PORTAS_TESTE[1])
        falhas += _check(f"get_porta_ativa() = {browser.get_porta_ativa()}",
                         browser.get_porta_ativa() == PORTAS_TESTE[1])
    finally:
        mock.shutdown()
        mock.server_close()
        time.sleep(0.2)

    # ── 5. Mock CDP SEM SACI em Porta[0] (outra automação) ─────────────────
    print(f"\n[5] Mock CDP SEM SACI em {PORTAS_TESTE[0]} (outra automação) "
          f"-> escolhe {PORTAS_TESTE[1]} livre")
    _reset_state()
    mock = _iniciar_mock_cdp(PORTAS_TESTE[0], com_saci=False)
    try:
        falhas += _check(f"_porta_eh_nossa({PORTAS_TESTE[0]}) = False (CDP sem SACI)",
                         not browser._porta_eh_nossa(PORTAS_TESTE[0]))
        achada = browser.descobrir_porta_cdp_nossa()
        falhas += _check(f"descobrir_porta_cdp_nossa() = None (CDP alheio)",
                         achada is None)
        porta = browser.escolher_porta_livre()
        falhas += _check(f"escolher_porta_livre() = {porta} (pula a ocupada)",
                         porta == PORTAS_TESTE[1])
    finally:
        mock.shutdown()
        mock.server_close()
        time.sleep(0.2)

    print(f"\n{'=' * 50}")
    if falhas == 0:
        print("TODOS os cenários passaram.")
        return 0
    print(f"{falhas} verificações FALHARAM.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
