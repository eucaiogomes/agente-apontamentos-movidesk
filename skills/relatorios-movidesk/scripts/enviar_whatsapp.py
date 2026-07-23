# -*- coding: utf-8 -*-
"""Envia os PNGs de apontamentos ao grupo do WhatsApp via Evolution API.

Ao final de cada missao (chamado pelo runner_diario.py), manda o PNG individual
de cada agente para o grupo, marcando a pessoa, com a legenda:

    @<numero> <pct>% Relatorio Geral <dd/mm>

O WhatsApp renderiza `@<numero>` como o nome salvo do contato (ex.:
"Guilherme Raposo Desenvolvimento"). O `<pct>` e o aproveitamento da jornada do
agente no dia (min / jornada * 100).

A Evolution API roda num VPS (Docker) e e acessada por tunel SSH — o payload
(imagem em base64) e enviado por `ssh <host> "curl ... -d @-"`. Antes de enviar,
garante que o container esta de pe (`docker start`, idempotente).

Config (no .env da skill; a chave e segredo, fica fora do repo):
    EVOLUTION_SSH        root@2.25.71.207
    EVOLUTION_BASE       http://127.0.0.1:36721
    EVOLUTION_KEY        <apikey>
    EVOLUTION_INSTANCE   Whatsapp lector
    EVOLUTION_GROUP      120363041106999402@g.us
    EVOLUTION_CONTAINER  evolution-api-gi8t-api-1
    ENVIAR_WHATSAPP      1        (0/vazio desliga o envio)

Mapa de numeros: whatsapp_agentes.json na raiz da skill (nome do agente -> numero,
so digitos com DDI 55; vazio = nao envia aquele agente). Tambem fora do repo.

Uso:
    python enviar_whatsapp.py [AAAA-MM-DD] [--dry-run] [--so Nome]
"""
import os, sys, json, base64, subprocess, urllib.parse
from datetime import datetime

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(SCRIPTS)
sys.path.insert(0, SCRIPTS)
import mission_control as mc  # SAIDA, jornadas, dia util, carrega_env

SAIDA = mc.SAIDA
LOG_PATH = os.path.join(SAIDA, 'whatsapp_log.txt')
MAPA_PATH = os.path.join(RAIZ, 'whatsapp_agentes.json')

JORNADAS = getattr(mc, 'JORNADAS', {'Ricardo Schutz': 360})
JORNADA_PADRAO = getattr(mc, 'JORNADA_PADRAO', 510)


def log(msg):
    linha = f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] WHATS: {msg}'
    print(linha, flush=True)
    try:
        os.makedirs(SAIDA, exist_ok=True)
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(linha + '\n')
    except OSError:
        pass


def cfg():
    mc.carrega_env()
    return {
        'ssh': os.environ.get('EVOLUTION_SSH', 'root@2.25.71.207'),
        'base': os.environ.get('EVOLUTION_BASE', 'http://127.0.0.1:36721'),
        'key': os.environ.get('EVOLUTION_KEY', ''),
        'instance': os.environ.get('EVOLUTION_INSTANCE', 'Whatsapp lector'),
        'group': os.environ.get('EVOLUTION_GROUP', '120363041106999402@g.us'),
        'container': os.environ.get('EVOLUTION_CONTAINER', 'evolution-api-gi8t-api-1'),
        'ligado': os.environ.get('ENVIAR_WHATSAPP', '').strip() in ('1', 'true', 'True', 'sim'),
    }


def carrega_mapa():
    if not os.path.exists(MAPA_PATH):
        return {}
    try:
        d = json.load(open(MAPA_PATH, encoding='utf-8'))
        return {k: ''.join(ch for ch in str(v) if ch.isdigit())
                for k, v in d.items() if not k.startswith('_')}
    except (OSError, ValueError):
        return {}


def _ssh(c, comando_remoto, entrada=None, timeout=90):
    """Roda um comando no servidor via SSH; entrada opcional vai pelo stdin."""
    cmd = ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'BatchMode=yes',
           '-o', 'ConnectTimeout=15', c['ssh'], comando_remoto]
    return subprocess.run(cmd, input=entrada, capture_output=True, timeout=timeout)


def garante_docker(c):
    """Sobe o container da Evolution (idempotente) e confere o health da API."""
    try:
        _ssh(c, f'docker start {c["container"]} >/dev/null 2>&1 || true', timeout=45)
    except Exception as e:
        log(f'aviso: nao consegui rodar docker start ({e})')
    try:
        r = _ssh(c, f"curl -s -o /dev/null -w '%{{http_code}}' {c['base']}/ "
                    f"-H 'apikey: {c['key']}'", timeout=30)
        code = (r.stdout or b'').decode(errors='replace').strip()
        if code == '200':
            log(f'Evolution OK (container {c["container"]}, API 200)')
            return True
        log(f'Evolution respondeu HTTP {code or "?"} — segue tentando enviar mesmo assim')
        return False
    except Exception as e:
        log(f'aviso: health-check falhou ({e})')
        return False


def envia_media(c, png_path, caption, mencionados, dry_run=False):
    """Envia um PNG ao grupo mencionando os numeros em `mencionados` (lista).

    Retorna (ok, detalhe)."""
    if isinstance(mencionados, str):
        mencionados = [mencionados]
    mencionados = [n for n in (mencionados or []) if n]
    with open(png_path, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode()
    payload = {
        'number': c['group'],
        'mediatype': 'image', 'mimetype': 'image/png',
        'fileName': os.path.basename(png_path),
        'caption': caption,
        'media': b64,
    }
    if mencionados:
        payload['mentioned'] = [f'{n}@s.whatsapp.net' for n in mencionados]

    if dry_run:
        prev = dict(payload); prev['media'] = f'<base64 {len(b64)} bytes>'
        log('DRY-RUN payload: ' + json.dumps(prev, ensure_ascii=False))
        return True, 'dry-run'

    rota = f"{c['base']}/message/sendMedia/{urllib.parse.quote(c['instance'])}"
    remoto = (f"curl -s -o /tmp/evoresp -w '%{{http_code}}' -X POST '{rota}' "
              f"-H 'apikey: {c['key']}' -H 'Content-Type: application/json' -d @- "
              f"; echo ' '; cat /tmp/evoresp")
    r = _ssh(c, remoto, entrada=json.dumps(payload).encode(), timeout=120)
    saida = (r.stdout or b'').decode(errors='replace')
    code = saida.strip().split()[0] if saida.strip() else '?'
    ok = code in ('200', '201')
    return ok, saida.strip()[:300]


def pct_agente(nome, minutos):
    jornada = JORNADAS.get(nome, JORNADA_PADRAO)
    return round(minutos / jornada * 100, 2) if jornada else 0.0


def main():
    args = [a for a in sys.argv[1:]]
    dry = '--dry-run' in args
    args = [a for a in args if a != '--dry-run']
    so = None
    if '--so' in args:
        i = args.index('--so'); so = args[i + 1] if i + 1 < len(args) else None
        args = args[:i] + args[i + 2:]
    data_str = args[0] if args else mc.dia_util_anterior().isoformat()
    dd_mm = '/'.join(reversed(data_str.split('-')))[:5]

    c = cfg()
    if not c['ligado'] and not dry:
        log('ENVIAR_WHATSAPP desligado — nada a enviar. (use --dry-run para testar o payload)')
        return 0
    if not c['key'] and not dry:
        log('EVOLUTION_KEY nao definido no .env — abortando envio.')
        return 1

    try:
        resumo = json.load(open(os.path.join(SAIDA, f'resumo_{data_str}.json'), encoding='utf-8'))
    except (OSError, ValueError) as e:
        log(f'sem resumo_{data_str}.json ({e}) — rode a missao antes.')
        return 1

    mapa = carrega_mapa()
    agentes = resumo.get('agentes') or {}
    esperados = resumo.get('agentes_esperados') or list(agentes.keys())

    if not dry:
        garante_docker(c)

    enviados = pulados = falhas = 0
    for nome in esperados:
        if so and so.lower() not in nome.lower():
            continue
        dados = agentes.get(nome)
        png = os.path.join(SAIDA, f'Apontamentos_{nome.replace(" ", "_")}_{data_str}.png')
        if not dados or not os.path.exists(png):
            log(f'{nome}: sem apontamentos/PNG no dia — pulado')
            pulados += 1
            continue
        numero = mapa.get(nome, '')
        if not numero:
            log(f'{nome}: sem numero no whatsapp_agentes.json — envio pulado (configure para marcar)')
            pulados += 1
            continue
        pct = pct_agente(nome, dados.get('min', 0))
        caption = f'@{numero} {pct:.2f}% Relatorio Geral {dd_mm}'
        ok, detalhe = envia_media(c, png, caption, [numero], dry_run=dry)
        if ok:
            enviados += 1
            log(f'{nome}: enviado ({pct:.2f}%) -> grupo')
        else:
            falhas += 1
            log(f'{nome}: FALHA no envio -> {detalhe}')

    # Geral: dashboard da equipe (Equipe_<data>.png) marcando todos os agentes mapeados.
    if not so and '--sem-geral' not in sys.argv:
        png_eq = os.path.join(SAIDA, f'Equipe_{data_str}.png')
        nums = [mapa.get(n, '') for n in esperados if mapa.get(n, '')]
        if os.path.exists(png_eq) and nums:
            try:
                pct_time = mc.metricas_do_resumo(resumo).get('pct')
            except Exception:
                pct_time = None
            mencoes = ' '.join(f'@{n}' for n in nums)
            extra = f' — meta {pct_time:.1f}%' if isinstance(pct_time, (int, float)) else ''
            caption = f'{mencoes} Relatorio Geral da Equipe {dd_mm}{extra}'
            ok, detalhe = envia_media(c, png_eq, caption, nums, dry_run=dry)
            if ok:
                enviados += 1
                log(f'Equipe (geral): enviado marcando {len(nums)} -> grupo')
            else:
                falhas += 1
                log(f'Equipe (geral): FALHA no envio -> {detalhe}')
        elif not os.path.exists(png_eq):
            log(f'Equipe (geral): Equipe_{data_str}.png nao encontrado — pulado')

    log(f'=== resumo envio {data_str}: {enviados} enviados, {pulados} pulados, {falhas} falhas ===')
    return 0 if falhas == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
