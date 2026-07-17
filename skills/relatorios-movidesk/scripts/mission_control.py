# -*- coding: utf-8 -*-
"""Gera o painel Mission Control (mission_control.html) na pasta de relatorios.

Le o mission_state.json (escrito pelo runner_diario.py) e os resumo_*.json para
montar o quadro de missoes diarias: status de cada dia util, checklist de passos
(coleta, PNGs, PDF, verificacao), pendencias derivadas dos dados do dia
(follow-ups, ausentes, reprovados, feedbacks urgentes) e o log do runner.

Uso: python mission_control.py          (reconstroi o painel agora)
Tambem e importado pelo runner_diario.py apos cada execucao.
"""
import os, json, glob, html as html_mod
from datetime import date, timedelta, datetime

def carrega_env():
    """Le o .env da raiz da skill (CHAVE=valor) sem sobrescrever o ambiente real."""
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

SAIDA = os.environ.get('RELATORIOS_MOVIDESK_DIR',
                       os.path.join(os.path.expanduser('~'), 'Downloads', 'Relatorios Movidesk'))
AGENTES_PADRAO = ['Guilherme Raposo', 'Thiago Laguna', 'Ricardo Schutz', 'Luiz Firmo', 'Caio Gomes']
JORNADAS = {'Ricardo Schutz': 360}
JORNADA_PADRAO = 510
META_PCT = 90
DIAS_NO_PAINEL = 8
URGENTE_KW = ['urgent', 'impact', 'nao consigo', 'nao esta', 'nao estao', 'reclam',
              'erro', 'parou', 'travou', 'prejud', 'venda', 'urgenc', 'imediat']

ESTADO_PATH = os.path.join(SAIDA, 'mission_state.json')
PAINEL_PATH = os.path.join(SAIDA, 'mission_control.html')
LOG_PATH = os.path.join(SAIDA, 'runner_log.txt')

def h(s): return html_mod.escape(str(s))
def fmt(m): return f"{int(m)//60:02d}:{int(m)%60:02d}"

def dia_util_anterior(ref=None):
    d = (ref or date.today()) - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d

def dias_uteis(n, fim):
    """n dias uteis terminando em `fim`, do mais recente ao mais antigo."""
    out, d = [], fim
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d -= timedelta(days=1)
    return out

def carrega_estado():
    try:
        return json.load(open(ESTADO_PATH, encoding='utf-8'))
    except Exception:
        return {'runs': {}}

def norm(s):
    import unicodedata
    return unicodedata.normalize('NFKD', (s or '')).encode('ascii', 'ignore').decode().lower()

def metricas_do_resumo(resumo):
    ag = resumo.get('agentes', {})
    esperados = resumo.get('agentes_esperados') or AGENTES_PADRAO
    ausentes = resumo.get('ausentes')
    if ausentes is None:
        ausentes = [n for n in esperados if n not in ag]
    presentes = {n: a for n, a in ag.items() if a.get('min', 0) >= 30}
    total = sum(a.get('min', 0) for a in ag.values())
    pcts = [a['min'] / JORNADAS.get(n, JORNADA_PADRAO) * 100 for n, a in presentes.items()]
    pct = sum(pcts) / len(pcts) if pcts else 0.0
    tickets = sum(resumo.get('status', {}).values())
    return {'total_min': total, 'pct': round(pct, 1), 'tickets': tickets, 'ausentes': ausentes}

def pendencias_do_dia(data_str):
    """To-do list derivada dos dados do dia: o que exige acao humana amanha."""
    itens = []
    try:
        resumo = json.load(open(os.path.join(SAIDA, f'resumo_{data_str}.json'), encoding='utf-8'))
    except Exception:
        return itens
    itens.append(('conferir', 'Conferir visualmente os PNGs e o PDF do dia'))
    m = metricas_do_resumo(resumo)
    for nome in m['ausentes']:
        itens.append((f'ausente-{norm(nome).replace(" ", "-")}',
                      f'{nome} sem apontamentos — confirmar folga/falta'))
    st = resumo.get('status', {})
    n_cli = st.get('16 - Aguardando retorno cliente', 0)
    n_dev = st.get('23 - Aguardando Desenvolvimento', 0)
    if n_cli:
        itens.append(('follow-cliente', f'Follow-up nos {n_cli} ticket(s) em "Aguardando retorno cliente" antes das 10h'))
    if n_dev:
        itens.append(('follow-dev', f'{n_dev} ticket(s) em "Aguardando Desenvolvimento" — cobrar priorizacao'))
    n_reprov = sum(v for k, v in st.items() if 'reprov' in norm(k))
    if n_reprov:
        itens.append(('reprovados', f'{n_reprov} ticket(s) Reprovado(s) em HML — corrigir antes de novos itens'))
    for fb in resumo.get('feedbacks_clientes', [])[:5]:
        tx = norm(fb.get('trecho', ''))
        if any(k in tx for k in URGENTE_KW):
            itens.append((f'fb-{fb.get("ticket")}',
                          f'URGENTE — responder {fb.get("cliente", "cliente")} no ticket {fb.get("ticket")}'))
    return itens

CSS = """
:root { --bg:#0b1020; --panel:#111a30; --border:#1f2b4d; --tx:#d7e1f5; --dim:#7d8db2;
        --ok:#22d37f; --warn:#ffb020; --err:#ff5470; --acc:#4f8cff; }
* { box-sizing:border-box; margin:0; }
body { background:var(--bg); color:var(--tx); font:14px/1.5 ui-monospace,Consolas,monospace; padding:22px; }
a { color:var(--acc); text-decoration:none; } a:hover { text-decoration:underline; }
header { display:flex; justify-content:space-between; align-items:baseline; flex-wrap:wrap; gap:8px;
         border-bottom:1px solid var(--border); padding-bottom:12px; margin-bottom:18px; }
h1 { font-size:19px; letter-spacing:2px; } h1 b { color:var(--ok); }
.meta { color:var(--dim); font-size:12px; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; margin-bottom:18px; }
.card { background:var(--panel); border:1px solid var(--border); border-radius:8px; padding:12px 14px; }
.card .v { font-size:24px; font-weight:700; margin-top:2px; }
.card .l { color:var(--dim); font-size:11px; text-transform:uppercase; letter-spacing:1px; }
.ok { color:var(--ok); } .warn { color:var(--warn); } .err { color:var(--err); }
section { background:var(--panel); border:1px solid var(--border); border-radius:8px;
          padding:14px 16px; margin-bottom:16px; }
h2 { font-size:13px; letter-spacing:2px; text-transform:uppercase; color:var(--dim); margin-bottom:10px; }
table { width:100%; border-collapse:collapse; font-size:13px; }
th { text-align:left; color:var(--dim); font-size:11px; text-transform:uppercase; letter-spacing:1px;
     border-bottom:1px solid var(--border); padding:6px 8px; }
td { padding:7px 8px; border-bottom:1px solid rgba(31,43,77,.5); white-space:nowrap; }
.chip { display:inline-block; padding:1px 9px; border-radius:99px; font-size:11px; font-weight:700; }
.chip.ok { background:rgba(34,211,127,.15); color:var(--ok); }
.chip.err { background:rgba(255,84,112,.15); color:var(--err); }
.chip.pend { background:rgba(255,176,32,.15); color:var(--warn); }
.steps { letter-spacing:3px; font-size:13px; }
ul.todo { list-style:none; } ul.todo li { padding:5px 0; display:flex; gap:9px; align-items:baseline; }
ul.todo input { accent-color:var(--ok); transform:translateY(2px); }
ul.todo li.done label { color:var(--dim); text-decoration:line-through; }
pre { color:var(--dim); font-size:12px; overflow-x:auto; }
"""

JS = """
document.querySelectorAll('input.todo-check').forEach(function (cb) {
  var key = 'mc:' + cb.dataset.key;
  if (localStorage.getItem(key) === '1') { cb.checked = true; cb.closest('li').classList.add('done'); }
  cb.addEventListener('change', function () {
    localStorage.setItem(key, cb.checked ? '1' : '0');
    cb.closest('li').classList.toggle('done', cb.checked);
  });
});
"""

def _passos_html(steps):
    ordem = [('coleta', 'API'), ('pngs', 'PNG'), ('pdf', 'PDF'), ('verificacao', 'CHK')]
    partes = []
    for chave, rot in ordem:
        v = steps.get(chave)
        cls, mark = ('ok', '&#10003;') if v else (('err', '&#10007;') if v is False else ('meta', '&middot;'))
        partes.append(f'<span class="{cls}" title="{rot}">{mark}</span>')
    return f'<span class="steps">{"".join(partes)}</span>'

def build():
    estado = carrega_estado()
    hoje = date.today()
    alvo = dia_util_anterior(hoje)
    dias = dias_uteis(DIAS_NO_PAINEL, alvo)

    linhas, ultimo_com_dados = [], None
    pendentes = 0
    for d in dias:
        run = estado['runs'].get(d, {})
        tem_resumo = os.path.exists(os.path.join(SAIDA, f'resumo_{d}.json'))
        if tem_resumo and ultimo_com_dados is None:
            ultimo_com_dados = d
        if run.get('status') == 'ok':
            chip = '<span class="chip ok">OK</span>'
        elif run.get('status') == 'falha':
            chip = '<span class="chip err">FALHA</span>'
        elif tem_resumo:
            chip = '<span class="chip ok">OK &middot; manual</span>'
        else:
            chip = '<span class="chip pend">PENDENTE</span>'
            pendentes += 1
        if run:
            met = run
            steps = run.get('steps', {})
        elif tem_resumo:
            try:
                met = metricas_do_resumo(json.load(open(os.path.join(SAIDA, f'resumo_{d}.json'), encoding='utf-8')))
            except Exception:
                met = {}
            steps = {'coleta': True, 'pngs': None, 'pdf': os.path.exists(os.path.join(SAIDA, f'Analise_Operacional_{d}.pdf')), 'verificacao': None}
        else:
            met, steps = {}, {}
        aus = met.get('ausentes') or []
        links = []
        for nome_arq, rot in [(f'Analise_Operacional_{d}.pdf', 'PDF'), (f'Equipe_{d}.png', 'Equipe')]:
            if os.path.exists(os.path.join(SAIDA, nome_arq)):
                links.append(f'<a href="{h(nome_arq)}">{rot}</a>')
        linhas.append(
            '<tr><td>' + '/'.join(reversed(d.split('-'))) + f'</td><td>{chip}</td>'
            f'<td>{_passos_html(steps)}</td>'
            f'<td>{fmt(met["total_min"]) if met.get("total_min") is not None else "&mdash;"}</td>'
            f'<td>{str(met["pct"]) + "%" if met.get("pct") is not None else "&mdash;"}</td>'
            f'<td>{met.get("tickets", "&mdash;")}</td>'
            f'<td>{h(", ".join(n.split()[0] for n in aus)) if aus else "&mdash;"}</td>'
            f'<td>{" &middot; ".join(links) or "&mdash;"}</td></tr>')

    ult_run = estado['runs'].get(alvo.isoformat()) or (estado['runs'].get(ultimo_com_dados) if ultimo_com_dados else None)
    if ult_run and ult_run.get('status') == 'ok':
        estado_geral, cls_geral = 'NOMINAL', 'ok'
    elif ult_run and ult_run.get('status') == 'falha':
        estado_geral, cls_geral = 'FALHA NA ULTIMA MISSAO', 'err'
    elif ultimo_com_dados == alvo.isoformat():
        estado_geral, cls_geral = 'NOMINAL (manual)', 'ok'
    else:
        estado_geral, cls_geral = 'MISSAO DO DIA PENDENTE', 'warn'

    met_alvo = {}
    if ultimo_com_dados:
        try:
            met_alvo = metricas_do_resumo(json.load(open(os.path.join(SAIDA, f'resumo_{ultimo_com_dados}.json'), encoding='utf-8')))
        except Exception:
            pass

    todo_html = []
    if ultimo_com_dados:
        for slug, texto in pendencias_do_dia(ultimo_com_dados):
            key = h(f'{ultimo_com_dados}:{slug}')
            todo_html.append(f'<li><input type="checkbox" class="todo-check" data-key="{key}" id="t-{key}">'
                             f'<label for="t-{key}">{h(texto)}</label></li>')
    if pendentes:
        todo_html.append(f'<li><input type="checkbox" class="todo-check" data-key="backfill-{alvo.isoformat()}" id="t-bf">'
                         f'<label for="t-bf">Backfill: {pendentes} dia(s) util(eis) sem relatorio no painel — '
                         f'rodar runner_diario.py com a data</label></li>')
    if not todo_html:
        todo_html.append('<li>&mdash; sem pendencias &mdash;</li>')

    log_tail = ''
    if os.path.exists(LOG_PATH):
        try:
            log_tail = ''.join(open(LOG_PATH, encoding='utf-8', errors='replace').readlines()[-14:])
        except Exception:
            pass

    gerado = datetime.now().strftime('%d/%m/%Y %H:%M')
    pct_txt = f'{met_alvo["pct"]}%' if met_alvo.get('pct') is not None else '—'
    aus_txt = ', '.join(n.split()[0] for n in met_alvo.get('ausentes', [])) or 'nenhum'
    data_ref = '/'.join(reversed((ultimo_com_dados or alvo.isoformat()).split('-')))

    doc = ('<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">'
           '<meta http-equiv="refresh" content="300">'
           '<title>Mission Control - Apontamentos Movidesk</title>'
           f'<style>{CSS}</style></head><body>'
           '<header><h1>MISSION CONTROL <b>&#9646;</b> APONTAMENTOS MOVIDESK</h1>'
           f'<div class="meta">gerado {gerado} &middot; agendado seg&ndash;sex 09:00 '
           '(tarefa RelatoriosMovideskDiario) &middot; auto-refresh 5 min</div></header>'
           '<div class="grid">'
           f'<div class="card"><div class="l">Status</div><div class="v {cls_geral}">{estado_geral}</div></div>'
           f'<div class="card"><div class="l">Ultimo dia com dados</div><div class="v">{data_ref}</div></div>'
           f'<div class="card"><div class="l">Horas da equipe</div><div class="v">{fmt(met_alvo["total_min"]) if met_alvo.get("total_min") is not None else "&mdash;"}</div></div>'
           f'<div class="card"><div class="l">Meta (90%)</div><div class="v {"ok" if met_alvo.get("pct", 0) >= META_PCT else "warn"}">{pct_txt}</div></div>'
           f'<div class="card"><div class="l">Tickets tocados</div><div class="v">{met_alvo.get("tickets", "&mdash;")}</div></div>'
           f'<div class="card"><div class="l">Ausentes</div><div class="v" style="font-size:16px">{h(aus_txt)}</div></div>'
           '</div>'
           '<section><h2>Missoes &mdash; ultimos dias uteis</h2><table>'
           '<tr><th>Dia</th><th>Status</th><th>API PNG PDF CHK</th><th>Horas</th><th>Meta</th>'
           '<th>Tickets</th><th>Ausentes</th><th>Arquivos</th></tr>'
           + ''.join(linhas) + '</table></section>'
           f'<section><h2>To-do &mdash; pendencias do dia {data_ref}</h2><ul class="todo">'
           + ''.join(todo_html) + '</ul></section>'
           '<section><h2>Log do runner</h2><pre>' + h(log_tail or '(sem execucoes registradas ainda)') + '</pre></section>'
           f'<script>{JS}</script></body></html>')

    os.makedirs(SAIDA, exist_ok=True)
    with open(PAINEL_PATH, 'w', encoding='utf-8') as f:
        f.write(doc)
    return PAINEL_PATH

if __name__ == '__main__':
    print('OK painel:', build())
