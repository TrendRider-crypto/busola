#!/usr/bin/env python3
"""Zbieracz publicznych danych Binance Futures (funding, cena mark, open interest).

Bez kluczy API i bez konta: tylko publiczne endpointy. To jest opis rynku, nie sygnał.
Zapisuje do katalogu --out:
  oi/RRRR-MM-DD.csv   dopisywane wiersze: ts_utc,symbol,open_interest,oi_usd,mark_price,funding_rate,vol24h_usd
  latest.json         ostatni odczyt wszystkich coinów (łatwy do pobrania przez Nawigator)
  status.json         czy Binance odpowiedział z tego miejsca (kody HTTP, błędy)
"""
import argparse, csv, datetime as dt, json, os, re, sys, time, urllib.error, urllib.request

BASE = os.environ.get('BINANCE_BASE', 'https://fapi.binance.com')
TOPN = int(os.environ.get('TOPN', '30'))
STABLE = re.compile(r'^(USDC|FDUSD|TUSD|BUSD|USDP|DAI|EUR|AEUR)USDT$')


def get(path):
    """Zwraca (kod_http, dane_json_lub_tekst_błędu). Nigdy nie rzuca wyjątku."""
    req = urllib.request.Request(BASE + path, headers={'User-Agent': 'busola-collector/1'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode('utf-8', 'replace')[:200]
        except Exception:
            body = ''
        return e.code, body
    except Exception as e:  # brak sieci, timeout, DNS
        return 0, f'{type(e).__name__}: {e}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--coins', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'coins.json'))
    a = ap.parse_args()
    os.makedirs(os.path.join(a.out, 'oi'), exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)
    ts = now.strftime('%Y-%m-%dT%H:%M:%SZ')
    status = {'ts': ts, 'base': BASE, 'ok': False, 'checks': {}, 'errors': [], 'github_actions': bool(os.environ.get('GITHUB_ACTIONS')),
              'runner_os': os.environ.get('RUNNER_OS', ''), 'coins_requested': 0, 'coins_ok': 0}

    def finish():
        with open(os.path.join(a.out, 'status.json'), 'w', encoding='utf-8') as f:
            json.dump(status, f, ensure_ascii=False, indent=1)
        print(json.dumps({k: status[k] for k in ('ts', 'ok', 'checks', 'coins_requested', 'coins_ok')}, ensure_ascii=False))
        for e in status['errors'][:5]:
            print('  błąd:', e)

    code, tick = get('/fapi/v1/ticker/24hr')
    status['checks']['ticker24h'] = code
    if code != 200 or not isinstance(tick, list):
        status['errors'].append(f'ticker24h: HTTP {code} {tick if isinstance(tick, str) else ""}'.strip())
        return finish()

    extra = []
    try:
        with open(a.coins, encoding='utf-8') as f:
            extra = [x for x in json.load(f).get('extra', []) if re.fullmatch(r'[A-Z0-9]{2,24}', x)]
    except Exception:
        pass
    vol = {x['symbol']: float(x['quoteVolume']) for x in tick if x['symbol'].endswith('USDT') and '_' not in x['symbol'] and not STABLE.match(x['symbol'])}
    top = [s for s, _ in sorted(vol.items(), key=lambda kv: -kv[1])[:TOPN]]
    coins = top + [s for s in extra if s in vol and s not in top]
    status['coins_requested'] = len(coins)

    code, prem = get('/fapi/v1/premiumIndex')
    status['checks']['premiumIndex'] = code
    if code != 200 or not isinstance(prem, list):
        status['errors'].append(f'premiumIndex: HTTP {code} {prem if isinstance(prem, str) else ""}'.strip())
        return finish()
    pm = {x['symbol']: x for x in prem}

    rows, ok = [], 0
    for i, sym in enumerate(coins):
        code, oi = get(f'/fapi/v1/openInterest?symbol={sym}')
        if i == 0:
            status['checks']['openInterest'] = code
        if code != 200 or not isinstance(oi, dict):
            status['errors'].append(f'{sym}: HTTP {code} {oi if isinstance(oi, str) else ""}'.strip())
            continue
        p = pm.get(sym, {})
        mark = float(p.get('markPrice', 0) or 0)
        q = float(oi['openInterest'])
        rows.append({'ts': ts, 'symbol': sym, 'open_interest': q, 'oi_usd': round(q * mark, 2), 'mark_price': mark,
                     'funding_rate': float(p.get('lastFundingRate', 0) or 0), 'vol24h_usd': round(vol.get(sym, 0), 0)})
        ok += 1
        time.sleep(0.08)
    status['coins_ok'] = ok
    status['ok'] = ok > 0

    if rows:
        path = os.path.join(a.out, 'oi', now.strftime('%Y-%m-%d') + '.csv')
        new = not os.path.exists(path)
        cols = ['ts', 'symbol', 'open_interest', 'oi_usd', 'mark_price', 'funding_rate', 'vol24h_usd']
        with open(path, 'a', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=cols)
            if new:
                w.writeheader()
            w.writerows(rows)
        with open(os.path.join(a.out, 'latest.json'), 'w', encoding='utf-8') as f:
            json.dump({'ts': ts, 'rows': rows}, f, ensure_ascii=False)
    finish()


if __name__ == '__main__':
    main()
