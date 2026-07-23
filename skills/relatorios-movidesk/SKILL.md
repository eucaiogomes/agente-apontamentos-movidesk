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

## Automação — cron diário + Mission Control

O fluxo roda sozinho todo dia útil às **09:00** via Agendador de Tarefas do Windows
(tarefa `RelatoriosMovideskDiario`, seg–sex, com "executar assim que possível" se a máquina
estiver desligada no horário). A tarefa chama:

    python scripts/runner_diario.py [AAAA-MM-DD]

O runner executa a missão completa (pipeline → PDF → verificação de arquivos), grava o resultado
em `mission_state.json` e reconstrói o painel **`mission_control.html`** na pasta de saída — um
dashboard estilo mission control com:

- status de cada dia útil (OK / FALHA / PENDENTE) e checklist de passos (API, PNG, PDF, CHK);
- métricas do último dia (horas, % meta, tickets, ausentes) e links para PDF/PNG;
- **to-do de pendências** derivado dos dados do dia (follow-ups em "Aguardando...", ausentes a
  confirmar, reprovados de HML, feedbacks urgentes) — checkboxes persistem no navegador;
- log das últimas execuções do runner.

### Aplicação (PWA) — servidor local sempre de pé

`scripts/mission_server.py` serve o painel em **http://localhost:8765** como aplicação instalável
(PWA: manifest + service worker + ícones — no Chrome/Edge use "Instalar app" para virar janela
própria). Pela interface dá para **dar play no agente**: o botão "▶ RODAR MISSÃO" dispara a missão
do dia útil anterior e cada dia PENDENTE tem um ▶ de backfill; o status ("AGENTE OCIOSO" /
"EM EXECUÇÃO") atualiza sozinho e a página recarrega ao terminar.

API: `GET /api/status` e `POST /api/run` (`{"date":"AAAA-MM-DD"}` opcional; 409 se já houver missão
rodando). O servidor sobe sozinho: `mission_server.vbs` na pasta Inicializar (logon) + tarefa
`RelatoriosMovideskServer` diária às 08:50 (idempotente — porta ocupada = já está rodando, sai com 0).
Logs em `server_log.txt`; saída dos runs disparados pela API em `runner_launch.log`.

Backfill por linha de comando (alternativa ao ▶): `python scripts/runner_diario.py AAAA-MM-DD`.
Reconstruir só o painel: `python scripts/mission_control.py`. O painel continua funcionando aberto
como arquivo local — os controles de play só aparecem quando servido pelo mission_server.

Recriar a tarefa agendada (se trocar de máquina): use os modelos do repositório
(`relatorios_movidesk_task.xml.example` + `scripts/runner_diario.cmd.example`) e registre com
`schtasks /Create /TN RelatoriosMovideskDiario /XML <arquivo>` (XML salvo em UTF-16).
**Armadilhas aprendidas na prática:**
- O XML precisa de `<Priority>5</Priority>` — sem isso a tarefa roda em prioridade *idle* e o
  Windows 11 praticamente congela o processo (fica minutos sem ganhar CPU).
- A ação deve chamar o **wrapper `runner_diario.cmd`** (com CRLF!), não o Python direto — o wrapper
  registra cada lançamento em `runner_launch.log`, o que torna falhas do agendador diagnosticáveis.
- O `pythonw.exe` do gerenciador de Python do Windows não funciona sob o Agendador; use `python.exe`.

## Aba "Extrator Obsidian" — tickets → Markdown

O painel Mission Control tem duas abas: **Missões** (relatórios diários, acima) e **Extrator
Obsidian**. O extrator (`scripts/extrator_obsidian.py`) puxa tickets pela **mesma API** (token
`MOVIDESK_TOKEN`) e salva cada um como Markdown num Vault do Obsidian, uma pasta por cliente:

    <destino>/<Cliente>/<ID> - <Assunto>.md

Cada arquivo tem frontmatter (ticket, cliente, status, categoria, urgência, data, url) e o histórico
de ações do ticket com o HTML convertido para Markdown (conversor stdlib, sem dependências extras).
Destino padrão: `~/Downloads/CAIOSs/caios-data/movidesk-obsidian` (sobrescreva com a env var
`EXTRATOR_OBSIDIAN_DIR` ou o campo "Destino" na aba). Subdomínio do link Movidesk: `MOVIDESK_SUBDOMAIN`
(padrão `lectortec`).

Dois modos (na aba ou por linha de comando):

    python scripts/extrator_obsidian.py --range 9000 9200      # varre intervalo de IDs
    python scripts/extrator_obsidian.py --ids 11284,11090      # lista específica
    # opcional: --dest "C:\caminho\Vault"

No modo `--range` ele para sozinho após **30 IDs seguidos sem ticket** (`LIMITE_MISS`). Progresso vai
para `extrator_state.json` (lido pelo painel) e o log para `extrator_log.txt`, ambos na pasta de saída.

API do servidor: `GET /api/extrator/status` (progresso ao vivo) e `POST /api/extrator/run`
(`{"modo":"range","inicio":N,"fim":N}` ou `{"modo":"lista","ids":"1,2,3"}`, `dest` opcional; 409 se já
houver extração rodando). Como no play das missões, os controles da aba só funcionam com o painel
servido pelo `mission_server.py`.

## Envio automático ao WhatsApp (Evolution API)

Ao final de **toda missão** (cron 09:00 e botão RODAR MISSÃO), o `runner_diario.py` chama
`scripts/enviar_whatsapp.py`, que manda os relatórios ao grupo do WhatsApp *Registro de apontamentos*:

- **um PNG por agente** que trabalhou, marcando a pessoa, com legenda `@<num> <pct>% Relatorio Geral <dd/mm>`
  (o WhatsApp renderiza `@<num>` como o nome salvo do contato). O `<pct>` é `min ÷ jornada × 100`;
- ao final, o **dashboard da equipe** (`Equipe_<data>.png`) marcando todos, com legenda
  `@... Relatorio Geral da Equipe <dd/mm> — meta <pct>%`.

A Evolution API roda num **VPS via Docker** e é acessada por **túnel SSH**; antes de enviar, o script
garante o container de pé (`docker start`, idempotente). O envio **nunca derruba a missão**: se o
WhatsApp/Evolution falhar, só registra o aviso em `whatsapp_log.txt` e a missão segue OK.

Config no `.env` da skill (a `EVOLUTION_KEY` é segredo — fica fora do repo, como o `MOVIDESK_TOKEN`):

    EVOLUTION_SSH=root@2.25.71.207
    EVOLUTION_BASE=http://127.0.0.1:36721
    EVOLUTION_KEY=<apikey>
    EVOLUTION_INSTANCE=Whatsapp lector
    EVOLUTION_GROUP=120363041106999402@g.us
    EVOLUTION_CONTAINER=evolution-api-gi8t-api-1
    ENVIAR_WHATSAPP=1        # 0/vazio desliga o envio

Mapa nome→número em `whatsapp_agentes.json` na raiz da skill (dado pessoal, **fora do repo**). Use o
**JID legado** (o WhatsApp dropa o 9 de celulares antigos); confira contra os participantes reais do
grupo (`GET /group/participants/<instance>?groupJid=<jid>`). Rodar manualmente / testar:

    python scripts/enviar_whatsapp.py [AAAA-MM-DD] --dry-run          # mostra o payload, não envia
    python scripts/enviar_whatsapp.py [AAAA-MM-DD] --so Guilherme     # envia só um agente (teste)
    python scripts/enviar_whatsapp.py [AAAA-MM-DD] --sem-geral        # pula o dashboard da equipe

Rota usada: `POST /message/sendMedia/<instance>` com `media` em base64 puro, `caption` e
`mentioned:[<jid>@s.whatsapp.net]`. A instância `Whatsapp lector` precisa estar `open`
(`GET /instance/fetchInstances`).

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
