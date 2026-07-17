---
name: relatorios-movidesk
description: Gera os relatórios diários de apontamentos do Movidesk (PNG por agente, dashboard da equipe, JSONs e PDF de análise gerencial) do dia útil anterior. Use quando o usuário pedir para "puxar/gerar os relatórios de apontamentos", "relatório Movidesk", "análise operacional do dia", ou mencionar apontamentos da equipe Lector.
---

# Relatórios diários Movidesk (equipe Lector)

Gera o pacote completo de relatórios de apontamentos do **dia útil anterior** a partir da API
pública do Movidesk. Tudo é determinístico (dois scripts Python fazem a coleta e a renderização),
então **qualquer modelo produz o mesmo resultado**. Não invente números — eles vêm sempre dos scripts/JSONs.

Os scripts ficam ao lado deste arquivo, em `scripts/`. Eles são **autocontidos**: não dependem de
nenhuma outra pasta. Saída padrão: `~/Downloads/Relatorios Movidesk`
(sobrescreva com a env var `RELATORIOS_MOVIDESK_DIR` se precisar).

Não pergunte nada ao usuário; execute de ponta a ponta. Se ele passar uma data (AAAA-MM-DD), use-a
como argumento nos dois scripts; sem data, os scripts calculam o dia útil anterior sozinhos.

**Rode os dois passos em sequência, sem demora entre eles.** A API é ao vivo: o Passo 2 lê os JSONs
do Passo 1, então intercalar outras tarefas faz o PDF descrever um retrato diferente dos PNGs.

## Passo 0 — Dependências (só se faltar)

    pip install requests matplotlib pandas openpyxl pymupdf

(`pymupdf` é só para conferir o PDF no Passo 3.)

## Passo 1 — Coleta + PNGs + JSONs

Rode o pipeline (substitua `<SKILL_DIR>` pelo caminho real desta skill; opcionalmente acrescente a data):

    python "<SKILL_DIR>/scripts/pipeline_movidesk.py" [AAAA-MM-DD]

Isso consulta a API (token lido de `MOVIDESK_TOKEN`) e gera na pasta de saída:

- `Apontamentos_<Agente>_<data>.png` — relatório individual de cada agente (tabela de apontamentos + gráficos)
- `Equipe_<data>.png` — dashboard da equipe (meta 90%; jornada 8h30, exceto Ricardo Schutz 6h)
- `dados_<data>.json` — dados completos (tickets, apontamentos, feedbacks de clientes)
- `resumo_<data>.json` — resumo agregado: `agentes` (só quem apontou), `status`, `resolvidos_no_dia`,
  `agentes_esperados` (roster completo), `ausentes` e `feedbacks_clientes`

Se algum agente não tiver apontamentos, o script apenas avisa (`AVISO: ...`); isso é normal (folga/falta),
**não é erro**. Agentes esperados: Guilherme Raposo, Thiago Laguna, Ricardo Schutz, Luiz Firmo, Caio Gomes.

> **Importante:** quem não apontou nada **não aparece** em `resumo["agentes"]` — só em
> `resumo["ausentes"]`. Nunca deduza a equipe a partir de `agentes`; use `agentes_esperados`, senão o
> ausente some do relatório (foi um bug real). Vale o mesmo para qualquer contagem "X de Y agentes".

## Passo 2 — PDF de análise gerencial

    python "<SKILL_DIR>/scripts/gerar_analise.py" [AAAA-MM-DD]

Gera `Analise_Operacional_<data>.pdf` (A4 retrato, 4 páginas, em português), lendo os JSONs do Passo 1:

1. **Resumo Executivo** — visão geral (horas, tickets, % da meta), pontos positivos, pontos críticos,
   recomendações. Prosa **data-grounded**: cita tickets por número, retrabalho (status "Reprovado"),
   tickets parados ("Aguardando..."), interno (LECTOR) × externo, maior ralo de tempo.
2. **Onde o tempo foi gasto** — minutos e tickets por agente, pizza por categoria, interno × externo, top 10 tickets.
3. **Perfil individual** — por agente: função, serviços, onde gastou mais tempo, aproveitamento da jornada.
4. **Fluxo de status (proxy de SLA) e voz do cliente** — barras de status, leitura do funil, feedbacks reais de clientes.

O script já detecta sozinho os ralos, tickets parados, reprovações, feedbacks urgentes e tendências
(tickets recorrentes vs. dias anteriores). Os perfis/funções e regras estão em `references/perfis_equipe.md`.


## Passo 3 — Verificação e resposta

Não entregue sem olhar a saída — os scripts podem terminar com sucesso e ainda assim gerar um relatório errado.

- Confirme que existem na pasta de saída: um PNG por agente **que trabalhou**, o `Equipe_<data>.png`,
  os dois JSONs e o PDF. Confira a contagem contra `agentes_esperados` menos `ausentes`.
- Abra 1–2 PNGs e a página 1 do PDF. Para rasterizar o PDF:

      python -c "import fitz; d=fitz.open('<pasta>/Analise_Operacional_<data>.pdf'); d[0].get_pixmap(dpi=90).save('p1.png')"

- Termine com um resumo curto em português: **data analisada, total de horas da equipe, % da meta,
  nº de tickets, destaques positivos e críticos do dia, e os caminhos dos arquivos gerados.**
  Se alguém estiver ausente, **diga isso explicitamente** — é informação gerencial, não um detalhe.

## Notas de manutenção e armadilhas

- A API é **ao vivo**: rodar em horários diferentes muda os números (apontamentos vão sendo lançados ao
  longo do dia). Dois relatórios do mesmo dia não batem se gerados com horas de diferença — normal.
- A média da equipe considera **apenas quem apontou**, para bater com o `Equipe_<data>.png`. Ausentes
  não entram na média, mas devem ser reportados à parte.
- Se os scripts derem erro de caminho, verifique `RELATORIOS_MOVIDESK_DIR`.
- Ao mudar o time, edite `references/perfis_equipe.md` **e** os dicts `AGENTES`/`METAS` (pipeline) e
  `PERFIS` (análise) — os três precisam concordar.
- Emojis quebram no matplotlib (a fonte DejaVu não tem glifos como 📊) — use texto simples, `x`/`-`.
- Relatórios individuais curtos (poucos apontamentos) já têm o espaçamento de cabeçalho corrigido;
  se mexer no layout do PNG, teste com um agente de poucas linhas **e** um de muitas.
