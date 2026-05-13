-- Coluna pra rastrear envio do e-mail de boas-vindas (idempotência).
-- A Edge Function asaas-webhook só dispara o e-mail uma vez por subscriber:
-- se welcome_email_sent_at IS NULL no momento da ativação, manda + seta.

alter table public.subscribers
  add column if not exists welcome_email_sent_at timestamptz;
