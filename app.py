import os
import io
import time
import requests
from datetime import datetime
from flask import Flask, jsonify, request, render_template, send_file
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import database as db

_price_cache: dict = {}
_price_cache_ts: float = 0
_PRICE_TTL = 30  # seconds

app = Flask(__name__)

with app.app_context():
    db.init()


@app.route('/profiles')
def profiles_page():
    return render_template('profiles.html')


@app.route('/api/profiles', methods=['GET'])
def get_profiles():
    return jsonify(db.list_profiles())


@app.route('/api/profiles/select', methods=['POST'])
def select_profile():
    name = (request.json.get('name') or '').strip()
    if not name or '/' in name or '\\' in name or '..' in name:
        return jsonify({'error': 'Недопустимое имя'}), 400
    db.set_profile(name)
    return jsonify({'ok': True})


@app.route('/api/profiles/current', methods=['GET'])
def current_profile():
    import os
    name = os.path.splitext(os.path.basename(db.DB_PATH))[0]
    return jsonify({'name': name})


@app.route('/api/profiles/rename', methods=['POST'])
def rename_profile():
    import os
    old_name = (request.json.get('old_name') or '').strip()
    new_name = (request.json.get('new_name') or '').strip()
    if not old_name or not new_name:
        return jsonify({'error': 'Укажите оба имени'}), 400
    for n in (old_name, new_name):
        if '/' in n or '\\' in n or '..' in n:
            return jsonify({'error': 'Недопустимые символы'}), 400
    old_path = os.path.join(db._DATA_DIR, f'{old_name}.db')
    new_path = os.path.join(db._DATA_DIR, f'{new_name}.db')
    if not os.path.exists(old_path):
        return jsonify({'error': 'Профиль не найден'}), 404
    if os.path.exists(new_path):
        return jsonify({'error': 'Такое имя уже занято'}), 400
    os.rename(old_path, new_path)
    if db.DB_PATH == old_path:
        db.DB_PATH = new_path
    return jsonify({'ok': True})


@app.route('/api/profiles/delete', methods=['POST'])
def delete_profile():
    import os
    name = (request.json.get('name') or '').strip()
    if not name or '/' in name or '\\' in name or '..' in name:
        return jsonify({'error': 'Invalid name'}), 400
    path = os.path.join(db._DATA_DIR, f'{name}.db')
    if not os.path.exists(path):
        return jsonify({'error': 'Profile not found'}), 404
    if db.DB_PATH == path:
        return jsonify({'error': 'Cannot delete the active profile'}), 400
    os.remove(path)
    return jsonify({'ok': True})


@app.route('/')
def index():
    return render_template('index.html')


# --- Stats ---

@app.route('/api/stats')
def stats():
    s = db.get_stats()
    s['pnl'] = round(s['total_earned'] - s['total_spent'], 2)
    return jsonify(s)


# --- Protocols ---

@app.route('/api/protocols', methods=['GET'])
def get_protocols():
    protocols = db.get_protocols()
    for p in protocols:
        deposit = p.get('total_deposit') or 0
        balance = p.get('total_balance') or 0
        wp_earned = p.get('total_wp_earned') or 0
        has_wallet_data = deposit > 0 or balance > 0 or wp_earned > 0
        if has_wallet_data:
            total_spent = round(max(0, deposit - balance - wp_earned), 2)
            p['total_spent'] = total_spent
            p['pnl'] = round(wp_earned + balance - deposit, 2)
        else:
            manual_spent = p.get('spent') or 0
            p['total_spent'] = round(manual_spent, 2)
            p['pnl'] = round((p.get('earned') or 0) - manual_spent, 2)
    return jsonify(protocols)


@app.route('/api/protocols', methods=['POST'])
def add_protocol():
    data = request.json
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Название обязательно'}), 400
    try:
        db.add_protocol(
            name=name,
            spent=float(data.get('spent') or 0),
            earned=float(data.get('earned') or 0),
            status=data.get('status', 'фармлю'),
            note=data.get('note', ''),
            color=data.get('color', '#10b981')
        )
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/protocols/<int:pid>', methods=['PATCH'])
def patch_protocol(pid):
    data = request.json
    protocols = {p['id']: p for p in db.get_protocols()}
    p = protocols.get(pid)
    if not p:
        return jsonify({'error': 'Not found'}), 404
    db.update_protocol(
        pid=pid,
        spent=float(data.get('spent', p['spent']) or 0),
        earned=float(data.get('earned', p['earned']) or 0),
        status=data.get('status', p['status']),
        note=data.get('note', p['note'] or ''),
        color=data.get('color', p.get('color', '#10b981')),
        points=float(data.get('points', p.get('points') or 0) or 0),
        point_price=float(data.get('point_price', p.get('point_price') or 0) or 0),
    )
    pnl = round(float(data.get('earned', p['earned']) or 0) - float(data.get('spent', p['spent']) or 0), 2)
    return jsonify({'ok': True, 'pnl': pnl})


@app.route('/api/protocols/<int:pid>', methods=['PUT'])
def update_protocol(pid):
    data = request.json
    db.update_protocol(
        pid=pid,
        spent=float(data.get('spent') or 0),
        earned=float(data.get('earned') or 0),
        status=data.get('status', 'фармлю'),
        note=data.get('note', ''),
        color=data.get('color', '#10b981'),
        points=float(data.get('points') or 0),
        point_price=float(data.get('point_price') or 0),
    )
    return jsonify({'ok': True})


@app.route('/api/protocols/<int:pid>', methods=['DELETE'])
def delete_protocol(pid):
    db.delete_protocol(pid)
    return jsonify({'ok': True})


@app.route('/api/protocols/<path:name>/wallets', methods=['GET'])
def get_protocol_wallets_detail(name):
    return jsonify(db.get_protocol_wallets_detail(name))


@app.route('/api/protocols/<path:name>/import', methods=['POST'])
def import_protocol_wallets(name):
    rows = request.json.get('rows', [])
    add_points = bool(request.json.get('add_points', False))
    add_deposit = bool(request.json.get('add_deposit', False))
    result = db.import_protocol_wallet_data(name, rows, add_points=add_points, add_deposit=add_deposit)
    return jsonify({'ok': True, **result})


@app.route('/api/wallet-protocols', methods=['PATCH'])
def update_wallet_protocol():
    data = request.json
    db.update_wallet_protocol(
        wallet_id=int(data['wallet_id']),
        protocol=data['protocol'],
        deposit=float(data['deposit']) if 'deposit' in data else None,
        wallet_balance=float(data['wallet_balance']) if 'wallet_balance' in data else None,
        wp_points=float(data['wp_points']) if 'wp_points' in data else None,
        wp_earned=float(data['wp_earned']) if 'wp_earned' in data else None,
    )
    return jsonify({'ok': True})


# --- Wallets ---

@app.route('/api/wallets', methods=['GET'])
def get_wallets():
    protocol = request.args.get('protocol')
    unassigned = request.args.get('unassigned') == '1'
    chain = request.args.get('chain') or None
    return jsonify(db.get_wallets(protocol=protocol or None, unassigned_only=unassigned, chain=chain))


@app.route('/api/wallets', methods=['POST'])
def add_wallet():
    data = request.json
    protocol = (data.get('protocol') or '').strip()
    address = (data.get('address') or '').strip()
    if not protocol or not address:
        return jsonify({'error': 'Протокол и адрес обязательны'}), 400
    db.add_wallet(protocol, address, data.get('label', ''))
    return jsonify({'ok': True})



@app.route('/api/wallets/bulk', methods=['POST'])
def bulk_add_wallets():
    data = request.json
    raw = data.get('addresses', '')
    addresses = [a.strip() for a in (raw if isinstance(raw, list) else raw.split('\n')) if a.strip()]
    if not addresses:
        return jsonify({'error': 'Нет адресов'}), 400
    protocols = [p for p in (data.get('protocols') or []) if p]
    count = db.bulk_add_wallets(addresses, protocols=protocols or None, label=data.get('label', ''))
    return jsonify({'ok': True, 'count': count})


@app.route('/api/wallets/assign', methods=['PUT'])
def assign_wallets():
    data = request.json
    ids = data.get('ids', [])
    if not ids:
        return jsonify({'error': 'Нет кошельков'}), 400

    if 'protocols' in data:
        # Replace all protocols for each wallet (single-wallet assign modal)
        for wid in ids:
            db.set_wallet_protocols(wid, data['protocols'])
    else:
        # Add one protocol to multiple wallets (bulk bar action)
        db.add_protocol_to_wallets(ids, data.get('protocol'))

    return jsonify({'ok': True})


@app.route('/api/wallets/<int:wid>', methods=['PATCH'])
def update_wallet(wid):
    data = request.json or {}
    if 'label' in data:
        db.update_wallet_label(wid, data.get('label', ''))
    if 'proxy' in data:
        db.update_wallet_proxy(wid, data.get('proxy', ''))
    if 'chain' in data:
        import sqlite3 as _sq
        with db._conn() as c:
            c.execute('UPDATE wallets SET chain=? WHERE id=?', (data.get('chain') or None, wid))
    return jsonify({'ok': True})



@app.route('/api/wallets/import-balances', methods=['POST'])
def import_balances():
    import openpyxl, io
    f = request.files.get('file')
    if not f:
        return jsonify({'error': 'Нет файла'}), 400
    wb = openpyxl.load_workbook(io.BytesIO(f.read()), data_only=True)
    rows = []
    for sheet in wb.worksheets:
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if not row or not row[1]:
                continue
            rows.append({
                'address_short': str(row[1]),
                'volume':  row[2],
                'burn':    row[3],
                'points':  row[4],
                'p_price': row[5],
                'balance': row[6],
            })
    matched = db.import_balances(rows)
    return jsonify({'ok': True, 'matched': matched, 'total': len(rows)})


@app.route('/api/wallets/bulk-delete', methods=['POST'])
def bulk_delete_wallets():
    ids = request.json.get('ids', [])
    for wid in ids:
        db.delete_wallet(wid)
    return jsonify({'ok': True, 'count': len(ids)})


@app.route('/api/wallets/<int:wid>', methods=['DELETE'])
def delete_wallet(wid):
    db.delete_wallet(wid)
    return jsonify({'ok': True})


# --- Reminders ---

@app.route('/api/reminders', methods=['GET'])
def get_reminders():
    include_done = request.args.get('include_done') == '1'
    return jsonify(db.get_reminders(include_done=include_done))


@app.route('/api/reminders', methods=['POST'])
def add_reminder():
    data = request.json
    protocol = (data.get('protocol') or '').strip()
    remind_at = (data.get('remind_at') or '').strip()
    if not protocol or not remind_at:
        return jsonify({'error': 'Протокол и дата обязательны'}), 400
    db.add_reminder(protocol, remind_at)
    return jsonify({'ok': True})


@app.route('/api/reminders/<int:rid>', methods=['DELETE'])
def delete_reminder(rid):
    db.delete_reminder(rid)
    return jsonify({'ok': True})


@app.route('/api/reminders/<int:rid>/done', methods=['POST'])
def mark_done(rid):
    db.mark_done(rid)
    return jsonify({'ok': True})


@app.route('/api/due-reminders')
def due_reminders():
    return jsonify(db.get_due_reminders())


# --- Hyperliquid ---

HL_API = 'https://api.hyperliquid.xyz/info'

_mids_cache: dict = {}
_mids_cache_ts: float = 0


def _fetch_hl_account(address, mids):
    state = requests.post(HL_API, json={'type': 'clearinghouseState', 'user': address}, timeout=10).json()
    positions = []
    for ap in state.get('assetPositions', []):
        p = ap['position']
        szi = float(p['szi'])
        if szi == 0:
            continue
        coin = p['coin']
        direction = 'long' if szi > 0 else 'short'
        cur = float(mids[coin]) if coin in mids else None
        liq = float(p['liquidationPx']) if p.get('liquidationPx') else None
        dist_liq = None
        if cur and liq:
            dist_liq = round(((cur - liq) / cur * 100) if direction == 'long' else ((liq - cur) / cur * 100), 2)
        positions.append({
            'coin': coin, 'direction': direction, 'size': abs(szi),
            'entry_price': float(p['entryPx']), 'current_price': cur,
            'liq_price': liq, 'dist_liq': dist_liq,
            'margin_used': float(p['marginUsed']),
            'position_value': float(p['positionValue']),
            'unrealized_pnl': float(p['unrealizedPnl']),
            'leverage': p['leverage']['value'],
            'leverage_type': p['leverage']['type'],
            'roe': round(float(p.get('returnOnEquity', 0)) * 100, 2),
        })
    ms = state.get('marginSummary', {})
    return {
        'positions': positions,
        'summary': {
            'account_value': float(ms.get('accountValue', 0)),
            'total_margin':  float(ms.get('totalMarginUsed', 0)),
            'total_pnl':     float(ms.get('totalUnrealizedPnl', 0)),
            'withdrawable':  float(state.get('withdrawable', 0)),
        }
    }


@app.route('/api/hl/accounts', methods=['GET'])
def get_hl_accounts():
    return jsonify(db.get_hl_accounts())


@app.route('/api/hl/accounts', methods=['POST'])
def add_hl_account():
    data = request.json
    label = (data.get('label') or '').strip()
    address = (data.get('address') or '').strip()
    if not label or not address:
        return jsonify({'error': 'label and address required'}), 400
    db.add_hl_account(label, address)
    return jsonify({'ok': True})


@app.route('/api/hl/accounts/<int:aid>', methods=['DELETE'])
def delete_hl_account(aid):
    db.delete_hl_account(aid)
    return jsonify({'ok': True})


@app.route('/api/hl/all-positions')
def hl_all_positions():
    global _mids_cache, _mids_cache_ts
    accounts = db.get_hl_accounts()
    if not accounts:
        return jsonify({'accounts': [], 'mids_ts': None})
    try:
        now = time.time()
        if not _mids_cache or (now - _mids_cache_ts) > _PRICE_TTL:
            _mids_cache = requests.post(HL_API, json={'type': 'allMids'}, timeout=10).json()
            _mids_cache_ts = now
        mids = _mids_cache

        result = []
        for acc in accounts:
            try:
                data = _fetch_hl_account(acc['address'], mids)
                data['id'] = acc['id']
                data['label'] = acc['label']
                data['address'] = acc['address']
                result.append(data)
            except Exception as e:
                result.append({'id': acc['id'], 'label': acc['label'],
                               'address': acc['address'], 'error': str(e),
                               'positions': [], 'summary': {}})
        return jsonify({'accounts': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 502


# --- Calculator (manual positions) ---

@app.route('/api/positions', methods=['GET'])
def get_positions():
    return jsonify(db.get_positions())


@app.route('/api/positions', methods=['POST'])
def add_position():
    data = request.json
    try:
        gid = data.get('group_id')
        db.add_position(
            symbol=data['symbol'],
            direction=data['direction'],
            collateral=float(data['collateral']),
            leverage=float(data['leverage']),
            entry_price=float(data['entry_price']),
            note=data.get('note', ''),
            group_id=int(gid) if gid else None,
        )
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/positions/<int:pid>', methods=['PATCH'])
def update_position(pid):
    data = request.json
    try:
        gid = data.get('group_id')
        db.update_position(
            pid=pid,
            symbol=data['symbol'],
            direction=data['direction'],
            collateral=float(data['collateral']),
            leverage=float(data['leverage']),
            entry_price=float(data['entry_price']),
            note=data.get('note', ''),
            group_id=int(gid) if gid else None,
        )
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/positions/<int:pid>', methods=['DELETE'])
def delete_position(pid):
    db.delete_position(pid)
    return jsonify({'ok': True})


# --- Position groups ---

@app.route('/api/position-groups', methods=['GET'])
def get_position_groups():
    return jsonify(db.get_position_groups())


@app.route('/api/position-groups', methods=['POST'])
def add_position_group():
    data = request.json
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Нужно имя'}), 400
    gid = db.add_position_group(name)
    return jsonify({'id': gid, 'ok': True})


@app.route('/api/position-groups/<int:gid>', methods=['PATCH'])
def rename_position_group(gid):
    data = request.json
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Нужно имя'}), 400
    db.rename_position_group(gid, name)
    return jsonify({'ok': True})


@app.route('/api/position-groups/<int:gid>', methods=['DELETE'])
def delete_position_group(gid):
    db.delete_position_group(gid)
    return jsonify({'ok': True})


@app.route('/api/hl/mids')
def hl_mids():
    """Return all current mid prices from Hyperliquid."""
    global _mids_cache, _mids_cache_ts
    try:
        now = time.time()
        if not _mids_cache or (now - _mids_cache_ts) > _PRICE_TTL:
            _mids_cache = requests.post(HL_API, json={'type': 'allMids'}, timeout=10).json()
            _mids_cache_ts = now
        return jsonify(_mids_cache)
    except Exception as e:
        return jsonify({'error': str(e)}), 502


@app.route('/api/hl/search')
def hl_search():
    """Search HL tokens by symbol prefix."""
    global _mids_cache, _mids_cache_ts
    q = request.args.get('q', '').strip().upper()
    try:
        now = time.time()
        if not _mids_cache or (now - _mids_cache_ts) > _PRICE_TTL:
            _mids_cache = requests.post(HL_API, json={'type': 'allMids'}, timeout=10).json()
            _mids_cache_ts = now
        results = [
            {'symbol': k, 'price': float(v)}
            for k, v in _mids_cache.items()
            if q in k.upper()
        ]
        results.sort(key=lambda x: (not x['symbol'].upper().startswith(q), x['symbol']))
        return jsonify(results[:10])
    except Exception as e:
        return jsonify({'error': str(e)}), 502


# --- Export ---

@app.route('/api/proxies', methods=['GET'])
def get_proxies():
    db.sync_proxies()
    return jsonify(db.get_proxies())


@app.route('/api/proxies/bulk', methods=['POST'])
def bulk_add_proxies():
    lines = (request.json.get('proxies') or [])
    added = db.bulk_add_proxies(lines)
    return jsonify({'ok': True, 'added': added})


@app.route('/api/proxies/<int:pid>', methods=['PATCH'])
def update_proxy(pid):
    data = request.json or {}
    if 'label' in data:
        db.update_proxy_label(pid, data['label'])
    if 'wallet_id' in data:
        wid = data['wallet_id']
        if wid:
            db.assign_proxy(pid, wid)
        else:
            db.unassign_proxy(pid)
    return jsonify({'ok': True})


@app.route('/api/proxies/<int:pid>', methods=['DELETE'])
def delete_proxy(pid):
    db.delete_proxy(pid)
    return jsonify({'ok': True})


@app.route('/api/open-folder', methods=['POST'])
def open_folder():
    import subprocess
    path = request.json.get('path', '')
    if path and os.path.exists(path):
        subprocess.Popen(['explorer', '/select,', os.path.normpath(path)])
    return jsonify({'ok': True})


@app.route('/api/export')
def export():
    wb = openpyxl.Workbook()

    dark = PatternFill('solid', fgColor='1a1a2e')
    light = PatternFill('solid', fgColor='F5F5F3')
    header_font = Font(bold=True, color='FFFFFF', size=11)
    header_align = Alignment(horizontal='center', vertical='center')
    thin = Border(
        left=Side(style='thin', color='2d3748'),
        right=Side(style='thin', color='2d3748'),
        top=Side(style='thin', color='2d3748'),
        bottom=Side(style='thin', color='2d3748'),
    )

    def style_header(ws, headers):
        ws.append(headers)
        for cell in ws[1]:
            cell.fill = dark
            cell.font = header_font
            cell.alignment = header_align
            cell.border = thin
        ws.row_dimensions[1].height = 28

    def style_rows(ws, start=2):
        for i, row in enumerate(ws.iter_rows(min_row=start)):
            if i % 2 == 0:
                for cell in row:
                    cell.fill = light
                    cell.border = thin

    # Sheet 1: Protocols
    ws1 = wb.active
    ws1.title = 'Протоколы'
    style_header(ws1, ['Протокол', 'Потрачено', 'Заработано', 'P&L', 'Кошельки', 'Статус', 'Заметка'])

    protocols = db.get_protocols()
    wallet_counts = db.get_wallet_counts()
    for p in protocols:
        pnl = round((p['earned'] or 0) - (p['spent'] or 0), 2)
        ws1.append([p['name'], p['spent'], p['earned'], pnl,
                    wallet_counts.get(p['name'], 0), p['status'], p['note'] or ''])

    style_rows(ws1)
    for i, row in enumerate(ws1.iter_rows(min_row=2), 0):
        pnl_cell = ws1.cell(i + 2, 4)
        v = pnl_cell.value or 0
        if v > 0:
            pnl_cell.font = Font(color='1D9E75', bold=True)
        elif v < 0:
            pnl_cell.font = Font(color='E24B4A', bold=True)

    for col, w in enumerate([22, 14, 14, 12, 10, 14, 30], 1):
        ws1.column_dimensions[get_column_letter(col)].width = w

    # Sheet 2: Wallets
    ws2 = wb.create_sheet('Кошельки')
    style_header(ws2, ['Адрес', 'Протоколы', 'Метка', 'Добавлен'])
    for w in db.get_wallets():
        protos = ', '.join(w.get('protocols') or []) or '—'
        ws2.append([w['address'], protos, w.get('label', ''), w['added_at']])
    style_rows(ws2)
    for col, width in enumerate([18, 45, 20, 22], 1):
        ws2.column_dimensions[get_column_letter(col)].width = width

    # Sheet 3: Summary
    ws3 = wb.create_sheet('Сводка')
    style_header(ws3, ['Показатель', 'Значение'])
    s = db.get_stats()
    pnl = round(s['total_earned'] - s['total_spent'], 2)
    for row in [
        ['Всего протоколов', s['total']],
        ['Активных', s['active']],
        ['Кошельков', s['total_wallets']],
        ['Потрачено ($)', s['total_spent']],
        ['Заработано ($)', s['total_earned']],
        ['P&L ($)', pnl],
        ['Дата экспорта', datetime.now().strftime('%d.%m.%Y %H:%M')],
    ]:
        ws3.append(row)
    style_rows(ws3)
    ws3.column_dimensions['A'].width = 25
    ws3.column_dimensions['B'].width = 20

    # Save to Downloads
    downloads = os.path.join(os.path.expanduser('~'), 'Downloads')
    os.makedirs(downloads, exist_ok=True)
    filename = f'farmtrack_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx'
    filepath = os.path.join(downloads, filename)
    wb.save(filepath)

    return jsonify({'ok': True, 'filename': filename, 'path': filepath, 'folder': downloads})
