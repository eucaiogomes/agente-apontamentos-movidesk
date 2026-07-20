# -*- coding: utf-8 -*-
"""Extrator Movidesk -> Obsidian (via API publica).

Puxa tickets pela API oficial do Movidesk (usa o mesmo MOVIDESK_TOKEN dos
relatorios) e salva cada um como um arquivo Markdown dentro de uma pasta por
cliente, pronto para virar um Vault do Obsidian:

    <DESTINO>/<Cliente>/<ID> - <Assunto>.md

Modos:
    python extrator_obsidian.py --range 9000 9200      # varre um intervalo de IDs
    python extrator_obsidian.py --ids 11284,11090      # lista especifica de IDs
    python extrator_obsidian.py --range 9000 9999 --dest "C:\\caminho\\Vault"

No modo --range o script para sozinho apos LIMITE_MISS IDs seguidos sem ticket
(equivalente ao comportamento do extrator original). Progresso e escrito em
extrator_state.json (lido pelo painel Mission Control) e o log em
extrator_log.txt, ambos na pasta de relatorios (SAIDA).

Reconstruido em 2026-07-20 a partir do agente do repo movidesk-obsidian,
trocando o scraping por cookie pela API oficial (token que nao expira).
"""
import os, sys, re, json, time, html as html_mod, argparse, unicodedata
from datetime import datetime, date
from html.parser import HTMLParser
import requests

# ---------------- Config / ambiente ----------------
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

TOKEN = os.environ.get('MOVIDESK_TOKEN')
SAIDA = os.environ.get('RELATORIOS_MOVIDESK_DIR',
                       os.path.join(os.path.expanduser('~'), 'Downloads', 'Relatorios Movidesk'))
DEST_PADRAO = os.environ.get(
    'EXTRATOR_OBSIDIAN_DIR',
    os.path.join(os.path.expanduser('~'), 'Downloads', 'CAIOSs', 'caios-data', 'movidesk-obsidian'))
SUBDOMINIO = os.environ.get('MOVIDESK_SUBDOMAIN', 'lectortec')

URL_API = 'https://api.movidesk.com/public/v1/tickets'
LIMITE_MISS = 30          # para o modo --range: IDs seguidos sem ticket antes de parar
PAUSA = 0.15              # respiro entre chamadas para nao estressar a API

ESTADO_PATH = os.path.join(SAIDA, 'extrator_state.json')
LOG_PATH = os.path.join(SAIDA, 'extrator_log.txt')

SELECT = 'id,subject,status,baseStatus,category,urgency,createdDate,resolvedIn'
EXPAND = ('clients($select=businessName,personType,profileType),'
          'actions($select=id,type,description,createdDate;'
          '$expand=createdBy($select=businessName))')


# ---------------- Utilidades ----------------
def limpar_nome(nome, limite=90):
    """Remove caracteres que o Windows nao aceita em pastas/arquivos."""
    if not nome:
        return 'Desconhecido'
    nome = re.sub(r'[\\/?:"<>|*\n\r\t]', '-', nome)
    nome = ' '.join(nome.split()).strip(' .')
    return (nome or 'Desconhecido')[:limite]


def log(msg):
    linha = f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {msg}'
    print(linha, flush=True)
    try:
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(linha + '\n')
    except OSError:
        pass


class _Estado:
    """Espelha o progresso em extrator_state.json a cada passo (o painel le isso)."""
    def __init__(self, modo, total, dest):
        self.d = {'running': True, 'modo': modo, 'total': total, 'dest': dest,
                  'processados': 0, 'salvos': 0, 'vazios': 0, 'erros': 0,
                  'atual': None, 'ultimo_arquivo': None, 'mensagem': '',
                  'started': datetime.now().isoformat(timespec='seconds'),
                  'finished': None}
        self.salva()

    def salva(self):
        try:
            with open(ESTADO_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.d, f, ensure_ascii=False)
        except OSError:
            pass

    def passo(self, **kw):
        self.d.update(kw)
        self.salva()

    def fim(self, msg):
        self.d.update(running=False, mensagem=msg, atual=None,
                      finished=datetime.now().isoformat(timespec='seconds'))
        self.salva()


# ---------------- HTML -> Markdown (sem dependencias) ----------------
class _HTML2MD(HTMLParser):
    """Conversor minimalista de HTML para Markdown usando so a stdlib."""
    _BLOCO = {'p', 'div', 'br', 'tr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'ul', 'ol'}

    def __init__(self):
        super().__init__()
        self.out = []
        self._lista = []   # pilha: 'ul' ou ('ol', contador)
        self._href = None

    def handle_starttag(self, tag, attrs):
        if tag in ('b', 'strong'):
            self.out.append('**')
        elif tag in ('i', 'em'):
            self.out.append('*')
        elif tag == 'br':
            self.out.append('\n')
        elif tag in ('p', 'div', 'tr'):
            self.out.append('\n\n')
        elif tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self.out.append('\n\n' + '#' * int(tag[1]) + ' ')
        elif tag == 'ul':
            self._lista.append('ul')
            self.out.append('\n')
        elif tag == 'ol':
            self._lista.append(['ol', 0])
            self.out.append('\n')
        elif tag == 'li':
            self.out.append('\n')
            if self._lista and isinstance(self._lista[-1], list):
                self._lista[-1][1] += 1
                self.out.append(f'{self._lista[-1][1]}. ')
            else:
                self.out.append('- ')
        elif tag == 'a':
            self._href = dict(attrs).get('href')

    def handle_endtag(self, tag):
        if tag in ('b', 'strong'):
            self.out.append('**')
        elif tag in ('i', 'em'):
            self.out.append('*')
        elif tag in ('p', 'div', 'tr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self.out.append('\n')
        elif tag in ('ul', 'ol') and self._lista:
            self._lista.pop()
        elif tag == 'a' and self._href:
            self.out.append(f' ({self._href})')
            self._href = None

    def handle_data(self, data):
        self.out.append(data)

    def texto(self):
        txt = html_mod.unescape(''.join(self.out))
        txt = re.sub(r'[ \t]+', ' ', txt)
        txt = re.sub(r'\n{3,}', '\n\n', txt)
        return txt.strip()


def html_para_md(bruto):
    if not bruto:
        return ''
    p = _HTML2MD()
    try:
        p.feed(bruto)
    except Exception:
        return re.sub(r'<[^>]+>', '', html_mod.unescape(bruto)).strip()
    return p.texto()


# ---------------- API ----------------
def busca_ticket(ticket_id):
    """Retorna o dict do ticket, None se nao existir, ou levanta em erro real."""
    r = requests.get(URL_API, params={
        'token': TOKEN, 'id': ticket_id, '$select': SELECT, '$expand': EXPAND}, timeout=90)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    dados = r.json()
    if isinstance(dados, list):
        return dados[0] if dados else None
    return dados or None


# ---------------- Geracao do arquivo ----------------
def nome_cliente(ticket):
    for c in (ticket.get('clients') or []):
        nome = (c.get('businessName') or '').strip()
        if nome:
            return nome
    return 'Sem cliente'


def monta_markdown(ticket):
    tid = ticket.get('id')
    assunto = (ticket.get('subject') or '(sem assunto)').strip()
    cliente = nome_cliente(ticket)
    url = f'https://{SUBDOMINIO}.movidesk.com/Ticket/Edit/{tid}'
    criado = (ticket.get('createdDate') or '')[:10]

    fm = {
        'ticket': tid, 'cliente': cliente, 'assunto': assunto,
        'status': ticket.get('status') or '', 'categoria': ticket.get('category') or '',
        'urgencia': ticket.get('urgency') or '', 'criado': criado,
        'url': url, 'extraido': datetime.now().isoformat(timespec='seconds'),
    }
    linhas = ['---']
    for k, v in fm.items():
        val = str(v).replace('"', "'")
        linhas.append(f'{k}: "{val}"' if isinstance(v, str) else f'{k}: {val}')
    linhas.append('---\n')
    linhas.append(f'# {tid} — {assunto}\n')
    linhas.append(f'**Cliente:** {cliente}  ')
    linhas.append(f'**Status:** {fm["status"]} · **Categoria:** {fm["categoria"] or "—"}  ')
    linhas.append(f'**Aberto em:** {criado or "—"} · [Abrir no Movidesk]({url})\n')

    acoes = ticket.get('actions') or []
    if acoes:
        linhas.append('## Histórico / Ações\n')
        for a in acoes:
            autor = ((a.get('createdBy') or {}).get('businessName') or 'Sistema')
            quando = (a.get('createdDate') or '')[:16].replace('T', ' ')
            corpo = html_para_md(a.get('description') or '')
            linhas.append(f'### {quando} — {autor}\n')
            linhas.append((corpo or '_(sem conteúdo)_') + '\n')
    return '\n'.join(linhas)


def salva_ticket(ticket, dest):
    cliente = limpar_nome(nome_cliente(ticket))
    tid = ticket.get('id')
    assunto = limpar_nome(ticket.get('subject') or 'sem-assunto')
    pasta = os.path.join(dest, cliente)
    os.makedirs(pasta, exist_ok=True)
    arquivo = os.path.join(pasta, f'{tid} - {assunto}.md')
    with open(arquivo, 'w', encoding='utf-8') as f:
        f.write(monta_markdown(ticket))
    return os.path.join(cliente, f'{tid} - {assunto}.md')


# ---------------- Execucao ----------------
def ids_do_range(inicio, fim):
    passo = 1 if fim >= inicio else -1
    return range(inicio, fim + passo, passo)


def executa(modo, ids, dest, usa_limite_miss):
    os.makedirs(SAIDA, exist_ok=True)
    os.makedirs(dest, exist_ok=True)
    total = len(ids) if hasattr(ids, '__len__') else None
    est = _Estado(modo, total, dest)
    log(f'=== Extracao {modo} iniciada — destino: {dest} ===')

    salvos = vazios = erros = miss_seguidos = proc = 0
    for tid in ids:
        proc += 1
        est.passo(atual=tid, processados=proc)
        try:
            ticket = busca_ticket(tid)
        except requests.RequestException as e:
            erros += 1
            miss_seguidos = 0
            log(f'ticket {tid}: erro de rede/API ({e})')
            est.passo(erros=erros)
            time.sleep(PAUSA * 4)
            continue

        if not ticket:
            vazios += 1
            miss_seguidos += 1
            est.passo(vazios=vazios)
            if usa_limite_miss and miss_seguidos >= LIMITE_MISS:
                log(f'{LIMITE_MISS} IDs seguidos sem ticket (parou em {tid}) — encerrando varredura.')
                break
            time.sleep(PAUSA)
            continue

        miss_seguidos = 0
        try:
            rel = salva_ticket(ticket, dest)
            salvos += 1
            est.passo(salvos=salvos, ultimo_arquivo=rel)
            log(f'ticket {tid}: salvo -> {rel}')
        except OSError as e:
            erros += 1
            est.passo(erros=erros)
            log(f'ticket {tid}: falha ao salvar ({e})')
        time.sleep(PAUSA)

    msg = f'{salvos} salvos · {vazios} inexistentes · {erros} erros'
    est.fim(msg)
    log(f'=== Extracao {modo} concluida: {msg} ===')
    return salvos, vazios, erros


def main():
    if not TOKEN:
        sys.exit('MOVIDESK_TOKEN nao definido. Configure o .env da skill (veja .env.example).')

    ap = argparse.ArgumentParser(description='Extrator Movidesk -> Obsidian (API).')
    ap.add_argument('--range', nargs=2, type=int, metavar=('INICIO', 'FIM'),
                    help='intervalo de IDs a varrer (ex.: --range 9000 9200)')
    ap.add_argument('--ids', help='lista de IDs separados por virgula (ex.: --ids 11284,11090)')
    ap.add_argument('--dest', default=DEST_PADRAO, help='pasta destino do Vault (padrao: %(default)s)')
    args = ap.parse_args()

    if args.ids:
        ids = [int(x) for x in re.split(r'[,\s]+', args.ids.strip()) if x]
        executa('lista', ids, args.dest, usa_limite_miss=False)
    elif args.range:
        ids = ids_do_range(args.range[0], args.range[1])
        executa('range', ids, args.dest, usa_limite_miss=True)
    else:
        ap.error('informe --range INICIO FIM ou --ids 1,2,3')


if __name__ == '__main__':
    main()
