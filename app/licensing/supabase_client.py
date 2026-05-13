"""
Factory + config do cliente Supabase usado pra auth (magic link OTP) e
consulta da tabela `subscribers`.

Variaveis de ambiente esperadas (lidas via python-dotenv se houver .env):
  SUPABASE_URL          — URL do projeto, ex https://xyz.supabase.co
  SUPABASE_ANON_KEY     — anon/public key do projeto

Se as variaveis nao estiverem definidas, get_client() levanta RuntimeError.
A UI deve tratar esse erro com mensagem clara em vez de crashar.

Schema esperado no Supabase (criado manualmente uma vez):
  ┌─ tabela auth.users (gerenciada pelo Supabase Auth)
  │
  └─ tabela public.subscribers
       user_id     uuid  PK  references auth.users(id) on delete cascade
       email       text       not null
       active      bool       not null default false
       valid_until timestamptz
       updated_at  timestamptz default now()

  RLS policy (auth.uid() = user_id) pra select.
"""
import os
from pathlib import Path
from typing import Optional

from supabase import Client, create_client

from app.core.logger import get_logger

log = get_logger()

_client_cache: Optional[Client] = None


def _carregar_env() -> None:
    """Carrega .env se existir, sem sobrescrever variaveis ja definidas."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    # Procura .env no diretorio do projeto (raiz do app_anac)
    aqui = Path(__file__).resolve()
    for ancestor in [aqui.parent.parent.parent, aqui.parent.parent]:
        env_path = ancestor / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=False)
            break


def get_client() -> Client:
    """Retorna cliente Supabase singleton. Levanta se config faltar."""
    global _client_cache
    if _client_cache is not None:
        return _client_cache

    _carregar_env()
    url = os.environ.get("SUPABASE_URL", "").strip()
    anon_key = os.environ.get("SUPABASE_ANON_KEY", "").strip()

    if not url or not anon_key:
        raise RuntimeError(
            "Configuracao Supabase ausente. Defina SUPABASE_URL e "
            "SUPABASE_ANON_KEY no arquivo .env ou nas variaveis de ambiente."
        )

    _client_cache = create_client(url, anon_key)
    log.debug(f"Supabase client inicializado: {url}")
    return _client_cache
