# -*- coding: utf-8 -*-
"""Servidor local do Mission Control — transforma o painel numa aplicacao (PWA).

Serve o painel e os relatorios em http://localhost:8765, expoe a API que permite
"dar play" no agente pela interface e fornece manifest + service worker para o
navegador instalar o painel como app (janela propria, sempre aberta).

Endpoints:
  GET  /               painel (reconstruido a cada carga, sempre fresco)
  GET  /api/status     {running, date, log, atualizado}
  POST /api/run        {"date": "AAAA-MM-DD"?}  -> dispara runner_diario.py
  GET  /manifest.json, /sw.js, /icon-*.png     assets do PWA
  GET  /<arquivo>      PDFs/PNGs/JSONs da pasta de relatorios

Uso: python mission_server.py [porta]   (padrao 8765; bind so em 127.0.0.1)
Se a porta ja estiver em uso, assume que o servidor ja esta rodando e sai com 0
(o autostart no logon fica idempotente).
"""
import os, sys, re, json, threading, subprocess
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS)
import mission_control as mc

SAIDA = mc.SAIDA
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
SERVER_LOG = os.path.join(SAIDA, 'server_log.txt')

MANIFEST = json.dumps({
    'name': 'Mission Control — Apontamentos Movidesk',
    'short_name': 'MissionControl',
    'start_url': '/', 'scope': '/', 'display': 'standalone',
    'background_color': '#0b1020', 'theme_color': '#0b1020',
    'icons': [{'src': '/icon-192.png', 'sizes': '192x192', 'type': 'image/png'},
              {'src': '/icon-512.png', 'sizes': '512x512', 'type': 'image/png'}],
}, ensure_ascii=False).encode('utf-8')

SW = (b"self.addEventListener('install',function(e){self.skipWaiting();});"
      b"self.addEventListener('activate',function(e){self.clients.claim();});"
      b"self.addEventListener('fetch',function(){});")

_lock = threading.Lock()
_run = {'proc': None, 'date': None, 'inicio': None}
_ext = {'proc': None, 'modo': None, 'inicio': None}
EXT_STATE = os.path.join(SAIDA, 'extrator_state.json')
DEST_OBSIDIAN = os.environ.get(
    'EXTRATOR_OBSIDIAN_DIR',
    os.path.join(os.path.expanduser('~'), 'Downloads', 'CAIOSs', 'caios-data', 'movidesk-obsidian'))

def log_srv(msg):
    linha = f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {msg}'
    print(linha)
    try:
        with open(SERVER_LOG, 'a', encoding='utf-8') as f:
            f.write(linha + '\n')
    except OSError:
        pass

def rodando():
    p = _run['proc']
    return p is not None and p.poll() is None

def ext_rodando():
    p = _ext['proc']
    return p is not None and p.poll() is None

def gera_icones():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    for px in (192, 512):
        alvo = os.path.join(SAIDA, f'icon-{px}.png')
        if os.path.exists(alvo):
            continue
        fig = plt.figure(figsize=(1, 1), dpi=px)
        fig.patch.set_facecolor('#0b1020')
        fig.text(0.5, 0.56, 'MC', ha='center', va='center', fontsize=30,
                 color='#22d37f', fontweight='bold', family='monospace')
        fig.text(0.5, 0.24, 'MOVIDESK', ha='center', va='center', fontsize=6.5,
                 color='#4f8cff', family='monospace')
        fig.savefig(alvo, facecolor='#0b1020')
        plt.close(fig)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=SAIDA, **kw)

    def log_message(self, *a):
        pass

    def _bytes(self, corpo, ctype, status=200):
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(corpo)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(corpo)

    def _json(self, obj, status=200):
        self._bytes(json.dumps(obj, ensure_ascii=False).encode('utf-8'),
                    'application/json; charset=utf-8', status)

    def do_GET(self):
        if self.path in ('/', '/index.html', '/mission_control.html'):
            try:
                mc.build()
            except Exception as e:
                log_srv(f'erro ao reconstruir painel: {e}')
            self.path = '/mission_control.html'
            return super().do_GET()
        if self.path == '/api/status':
            log_tail = ''
            if os.path.exists(mc.LOG_PATH):
                try:
                    log_tail = ''.join(open(mc.LOG_PATH, encoding='utf-8',
                                            errors='replace').readlines()[-8:])
                except OSError:
                    pass
            return self._json({'running': rodando(), 'date': _run['date'],
                               'inicio': _run['inicio'], 'log': log_tail,
                               'atualizado': mc.carrega_estado().get('atualizado')})
        if self.path == '/api/extrator/status':
            estado = {}
            if os.path.exists(EXT_STATE):
                try:
                    estado = json.load(open(EXT_STATE, encoding='utf-8'))
                except (OSError, ValueError):
                    pass
            estado['running'] = ext_rodando()
            estado['dest_padrao'] = DEST_OBSIDIAN
            return self._json(estado)
        if self.path == '/manifest.json':
            return self._bytes(MANIFEST, 'application/manifest+json')
        if self.path == '/sw.js':
            return self._bytes(SW, 'text/javascript')
        return super().do_GET()

    def do_POST(self):
        if self.path not in ('/api/run', '/api/extrator/run'):
            return self.send_error(404)
        try:
            n = int(self.headers.get('Content-Length') or 0)
            corpo = json.loads(self.rfile.read(n) or b'{}') if n else {}
        except (ValueError, json.JSONDecodeError):
            corpo = {}
        if self.path == '/api/extrator/run':
            return self._extrator_run(corpo)
        data_str = corpo.get('date') or mc.dia_util_anterior().isoformat()
        with _lock:
            if rodando():
                return self._json({'ok': False, 'erro': 'missao ja em execucao',
                                   'date': _run['date']}, 409)
            log_saida = open(os.path.join(SAIDA, 'runner_launch.log'), 'ab')
            _run['proc'] = subprocess.Popen(
                [sys.executable, os.path.join(SCRIPTS, 'runner_diario.py'), data_str],
                cwd=SCRIPTS, stdout=log_saida, stderr=subprocess.STDOUT,
                creationflags=CREATE_NO_WINDOW)
            _run['date'] = data_str
            _run['inicio'] = datetime.now().isoformat(timespec='seconds')
        log_srv(f'play recebido: missao {data_str} disparada (pid {_run["proc"].pid})')
        return self._json({'ok': True, 'date': data_str})

    def _extrator_run(self, corpo):
        modo = (corpo.get('modo') or '').strip()
        dest = (corpo.get('dest') or '').strip() or DEST_OBSIDIAN
        if modo == 'range':
            try:
                inicio, fim = int(corpo.get('inicio')), int(corpo.get('fim'))
            except (TypeError, ValueError):
                return self._json({'ok': False, 'erro': 'informe inicio e fim numericos'}, 400)
            args = ['--range', str(inicio), str(fim)]
            rotulo = f'range {inicio}-{fim}'
        elif modo == 'lista':
            ids = re.sub(r'[^0-9,\s]', '', corpo.get('ids') or '').strip()
            if not ids:
                return self._json({'ok': False, 'erro': 'informe ao menos um ID'}, 400)
            args = ['--ids', ids]
            rotulo = f'ids {ids[:40]}'
        else:
            return self._json({'ok': False, 'erro': "modo deve ser 'range' ou 'lista'"}, 400)

        with _lock:
            if ext_rodando():
                return self._json({'ok': False, 'erro': 'extracao ja em execucao'}, 409)
            log_saida = open(os.path.join(SAIDA, 'extrator_launch.log'), 'ab')
            _ext['proc'] = subprocess.Popen(
                [sys.executable, os.path.join(SCRIPTS, 'extrator_obsidian.py'),
                 '--dest', dest, *args],
                cwd=SCRIPTS, stdout=log_saida, stderr=subprocess.STDOUT,
                creationflags=CREATE_NO_WINDOW)
            _ext['modo'] = modo
            _ext['inicio'] = datetime.now().isoformat(timespec='seconds')
        log_srv(f'extrator disparado: {rotulo} -> {dest} (pid {_ext["proc"].pid})')
        return self._json({'ok': True, 'modo': modo})

def main():
    os.makedirs(SAIDA, exist_ok=True)
    try:
        gera_icones()
    except Exception as e:
        log_srv(f'aviso: nao gerou icones ({e})')
    try:
        servidor = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    except OSError:
        print(f'Porta {PORT} ja em uso — servidor provavelmente ja esta rodando. Saindo.')
        sys.exit(0)
    log_srv(f'Mission Control servindo em http://localhost:{PORT} (pasta {SAIDA})')
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()
