# Como preencher sua planilha — App Iter

Olá, piloto.

Aqui vai um guia direto pra preencher sua planilha de horas e o App Iter levar tudo pro SACI em poucos minutos. **Use sempre o modelo oficial** — baixe-o pelo botão "Baixar modelo" na tela do app.

---

## A planilha tem 15 colunas

A ordem segue exatamente o que aparece na tela "Lançar Voo" do SACI da ANAC. Cada linha = um lançamento de voo.

São dois blocos:

### Bloco "Dados do vôo" (colunas 1 a 7)

| Coluna | O que é | Como preencher | Obrigatório? |
|---|---|---|---|
| `DATA` | Data do voo | `DD/MM/AAAA` (ex.: `12/03/2026`) | Sim |
| `POUSOS` | Quantos pousos realizou | Número 1 a 99 | Sim |
| `FUNCAO` | Sua função a bordo | **Clique na célula → seta de dropdown → escolha** | Sim |
| `ANAC_ALUNO` | Código ANAC do aluno (8 dígitos) | Só preencha **se** FUNCAO for `Instrutor Voo` ou `Instrutor de voo em solo` | Condicional |
| `CURSO_COMERCIAL` | Voo dentro de curso de piloto comercial com instrutor a bordo? | Dropdown `Sim` / `Não`. Marque `Sim` **só** se FUNCAO = `Piloto em Comando` E o voo foi dentro do curso | Condicional |
| `OBSERVACOES` | Texto livre | Qualquer anotação (ex.: "Translado", "Treinamento ILS") | Não |
| `MILHAS_NAV` | Milhas náuticas de navegação | Inteiro (ex.: `50`) | Não |

### Bloco "Tempo de vôo" (colunas 8 a 15)

| Coluna | O que é | Como preencher | Obrigatório? |
|---|---|---|---|
| `MATRICULA` | Matrícula da aeronave | Até 5 caracteres (ex.: `PTBIC`) | Sim |
| `ORIGEM` | Aeródromo de origem | Código ICAO 4 letras (ex.: `SBSP`) | Sim |
| `DESTINO` | Aeródromo de destino | Código ICAO 4 letras (ex.: `SBKP`) | Sim |
| `DIURNO` | Horas diurnas | `HH:MM` (ex.: `00:45`) | **Pelo menos uma** entre DIURNO e NOTURNO |
| `NOTURNO` | Horas noturnas | `HH:MM` | **Pelo menos uma** entre DIURNO e NOTURNO |
| `NAVEGACAO` | Horas de navegação | `HH:MM` | Não |
| `INSTRUMENTO` | Horas em Instrumento Real (IFR efetivo) | `HH:MM` | Não |
| `SOB_CAPOTA` | Horas de instrução IFR simulada | `HH:MM` | Não |

---

## As 7 opções do dropdown FUNCAO

São exatamente as mesmas que aparecem no SACI. Escolha sempre pela seta da célula (não digite manualmente, pra evitar erro de grafia):

1. **Instrutor Voo** — habilita preenchimento de `ANAC_ALUNO`
2. **Piloto em Comando** — habilita `CURSO_COMERCIAL`
3. **Piloto em Instrução**
4. **Instrutor de voo em solo** — habilita `ANAC_ALUNO`
5. **Co-Piloto Single Pilot**
6. **Co-Piloto Single Pilot com co-piloto, por questão regulamentar**
7. **Co-Piloto Dual Pilot**

---

## Regras condicionais (que o app valida antes de iniciar)

- Se FUNCAO **for** Instrutor (Voo ou em solo): `ANAC_ALUNO` é **obrigatório** (8 dígitos).
- Se FUNCAO **não for** Instrutor: `ANAC_ALUNO` deve estar **vazio**.
- `CURSO_COMERCIAL = Sim` só funciona se FUNCAO = `Piloto em Comando`. Em qualquer outra função, deixe **vazio** ou `Não`.
- Toda linha precisa ter pelo menos uma de DIURNO ou NOTURNO preenchida (não dá pra ter linha sem nenhum tempo de voo).

Se a planilha tiver inconsistências, o app mostra um painel listando linha por linha o que precisa ajustar — antes de qualquer coisa subir pro SACI.

---

## Exemplo de linha completa

| DATA | POUSOS | FUNCAO | ANAC_ALUNO | CURSO_COMERCIAL | OBSERVACOES | MILHAS_NAV | MATRICULA | ORIGEM | DESTINO | DIURNO | NOTURNO | NAVEGACAO | INSTRUMENTO | SOB_CAPOTA |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 12/03/2026 | 1 | Piloto em Comando |  | Não | Translado | 50 | PTBIC | SBSP | SBKP | 00:45 | 00:30 | 01:50 | 00:30 | 00:30 |

---

## Como usar o App Iter

1. **Abra o App Iter** no menu Iniciar.
2. **Baixar modelo** (link no canto inferior do dropzone) → salve em algum lugar fácil.
3. **Preencha a planilha** no Excel: uma linha por voo.
4. **Volte ao app** e clique no dropzone pra carregar sua planilha preenchida.
5. **Confira o painel**: mostra quantos lançamentos válidos e (se houver) quais linhas têm inconsistência.
6. **Clique em INICIAR SESSÃO**. O app pergunta sobre a sessão SACI:
   - Clique **Abrir SACI** — o app vai abrir seu navegador (Brave, Chrome, Edge, Opera — o que você já usa) já com a tela de login do SACI.
   - **Faça login no SACI** normalmente.
   - O status do app vai mudar pra **verde** ("SACI detectado — pronto para iniciar") automaticamente.
   - Clique **Prosseguir**.
7. O app começa a lançar voo por voo, mostrando o progresso na coluna direita. Você vê cada linha sendo preenchida na tela do SACI ao vivo.
8. Se precisar parar no meio, clique **CANCELAR** — o app termina o que tá fazendo em até 1 segundo e mostra o relatório do parcial.

---

## Dicas

- **Formato das células de tempo**: deixe o Excel mostrar como texto (`HH:MM`) ou como hora — qualquer um funciona.
- **Voo só diurno ou só noturno**: deixa a outra coluna vazia, sem zero. O SACI aceita.
- **Erros comuns** que o app aceita silenciosamente:
  - Excel salvou a data como número (ex.: 12032026) — o app converte.
  - Excel salvou hora como `01:30:00` — o app trunca pros minutos.
  - ICAO digitado em minúsculo — o app converte pra maiúsculo.
- **Mantenha a planilha fechada** quando rodar o app (o Excel bloqueia o arquivo).

---

## Dúvidas

Escreva pra **suporte.iter@gmail.com** — a gente responde direto, sem fila.

Bons voos.
