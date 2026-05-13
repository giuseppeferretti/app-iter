"""
Auth via Supabase + check de assinatura ativa.

Fluxo:
  1. tela_licenca chama enviar_otp(email) — Supabase manda código de 6 dígitos
  2. Usuário digita o código, a tela chama verificar_otp(email, codigo)
  3. Sessão (access+refresh) criptografada via cache.salvar_sessao
  4. A cada abertura do app, main_app chama checar_acesso():
       a. Lê o cache. Se vazio: bloqueia (UI vai para a tela_licenca)
       b. Se access_token expirado: tenta refresh_session
       c. A cada CACHE_TTL_HORAS: revalida a assinatura via tabela subscribers
       d. Se a assinatura está inativa ou vencida: bloqueia
       e. Se está offline e dentro do grace period: libera

Sem servidor próprio — toda a lógica server-side vive no Supabase:
  - Auth (sign_in_with_otp, verify_otp, refresh_session)
  - Tabela subscribers (Edge Function escreve via service_role, app lê com RLS)
  - Webhook do gateway de pagamento (Asaas/MP/etc) -> Edge Function ->
    upsert na tabela subscribers
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, TypedDict

from app.core.logger import get_logger
from app.licensing.cache import (
    SessaoIter,
    ler_sessao,
    limpar_sessao,
    salvar_sessao,
)
from app.licensing.supabase_client import get_client

log = get_logger()

CACHE_TTL_HORAS    = 24   # revalida assinatura ativa a cada 24h
GRACE_PERIOD_DIAS  = 7    # funciona offline ate 7d se Supabase estiver fora
ACCESS_TOKEN_BUFFER_MIN = 5  # renova access antes de expirar


class ResultadoEnvio(TypedDict):
    ok: bool
    motivo: str


class ResultadoVerificacao(TypedDict):
    ok: bool
    motivo: str
    email: Optional[str]


def _agora() -> datetime:
    return datetime.now(timezone.utc)


# ── 1. Enviar OTP por email ───────────────────────────────────────────────────


def enviar_otp(email: str) -> ResultadoEnvio:
    """
    Manda o codigo OTP de 6 digitos pro email informado.
    Cria a auth.user se for primeiro contato — a tabela subscribers e que
    valida se o usuario tem assinatura ativa, entao criar conta sozinho nao
    libera acesso.
    """
    email = (email or "").strip().lower()
    if "@" not in email:
        return {"ok": False, "motivo": "E-mail inválido"}

    try:
        client = get_client()
    except RuntimeError as exc:
        return {"ok": False, "motivo": str(exc)}

    try:
        client.auth.sign_in_with_otp({
            "email": email,
            "options": {
                # Cria o usuário automaticamente se ainda não existe.
                # O acesso continua dependendo do status na tabela subscribers.
                "should_create_user": True,
            },
        })
        log.info(f"OTP enviado para {email}.")
        return {"ok": True, "motivo": "Enviamos um código de 6 dígitos para o seu e-mail."}
    except Exception as exc:
        log.warning(f"Falha ao enviar OTP para {email}: {exc}")
        return {"ok": False, "motivo": f"Falha ao enviar o código: {exc}"}


# ── 2. Verificar OTP e salvar sessao ──────────────────────────────────────────


def verificar_otp(email: str, codigo: str) -> ResultadoVerificacao:
    """
    Troca o OTP por uma sessao Supabase. Em sucesso, persiste localmente.
    """
    email = (email or "").strip().lower()
    codigo = (codigo or "").strip()
    if not codigo:
        return {"ok": False, "motivo": "Código vazio", "email": None}

    try:
        client = get_client()
    except RuntimeError as exc:
        return {"ok": False, "motivo": str(exc), "email": None}

    try:
        resp = client.auth.verify_otp({
            "email": email,
            "token": codigo,
            "type": "email",
        })
    except Exception as exc:
        log.warning(f"Falha ao verificar OTP de {email}: {exc}")
        return {"ok": False, "motivo": "Código inválido ou expirado", "email": None}

    sess = resp.session
    if sess is None:
        return {"ok": False, "motivo": "Sessão não retornada", "email": None}

    expires_at = datetime.fromtimestamp(sess.expires_at, tz=timezone.utc)
    salvar_sessao(SessaoIter(
        email=email,
        access_token=sess.access_token,
        refresh_token=sess.refresh_token,
        expires_at=expires_at,
        proxima_revalidacao=_agora(),  # força check de assinatura já na primeira abertura
    ))
    log.info(f"Sessão Iter ativada para {email}.")
    return {"ok": True, "motivo": "OK", "email": email}


# ── 3. Check de acesso por boot do app ────────────────────────────────────────


def checar_acesso() -> bool:
    """
    Chamado na abertura do app.

    Estrategia:
      1. Sem cache local       -> False (UI vai pra tela_licenca)
      2. access_token expirado -> tenta refresh_session
      3. Cache de subscription expirado -> consulta tabela subscribers
      4. Subscription inativa  -> False (e limpa cache)
      5. Online indisponivel + grace period nao venceu -> True (libera)
      6. Senao -> True
    """
    sess = ler_sessao()
    if sess is None:
        return False

    agora = _agora()

    # Renova access_token se proximo de expirar (ou ja expirou)
    if sess.expires_at - agora < timedelta(minutes=ACCESS_TOKEN_BUFFER_MIN):
        sess_nova = _refresh(sess)
        if sess_nova is None:
            # Offline ou refresh falhou — checa grace period
            if _ainda_em_grace(sess, agora):
                log.warning("Sem internet — usando grace period offline.")
                return True
            log.warning("Refresh do token falhou e grace period venceu.")
            return False
        sess = sess_nova

    # Revalida status de assinatura periodicamente
    if sess.proxima_revalidacao <= agora:
        ativo = _query_assinatura_ativa(sess)
        if ativo is None:
            # Erro de rede — grace period
            if _ainda_em_grace(sess, agora):
                log.warning("Sem internet pra revalidar assinatura — grace period.")
                return True
            return False
        if not ativo:
            log.warning(f"Assinatura inativa/vencida para {sess.email}.")
            limpar_sessao()
            return False
        # Atualiza proxima_revalidacao
        sess.proxima_revalidacao = agora + timedelta(hours=CACHE_TTL_HORAS)
        salvar_sessao(sess)

    return True


def _refresh(sess: SessaoIter) -> Optional[SessaoIter]:
    """Renova access_token via refresh_token. None em caso de falha."""
    try:
        client = get_client()
    except RuntimeError:
        return None
    try:
        resp = client.auth.refresh_session(sess.refresh_token)
    except Exception as exc:
        log.debug(f"refresh_session falhou: {exc}")
        return None

    nova_sess = resp.session
    if nova_sess is None:
        return None

    sess.access_token = nova_sess.access_token
    sess.refresh_token = nova_sess.refresh_token
    sess.expires_at = datetime.fromtimestamp(nova_sess.expires_at, tz=timezone.utc)
    salvar_sessao(sess)
    log.debug("access_token renovado via refresh_token.")
    return sess


def _query_assinatura_ativa(sess: SessaoIter) -> Optional[bool]:
    """
    Consulta a tabela subscribers (RLS filtra por auth.uid()).
    Retorna True/False, ou None se rede falhou.
    """
    try:
        client = get_client()
        client.postgrest.auth(sess.access_token)
        resp = (
            client.table("subscribers")
            .select("active, valid_until")
            .limit(1)
            .execute()
        )
    except Exception as exc:
        log.debug(f"Query subscribers falhou: {exc}")
        return None

    linhas = resp.data or []
    if not linhas:
        return False

    linha = linhas[0]
    if not linha.get("active"):
        return False

    valido_ate_iso = linha.get("valid_until")
    if valido_ate_iso:
        valido_ate = datetime.fromisoformat(valido_ate_iso.replace("Z", "+00:00"))
        if valido_ate < _agora():
            return False

    return True


def _ainda_em_grace(sess: SessaoIter, agora: datetime) -> bool:
    """True se proxima_revalidacao venceu ha menos de GRACE_PERIOD_DIAS."""
    return (agora - sess.proxima_revalidacao) < timedelta(days=GRACE_PERIOD_DIAS)
