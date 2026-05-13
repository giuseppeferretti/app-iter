# App Iter

Software desktop Windows que automatiza o lançamento de horas de voo (CIV) no SACI da ANAC. Sub-produto da **Iter** — público: pilotos brasileiros.

> Site: <https://app-anac.vercel.app> · Suporte: `suporte.iter@gmail.com`

## Stack

- **UI**: Flet 0.85 (Python + renderer Flutter)
- **Automação**: Playwright via Chrome DevTools Protocol (CDP) — usa o navegador do próprio cliente, não embute Chromium
- **Auth/Licença**: Supabase Auth (OTP por e-mail) + tabela `subscribers` com RLS
- **Pagamento**: Asaas (link de pagamento + webhook → Edge Function Supabase ativa o usuário)
- **Distribuição**: PyInstaller (`--onedir`) + Inno Setup → instalador `.exe` único

## Estrutura

```
app_anac/
├── app/
│   ├── main_app.py           entry point (registrado no launcher)
│   ├── ui/                   telas (onboarding, licença, principal, relatório)
│   ├── core/                 browser CDP + excel reader + civ_bot
│   ├── licensing/            supabase client + cache Fernet + verificador
│   ├── state/                idempotência (hash planilha) + histórico
│   └── assets/               ícones, GIF, template.xlsx
├── infra/supabase/
│   ├── migrations/           SQL schema da tabela subscribers
│   └── functions/asaas-webhook/   Edge Function (Deno/TypeScript)
├── app_iter_launcher.py      entry point empacotado pelo PyInstaller
├── build.spec                PyInstaller config
├── installer.iss             Inno Setup config
└── .env.dist                 template público (sem secrets)
```

## Desenvolvimento

```powershell
pip install -r app/requirements.txt
copy .env.example .env   # preencher SUPABASE_URL/ANON_KEY/ASAAS_CHECKOUT_URL
python -m app.main_app
```

Variáveis (em `.env`):
- `SUPABASE_URL`, `SUPABASE_ANON_KEY` — projeto Supabase
- `ASAAS_CHECKOUT_URL` — link de pagamento
- `APP_ANAC_DEV=1` — pula licença, mostra DEV pill com atalhos para todas as telas

## Build do instalador

```powershell
pip install pyinstaller
pyinstaller --clean --noconfirm build.spec
& "C:\Users\giuseppe\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer.iss
```

Saída: `Output\AppIter_Setup.exe` (~65 MB). É esse arquivo que vai pro GitHub Releases.

## Infra Supabase

Setup completo em [`infra/SETUP_ASAAS.md`](infra/SETUP_ASAAS.md). Resumo:

1. Migration `infra/supabase/migrations/001_subscribers.sql` cria tabela com RLS
2. Edge Function `asaas-webhook` recebe POST do Asaas, valida `asaas-access-token`, cria usuário via Admin API, faz `upsert` idempotente em `subscribers`
3. Secrets da function: `ASAAS_WEBHOOK_TOKEN`, `ASAAS_API_KEY`, `ASAAS_ENV`

## Distribuição

O `.exe` instalado fica em `%PROGRAMFILES%\Iter\AppIter\`. O `.env` viaja junto (vindo de `.env.dist` — chaves públicas por design, RLS protege os dados).

Updates: o usuário baixa a nova versão do mesmo link de release e reinstala (sem auto-update por enquanto).
