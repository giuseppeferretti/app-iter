# Promove o App Iter de Asaas Sandbox para Produção.
#
# O que este script automatiza:
#   1. Atualiza Supabase secrets: ASAAS_ENV=production + nova ASAAS_API_KEY
#      + novo ASAAS_WEBHOOK_TOKEN (regerado).
#   2. Atualiza .env.dist com a URL de produção do Asaas.
#   3. Rebuilda o instalador (pyinstaller + Inno Setup).
#   4. Publica nova release no GitHub (default: v0.1.1).
#   5. Imprime o checklist do que VOCÊ precisa fazer manualmente no
#      painel Asaas + Vercel (não dá pra automatizar via CLI).
#
# Uso:
#   .\scripts\promote_to_production.ps1 `
#       -CheckoutUrl  "https://www.asaas.com/c/SEU-LINK-PROD" `
#       -AsaasApiKey  "$aaas_PRODUCAO_xxx" `
#       -WebhookToken "<gere-um-token-aleatorio-32-chars>" `
#       -Version      "v0.1.1"

param(
    [Parameter(Mandatory=$true)]
    [string]$CheckoutUrl,

    [Parameter(Mandatory=$true)]
    [string]$AsaasApiKey,

    [Parameter(Mandatory=$true)]
    [string]$WebhookToken,

    [string]$Version = "v0.1.1"
)

$env:Path = "C:\Program Files\GitHub CLI;" + $env:Path

function Step($msg) { Write-Host "`n>>> $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "    $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "    $msg" -ForegroundColor Red; exit 1 }

Set-Location c:\dev\app_anac

# ── Sanity ──────────────────────────────────────────────────────────────────
Step "Sanity checks"
if ($CheckoutUrl -notmatch "^https://www\.asaas\.com/") {
    Fail "CheckoutUrl não parece ser de produção (deve começar com https://www.asaas.com/...)."
}
if ($AsaasApiKey.Length -lt 30) { Fail "AsaasApiKey muito curta — confira na conta de produção do Asaas." }
if ($WebhookToken.Length -lt 16) { Fail "WebhookToken muito curto — use ao menos 32 chars aleatórios." }
Ok "Parâmetros OK"

# ── 1. Supabase secrets ─────────────────────────────────────────────────────
Step "Atualizando secrets do Supabase (Edge Function)"
& npx -y supabase secrets set `
    ASAAS_ENV=production `
    "ASAAS_API_KEY=$AsaasApiKey" `
    "ASAAS_WEBHOOK_TOKEN=$WebhookToken"
if ($LASTEXITCODE -ne 0) { Fail "Falha ao atualizar secrets." }
Ok "Secrets atualizadas"

# ── 2. .env.dist do instalador ──────────────────────────────────────────────
Step "Atualizando .env.dist"
$envDist = @"
# Configuração do App Iter (instalado).
# Estas chaves são públicas por design — o Supabase usa RLS para proteger
# os dados; a anon key só permite ler a linha da própria conta após login.

# ── Supabase ────────────────────────────────────────────────────────────────
SUPABASE_URL=https://alldxuligzfdxgrknqxf.supabase.co
SUPABASE_ANON_KEY=sb_publishable_nbohNu8rX5Ec5xNDFOs-2Q_QzTa0768

# ── Asaas (produção) ────────────────────────────────────────────────────────
ASAAS_CHECKOUT_URL=$CheckoutUrl

# ── Modo ────────────────────────────────────────────────────────────────────
APP_ANAC_DEV=0
"@
$utf8bom = New-Object System.Text.UTF8Encoding($true)
[System.IO.File]::WriteAllText("c:\dev\app_anac\.env.dist", $envDist, $utf8bom)
Ok ".env.dist atualizado pra produção"

# ── 3. Rebuild do instalador ────────────────────────────────────────────────
Step "Limpando builds anteriores"
Remove-Item dist, build, Output -Recurse -Force -ErrorAction SilentlyContinue
Ok "Limpo"

Step "Rodando PyInstaller"
& pyinstaller --clean --noconfirm build.spec | Out-Null
if ($LASTEXITCODE -ne 0) { Fail "PyInstaller falhou." }
Ok "Bundle gerado em dist\AppIter\"

Step "Rodando Inno Setup"
& "C:\Users\giuseppe\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer.iss | Out-Null
if ($LASTEXITCODE -ne 0) { Fail "Inno Setup falhou." }
$installer = "Output\AppIter_Setup.exe"
if (-not (Test-Path $installer)) { Fail "Instalador não encontrado em $installer." }
$mb = [math]::Round((Get-Item $installer).Length / 1MB, 1)
Ok "Instalador: $installer ($mb MB)"

# ── 4. Commit + push + release ──────────────────────────────────────────────
Step "Commitando .env.dist atualizado"
& git add .env.dist
& git commit -m "chore: promote to Asaas production ($Version)"
if ($LASTEXITCODE -ne 0) {
    Warn "Nada novo pra comitar (ou commit falhou) — seguindo."
}

Step "Publicando release $Version"
& .\scripts\publish_release.ps1 -Version $Version

# ── 5. Checklist manual ─────────────────────────────────────────────────────
Write-Host "`n================================================================" -ForegroundColor Yellow
Write-Host " AGORA AS ETAPAS QUE PRECISAM DE VOCÊ (não dá pra automatizar):" -ForegroundColor Yellow
Write-Host "================================================================" -ForegroundColor Yellow

Write-Host @"

[1] Asaas — painel de PRODUÇÃO (https://www.asaas.com)

    1.1. Confirme que o link de pagamento de produção está ativo
         e aceita Pix + Cartão recorrente.
         URL configurada: $CheckoutUrl

    1.2. Settings → Webhooks → Adicionar webhook:
         - URL: https://alldxuligzfdxgrknqxf.supabase.co/functions/v1/asaas-webhook
         - Access Token: $WebhookToken
         - Eventos: marque TODOS de "Assinaturas" e "Cobranças"
         - Modo: SEQUENCIAL
         - Status: HABILITADO (NÃO interrompido)

    1.3. Desabilite ou remova o webhook SANDBOX antigo
         pra evitar receber eventos de teste em produção.

[2] Vercel — Environment Variables (https://vercel.com/dashboard)

    2.1. Projeto app-anac → Settings → Environment Variables
    2.2. Edite NEXT_PUBLIC_CHECKOUT_URL pra: $CheckoutUrl
    2.3. Apague o valor antigo (sandbox)
    2.4. Vá em Deployments → último deploy → "Redeploy"

[3] Teste end-to-end (com cartão real ou Pix de baixo valor):

    3.1. Abra https://app-anac.vercel.app no anônimo
    3.2. "Adquirir agora" → paga com Pix de R$ 9,90
    3.3. Acompanhe os logs:
         npx supabase functions logs asaas-webhook --tail
    3.4. Espera ver: event=PAYMENT_CONFIRMED welcome_email=sent
    3.5. Confere e-mail (caixa de entrada)
    3.6. Baixa o instalador do link do e-mail, instala, abre o app,
         entra com o mesmo e-mail.

"@ -ForegroundColor White

Write-Host "URL pública do instalador (Release v$Version):" -ForegroundColor Yellow
Write-Host "https://github.com/giuseppeferretti/app-iter/releases/download/$Version/AppIter_Setup.exe" -ForegroundColor White
