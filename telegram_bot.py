import threading
import time
import requests
from datetime import datetime, timedelta
import database as db

_BASE_URL = 'http://127.0.0.1:5632'
_EXCHANGES = [
    ('Hyperliquid', '/api/hl/all-positions'),
    ('Pacifica',    '/api/pacifica/all-positions'),
    ('Nado',        '/api/nado/all-positions'),
    ('Extended',    '/api/extended/all-positions'),
    ('Ethereal',    '/api/ethereal/all-positions'),
]


# --- Telegram API helpers ---

def send_message(token: str, chat_id: str, text: str) -> bool:
    try:
        resp = requests.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            json={'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'},
            timeout=10,
        )
        return resp.ok
    except Exception:
        return False


def _get_updates(token: str, offset: int, timeout: int = 30) -> list:
    try:
        resp = requests.get(
            f'https://api.telegram.org/bot{token}/getUpdates',
            params={'offset': offset, 'timeout': timeout},
            timeout=timeout + 5,
        )
        if resp.ok:
            return resp.json().get('result', [])
    except Exception:
        pass
    return []


# --- Position data fetching ---

def _fetch_all_positions() -> list[dict]:
    positions = []
    for exchange, endpoint in _EXCHANGES:
        try:
            resp = requests.get(f'{_BASE_URL}{endpoint}', timeout=15)
            data = resp.json()
            for acc in data.get('accounts', []):
                label = acc.get('label', '')
                address = acc.get('address') or acc.get('api_key', '')
                for pos in acc.get('positions', []):
                    positions.append({
                        **pos,
                        'exchange': exchange,
                        'label': label,
                        'address': address,
                    })
        except Exception:
            pass
    return positions


def _position_key(pos: dict) -> str:
    sym = pos.get('coin') or pos.get('market') or pos.get('symbol', '?')
    return f"{pos.get('exchange')}:{pos.get('address')}:{sym}"


# --- Formatting helpers ---

def _get_symbol(pos: dict) -> str:
    return pos.get('coin') or pos.get('market') or pos.get('symbol', '?')


def _get_direction(pos: dict) -> str:
    d = pos.get('direction') or pos.get('side', '')
    return d.capitalize() if d else '?'


def _get_dist_liq(pos: dict) -> float | None:
    dist = pos.get('dist_liq')
    if dist is not None:
        return float(dist)
    liq = pos.get('liq_price')
    mark = pos.get('current_price') or pos.get('mark_price')
    if liq and mark and float(mark) > 0:
        liq, mark = float(liq), float(mark)
        d = _get_direction(pos).lower()
        return (mark - liq) / mark * 100 if d == 'long' else (liq - mark) / mark * 100
    return None


def _get_pnl(pos: dict) -> float:
    return float(pos.get('unrealized_pnl') or pos.get('unrealised_pnl') or 0)


def _get_mark(pos: dict):
    return pos.get('current_price') or pos.get('mark_price')


def _fmt_price(p) -> str:
    if p is None:
        return 'N/A'
    p = float(p)
    return f'${p:,.0f}' if p >= 1000 else f'${p:.4f}'


def _fmt_pnl(p: float) -> str:
    sign = '+' if p >= 0 else ''
    return f'{sign}${p:,.2f}'


def _dist_emoji(dist: float | None) -> str:
    if dist is None:
        return ''
    if dist < 5:
        return ' 🔴'
    if dist < 10:
        return ' 🟠'
    if dist < 20:
        return ' 🟡'
    return ''


# --- Message formatters ---

def format_liq_alert(pos: dict) -> str:
    sym = _get_symbol(pos)
    direction = _get_direction(pos)
    dist = _get_dist_liq(pos)
    liq = pos.get('liq_price')
    mark = _get_mark(pos)
    pnl = _get_pnl(pos)
    dist_str = f'{dist:.1f}%' if dist is not None else 'N/A'
    return (
        f'🚨 <b>LIQ ALERT</b>\n'
        f'{sym} {direction} | {pos.get("exchange")}: {pos.get("label")}\n'
        f'Dist: {dist_str} | Liq: {_fmt_price(liq)} | Mark: {_fmt_price(mark)}\n'
        f'PnL: {_fmt_pnl(pnl)}'
    )


def format_full_report(positions: list[dict]) -> str:
    if not positions:
        return '📊 <b>FarmTrack Report</b>\n\nНет открытых позиций.'

    _EMOJI = {'Hyperliquid': '🔵', 'Pacifica': '🟣', 'Nado': '🟢', 'Extended': '⚪', 'Ethereal': '🔷'}
    now = datetime.utcnow().strftime('%H:%M UTC')
    lines = [f'📊 <b>FarmTrack Report</b> | {now}\n']
    total_pnl = 0.0

    by_account: dict[tuple, list] = {}
    for pos in positions:
        key = (pos.get('exchange', ''), pos.get('label', ''))
        by_account.setdefault(key, []).append(pos)

    for (exchange, label), acct_pos in by_account.items():
        emoji = _EMOJI.get(exchange, '⚫')
        lines.append(f'\n{emoji} <b>{exchange}</b> — {label}')
        for pos in acct_pos:
            sym = _get_symbol(pos)
            direction = _get_direction(pos)
            lev = pos.get('leverage')
            lev_str = f' ×{lev:.0f}' if lev else ''
            pnl = _get_pnl(pos)
            total_pnl += pnl
            dist = _get_dist_liq(pos)
            dist_str = f'{dist:.1f}%{_dist_emoji(dist)}' if dist is not None else 'N/A'
            liq = pos.get('liq_price')

            line = f'  {sym} {direction}{lev_str}'
            entry = pos.get('entry_price')
            mark = _get_mark(pos)
            if entry:
                line += f' | Entry: {_fmt_price(entry)}'
            if mark:
                line += f' | Mark: {_fmt_price(mark)}'
            line += f'\n  PnL: {_fmt_pnl(pnl)}'
            if liq:
                line += f' | Liq: {_fmt_price(liq)} | Dist: {dist_str}'
            lines.append(line)

    lines.append(f'\n💰 <b>Total PnL: {_fmt_pnl(total_pnl)}</b>')
    return '\n'.join(lines)


def format_danger_report(positions: list[dict], threshold: float) -> str:
    dangerous = [p for p in positions if (_get_dist_liq(p) is not None and _get_dist_liq(p) < threshold)]
    if not dangerous:
        return f'✅ Нет позиций с дистанцией до ликвидации < {threshold:.0f}%'
    return format_full_report(dangerous)


# --- TelegramMonitor ---

class TelegramMonitor:
    def __init__(self):
        self._cfg: dict = {}
        self._stop = threading.Event()
        self._monitor_thread: threading.Thread | None = None
        self._polling_thread: threading.Thread | None = None
        self._alert_cooldown: dict[str, datetime] = {}  # key → last alert time

    def update_config(self, cfg: dict) -> None:
        self._cfg = dict(cfg)

    def start(self) -> None:
        self._stop.clear()
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True, name='tg-monitor')
        self._polling_thread = threading.Thread(target=self._polling_loop, daemon=True, name='tg-polling')
        self._monitor_thread.start()
        self._polling_thread.start()

    def stop(self) -> None:
        self._stop.set()

    def is_running(self) -> bool:
        return (
            self._monitor_thread is not None and self._monitor_thread.is_alive()
        )

    # --- Monitor loop ---

    def _monitor_loop(self) -> None:
        last_check = 0.0
        last_report = 0.0

        while not self._stop.is_set():
            cfg = self._cfg
            if not cfg.get('enabled') or not cfg.get('bot_token') or not cfg.get('chat_id'):
                self._stop.wait(30)
                continue

            now = time.time()
            check_interval = cfg.get('check_interval_minutes', 5) * 60
            report_interval = cfg.get('report_interval_minutes', 60) * 60

            if now - last_check >= check_interval:
                last_check = now
                try:
                    positions = _fetch_all_positions()
                    if cfg.get('alerts_enabled', 1):
                        self._check_and_alert(positions, cfg)
                    if cfg.get('reports_enabled', 1) and (now - last_report >= report_interval):
                        last_report = now
                        self._send_full_report(positions, cfg)
                except Exception:
                    pass

            self._stop.wait(30)

    def _check_and_alert(self, positions: list[dict], cfg: dict) -> None:
        threshold = cfg.get('alert_threshold_pct', 10.0)
        cooldown_minutes = cfg.get('alert_cooldown_minutes', 60)
        token = cfg['bot_token']
        chat_id = cfg['chat_id']

        for pos in positions:
            dist = _get_dist_liq(pos)
            if dist is None or dist >= threshold:
                continue
            key = _position_key(pos)
            last = self._alert_cooldown.get(key)
            if last and (datetime.now() - last) < timedelta(minutes=cooldown_minutes):
                continue
            self._alert_cooldown[key] = datetime.now()
            send_message(token, chat_id, format_liq_alert(pos))

    def _send_full_report(self, positions: list[dict], cfg: dict) -> None:
        send_message(cfg['bot_token'], cfg['chat_id'], format_full_report(positions))

    # --- Telegram long-polling loop ---

    def _polling_loop(self) -> None:
        offset = 0
        while not self._stop.is_set():
            cfg = self._cfg
            if not cfg.get('enabled') or not cfg.get('bot_token') or not cfg.get('chat_id'):
                self._stop.wait(10)
                continue

            updates = _get_updates(cfg['bot_token'], offset, timeout=20)
            for update in updates:
                offset = update['update_id'] + 1
                self._handle_update(update, cfg)

    def _handle_update(self, update: dict, cfg: dict) -> None:
        msg = update.get('message') or update.get('edited_message')
        if not msg:
            return
        text = (msg.get('text') or '').strip().split()[0].lower()
        token = cfg['bot_token']
        chat_id = cfg['chat_id']

        if text == '/report':
            try:
                positions = _fetch_all_positions()
                send_message(token, chat_id, format_full_report(positions))
            except Exception as e:
                send_message(token, chat_id, f'❌ Ошибка: {e}')
        elif text == '/danger':
            try:
                positions = _fetch_all_positions()
                threshold = cfg.get('alert_threshold_pct', 10.0)
                send_message(token, chat_id, format_danger_report(positions, threshold))
            except Exception as e:
                send_message(token, chat_id, f'❌ Ошибка: {e}')
