# Perfis da equipe e regras de negócio

Fonte da verdade para a análise. Se o time mudar, atualize aqui **e** o dict `PERFIS`
em `scripts/pipeline_movidesk.py` e `scripts/gerar_analise.py`.

## Agentes, função e jornada

| Agente             | Função (dia típico)                                             | Jornada |
|--------------------|----------------------------------------------------------------|---------|
| Caio Gomes         | Dev de foco profundo: landpages, propostas comerciais, front-ends de telas, automações, logo/branding | 8h30 |
| Thiago Laguna      | QA — testes em HML e preparação de versão                      | 8h30 |
| Luiz Firmo         | Linha de frente do Suporte ao cliente                          | 8h30 |
| Guilherme Raposo   | Desenvolvedor — vazão de correções e entregas de versão        | 8h30 |
| Ricardo Schutz     | Desenvolvedor investigativo (bugs críticos)                    | **6h** |

- Meta de aproveitamento de jornada: **90%**.
- Jornada padrão: 8h30 (510 min). Ricardo Schutz: 6h (360 min).

## Como ler os números (para a prosa do PDF)

A análise deve ser **real**, baseada nos números do dia — nunca texto genérico. Sempre:

- Citar **tickets específicos por número**.
- Sinalizar **retrabalho**: status contendo "Reprovado" (ex.: Reprovado HML).
- Sinalizar **tickets parados**: "16 - Aguardando retorno cliente", "23 - Aguardando Desenvolvimento".
- Comparar **tempo interno (cliente = LECTOR)** vs **clientes externos**.
- Destacar o **maior ralo de tempo** (ticket que somou mais minutos no dia).
- Reproduzir **feedbacks de clientes reais** (autores que não são agentes internos), citando ticket e trecho; marcar os urgentes.

## Observação fixa sobre SLA

O plano atual da API Movidesk **não expõe métricas formais de SLA**. A leitura do funil
usa o **fluxo de status como proxy** — deixe isso explícito no relatório.

## Dia útil de referência

Sempre o **dia útil anterior**: terça a sexta = ontem; segunda = sexta-feira anterior.
O `pipeline_movidesk.py` calcula isso sozinho quando chamado sem argumento.
