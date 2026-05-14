# Script que cria o repo no GitHub e publica o instalador como release.
#
# Pré-requisitos (executar UMA vez antes do primeiro release):
#   gh auth login    -> escolher GitHub.com, HTTPS, login via browser
#
# Uso:
#   .\scripts\publish_release.ps1
#   .\scripts\publish_release.ps1 -Version v0.1.1
#
# O que faz:
#   1. Garante que o gh está autenticado.
#   2. Cria o repo `app-iter` na sua conta (privado), se ainda não existir.
#   3. Faz push do commit atual.
#   4. Cria a tag/release e faz upload do AppIter_Setup.exe como asset.
#   5. Imprime a URL pública de download.

param(
    [string]$Version = "v0.1.0",
    [string]$RepoName = "app-iter",
    [switch]$Public,
    [string]$InstallerPath = "Output\AppIter_Setup.exe",
    [string]$TutorialPath = "tutorial_planilha.pdf"
)

# Não usamos $ErrorActionPreference = "Stop" porque comandos nativos (gh, git)
# escrevem em stderr mesmo em casos normais (ex.: "repo not found"), e isso
# vira erro fatal em PowerShell 5.1. Checamos $LASTEXITCODE explicitamente.

# Garante gh no PATH (winget instala em Program Files)
$env:Path = "C:\Program Files\GitHub CLI;" + $env:Path

function Step($msg) { Write-Host "`n>>> $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Fail($msg) { Write-Host "    $msg" -ForegroundColor Red; exit 1 }

# 1. Sanity checks
Step "Verificando pré-requisitos"
& gh auth status *> $null
if ($LASTEXITCODE -ne 0) { Fail "gh não está autenticado. Rode 'gh auth login' primeiro." }
Ok "gh autenticado"

if (-not (Test-Path $InstallerPath)) {
    Fail "Instalador não encontrado em $InstallerPath. Rode pyinstaller + ISCC.exe antes."
}
$size = (Get-Item $InstallerPath).Length / 1MB
Ok ("Instalador: {0:N1} MB ({1})" -f $size, $InstallerPath)

# Tutorial PDF (opcional — se não existe, segue sem)
$IncluirTutorial = Test-Path $TutorialPath
if ($IncluirTutorial) {
    $tsize = (Get-Item $TutorialPath).Length / 1KB
    Ok ("Tutorial PDF: {0:N0} KB ({1})" -f $tsize, $TutorialPath)
} else {
    Write-Host "    Tutorial PDF não encontrado em $TutorialPath — release sem PDF anexo." -ForegroundColor Yellow
}

$user = & gh api user --jq .login
if (-not $user) { Fail "Não consegui pegar seu usuário do GitHub." }
Ok "GitHub user: $user"

$full = "$user/$RepoName"

# 2. Cria o repo (idempotente)
Step "Verificando repo $full"
& gh repo view $full *> $null
if ($LASTEXITCODE -ne 0) {
    $visibility = if ($Public) { "--public" } else { "--private" }
    Step "Criando repo $full ($visibility)"
    & gh repo create $RepoName $visibility --source=. --remote=origin --description "App Iter - desktop automation for ANAC SACI"
    if ($LASTEXITCODE -ne 0) { Fail "Falha ao criar repo." }
    Ok "Repo criado"
} else {
    Ok "Repo já existe"
    # Garante que o remote origin existe
    & git remote get-url origin *> $null
    if ($LASTEXITCODE -ne 0) {
        & git remote add origin "https://github.com/$full.git"
        Ok "Remote origin adicionado"
    }
}

# 3. Push
Step "Fazendo push do branch main"
& git push -u origin main
if ($LASTEXITCODE -ne 0) { Fail "Falha no push." }
Ok "Push concluído"

# 4. Cria/atualiza a release. Faz upload do .exe + PDF tutorial (se existir).
Step "Criando release $Version"

# Monta lista de assets
$assets = @($InstallerPath)
if ($IncluirTutorial) { $assets += $TutorialPath }

& gh release view $Version --repo $full *> $null
if ($LASTEXITCODE -eq 0) {
    Step "Release $Version já existe — fazendo upload dos assets (clobber)"
    & gh release upload $Version @assets --repo $full --clobber
} else {
    $notes = @'
Release do App Iter.

## Instalação
1. Baixe o AppIter_Setup.exe abaixo.
2. Execute. Como é um instalador não-assinado, o Windows SmartScreen mostra um aviso — clique em **Mais informações** > **Executar mesmo assim**.
3. O app abre na tela de licença. Digite o e-mail que usou no pagamento e receba o código por e-mail.

Veja o `tutorial_planilha.pdf` abaixo pra entender como preencher a planilha.
'@
    & gh release create $Version @assets --repo $full --title "App Iter $Version" --notes $notes
}
if ($LASTEXITCODE -ne 0) { Fail "Falha ao criar/atualizar release." }
Ok "Release publicada"

# 5. Imprime a URL final
$asset = (Split-Path $InstallerPath -Leaf)
$url = "https://github.com/$full/releases/download/$Version/$asset"
Write-Host "`n========================================" -ForegroundColor Yellow
Write-Host "  URL pública do instalador:" -ForegroundColor Yellow
Write-Host "  $url" -ForegroundColor White
Write-Host "========================================`n" -ForegroundColor Yellow
