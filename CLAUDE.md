# App Iter

> **Nome do produto:** App Iter (sub-produto da Iter). Em documentos de programação, sempre usar "App Iter". O nome legado "App ANAC" foi descontinuado em 2026-05-13 (mantido apenas no caminho de pasta `c:\dev\app_anac\` para preservar histórico; será migrado depois). No site público o nome ainda é "App ANAC" — alteração para "App Iter" pendente para uma próxima rodada.

Software desktop Windows que automatiza o lançamento de horas de voo (CIV) no SACI da ANAC. Público: pilotos brasileiros. Sub-produto da **Iter** (empresa de automação e IA).

## Output target de landing/site

Landing pages e sites associados a este produto **não vivem neste repositório**. Eles ficam centralizados no monorepo de marketing em:

- **Destino:** `c:\dev\marketing\sites\app-anac\` (slug sugerido)
- **Template fonte:** `c:\dev\marketing\template\`
- **Skill responsável:** `/site` (user-level, em `~/.claude/skills/site/`)

Quando o usuário pedir landing/site/marketing-page deste produto, invoque a skill `/site` — ela já trata template fonte, scaffolding e workflow (DIRECTION.md → cenas → visual-check) corretamente. Use **sempre paths absolutos com `c:\dev\marketing\`** nos tool calls — não confie no cwd da sessão.

## Identidade visual

Este produto é SUB-produto da Iter — visualmente coerente com o site principal (`c:\dev\marketing\sites\iter\`), mas com identidade própria (é "App Iter", não a empresa).

Reaproveitar do site Iter:
- `c:\dev\marketing\sites\iter\components\iter-logo.tsx`
- `c:\dev\marketing\sites\iter\components\nav-pill.tsx`
- `c:\dev\marketing\sites\iter\components\sections\site-footer.tsx`
- Componentes de motion: `lenis-provider`, `reveal`, `split-text-reveal`, `hero-cinematic`, `accent-words`, `gradient-text`
- Paleta, tipografia, espaçamentos do `tailwind.config.ts`
- Estilo de cenas (`Scene1Hero`, `Scene4HowItWorks`, etc.)

## Diretrizes específicas do App Iter

- **Padrão de excelência obrigatório** — site cinematográfico no nível da skill `/site` (Awwwards-tier, motion AI-native, cenas com identidade própria). Não aceitar template polido genérico.
- **Imagens temáticas** — sempre buscar referências visuais de aviação **agrícola, executiva, geral e instrução** (público real do produto). Evitar stock photos genéricos de aviação comercial / linhas aéreas (não é o público). Fotos cinematográficas de cockpit, prancheta com caderneta, planilha em monitor, pista de pouso pequena, aeronaves leves/médias são alinhadas.
- **Tom** — sério, técnico, respeitoso com a profissão. Piloto brasileiro de aviação geral é exigente e detesta marketing exagerado.

## Pasta `landing/` legada

Existe `c:\dev\app_anac\landing\` no repo — provavelmente obsoleta após migração pra `marketing/sites/app-anac/`. Confirmar com usuário antes de remover.
