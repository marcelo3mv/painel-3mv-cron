#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
injetar_agenda.py - Puxa eventos de hoje do Google Calendar do Marcelo
e injeta em dados.json para o Painel Mobile mostrar na seccao roxa.

3 modos de autenticacao (escolha o que tiver mais facil):

  1) iCal URL (mais simples):
     - Vai em https://calendar.google.com -> Settings -> Settings for my calendars
       -> escolhe Marcelo -> "Integrate calendar" -> "Secret address in iCal format"
     - Define env GOOGLE_CALENDAR_ICAL_URL com essa URL

  2) OAuth Refresh Token:
     - Define env GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, GOOGLE_OAUTH_REFRESH_TOKEN
     - Gera no https://developers.google.com/oauthplayground/

Saida:
  dados.json['agenda_hoje'] = [
    {titulo, cliente, inicio_iso, fim_iso, descricao, local},
    ...
  ]

Roda DEPOIS de injetar_crm.py (precisa do CRM pra fazer match cliente)
e ANTES de gerar_painel.py.
"""
import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.parse import urlencode

HERE = Path(__file__).parent
DADOS_JSON = HERE / 'dados.json'


def _br_today_range():
    tz_sp = timezone(timedelta(hours=-3))
    agora = datetime.now(tz_sp)
    inicio = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    fim = inicio + timedelta(days=1)
    return inicio.astimezone(timezone.utc), fim.astimezone(timezone.utc)


def _ical_unfold(text):
    out = []
    for line in text.splitlines():
        if line.startswith((' ', '\t')) and out:
            out[-1] += line.lstrip()
        else:
            out.append(line)
    return out


def _ical_parse_dt(s):
    s = s.strip()
    m = re.search(r'(\d{8}T\d{6})(Z?)', s)
    if not m:
        return None
    base = m.group(1)
    try:
        dt = datetime.strptime(base, '%Y%m%dT%H%M%S')
        return dt.replace(tzinfo=timezone.utc) if m.group(2) == 'Z' else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def fetch_via_ical(url, ini_utc, fim_utc):
    print('  Modo: iCal URL')
    try:
        with urlopen(Request(url, headers={'User-Agent': '3MV-Painel-Mobile/1.0'}), timeout=20) as r:
            text = r.read().decode('utf-8', errors='replace')
    except Exception as e:
        print(f'  ERRO ao baixar iCal: {e}', file=sys.stderr)
        return []
    eventos = []
    atual = None
    for line in _ical_unfold(text):
        if line == 'BEGIN:VEVENT':
            atual = {}
        elif line == 'END:VEVENT':
            if atual is not None and 'inicio' in atual:
                if ini_utc <= atual['inicio'] < fim_utc:
                    eventos.append(atual)
            atual = None
        elif atual is not None:
            if line.startswith('SUMMARY'):
                atual['titulo'] = line.split(':', 1)[1] if ':' in line else ''
            elif line.startswith('DTSTART'):
                v = line.split(':', 1)[1] if ':' in line else ''
                atual['inicio'] = _ical_parse_dt(v)
            elif line.startswith('DTEND'):
                v = line.split(':', 1)[1] if ':' in line else ''
                atual['fim'] = _ical_parse_dt(v)
            elif line.startswith('DESCRIPTION'):
                atual['descricao'] = line.split(':', 1)[1] if ':' in line else ''
            elif line.startswith('LOCATION'):
                atual['local'] = line.split(':', 1)[1] if ':' in line else ''
    return eventos


def fetch_via_oauth(client_id, client_secret, refresh_token, ini_utc, fim_utc):
    print('  Modo: OAuth refresh token')
    body = urlencode({
        'client_id': client_id, 'client_secret': client_secret,
        'refresh_token': refresh_token, 'grant_type': 'refresh_token',
    }).encode('utf-8')
    try:
        with urlopen(Request('https://oauth2.googleapis.com/token', data=body), timeout=20) as r:
            tok = json.loads(r.read())
        access_token = tok['access_token']
    except Exception as e:
        print(f'  ERRO access_token: {e}', file=sys.stderr)
        return []
    params = urlencode({
        'timeMin': ini_utc.isoformat(), 'timeMax': fim_utc.isoformat(),
        'singleEvents': 'true', 'orderBy': 'startTime', 'maxResults': '50',
    })
    url = f'https://www.googleapis.com/calendar/v3/calendars/primary/events?{params}'
    try:
        with urlopen(Request(url, headers={'Authorization': f'Bearer {access_token}'}), timeout=20) as r:
            data = json.loads(r.read())
    except Exception as e:
        print(f'  ERRO Calendar API: {e}', file=sys.stderr)
        return []
    eventos = []
    for ev in data.get('items', []):
        ini_str = (ev.get('start') or {}).get('dateTime') or (ev.get('start') or {}).get('date')
        fim_str = (ev.get('end') or {}).get('dateTime') or (ev.get('end') or {}).get('date')
        if not ini_str:
            continue
        try:
            ini = datetime.fromisoformat(ini_str.replace('Z', '+00:00'))
            fim = datetime.fromisoformat(fim_str.replace('Z', '+00:00')) if fim_str else None
        except Exception:
            continue
        eventos.append({
            'titulo': ev.get('summary', ''), 'descricao': ev.get('description', ''),
            'local': ev.get('location', ''), 'inicio': ini, 'fim': fim,
        })
    return eventos


def match_cliente(titulo, descricao, lista_clientes):
    s = ((titulo or '') + ' ' + (descricao or '')).upper()
    for nome in lista_clientes:
        if nome.upper() in s:
            return nome
    return None


def main():
    print('-> Injetar Agenda Google Calendar')
    ical_url = os.environ.get('GOOGLE_CALENDAR_ICAL_URL', '').strip()
    oauth_cid = os.environ.get('GOOGLE_OAUTH_CLIENT_ID', '').strip()
    oauth_cs = os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET', '').strip()
    oauth_rt = os.environ.get('GOOGLE_OAUTH_REFRESH_TOKEN', '').strip()
    ini_utc, fim_utc = _br_today_range()
    print(f'  Janela: {ini_utc.isoformat()} -> {fim_utc.isoformat()}')

    eventos = []
    if ical_url:
        eventos = fetch_via_ical(ical_url, ini_utc, fim_utc)
    elif oauth_cid and oauth_cs and oauth_rt:
        eventos = fetch_via_oauth(oauth_cid, oauth_cs, oauth_rt, ini_utc, fim_utc)
    else:
        print('  AVISO: nenhuma credencial configurada')

    print(f'  Eventos encontrados: {len(eventos)}')

    if not DADOS_JSON.exists():
        print('  AVISO: dados.json nao existe')
        return 0

    d = json.loads(DADOS_JSON.read_text(encoding='utf-8'))
    clientes = list(((d.get('crm') or {}).get('clientes') or {}).keys())

    agenda_hoje = []
    for ev in eventos:
        cli = match_cliente(ev.get('titulo'), ev.get('descricao'), clientes)
        agenda_hoje.append({
            'titulo': ev.get('titulo') or '', 'cliente': cli or '',
            'descricao': ev.get('descricao') or '', 'local': ev.get('local') or '',
            'inicio_iso': ev['inicio'].isoformat() if ev.get('inicio') else None,
            'fim_iso': ev['fim'].isoformat() if ev.get('fim') else None,
        })

    d['agenda_hoje'] = agenda_hoje
    d['agenda_atualizada_em'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    DADOS_JSON.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
    print(f'  OK: {len(agenda_hoje)} evento(s) injetado(s)')
    return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
