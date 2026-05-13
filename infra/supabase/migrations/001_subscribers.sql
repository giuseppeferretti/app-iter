-- Tabela subscribers + RLS
-- Rodar UMA VEZ no SQL Editor do Supabase (ou via supabase db push se você
-- linkou o projeto pela CLI).
--
-- Modelo:
--   - 1 linha por assinante
--   - PK = user_id (link com auth.users — o usuário só existe quando paga)
--   - active=true quando assinatura ativa (pagamento confirmado, não vencido)
--   - valid_until = data limite de acesso (nextDueDate do Asaas + grace 7d)
--   - asaas_customer_id/subscription_id pra rastreabilidade
--   - ultimo_evento mostra o último webhook recebido (debug)
--
-- Segurança:
--   - RLS ligado
--   - Política de SELECT: cada usuário só lê a própria linha (auth.uid())
--   - Sem políticas de INSERT/UPDATE/DELETE: só service_role consegue escrever
--     (a Edge Function asaas-webhook usa SUPABASE_SERVICE_ROLE_KEY)

create table if not exists public.subscribers (
  user_id               uuid primary key references auth.users(id) on delete cascade,
  email                 text not null,
  asaas_customer_id     text,
  asaas_subscription_id text,
  active                boolean not null default false,
  valid_until           timestamptz,
  ultimo_evento         text,
  updated_at            timestamptz not null default now()
);

-- Índice secundário pelo customer_id do Asaas (consulta no webhook)
create index if not exists subscribers_asaas_customer_idx
  on public.subscribers(asaas_customer_id);

-- Habilita RLS na tabela
alter table public.subscribers enable row level security;

-- Cada usuário só pode ler a PRÓPRIA linha. O app desktop está autenticado
-- via auth.uid() (sessão Supabase OTP).
drop policy if exists "users read own subscription" on public.subscribers;
create policy "users read own subscription"
  on public.subscribers
  for select
  using (auth.uid() = user_id);

-- Não criar policies de insert/update/delete:
-- ausência de policy = bloqueio total pra anon e authenticated.
-- Apenas o service_role bypass RLS e pode escrever (vem da Edge Function).

-- Trigger pra atualizar updated_at automaticamente
create or replace function public.subscribers_set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists subscribers_updated_at_trigger on public.subscribers;
create trigger subscribers_updated_at_trigger
  before update on public.subscribers
  for each row
  execute function public.subscribers_set_updated_at();
