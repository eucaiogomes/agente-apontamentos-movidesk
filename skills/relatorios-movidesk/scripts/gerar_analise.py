# -*- coding: utf-8 -*-
"""Gera o PDF de Analise Operacional (4 paginas) a partir dos JSONs do pipeline.

Uso:
    python gerar_analise.py [AAAA-MM-DD]
Sem argumento, usa o resumo_*.json mais recente da pasta de saida.

Diferente da versao chumbada num dia, este script e GENERICO e data-driven:
- todos os numeros vem do resumo/dados do dia (nunca inventados);
- detecta dinamicamente o maior ralo de tempo, tickets parados, reprovacoes de
  HML, feedbacks urgentes (por palavra-chave) e interno x externo;
- compara com os dias anteriores (historico de resumo_*.json) para sinalizar
  tickets recorrentes entre os mais custosos -> substrato do "aprendizado".
"""
import sys, os, json, glob, collections, textwrap, re
from datetime import date
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

BASE = os.environ.get('RELATORIOS_MOVIDESK_DIR',
                      os.path.join(os.path.expanduser('~'), 'Downloads', 'Relatorios Movidesk'))
AZUL='#1f3b73'; VERDE='#059669'; VERM='#dc2626'; LAR='#d97706'; CINZA='#5a6577'; ESCURO='#1e293b'

# Perfil/funcao de cada agente e jornada (min).
PERFIS = {
    'Caio Gomes':       ('Dev de foco profundo (logo, front mobile, automacoes, landpages)', 510),
    'Thiago Laguna':    ('QA / Testes (HML)', 510),
    'Luiz Firmo':       ('Linha de frente do Suporte', 510),
    'Guilherme Raposo': ('Desenvolvedor (vazao de correcoes)', 510),
    'Ricardo Schutz':   ('Desenvolvedor investigativo (jornada 6h)', 360),
}
JORNADA_PADRAO = 510
META_PCT = 90
URGENTE_KW = ['urgent', 'impact', 'nao consigo', 'nao esta', 'nao estao', 'reclam',
              'erro', 'parou', 'travou', 'prejud', 'venda', 'urgenc', 'imediat']

def fmt(m): return f"{int(m//60):02d}:{int(m%60):02d}"
def norm(s):
    import unicodedata
    return unicodedata.normalize('NFKD', (s or '')).encode('ascii','ignore').decode().lower()

# ---------------- carga ----------------
DATA = sys.argv[1] if len(sys.argv) > 1 else None
if DATA is None:
    cands = sorted(glob.glob(os.path.join(BASE, 'resumo_*.json')))
    if not cands:
        sys.exit('Nenhum resumo_*.json encontrado em ' + BASE)
    DATA = os.path.basename(cands[-1])[7:-5]
dados = json.load(open(os.path.join(BASE, f'dados_{DATA}.json'), encoding='utf-8'))
resumo = json.load(open(os.path.join(BASE, f'resumo_{DATA}.json'), encoding='utf-8'))
ts = dados['tickets']
ag = resumo['agentes']
st = resumo['status']
DATA_BR = '/'.join(reversed(DATA.split('-')))

def jornada(n): return PERFIS.get(n, ('', JORNADA_PADRAO))[1]
def funcao(n):  return PERFIS.get(n, ('Agente', JORNADA_PADRAO))[0]

TOTAL_MIN = sum(a['min'] for a in ag.values())
N_TK = len(ts)
pct = {n: ag[n]['min']/jornada(n)*100 for n in ag}
pct_equipe = sum(pct.values())/len(pct) if pct else 0
ausentes = [n for n in ag if ag[n]['min'] < 30]
n_resolv = st.get('20 - Resolvido', 0)
n_ag_cli = st.get('16 - Aguardando retorno cliente', 0)
n_ag_dev = st.get('23 - Aguardando Desenvolvimento', 0)
n_reprov = sum(v for k, v in st.items() if 'reprov' in norm(k))

# maior ralo de tempo (ticket somando todos os agentes)
tk_total = collections.Counter()
tk_assunto = {}
for t in ts:
    m = sum(a['min'] for a in t['apontamentos'])
    tk_total[t['id']] += m
    tk_assunto[t['id']] = (t['assunto'] or '')
ralo_id, ralo_min = tk_total.most_common(1)[0]
ralo_quem = []
for n in ag:
    for tid, _, _, mm in ag[n]['top_tickets']:
        if tid == ralo_id:
            ralo_quem.append(f"{n.split()[0]} {fmt(mm)}")

# interno x externo
interno = sum(sum(a['min'] for a in t['apontamentos']) for t in ts if t['cliente'] == 'LECTOR')
externo = TOTAL_MIN - interno

# feedbacks: so clientes reais + sinaliza urgentes
fbs = dados.get('feedbacks', resumo.get('feedbacks_clientes', []))
fb_dia = [f for f in fbs if f.get('data', '').startswith(DATA)]
def urgente(f):
    tx = norm(f.get('trecho', ''))
    return any(k in tx for k in URGENTE_KW)
fb_urg = [f for f in fb_dia if urgente(f)]

# ---------------- historico / tendencias ----------------
hist = []
for p in sorted(glob.glob(os.path.join(BASE, 'resumo_*.json'))):
    dd = os.path.basename(p)[7:-5]
    if dd >= DATA: continue
    try: hist.append((dd, json.load(open(p, encoding='utf-8'))))
    except Exception: pass
hist = hist[-5:]  # ate 5 dias anteriores
# tickets recorrentes entre os mais custosos
recorrencia = collections.Counter()
for dd, rj in hist + [(DATA, resumo)]:
    vistos = set()
    for n, a in rj.get('agentes', {}).items():
        for tid, *_ in a.get('top_tickets', []):
            vistos.add(tid)
    for tid in vistos: recorrencia[tid] += 1
recorrentes = [(tid, c) for tid, c in recorrencia.most_common() if c >= 2 and tid in tk_total][:4]

# ================= PDF =================
def page(pdf, title):
    fig = plt.figure(figsize=(8.27, 11.69), dpi=150)
    fig.patch.set_facecolor('white')
    fig.text(0.07, 0.965, title, fontsize=16, fontweight='bold', color=AZUL)
    fig.text(0.07, 0.945, f'Analise Operacional — {DATA_BR}  |  Fonte: API Movidesk', fontsize=8.5, color=CINZA)
    fig.lines.append(plt.Line2D([0.07, 0.93], [0.935, 0.935], transform=fig.transFigure, color='#dde3ec', lw=1))
    return fig

def block(fig, y, titulo, linhas, cor=AZUL, lh=0.0150, fs=8.8):
    fig.text(0.07, y, titulo, fontsize=11.5, fontweight='bold', color=cor)
    y -= 0.021
    for l in linhas:
        for w in textwrap.wrap(l, 112):
            fig.text(0.09, y, w, fontsize=fs, color=ESCURO)
            y -= lh
        y -= 0.003
    return y - 0.016

pdf = PdfPages(os.path.join(BASE, f'Analise_Operacional_{DATA}.pdf'))

# ---- P1 Resumo executivo ----
fig = page(pdf, 'Resumo Executivo do Dia')
y = 0.915
visao = [
 f'• A equipe apontou {fmt(TOTAL_MIN)} no total em {N_TK} tickets distintos tocados no dia ({DATA_BR}).',
 f'• Aproveitamento de jornada: {pct_equipe:.1f}% (meta {META_PCT}%).',
 f'• {n_resolv} tickets em status "Resolvido"; maior ralo de tempo: ticket {ralo_id} "{tk_assunto[ralo_id][:46]}" ({fmt(ralo_min)}).']
if ausentes:
    visao.append('• Sem apontamento relevante: ' + ', '.join(ausentes) + ' (provavel folga/ausencia) — puxa a media para baixo.')
y = block(fig, y, 'Visao geral', visao)

pos = [f'• {len(ag)-len(ausentes)} de {len(ag)} agentes acima da meta: ' +
       ', '.join(f"{n.split()[0]} {pct[n]:.0f}%" for n in sorted(ag, key=lambda k:-pct[k]) if ag[n]['min']>=30) + '.',
       f'• Alta vazao de resolucao: {n_resolv} tickets em "20 - Resolvido".']
pos.append('• ZERO reprovacoes de HML no dia — sem retrabalho de QA registrado.' if n_reprov == 0
           else f'• Atencao: {n_reprov} ticket(s) em status de reprovacao de HML (retrabalho).')
y = block(fig, y, 'Pontos positivos', pos, cor=VERDE)

crit = []
if fb_urg:
    f0 = fb_urg[0]
    crit.append(f'• URGENCIA EXTERNA: {f0.get("cliente","cliente")} (ticket {f0.get("ticket")}) relata: "{f0.get("trecho","")[:120].strip()}..."')
crit.append(f'• Concentracao de tempo: ticket {ralo_id} consumiu {fmt(ralo_min)}' +
            (f' ({"; ".join(ralo_quem)})' if ralo_quem else '') + ' — maior ralo do dia.')
crit.append(f'• {n_ag_cli} tickets em "Aguardando retorno cliente" e {n_ag_dev} em "Aguardando Desenvolvimento" — volume parado, risco de SLA sem follow-up.')
pcent_int = interno/TOTAL_MIN*100 if TOTAL_MIN else 0
crit.append(f'• {pcent_int:.0f}% do tempo foi em demanda interna (LECTOR); clientes externos ficaram com {100-pcent_int:.0f}%.')
y = block(fig, y, 'Pontos criticos', crit, cor=VERM)

rec = ['1. Priorizar os tickets externos com urgencia declarada e os que estao "Aguardando retorno cliente".',
       f'2. Dar visibilidade ao ticket guarda-chuva {ralo_id}: subdividir em itens menores para medir o avanco.',
       '3. Confirmar disponibilidade de quem nao apontou e redistribuir as frentes sem dono.' if ausentes
       else '3. Manter o ritmo de fechamento; revisar diariamente os tickets parados aguardando terceiros.']
if recorrentes:
    rec.append('4. Acompanhar de perto os tickets recorrentes entre os mais custosos (ver pagina 4): ' +
               ', '.join(str(t) for t, _ in recorrentes) + '.')
block(fig, y, 'Recomendacoes para o proximo dia util', rec, cor=LAR)
pdf.savefig(fig); plt.close(fig)

# ---- P2 Onde o tempo foi gasto ----
fig = page(pdf, 'Onde o tempo foi gasto')
nomes = sorted(ag, key=lambda n: n.split()[0])
mins = [ag[n]['min'] for n in nomes]; ntk = [ag[n]['tickets'] for n in nomes]
ax1 = fig.add_axes([0.10, 0.70, 0.36, 0.19]); ax1.bar([n.split()[0] for n in nomes], mins, color=AZUL)
ax1.set_title('Minutos apontados por agente', fontsize=10, color=AZUL, fontweight='bold'); ax1.tick_params(labelsize=8)
for i, v in enumerate(mins): ax1.text(i, v+8, fmt(v), ha='center', fontsize=7.5)
for s in ['top','right']: ax1.spines[s].set_visible(False)
ax2 = fig.add_axes([0.58, 0.70, 0.36, 0.19]); ax2.bar([n.split()[0] for n in nomes], ntk, color='#5b7fc4')
ax2.set_title('Tickets distintos por agente', fontsize=10, color=AZUL, fontweight='bold'); ax2.tick_params(labelsize=8)
for i, v in enumerate(ntk): ax2.text(i, v+0.6, str(v), ha='center', fontsize=8)
for s in ['top','right']: ax2.spines[s].set_visible(False)
cat = collections.Counter(); cli = collections.Counter()
for t in ts:
    m = sum(a['min'] for a in t['apontamentos'])
    cat[t['categoria'] or '-'] += m
    cli['LECTOR (interno)' if t['cliente']=='LECTOR' else 'Clientes externos'] += m
ci = cat.most_common()
ax3 = fig.add_axes([0.10, 0.42, 0.34, 0.19])
ax3.pie([v for _,v in ci], labels=[k for k,_ in ci], autopct='%1.0f%%', textprops={'fontsize':7},
        colors=['#1f3b73','#5b7fc4','#9db4dd','#c9d6ec','#dfe7f4','#eef2f9'])
ax3.set_title('Tempo por categoria', fontsize=10, color=AZUL, fontweight='bold')
ax4 = fig.add_axes([0.56, 0.42, 0.34, 0.19])
ax4.pie(list(cli.values()), labels=list(cli.keys()), autopct='%1.0f%%', textprops={'fontsize':8}, colors=['#1f3b73','#10b981'])
ax4.set_title('Interno × Externo (tempo)', fontsize=10, color=AZUL, fontweight='bold')
top = tk_total.most_common(10)
ax5 = fig.add_axes([0.30, 0.06, 0.62, 0.28])
ax5.barh([f"{i} · {tk_assunto[i][:44]}" for i,_ in top][::-1], [v for _,v in top][::-1], color=AZUL)
ax5.set_title('Top 10 tickets por tempo total (min)', fontsize=10, color=AZUL, fontweight='bold'); ax5.tick_params(labelsize=7)
for yv,(i,v) in enumerate(top[::-1]): ax5.text(v+4, yv, fmt(v), va='center', fontsize=7, color=CINZA)
for s in ['top','right']: ax5.spines[s].set_visible(False)
pdf.savefig(fig); plt.close(fig)

# ---- P3 Perfil individual ----
fig = page(pdf, 'Perfil individual — em que cada um e forte')
y = 0.915
for n in sorted(ag, key=lambda k: -ag[k]['min']):
    a = ag[n]
    srv = ', '.join(f"{k} {v}min" for k, v in sorted(a['servicos'].items(), key=lambda kv:-kv[1]))
    tops = ', '.join(f"{t[0]} ({fmt(t[3])})" for t in a['top_tickets'][:3])
    linhas = [f"• Funcao: {funcao(n)}. Servicos: {srv}.",
              f"• Onde gastou mais tempo: {tops}." if tops else "• Sem tickets apontados."]
    if a['min'] < 30:
        linhas.append('• Ponto de atencao: praticamente sem apontamento no dia — confirmar folga/ausencia.')
    else:
        linhas.append(f"• Aproveitamento de jornada: {pct[n]:.0f}% (meta {META_PCT}%).")
    y = block(fig, y, f"{n} — {fmt(a['min'])} · {a['tickets']} tickets", linhas)
pdf.savefig(fig); plt.close(fig)

# ---- P4 Fluxo de status e voz do cliente ----
fig = page(pdf, 'Fluxo de status (proxy de SLA) e voz do cliente')
ordem = sorted(st.items(), key=lambda kv: -kv[1])
ax = fig.add_axes([0.40, 0.62, 0.52, 0.27])
ax.barh([k for k,_ in ordem][::-1], [v for _,v in ordem][::-1], color=AZUL)
ax.set_title('Tickets tocados no dia, por status atual', fontsize=10, color=AZUL, fontweight='bold'); ax.tick_params(labelsize=7.5)
for yv,(k,v) in enumerate(ordem[::-1]): ax.text(v+0.15, yv, str(v), va='center', fontsize=7.5)
for s in ['top','right']: ax.spines[s].set_visible(False)
y = 0.555
funil = [f'• Resolucao: {n_resolv} em "20 - Resolvido" — ' + ('maior grupo do funil.' if st and n_resolv==max(st.values()) else 'acompanhar.'),
         f'• Espera: {n_ag_cli} "Aguardando retorno cliente" + {n_ag_dev} "Aguardando Desenvolvimento" — precisam de follow-up ativo.',
         ('• Sem reprovacoes de HML.' if n_reprov==0 else f'• {n_reprov} reprovacao(oes) de HML = retrabalho.'),
         '• Obs.: o plano da API Movidesk nao expoe metricas formais de SLA; esta leitura usa o fluxo de status como proxy.']
if recorrentes:
    funil.insert(0, '• TENDENCIA (vs dias anteriores): tickets recorrentes entre os mais custosos: ' +
                 ', '.join(f'{t} (em {c} dias)' for t, c in recorrentes) + '.')
y = block(fig, y, 'Leitura do funil (proxy de SLA)' + (' + tendencias' if recorrentes else ''), funil)
voz = []
for f in (fb_dia[:6] or [{'cliente':'(sem feedback de cliente no dia)','ticket':'-','trecho':''}]):
    mark = 'x' if urgente(f) else '-'
    tx = ' '.join(f.get('trecho','').split())[:120]
    voz.append(f"{mark} {f.get('cliente','?')} (ticket {f.get('ticket')}): \"{tx}...\"" if tx else f"{mark} {f.get('cliente','?')}")
block(fig, y, f'Voz do cliente — feedbacks do dia ({DATA_BR})', voz, cor=VERDE)
pdf.savefig(fig); plt.close(fig)
pdf.close()
print(f'OK PDF: {os.path.join(BASE, f"Analise_Operacional_{DATA}.pdf")}')
print(f'Total {fmt(TOTAL_MIN)} | {N_TK} tickets | media {pct_equipe:.1f}% | resolvidos {n_resolv} | '
      f'ausentes {ausentes or "nenhum"} | recorrentes {[t for t,_ in recorrentes]}')
