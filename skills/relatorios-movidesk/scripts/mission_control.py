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
#ctl { display:none; align-items:center; gap:10px; }
.btn { background:rgba(34,211,127,.12); color:var(--ok); border:1px solid var(--ok);
       border-radius:6px; padding:6px 14px; font:700 13px ui-monospace,Consolas,monospace;
       letter-spacing:1px; cursor:pointer; }
.btn:hover { background:rgba(34,211,127,.25); }
.btn:disabled { opacity:.4; cursor:wait; }
.btn.mini { padding:0 7px; font-size:11px; margin-left:6px; }
.pill { display:inline-block; padding:3px 10px; border-radius:99px; font-size:11px; font-weight:700;
        border:1px solid var(--border); color:var(--dim); }
.pill.ok { color:var(--ok); border-color:var(--ok); }
.pill.warn { color:var(--warn); border-color:var(--warn); animation:pulse 1.2s infinite; }
@keyframes pulse { 50% { opacity:.45; } }
.tabs { display:flex; gap:6px; border-bottom:1px solid var(--border); margin-bottom:18px; }
.tab { background:none; border:none; border-bottom:2px solid transparent; color:var(--dim);
       font:700 12px ui-monospace,Consolas,monospace; letter-spacing:2px; text-transform:uppercase;
       padding:9px 14px; cursor:pointer; }
.tab:hover { color:var(--tx); }
.tab.active { color:var(--ok); border-bottom-color:var(--ok); }
.tabpane[hidden] { display:none; }
.field { display:flex; flex-direction:column; gap:4px; }
.field label { color:var(--dim); font-size:11px; text-transform:uppercase; letter-spacing:1px; }
.field input { background:var(--bg); border:1px solid var(--border); border-radius:6px; color:var(--tx);
       font:13px ui-monospace,Consolas,monospace; padding:7px 9px; }
.field input:focus { outline:none; border-color:var(--acc); }
.row { display:flex; gap:14px; flex-wrap:wrap; align-items:flex-end; margin-bottom:12px; }
.radio { display:flex; gap:16px; margin-bottom:6px; color:var(--tx); font-size:13px; }
.radio label { display:flex; gap:6px; align-items:center; cursor:pointer; }
.hint { color:var(--dim); font-size:12px; margin-bottom:12px; }
.bar { height:8px; background:var(--bg); border:1px solid var(--border); border-radius:99px; overflow:hidden; margin:8px 0; }
.bar > i { display:block; height:100%; width:0; background:var(--ok); transition:width .3s; }
.statgrid { display:grid; grid-template-columns:repeat(auto-fit,minmax(90px,1fr)); gap:10px; margin-top:10px; }
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

/* --- Controles do agente (so funcionam quando servido pelo mission_server.py) --- */
var estavaRodando = false;
function api(path, opts) {
  return fetch(path, opts).then(function (r) { return r.json(); }).catch(function () { return null; });
}
function atualizaPill(s) {
  var pill = document.getElementById('run-status');
  var play = document.getElementById('play');
  if (s.running) {
    pill.textContent = 'EM EXECUCAO \\u00b7 ' + (s.date || '');
    pill.className = 'pill warn';
    play.disabled = true;
    estavaRodando = true;
  } else {
    if (estavaRodando) { location.reload(); return; }
    pill.textContent = 'AGENTE OCIOSO';
    pill.className = 'pill ok';
    play.disabled = false;
  }
}
function poll() {
  api('/api/status').then(function (s) {
    if (!s) return;  // aberto como arquivo local: controles ficam ocultos
    document.getElementById('ctl').style.display = 'flex';
    atualizaPill(s);
    setTimeout(poll, s.running ? 3000 : 15000);
  });
}
function roda(dateStr) {
  api('/api/run', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(dateStr ? { date: dateStr } : {}) })
    .then(function () { estavaRodando = true; poll(); });
}
document.getElementById('play').addEventListener('click', function () { roda(null); });
document.querySelectorAll('.play-day').forEach(function (b) {
  b.addEventListener('click', function () { b.disabled = true; roda(b.dataset.date); });
});
if ('serviceWorker' in navigator && location.protocol.indexOf('http') === 0) {
  navigator.serviceWorker.register('/sw.js').catch(function () {});
}
poll();

/* --- Abas --- */
document.querySelectorAll('.tab').forEach(function (t) {
  t.addEventListener('click', function () {
    document.querySelectorAll('.tab').forEach(function (x) { x.classList.remove('active'); });
    document.querySelectorAll('.tabpane').forEach(function (p) { p.hidden = true; });
    t.classList.add('active');
    document.getElementById('pane-' + t.dataset.tab).hidden = false;
    localStorage.setItem('mc:tab', t.dataset.tab);
  });
});
(function () {
  var saved = localStorage.getItem('mc:tab');
  var btn = saved && document.querySelector('.tab[data-tab="' + saved + '"]');
  if (btn) btn.click();
})();

/* --- Extrator Obsidian (so ativo quando servido pelo mission_server.py) --- */
var extRodou = false;
function extToggleModo() {
  var modo = (document.querySelector('input[name=ext-modo]:checked') || {}).value;
  document.getElementById('ext-range-fields').style.display = modo === 'range' ? 'flex' : 'none';
  document.getElementById('ext-lista-fields').style.display = modo === 'lista' ? 'flex' : 'none';
}
function extPinta(s) {
  if (!s) return;
  document.getElementById('extrator-ui').style.display = 'block';
  var run = document.getElementById('ext-run');
  var badge = document.getElementById('ext-badge');
  var tot = s.total || 0, proc = s.processados || 0;
  var pct = tot ? Math.round(proc * 100 / tot) : (s.running ? 50 : (proc ? 100 : 0));
  document.getElementById('ext-progress').style.width = pct + '%';
  document.getElementById('ext-salvos').textContent = s.salvos || 0;
  document.getElementById('ext-vazios').textContent = s.vazios || 0;
  document.getElementById('ext-erros').textContent = s.erros || 0;
  document.getElementById('ext-proc').textContent = proc + (tot ? ' / ' + tot : '');
  document.getElementById('ext-ultimo').textContent = s.ultimo_arquivo || (s.atual ? 'ticket ' + s.atual : '—');
  if (s.dest_padrao && !document.getElementById('ext-dest').value) {
    document.getElementById('ext-dest').placeholder = s.dest_padrao;
  }
  if (s.running) {
    badge.textContent = 'EXTRAINDO' + (s.atual ? ' · ' + s.atual : '');
    badge.className = 'pill warn';
    run.disabled = true; extRodou = true;
  } else {
    badge.textContent = extRodou ? (s.mensagem || 'CONCLUIDO') : 'OCIOSO';
    badge.className = 'pill ok';
    run.disabled = false;
  }
}
function extPoll() {
  api('/api/extrator/status').then(function (s) {
    if (s === null) { document.getElementById('extrator-ui').style.display = 'none'; return; }
    extPinta(s);
    setTimeout(extPoll, s.running ? 2000 : 12000);
  });
}
function extRoda() {
  var modo = (document.querySelector('input[name=ext-modo]:checked') || {}).value;
  var body = { modo: modo, dest: document.getElementById('ext-dest').value.trim() };
  if (modo === 'range') {
    body.inicio = document.getElementById('ext-inicio').value;
    body.fim = document.getElementById('ext-fim').value;
  } else {
    body.ids = document.getElementById('ext-ids').value;
  }
  var run = document.getElementById('ext-run');
  run.disabled = true;
  api('/api/extrator/run', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                             body: JSON.stringify(body) })
    .then(function (r) {
      if (r && r.ok) { extRodou = true; extPoll(); }
      else { alert((r && r.erro) || 'Falha ao iniciar extracao'); run.disabled = false; }
    });
}
if (document.getElementById('ext-run')) {
  document.querySelectorAll('input[name=ext-modo]').forEach(function (r) {
    r.addEventListener('change', extToggleModo);
  });
  document.getElementById('ext-run').addEventListener('click', extRoda);
  extToggleModo();
  extPoll();
}
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
            chip = ('<span class="chip pend">PENDENTE</span>'
                    f'<button class="btn mini play-day" data-date="{d}" '
                    f'title="Backfill de {d}">&#9654;</button>')
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
           '<meta name="viewport" content="width=device-width, initial-scale=1">'
           '<meta http-equiv="refresh" content="300">'
           '<meta name="theme-color" content="#0b1020">'
           '<link rel="manifest" href="/manifest.json">'
           '<link rel="icon" href="/icon-192.png">'
           '<title>Mission Control - Apontamentos Movidesk</title>'
           f'<style>{CSS}</style></head><body>'
           '<header><h1>MISSION CONTROL <b>&#9646;</b> APONTAMENTOS MOVIDESK</h1>'
           '<div id="ctl"><button id="play" class="btn" title="Roda a missao do dia util anterior">'
           '&#9654; RODAR MISSAO</button><span id="run-status" class="pill">&hellip;</span></div>'
           f'<div class="meta">gerado {gerado} &middot; agendado seg&ndash;sex 09:00 '
           '(tarefa RelatoriosMovideskDiario) &middot; auto-refresh 5 min</div></header>'
           '<div class="tabs">'
           '<button class="tab active" data-tab="missoes">Missoes</button>'
           '<button class="tab" data-tab="extrator">Extrator Obsidian</button></div>'
           '<div id="pane-missoes" class="tabpane">'
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
           '</div>'  # fim pane-missoes
           '<div id="pane-extrator" class="tabpane" hidden>'
           '<section><h2>Extrator Movidesk &rarr; Obsidian</h2>'
           '<div class="hint">Puxa tickets pela API do Movidesk e salva cada um como Markdown '
           'em <code>&lt;destino&gt;/&lt;Cliente&gt;/&lt;ID&gt; - &lt;Assunto&gt;.md</code>. '
           'Os controles so funcionam com o painel servido pelo mission_server.py.</div>'
           '<div id="extrator-ui" style="display:none">'
           '<div class="radio">'
           '<label><input type="radio" name="ext-modo" value="range" checked> Intervalo de IDs</label>'
           '<label><input type="radio" name="ext-modo" value="lista"> Lista de IDs</label></div>'
           '<div class="row" id="ext-range-fields">'
           '<div class="field"><label>ID inicial</label><input id="ext-inicio" type="number" value="9000"></div>'
           '<div class="field"><label>ID final</label><input id="ext-fim" type="number" value="9200"></div>'
           '</div>'
           '<div class="row" id="ext-lista-fields" style="display:none">'
           '<div class="field" style="flex:1"><label>IDs (separados por virgula)</label>'
           '<input id="ext-ids" type="text" placeholder="11284, 11090, 9644"></div></div>'
           '<div class="row"><div class="field" style="flex:1"><label>Destino (deixe vazio p/ padrao)</label>'
           '<input id="ext-dest" type="text"></div>'
           '<button id="ext-run" class="btn">&#9654; EXTRAIR</button>'
           '<span id="ext-badge" class="pill">&hellip;</span></div>'
           '<div class="bar"><i id="ext-progress"></i></div>'
           '<div class="statgrid">'
           '<div class="card"><div class="l">Processados</div><div class="v" id="ext-proc" style="font-size:18px">0</div></div>'
           '<div class="card"><div class="l">Salvos</div><div class="v ok" id="ext-salvos" style="font-size:18px">0</div></div>'
           '<div class="card"><div class="l">Inexistentes</div><div class="v" id="ext-vazios" style="font-size:18px">0</div></div>'
           '<div class="card"><div class="l">Erros</div><div class="v err" id="ext-erros" style="font-size:18px">0</div></div>'
           '</div>'
           '<div class="meta" style="margin-top:10px">Ultimo: <span id="ext-ultimo">&mdash;</span></div>'
           '</div></section></div>'  # fim extrator-ui + section + pane-extrator
           f'<script>{JS}</script></body></html>')

    os.makedirs(SAIDA, exist_ok=True)
    with open(PAINEL_PATH, 'w', encoding='utf-8') as f:
        f.write(doc)
    return PAINEL_PATH

if __name__ == '__main__':
    print('OK painel:', build())
