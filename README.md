# Agente + Skill — Relatórios de Apontamentos Movidesk (equipe Lector)

Pacote para **Claude Code** que gera, de forma determinística, o pacote diário de relatórios de
apontamentos da equipe a partir da API pública do Movidesk. Como todo o trabalho pesado está em dois
scripts Python, **qualquer modelo produz o mesmo resultado** — o modelo apenas orquestra e confere.

Saídas geradas (do **dia útil anterior**, ou de uma data informada):

- `Apontamentos_<Agente>_<data>.png` — relatório individual (tabela de apontamentos + gráficos)
- `Equipe_<data>.png` — dashboard da equipe (meta 90%; jornada 8h30, exceto Ricardo Schutz 6h)
- `dados_<data>.json` / `resumo_<data>.json` — dados completos e resumo agregado
- `Analise_Operacional_<data>.pdf` — análise gerencial em 4 páginas (resumo executivo, onde o tempo foi
  gasto, perfil individual, fluxo de status/voz do cliente)

## Estrutura

```
agents/
  relatorios-movidesk.md          # definição do subagente (sem modelo fixo — roda em qualquer modelo)
skills/
  relatorios-movidesk/
    SKILL.md                      # instruções do fluxo (seguíveis por qualquer modelo)
    scripts/
      pipeline_movidesk.py        # coleta a API + gera PNGs + JSONs
      gerar_analise.py            # gera o PDF de análise a partir dos JSONs
      runner_diario.py            # missão completa p/ cron: pipeline + PDF + verificação + painel
      mission_control.py          # gera o painel mission_control.html (abas Missões + Extrator)
      mission_server.py           # serve o painel (PWA) + API de play das missões e do extrator
      extrator_obsidian.py        # aba Extrator: puxa tickets pela API e salva Markdown por cliente (Obsidian)
      enviar_whatsapp.py          # envia os PNGs ao grupo do WhatsApp (Evolution API) ao fim da missão
    references/
      perfis_equipe.md            # perfis, jornadas, meta e regras de negócio
```

## Instalação

1. Copie as pastas para o diretório de configuração do Claude Code (nível usuário):

   ```
   cp -r agents/relatorios-movidesk.md   ~/.claude/agents/
   cp -r skills/relatorios-movidesk      ~/.claude/skills/
   ```

   (No Windows, o destino é `%USERPROFILE%\.claude\`.)

2. Instale as dependências Python:

   ```
   pip install requests matplotlib pandas openpyxl pymupdf
   ```

3. Configure o token da API — copie `.env.example` para a **raiz da skill instalada** e preencha:

   ```
   cp .env.example ~/.claude/skills/relatorios-movidesk/.env
   ```

   Os scripts leem esse `.env` sozinhos. Alternativamente, exporte a variável (tem precedência):

   ```
   export MOVIDESK_TOKEN=seu-token        # Linux/macOS
   $env:MOVIDESK_TOKEN = "seu-token"      # PowerShell
   ```

   > O token **não** está versionado — é lido de `MOVIDESK_TOKEN` (via `.env` ou ambiente). Por isso o
   > código aqui é **idêntico** ao instalado localmente: sincronizar é um `cp`, sem editar segredo.

## Uso

No Claude Code:

- `/relatorios-movidesk` (invoca a skill), ou peça *"puxa os relatórios de apontamentos"*.
- Para delegar a um subagente: *"usa o agente relatorios-movidesk"*.
- Uma data específica é opcional (`AAAA-MM-DD`); sem data, usa o dia útil anterior.

Ou direto pela linha de comando:

```
python skills/relatorios-movidesk/scripts/pipeline_movidesk.py [AAAA-MM-DD]
python skills/relatorios-movidesk/scripts/gerar_analise.py    [AAAA-MM-DD]
```

## Configuração

| Variável                   | Obrigatória | Padrão                          | Descrição                          |
|----------------------------|-------------|---------------------------------|------------------------------------|
| `MOVIDESK_TOKEN`           | sim         | —                               | Token da API pública do Movidesk   |
| `RELATORIOS_MOVIDESK_DIR`  | não         | `~/Downloads/Relatorios Movidesk` | Pasta de saída dos relatórios     |

Ambas podem vir do `.env` na raiz da skill ou do ambiente (o ambiente vence).

Ao mudar o time, edite `skills/relatorios-movidesk/references/perfis_equipe.md` **e** os dicts
`PERFIS`/`METAS` nos dois scripts.

## Automação — cron diário + Mission Control

`scripts/runner_diario.py` executa a missão completa do dia útil anterior (pipeline → PDF →
verificação), grava o histórico em `mission_state.json` e reconstrói o painel
**`mission_control.html`** na pasta de saída: status por dia (OK/FALHA/PENDENTE), checklist de
passos, métricas, to-do de pendências derivado dos dados e log das execuções.

Para agendar seg–sex às 09:00 no Windows (Agendador de Tarefas), registre uma tarefa apontando
`pythonw.exe` para o `runner_diario.py` — recomendado via XML com `StartWhenAvailable=true`
(executa assim que possível se a máquina estava desligada às 9h):

```
schtasks /Create /F /TN "RelatoriosMovideskDiario" /XML relatorios_movidesk_task.xml
```

Backfill de um dia pendente: `python scripts/runner_diario.py AAAA-MM-DD`.
Reconstruir só o painel: `python scripts/mission_control.py`.

## Aplicação (PWA) — dar play no agente pela interface

`scripts/mission_server.py` serve o painel em **http://localhost:8765** como aplicação instalável
(PWA: manifest + service worker + ícones). No Chrome/Edge, use **"Instalar app"** para virar uma
janela própria que fica sempre aberta. Pela interface:

- **▶ RODAR MISSÃO** dispara a missão do dia útil anterior; cada dia PENDENTE tem um ▶ de backfill;
- o status ("AGENTE OCIOSO" / "EM EXECUÇÃO") atualiza sozinho e a página recarrega ao terminar;
- API: `GET /api/status` e `POST /api/run` (`{"date":"AAAA-MM-DD"}` opcional; 409 se ocupado).

Autostart (sem admin): copie `scripts/mission_server.vbs.example` → `mission_server.vbs` (ajuste os
caminhos), coloque uma cópia na pasta Inicializar (`shell:startup`) e registre a tarefa das 08:50 com
`mission_server_task.xml.example` — o servidor é idempotente (porta ocupada = já rodando, sai com 0).

## Notas

- A API do Movidesk é **ao vivo**: rodar em horários diferentes muda os números.
- O plano atual da API não expõe SLA formal; a leitura do funil usa o fluxo de status como proxy.
