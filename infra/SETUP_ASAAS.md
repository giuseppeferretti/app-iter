# SETUP — Asaas + Supabase (sandbox)

Tutorial completo pra ativar o fluxo de cobrança end-to-end: cliente paga no site → webhook do Asaas → Supabase Edge Function ativa o usuário → app desktop libera acesso.

**Tempo estimado:** ~25 minutos.

**Pré-requisitos:**
- Conta no [Asaas Sandbox](https://sandbox.asaas.com) (você já tem)
- Conta no [Supabase](https://supabase.com) (free tier basta)
- Node.js + npm instalado (pra Supabase CLI)
- Python 3.11+ (pro script de teste)

---

## 1. Supabase — criar projeto + schema (~5 min)

### 1.1 Criar projeto

1. Vá em [supabase.com/new](https://supabase.com/new)
2. Crie projeto com:
   - **Name:** `app-iter` (ou o que preferir)
   - **Database password:** gere uma forte e anote
   - **Region:** `South America (São Paulo)` — menor latência
3. Aguarde ~2 min provisionar

### 1.2 Copiar credenciais

No painel do projeto, em **Settings > API**, copie estes 3 valores (você vai precisar de todos):

- **Project URL** → vira `SUPABASE_URL` no `.env` do app
- **anon public** key → vira `SUPABASE_ANON_KEY` no `.env` do app
- **service_role secret** key → vai como secret da Edge Function (**NÃO** entra no `.env` do app)

> ⚠️ A `service_role key` tem privilégios totais. **Nunca** suba pro git ou pra um cliente. Só pode ficar nos secrets do Supabase.

### 1.3 Rodar a migration

1. No painel Supabase, vá em **SQL Editor** → **New query**
2. Cole o conteúdo de [`infra/supabase/migrations/001_subscribers.sql`](supabase/migrations/001_subscribers.sql) e clique **Run**
3. New query de novo, cole [`infra/supabase/migrations/002_welcome_email.sql`](supabase/migrations/002_welcome_email.sql) e clique **Run** (adiciona a coluna `welcome_email_sent_at` usada pelo envio idempotente do e-mail de boas-vindas)
4. Confere em **Table Editor**: tabela `subscribers` deve ter as colunas `user_id, email, asaas_customer_id, asaas_subscription_id, active, valid_until, ultimo_evento, welcome_email_sent_at, updated_at`.

### 1.4 Instalar Supabase CLI

```powershell
# Windows (via Scoop):
scoop install supabase

# OU via npm (cross-platform):
npm install -g supabase
```

Confirme: `supabase --version`.

### 1.5 Login e link no projeto

```powershell
supabase login          # abre browser, autoriza
supabase link --project-ref XXXXXXXX  # XXXXXXXX = última parte da Project URL
```

Exemplo: se Project URL é `https://abcdefgh.supabase.co`, o ref é `abcdefgh`.

---

## 2. Asaas Sandbox — configuração inicial (~10 min)

### 2.1 Pegar API Key

1. Login em [sandbox.asaas.com](https://sandbox.asaas.com)
2. Vá em **Integrações > API** (canto superior esquerdo, menu Settings)
3. Copie a **API Key** (formato `$aaas_XXXXX...`). Guarde — vai virar `ASAAS_API_KEY`.

### 2.2 Criar o Link de Pagamento

1. Menu lateral: **Cobranças > Links de Pagamento > Novo link**
2. Preencha:
   - **Nome:** `App Iter — assinatura mensal`
   - **Descrição:** `Acesso ao App Iter para lançamento automatizado de horas no SACI`
   - **Tipo de cobrança:** **Assinatura**
   - **Valor:** `9,90`
   - **Ciclo:** `Mensal`
   - **Formas de pagamento:** marque **Pix** e **Cartão de crédito**
   - **Imagem:** opcional (pode usar o `iter-wordmark.png`)
3. **Salvar**. O Asaas gera uma URL pública tipo `https://sandbox.asaas.com/c/XXXXXX` — **copie**, será sua `ASAAS_CHECKOUT_URL` e `NEXT_PUBLIC_CHECKOUT_URL`.

### 2.3 Gerar token do webhook

Gere uma string aleatória de ~32 caracteres. Pode usar:

```powershell
# PowerShell
[Guid]::NewGuid().ToString("N") + [Guid]::NewGuid().ToString("N").Substring(0,4)
```

Ou em qualquer prompt online de "random string". Guarde — será `ASAAS_WEBHOOK_TOKEN`.

> Esse token autentica que a requisição que chega na Edge Function veio do Asaas (e não de um atacante). Sem ele, qualquer pessoa que descobrir a URL da function poderia ativar contas.

---

## 3. Deploy da Edge Function (~5 min)

### 3.1 Setar secrets

```powershell
cd c:\dev\app_anac

supabase secrets set `
    ASAAS_WEBHOOK_TOKEN="cole-aqui-o-token-do-2.3" `
    ASAAS_API_KEY="cole-aqui-a-api-key-do-2.1" `
    ASAAS_ENV="sandbox" `
    RESEND_API_KEY="re_xxxxxxxxxxxxxxxxxxxxx" `
    "WELCOME_EMAIL_FROM=App Iter <onboarding@resend.dev>" `
    APP_DOWNLOAD_URL="https://github.com/giuseppeferretti/app-iter/releases/latest/download/AppIter_Setup.exe" `
    SUPPORT_EMAIL="suporte.iter@gmail.com"
```

(O `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY` já são automaticamente injetados pelo Supabase nas Edge Functions — não precisa setar.)

> **E-mail de boas-vindas (Resend)** — quando `RESEND_API_KEY` está setado, a Edge Function manda um e-mail automático com o link de download e instruções após cada ativação (`PAYMENT_CONFIRMED`). A coluna `welcome_email_sent_at` em `subscribers` garante idempotência (não envia duas vezes pro mesmo cliente). Se `RESEND_API_KEY` não estiver setado, o envio é silenciosamente skipado e o app funciona igual — só que o cliente fica sem o e-mail.
>
> **Remetente:** `onboarding@resend.dev` é o sandbox do Resend (funciona pra qualquer destinatário sem verificar domínio, mas com cara de teste). Quando você tiver um domínio próprio (ex.: `iter.com.br`) verificado no Resend, troque `WELCOME_EMAIL_FROM` pra `App Iter <noreply@iter.com.br>`.

### 3.2 Deploy

```powershell
supabase functions deploy asaas-webhook --no-verify-jwt
```

> `--no-verify-jwt` porque o Asaas não autentica com JWT do Supabase; usamos o header `asaas-access-token` em vez disso.

Saída esperada:
```
Deployed Function asaas-webhook to project XXXXXXXX
URL: https://XXXXXXXX.supabase.co/functions/v1/asaas-webhook
```

**Copie essa URL** — é o que vai no painel Asaas no próximo passo.

### 3.3 Smoke test (opcional, antes de plugar no Asaas)

```powershell
curl https://XXXXXXXX.supabase.co/functions/v1/asaas-webhook
```

Deve responder `{"ok":true,"service":"asaas-webhook"}`.

---

## 4. Asaas — configurar webhook (~3 min)

1. Painel Asaas > **Integrações > Webhooks > Adicionar webhook**
2. Preencha:
   - **URL:** a URL da Edge Function do passo 3.2
   - **Access Token:** o **mesmo valor** do `ASAAS_WEBHOOK_TOKEN` (passo 2.3). O Asaas envia esse valor no header `asaas-access-token` a cada requisição.
   - **Versão da API:** `v3`
   - **E-mail para alerta de falhas:** seu e-mail (avisa se a Edge Function rejeitar requisições)
   - **Eventos:** marque pelo menos:
     - `PAYMENT_CREATED`
     - `PAYMENT_CONFIRMED`
     - `PAYMENT_RECEIVED`
     - `PAYMENT_OVERDUE`
     - `PAYMENT_REFUNDED`
     - `PAYMENT_DELETED`
     - `SUBSCRIPTION_CREATED`
     - `SUBSCRIPTION_INACTIVATED`
     - `SUBSCRIPTION_DELETED`
3. **Salvar**. Asaas mostra um botão **Testar webhook** — clica pra confirmar conexão.

---

## 5. App desktop — `.env` (~2 min)

```powershell
cd c:\dev\app_anac
Copy-Item .env.example .env
notepad .env  # ou seu editor favorito
```

Preencha:

```
SUPABASE_URL=https://XXXXXXXX.supabase.co          # do passo 1.2
SUPABASE_ANON_KEY=eyJhbGciOiJI...                  # anon public, do 1.2
ASAAS_CHECKOUT_URL=https://sandbox.asaas.com/c/XX  # do passo 2.2
APP_ANAC_DEV=0                                     # liga a tela de licença real
```

Salve. Rode o app:

```powershell
python -m app.main_app
```

Deve cair direto na tela de licença (sem pílula DEV).

---

## 6. Site app-anac (Vercel) — variável de ambiente (~2 min)

1. [vercel.com](https://vercel.com) > seu projeto `app-anac`
2. **Settings > Environment Variables**
3. Adicionar:
   - **Key:** `NEXT_PUBLIC_CHECKOUT_URL`
   - **Value:** a URL do Asaas (passo 2.2)
   - **Environments:** todos (Production, Preview, Development)
4. **Save**
5. **Deployments > último deploy > Redeploy** (pra pegar a env var)

Agora o site, em produção, aponta o botão "Adquirir agora" pra `https://sandbox.asaas.com/c/XXX`.

---

## 7. Teste end-to-end (~5 min)

### 7.1 Pagamento de teste

1. Abra o site (ou pega o link direto do passo 2.2)
2. Clique **Adquirir agora** → cai no checkout Asaas
3. Preencha:
   - Nome: `Teste Iter`
   - **E-mail: use o e-mail que você vai usar no app** (importantíssimo — é a identidade)
   - CPF: qualquer válido (geradores online)
4. Pague via **Pix** ou **Cartão de teste** do Asaas:
   - Cartão de teste aprovado: `5162 3061 8001 7090` · CVV `318` · validade `09/27`
   - Pix de teste: clica "Já paguei" no painel do Asaas pra simular aprovação

### 7.2 Verificar a Edge Function

```powershell
supabase functions logs asaas-webhook --tail
```

Você deve ver linhas como:
```
[asaas-webhook] event=PAYMENT_CREATED id=evt_...
[asaas-webhook] OK email=teste@iter.com active=false valid_until=...
[asaas-webhook] event=PAYMENT_CONFIRMED id=evt_...
[asaas-webhook] OK email=teste@iter.com active=true valid_until=...
```

### 7.3 Verificar a tabela

Supabase > **Table Editor > subscribers**. Deve aparecer 1 linha com:
- `email` = e-mail que você usou
- `active` = `true` (após PAYMENT_CONFIRMED)
- `valid_until` = ~37 dias no futuro
- `asaas_customer_id` / `asaas_subscription_id` preenchidos

### 7.4 Ativar no app

1. Abra o app desktop: `python -m app.main_app`
2. Tela de licença: digita o **mesmo e-mail** que usou no Asaas
3. **Enviar código** → recebe OTP por e-mail (do Supabase)
4. Digita o código → **Validar código**
5. Cai na tela principal — pronto.

---

## 8. Promoção pra produção (quando estiver tudo verde)

1. No Asaas (produção, [asaas.com](https://www.asaas.com)):
   - Refaça os passos 2.1, 2.2, 2.3 (novos API Key, link, token)
2. No Supabase, atualize os secrets:
   ```powershell
   supabase secrets set `
       ASAAS_WEBHOOK_TOKEN="novo-token-de-producao" `
       ASAAS_API_KEY="novo-api-key-de-producao" `
       ASAAS_ENV="production"
   ```
3. Redeploy: `supabase functions deploy asaas-webhook --no-verify-jwt`
4. Refaça o webhook no painel Asaas de produção
5. App: troca `ASAAS_CHECKOUT_URL` no `.env` (e quando empacotar via PyInstaller, o `.env` vira o env vars do executável)
6. Site Vercel: troca `NEXT_PUBLIC_CHECKOUT_URL`

> ⚠️ Antes da promoção, teste pelo menos 3 cenários em sandbox: (a) pagamento confirmado, (b) cancelamento da assinatura, (c) atraso de pagamento — todos devem refletir corretamente na tabela `subscribers`.

---

## Promover de Sandbox → Produção

Quando o fluxo estiver validado em sandbox e você quiser cobrar de verdade:

### A. Asaas (manual, painel web)

1. Login em [https://www.asaas.com](https://www.asaas.com) (conta de **produção**, não sandbox)
2. Complete o cadastro da conta caso ainda não tenha (KYC, dados bancários — exigido pra movimentar dinheiro real)
3. Em **Integrações > API**: gere/copie sua **API Key de produção** (`$aaas_prod_...`)
4. Em **Cobranças > Links de Pagamento**: crie um novo link
   - Nome: `App Iter — Mensal`
   - Valor: R$ 9,90
   - Tipo: **Assinatura mensal**
   - Formas: Pix recorrente + Cartão de crédito
   - Copie a URL gerada — ex.: `https://www.asaas.com/c/abc123`
5. Em **Integrações > Webhooks**: adicione webhook
   - URL: `https://alldxuligzfdxgrknqxf.supabase.co/functions/v1/asaas-webhook`
   - Access Token: gere uma string aleatória de 32+ chars (você passa pro script abaixo)
   - Eventos: marque **todos** de "Assinaturas" e "Cobranças"
   - Modo: **SEQUENCIAL**
   - Estado: **HABILITADO**

> Pode deixar o webhook sandbox ativo em paralelo enquanto testa, mas remova quando estiver vendo eventos reais. Os dois apontam pra mesma Edge Function, e ela só funciona pra um ambiente por vez (controlado por `ASAAS_ENV`).

### B. Promoção do lado do código + Supabase (automatizado)

Roda o script:

```powershell
.\scripts\promote_to_production.ps1 `
  -CheckoutUrl  "https://www.asaas.com/c/SEU-LINK-PROD" `
  -AsaasApiKey  "$aaas_prod_xxxxxxx" `
  -WebhookToken "<o-mesmo-access-token-que-voce-pos-no-webhook-asaas>" `
  -Version      "v0.1.1"
```

Ele faz:
- Seta no Supabase: `ASAAS_ENV=production`, nova `ASAAS_API_KEY`, novo `ASAAS_WEBHOOK_TOKEN`
- Atualiza `.env.dist` com a URL de produção
- Rebuilda o instalador (PyInstaller + Inno Setup)
- Publica nova release no GitHub
- Imprime checklist de Vercel + teste

### C. Vercel (manual, painel web)

1. [Vercel dashboard](https://vercel.com/dashboard) → projeto `app-anac` → **Settings > Environment Variables**
2. Edite `NEXT_PUBLIC_CHECKOUT_URL` → cole a URL de produção do Asaas
3. Apague a entrada antiga (sandbox)
4. **Deployments** → último deploy → **Redeploy**

### D. Validação end-to-end (cartão real)

```powershell
npx supabase functions logs asaas-webhook --tail
```

Em outra janela, abra `https://app-anac.vercel.app` no anônimo, clique "Adquirir agora", pague Pix de R$ 9,90. Espere ver no log:

```
[asaas-webhook] event=PAYMENT_CONFIRMED ...
[asaas-webhook] OK email=... acao=activate active=true ... welcome_email=sent
```

Confere caixa de e-mail. Clique no link, instala o `AppIter_Setup.exe`, abre o app, digita o e-mail da compra, recebe OTP, entra.

---

## Troubleshooting

### Edge Function retornando 401 em cada call
- `asaas-access-token` enviado pelo Asaas não bate com `ASAAS_WEBHOOK_TOKEN` do Supabase secrets. Confira no painel Asaas (Integrações > Webhooks > seu webhook > editar) que o Access Token está EXATAMENTE igual ao que rodou em `supabase secrets set`.

### "Erro Asaas: GET /customers/X retornou 401"
- `ASAAS_API_KEY` errada. Pegue de novo em Integrações > API.

### Webhook do Asaas marca o evento como "Falha" no painel
- Olhe o response status nos logs do Asaas: 4xx = erro de auth/payload, 5xx = bug na função. Use `supabase functions logs asaas-webhook --tail` pra diagnosticar.

### Teste local da Edge Function
- Rode `supabase functions serve asaas-webhook --env-file .env.local` (crie um `.env.local` em `supabase/functions/asaas-webhook/` com os mesmos secrets)
- Em outro terminal: `python infra/supabase/functions/asaas-webhook/test_payload.py confirmed seu@email.com`
- Deve responder 200 e criar linha em `subscribers`

### Cliente paga mas `active` continua `false`
- O Asaas dispara `PAYMENT_CREATED` ANTES da confirmação do pagamento. `active` só vira `true` em `PAYMENT_CONFIRMED` ou `PAYMENT_RECEIVED`. Aguarde 1-2 min após o pagamento.
- Se mesmo assim não atualizar, cheque os logs da função.
