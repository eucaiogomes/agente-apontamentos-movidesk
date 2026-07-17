# -*- coding: utf-8 -*-
"""Pipeline diário Movidesk: coleta apontamentos do dia útil anterior,
gera PNG por agente, dashboard da equipe e dados para a análise em PDF.
Uso: python pipeline_movidesk.py [AAAA-MM-DD]  (sem argumento = dia útil anterior)

(Reconstruído em 2026-07-16 a partir do histórico — o original foi apagado.)
"""
import sys, json, collections, textwrap, unicodedata, re, os
from datetime import date, timedelta
import requests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

def carrega_env():
    """Le o .env da raiz da skill (CHAVE=valor) sem sobrescrever o ambiente real.

    Mantem o segredo fora do codigo: este arquivo e identico no repositorio
    publico e na instalacao local — so o .env (nao versionado) difere.
    """
    caminho = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    if not os.path.exists(caminho):
        return
    for linha in open(caminho, encoding='utf-8'):
        linha = linha.strip()
        if not linha or linha.startswith('#') or '=' not in linha:
            continue
        chave, valor = linha.split('=', 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))

carrega_env()

TOKEN = os.environ.get('MOVIDESK_TOKEN')
if not TOKEN:
    sys.exit('MOVIDESK_TOKEN nao definido. Crie um .env na raiz da skill (veja .env.example) '
             'ou exporte a variavel de ambiente.')
SAIDA = os.environ.get('RELATORIOS_MOVIDESK_DIR',
                       os.path.join(os.path.expanduser('~'), 'Downloads', 'Relatorios Movidesk'))
META_PCT = 90
# meta de jornada por agente (minutos); padrão 8h30
METAS = {'Ricardo Schutz': 6*60}
META_PADRAO = 8*60 + 30
AGENTES = ['Guilherme Raposo', 'Thiago Laguna', 'Ricardo Schutz', 'Luiz Firmo', 'Caio Gomes']

AZUL = '#1f3b73'; VERDE = '#10b981'; VERM = '#ef4444'; CINZA = '#5a6577'
FUNDO = '#f4f6fa'

def dia_util_anterior(ref=None):
    d = (ref or date.today()) - timedelta(days=1)
    while d.weekday() >= 5:  # sáb/dom
        d -= timedelta(days=1)
    return d

DATA = sys.argv[1] if len(sys.argv) > 1 else dia_util_anterior().isoformat()
DATA_BR = '/'.join(reversed(DATA.split('-')))
os.makedirs(SAIDA, exist_ok=True)

def norm(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode()
    return ' '.join(s.lower().split())

def fmt(m): return f"{int(m//60):02d}:{int(m%60):02d}"
def fmt_h(m): return f"{int(m//60)}:{int(m%60):02d}"

AGENTES_NORM = {norm(a): a for a in AGENTES}

def hhmm_para_min(s):
    """'01:30:00' ou '01:30' -> minutos"""
    if not s: return 0
    p = str(s).split(':')
    try:
        return int(p[0]) * 60 + int(p[1])
    except (ValueError, IndexError):
        return 0

# ---------------- 1. Coleta ----------------
URL = 'https://api.movidesk.com/public/v1/tickets'
dia_seguinte = (date.fromisoformat(DATA) + timedelta(days=1)).isoformat()
filtro = (f"actions/any(a: a/timeAppointments/any(t: "
          f"t/date ge {DATA}T00:00:00.00z and t/date lt {dia_seguinte}T00:00:00.00z))")
select = ('id,subject,status,baseStatus,category,urgency,serviceFirstLevel,'
          'serviceSecondLevel,createdDate,resolvedIn,ownerTeam')
expand = ('clients($select=businessName,profileType),'
          'actions($select=id,createdDate,description,createdBy;'
          '$expand=createdBy($select=businessName,profileType),'
          'timeAppointments($select=activity,date,periodStart,periodEnd,workTime,createdBy;'
          '$expand=createdBy($select=businessName)))')

brutos, skip = [], 0
while True:
    r = requests.get(URL, params={
        'token': TOKEN, '$filter': filtro, '$select': select, '$expand': expand,
        '$top': 100, '$skip': skip}, timeout=120)
    r.raise_for_status()
    lote = r.json()
    brutos.extend(lote)
    if len(lote) < 100:
        break
    skip += 100
print(f'API: {len(brutos)} tickets com apontamentos em {DATA}')

# ---------------- 2. Normalização ----------------
tickets, feedbacks = [], []
for t in brutos:
    cliente = ''
    for c in (t.get('clients') or []):
        cliente = c.get('businessName') or ''
        if cliente: break
    apts = []
    for a in (t.get('actions') or []):
        for ap in (a.get('timeAppointments') or []):
            if not (ap.get('date') or '').startswith(DATA):
                continue
            quem = ((ap.get('createdBy') or {}).get('businessName')
                    or (a.get('createdBy') or {}).get('businessName') or '')
            nome = AGENTES_NORM.get(norm(quem))
            if not nome:
                continue
            mins = hhmm_para_min(ap.get('workTime'))
            if mins <= 0:
                continue
            apts.append({
                'agente': nome,
                'inicio': (ap.get('periodStart') or '')[:5],
                'fim': (ap.get('periodEnd') or '')[:5],
                'min': mins,
                'atividade': ap.get('activity') or '',
            })
        # feedbacks de clientes no dia (autor da ação não é agente interno)
        cb = a.get('createdBy') or {}
        autor = cb.get('businessName') or ''
        if ((a.get('createdDate') or '').startswith(DATA)
                and autor and norm(autor) not in AGENTES_NORM
                and cb.get('profileType') == 2
                and (a.get('description') or '').strip()):
            trecho = ' '.join((a.get('description') or '').split())[:300]
            feedbacks.append({'ticket': t.get('id'), 'cliente': autor,
                              'trecho': trecho, 'data': a.get('createdDate')})
    if not apts:
        continue
    apts.sort(key=lambda x: x['inicio'])
    tickets.append({
        'id': t.get('id'),
        'assunto': t.get('subject') or '',
        'status': t.get('status') or '',
        'baseStatus': t.get('baseStatus') or '',
        'categoria': t.get('category') or '',
        'urgencia': t.get('urgency') or '',
        'servico': t.get('serviceFirstLevel') or '',
        'criado': t.get('createdDate') or '',
        'resolvido': t.get('resolvedIn') or '',
        'equipe': t.get('ownerTeam') or '',
        'cliente': cliente,
        'apontamentos': apts,
    })

with open(os.path.join(SAIDA, f'dados_{DATA}.json'), 'w', encoding='utf-8') as f:
    json.dump({'data': DATA, 'tickets': tickets, 'feedbacks': feedbacks},
              f, ensure_ascii=False, indent=1)

# ---------------- 3. Resumo agregado ----------------
ag = {}
status_cnt = collections.Counter()
resolvidos_no_dia = []
for t in tickets:
    status_cnt[t['status']] += 1
    if (t['resolvido'] or '').startswith(DATA):
        resolvidos_no_dia.append(t['id'])
    for ap in t['apontamentos']:
        a = ag.setdefault(ap['agente'], {
            'min': 0, 'tickets': set(),
            'categorias': collections.Counter(),
            'servicos': collections.Counter(),
            'clientes': collections.Counter(),
            '_por_ticket': collections.Counter(), '_meta_tk': {}})
        a['min'] += ap['min']
        a['tickets'].add(t['id'])
        if t['categoria']: a['categorias'][t['categoria']] += ap['min']
        if t['servico']:   a['servicos'][t['servico']] += ap['min']
        if t['cliente']:   a['clientes'][t['cliente']] += ap['min']
        a['_por_ticket'][t['id']] += ap['min']
        a['_meta_tk'][t['id']] = (t['assunto'][:60], t['status'])

resumo_ag = {}
for nome in AGENTES:
    if nome not in ag:
        continue
    a = ag[nome]
    top = [[tid, a['_meta_tk'][tid][0], a['_meta_tk'][tid][1], m]
           for tid, m in a['_por_ticket'].most_common(5)]
    resumo_ag[nome] = {
        'min': a['min'], 'tickets': len(a['tickets']),
        'categorias': dict(a['categorias'].most_common()),
        'servicos': dict(a['servicos'].most_common()),
        'clientes': dict(a['clientes'].most_common()),
        'top_tickets': top,
    }

# Quem nao aponta nada nao aparece em resumo_ag; grave o roster e os ausentes no
# JSON para que gerar_analise.py consiga enxerga-los (senao somem do relatorio).
ausentes = [a for a in AGENTES if a not in resumo_ag]

resumo = {'data': DATA, 'status': dict(status_cnt),
          'resolvidos_no_dia': resolvidos_no_dia, 'agentes': resumo_ag,
          'agentes_esperados': AGENTES, 'ausentes': ausentes,
          'feedbacks_clientes': feedbacks}
with open(os.path.join(SAIDA, f'resumo_{DATA}.json'), 'w', encoding='utf-8') as f:
    json.dump(resumo, f, ensure_ascii=False, indent=1)

for a in ausentes:
    print(f'AVISO: {a} sem apontamentos em {DATA} (folga/falta? nao e erro).')

# ---------------- 4. PNG por agente ----------------
def _card(fig, x, w, y, h, valor, rotulo, cor=AZUL):
    box = FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.004,rounding_size=0.006',
                         transform=fig.transFigure, facecolor='white',
                         edgecolor='#d8dfeb', lw=1)
    fig.patches.append(box)
    fig.text(x + w/2, y + h*0.62, valor, ha='center', fontsize=15,
             fontweight='bold', color=cor)
    fig.text(x + w/2, y + h*0.22, rotulo, ha='center', fontsize=8.5, color=CINZA)

def png_agente(nome):
    linhas = []  # (ticket, cliente, assunto, status, inicio, fim, min)
    for t in tickets:
        for ap in t['apontamentos']:
            if ap['agente'] == nome:
                linhas.append((t['id'], t['cliente'], t['assunto'], t['status'],
                               ap['inicio'], ap['fim'], ap['min']))
    if not linhas:
        return None
    linhas.sort(key=lambda x: x[4])
    total = sum(l[6] for l in linhas)
    n_tk = len({l[0] for l in linhas})
    periodo = f"{linhas[0][4]} - {max(l[5] for l in linhas)}"

    n = len(linhas)
    alt_tab = 0.30 + n * 0.032
    fig_h = max(10, 4.2 + alt_tab * 10)
    fig = plt.figure(figsize=(13.5, fig_h), dpi=110)
    fig.patch.set_facecolor(FUNDO)

    fig.text(0.02, 1 - 0.45/fig_h, 'Relatório de Apontamentos — Movidesk', fontsize=20,
             fontweight='bold', color=AZUL, va='top')
    fig.text(0.02, 1 - 0.95/fig_h, f'Agente: {nome}    |    Data: {DATA_BR}',
             fontsize=11, color=CINZA, va='top')

    y_cards = 1 - 1.85/fig_h
    h_cards = 0.55/fig_h
    for i, (v, r) in enumerate([(fmt(total), 'Total trabalhado'),
                                (str(n), 'Apontamentos'),
                                (str(n_tk), 'Tickets distintos'),
                                (periodo, 'Período')]):
        _card(fig, 0.02 + i*0.245, 0.215, y_cards, h_cards, v, r)

    # tabela
    cols =   ['Ticket', 'Cliente', 'Assunto', 'Status', 'Início', 'Fim', 'Horas']
    xs =     [0.02,      0.085,     0.185,     0.545,    0.735,    0.80,  0.865]
    ws =     [0.06,      0.095,     0.355,     0.185,    0.06,     0.06,  0.075]
    y0 = y_cards - 0.35/fig_h
    row_h = 0.30/fig_h
    # cabeçalho
    for x, w, c in zip(xs, ws, cols):
        fig.patches.append(plt.Rectangle((x, y0 - row_h), w, row_h,
                           transform=fig.transFigure, facecolor=AZUL))
        fig.text(x + w/2, y0 - row_h/2, c, ha='center', va='center',
                 fontsize=9.5, fontweight='bold', color='white')
    y = y0 - row_h
    for i, (tid, cli, ass, st_, ini, fim, m) in enumerate(linhas):
        y -= row_h
        cor_l = 'white' if i % 2 == 0 else '#eef1f7'
        fig.patches.append(plt.Rectangle((xs[0], y), sum(ws), row_h,
                           transform=fig.transFigure, facecolor=cor_l))
        vals = [str(tid), (cli or '')[:14] + ('…' if len(cli or '') > 14 else ''),
                (ass or '')[:52] + ('…' if len(ass or '') > 52 else ''),
                st_, ini, fim, fmt(m)]
        for x, w, v, ha in zip(xs, ws, vals, ['left','left','left','left','center','center','center']):
            px = x + 0.006 if ha == 'left' else x + w/2
            fig.text(px, y + row_h/2, v, ha=ha, va='center', fontsize=8.5, color='#1e293b')

    # gráficos inferiores
    por_tk = collections.Counter(); por_cli = collections.Counter()
    for tid, cli, *_r, m in [(l[0], l[1], l[6]) for l in linhas]:
        por_tk[tid] += m
    for l in linhas:
        por_cli[l[1] or '-'] += l[6]
    top_tk = por_tk.most_common(10)
    gy = 0.05/fig_h + 0.02
    gh = min(0.24, 2.6/fig_h)
    ax1 = fig.add_axes([0.06, gy, 0.52, gh])
    ax1.barh([str(t) for t, _ in top_tk][::-1], [v for _, v in top_tk][::-1], color=AZUL)
    ax1.set_title('Tempo por ticket (minutos)', fontsize=11, fontweight='bold', color=AZUL)
    ax1.tick_params(labelsize=8)
    for yv, v in enumerate([v for _, v in top_tk][::-1]):
        ax1.text(v + 1, yv, fmt(v), va='center', fontsize=7.5, color=CINZA)
    for s in ['top', 'right']: ax1.spines[s].set_visible(False)
    ax1.set_facecolor('white')
    ax2 = fig.add_axes([0.66, gy, 0.30, gh])
    cores_pie = ['#1f3b73', '#3a5fa3', '#5b7fc4', '#7d9ad5', '#9db4dd', '#c9d6ec']
    ax2.pie(list(por_cli.values()), labels=list(por_cli.keys()), autopct='%1.0f%%',
            textprops={'fontsize': 7.5}, colors=cores_pie[:len(por_cli)])
    ax2.set_title('Tempo por cliente', fontsize=11, fontweight='bold', color=AZUL)

    caminho = os.path.join(SAIDA, f"Apontamentos_{nome.replace(' ', '_')}_{DATA}.png")
    fig.savefig(caminho, facecolor=FUNDO, bbox_inches=None)
    plt.close(fig)
    return caminho

for nome in AGENTES:
    p = png_agente(nome)
    if p: print('OK PNG:', p)

# ---------------- 5. Dashboard da equipe ----------------
presentes = [a for a in AGENTES if a in resumo_ag]
if presentes:
    pcts = {a: resumo_ag[a]['min'] / METAS.get(a, META_PADRAO) * 100 for a in presentes}
    media = sum(pcts.values()) / len(pcts)
    tempo_medio = sum(resumo_ag[a]['min'] for a in presentes) / len(presentes)

    fig = plt.figure(figsize=(11, 13), dpi=110)
    fig.patch.set_facecolor(FUNDO)
    ok = media >= META_PCT
    cor_meta = VERDE if ok else VERM

    _card(fig, 0.04, 0.42, 0.895, 0.075, fmt_h(tempo_medio), 'Tempo Médio', cor=VERDE)
    _card(fig, 0.54, 0.42, 0.895, 0.075,
          f"{media:.1f}%  {'· Meta atingida!' if ok else '· Abaixo da meta'}",
          f'Média da Equipe (meta {META_PCT}%)', cor=cor_meta)

    ax = fig.add_axes([0.10, 0.42, 0.84, 0.40])
    nomes_c = [a.split()[-1] if a.split()[-1] not in ('Firmo',) else a.split()[0] for a in presentes]
    vals = [min(pcts[a], 110) for a in presentes]
    cores = [VERDE if pcts[a] >= META_PCT else VERM for a in presentes]
    bars = ax.bar(nomes_c, vals, color=cores, width=0.62)
    for b, a in zip(bars, presentes):
        ax.text(b.get_x() + b.get_width()/2, b.get_height() + 2, fmt(resumo_ag[a]['min']),
                ha='center', fontsize=10, fontweight='bold', color='#1e293b')
        ax.text(b.get_x() + b.get_width()/2, b.get_height() - 8, f'{pcts[a]:.1f}%',
                ha='center', fontsize=10, fontweight='bold', color='white')
    ax.axhline(META_PCT, color=CINZA, lw=1, ls='--', alpha=0.5)
    ax.set_title('Porcentagem Trabalhada por Funcionário', fontsize=14,
                 fontweight='bold', color='#1e293b', loc='left', pad=14)
    ax.set_ylabel('Porcentagem (%)'); ax.set_ylim(0, 115)
    for s in ['top', 'right']: ax.spines[s].set_visible(False)
    ax.set_facecolor('white')
    ax.legend(handles=[plt.Rectangle((0,0),1,1,color=VERDE),
                       plt.Rectangle((0,0),1,1,color=VERM)],
              labels=[f'Meta Atingida (>= {META_PCT}%)', f'Meta Não Atingida (< {META_PCT}%)'],
              loc='lower center', bbox_to_anchor=(0.5, -0.18), ncol=2, frameon=False, fontsize=10)

    fig.text(0.06, 0.30, 'Detalhes por Funcionário', fontsize=14, fontweight='bold', color='#1e293b')
    y = 0.245
    for i, a in enumerate(presentes):
        x = 0.05 if i % 2 == 0 else 0.53
        meta_h = fmt_h(METAS.get(a, META_PADRAO))
        _card(fig, x, 0.42, y, 0.05,
              f"{a.split()[-1] if a != 'Luiz Firmo' else 'Luiz'}  —  {pcts[a]:.1f}%",
              f'Meta: {meta_h}   Apontado: {fmt(resumo_ag[a]["min"])}',
              cor=VERDE if pcts[a] >= META_PCT else VERM)
        if i % 2 == 1: y -= 0.065
    if ausentes:
        fig.text(0.06, 0.03, 'Sem apontamentos: ' + ', '.join(ausentes), fontsize=10, color=CINZA)

    caminho = os.path.join(SAIDA, f'Equipe_{DATA}.png')
    fig.savefig(caminho, facecolor=FUNDO)
    plt.close(fig)
    print('OK PNG:', caminho)

total_eq = sum(a['min'] for a in resumo_ag.values())
print(f'Resumo {DATA}: {fmt(total_eq)} totais | {len(tickets)} tickets | '
      f'{len(presentes)}/{len(AGENTES)} agentes | ausentes: {ausentes or "nenhum"}')
