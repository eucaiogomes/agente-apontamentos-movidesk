# -*- coding: utf-8 -*-
"""Runner diario dos relatorios Movidesk — pensado para rodar via agendador (cron).

Executa a missao completa do dia util anterior (ou da data passada como argumento):
  1. pipeline_movidesk.py  (coleta API + PNGs + JSONs)
  2. gerar_analise.py      (PDF de 4 paginas)
  3. verificacao dos arquivos gerados
  4. grava o resultado em mission_state.json e reconstroi o mission_control.html

Uso:  python runner_diario.py [AAAA-MM-DD]
Saida com codigo 0 se a missao foi OK; 1 se houve falha (visivel no historico
 do Agendador de Tarefas).
"""
import sys, os, json, subprocess
from datetime import date, timedelta, datetime

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS)
import mission_control as mc  # reaproveita SAIDA, metricas e o build do painel

SAIDA = mc.SAIDA
LOG_PATH = mc.LOG_PATH
ESTADO_PATH = mc.ESTADO_PATH

def log(msg):
    linha = f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {msg}'
    print(linha)
    os.makedirs(SAIDA, exist_ok=True)
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(linha + '\n')

def roda(script, data_str):
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, script), data_str],
                       capture_output=True, text=True, encoding='utf-8',
                       errors='replace', timeout=1800)
    return r.returncode == 0, (r.stdout or ''), (r.stderr or '')

def main():
    data_str = sys.argv[1] if len(sys.argv) > 1 else mc.dia_util_anterior().isoformat()
    inicio = datetime.now().isoformat(timespec='seconds')
    log(f'=== Missao {data_str}: inicio ===')

    steps = {'coleta': False, 'pngs': False, 'pdf': False, 'verificacao': False}
    erro = ''

    ok, out, err = roda('pipeline_movidesk.py', data_str)
    steps['coleta'] = ok
    steps['pngs'] = ok and 'OK PNG' in out
    if not ok:
        erro = (err.strip().splitlines() or ['pipeline falhou'])[-1]
        log(f'FALHA no pipeline: {erro}')
    else:
        for linha in out.strip().splitlines():
            if linha.startswith(('API:', 'AVISO:', 'Resumo')):
                log(linha)

    if ok:
        ok_pdf, out2, err2 = roda('gerar_analise.py', data_str)
        steps['pdf'] = ok_pdf and os.path.exists(os.path.join(SAIDA, f'Analise_Operacional_{data_str}.pdf'))
        if not steps['pdf']:
            erro = (err2.strip().splitlines() or ['gerar_analise falhou'])[-1]
            log(f'FALHA no PDF: {erro}')

    met = {}
    if steps['coleta']:
        try:
            resumo = json.load(open(os.path.join(SAIDA, f'resumo_{data_str}.json'), encoding='utf-8'))
            met = mc.metricas_do_resumo(resumo)
            esperados = resumo.get('agentes_esperados') or mc.AGENTES_PADRAO
            presentes = [n for n in esperados if n not in met['ausentes']]
            faltando = [f'Apontamentos_{n.replace(" ", "_")}_{data_str}.png' for n in presentes
                        if not os.path.exists(os.path.join(SAIDA, f'Apontamentos_{n.replace(" ", "_")}_{data_str}.png'))]
            for arq in (f'Equipe_{data_str}.png', f'dados_{data_str}.json'):
                if not os.path.exists(os.path.join(SAIDA, arq)):
                    faltando.append(arq)
            steps['verificacao'] = steps['pdf'] and not faltando
            if faltando:
                erro = erro or ('arquivos faltando: ' + ', '.join(faltando))
                log('FALHA na verificacao: ' + ', '.join(faltando))
        except Exception as e:
            erro = erro or f'verificacao: {e}'
            log(f'FALHA na verificacao: {e}')

    status = 'ok' if all(steps.values()) else 'falha'
    estado = mc.carrega_estado()
    estado['runs'][data_str] = {
        'status': status, 'steps': steps,
        'inicio': inicio, 'fim': datetime.now().isoformat(timespec='seconds'),
        'total_min': met.get('total_min'), 'pct': met.get('pct'),
        'tickets': met.get('tickets'), 'ausentes': met.get('ausentes', []),
        'erro': erro,
    }
    estado['atualizado'] = datetime.now().isoformat(timespec='seconds')
    with open(ESTADO_PATH, 'w', encoding='utf-8') as f:
        json.dump(estado, f, ensure_ascii=False, indent=1)

    painel = mc.build()
    resumo_txt = (f'{mc.fmt(met["total_min"])} | meta {met["pct"]}% | {met["tickets"]} tickets | '
                  f'ausentes: {", ".join(met["ausentes"]) or "nenhum"}') if met else 'sem metricas'
    log(f'=== Missao {data_str}: {status.upper()} ({resumo_txt}) | painel: {painel} ===')
    sys.exit(0 if status == 'ok' else 1)

if __name__ == '__main__':
    main()
