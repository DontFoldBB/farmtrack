import sqlite3
import os
from contextlib import contextmanager
from datetime import datetime

_DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
DB_PATH = os.environ.get('DB_PATH', os.path.join(_DATA_DIR, 'farmtrack.db'))


def set_profile(name: str):
    """Switch active database to data/<name>.db and initialise it."""
    global DB_PATH
    os.makedirs(_DATA_DIR, exist_ok=True)
    DB_PATH = os.path.join(_DATA_DIR, f'{name}.db')
    init()


def list_profiles():
    """Return sorted list of profile names (existing .db files in data/)."""
    os.makedirs(_DATA_DIR, exist_ok=True)
    names = []
    for f in os.listdir(_DATA_DIR):
        if f.endswith('.db'):
            names.append(f[:-3])
    return sorted(names)


@contextmanager
def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init():
    with _conn() as c:
        c.executescript('''
            CREATE TABLE IF NOT EXISTS protocols (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                spent REAL DEFAULT 0,
                earned REAL DEFAULT 0,
                status TEXT DEFAULT 'фармлю',
                note TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS wallets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT NOT NULL UNIQUE,
                label TEXT DEFAULT '',
                added_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS wallet_protocols (
                wallet_id INTEGER NOT NULL,
                protocol  TEXT NOT NULL,
                PRIMARY KEY (wallet_id, protocol),
                FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                protocol TEXT NOT NULL,
                remind_at TEXT NOT NULL,
                done INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS position_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                collateral REAL NOT NULL,
                leverage REAL NOT NULL,
                entry_price REAL NOT NULL,
                note TEXT DEFAULT '',
                group_id INTEGER DEFAULT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS hl_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL,
                address TEXT NOT NULL UNIQUE,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS weekly_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet_id INTEGER NOT NULL,
                protocol TEXT NOT NULL,
                week TEXT NOT NULL,
                points REAL DEFAULT 0,
                UNIQUE(wallet_id, protocol, week),
                FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
            );
        ''')
        _migrate(c)


def _migrate(c):
    """Run all incremental migrations."""
    # Add color/points columns to protocols if missing
    proto_cols = {r[1] for r in c.execute("PRAGMA table_info(protocols)").fetchall()}
    if 'color' not in proto_cols:
        c.execute("ALTER TABLE protocols ADD COLUMN color TEXT DEFAULT '#10b981'")
    if 'points' not in proto_cols:
        c.execute("ALTER TABLE protocols ADD COLUMN points REAL DEFAULT 0")
    if 'point_price' not in proto_cols:
        c.execute("ALTER TABLE protocols ADD COLUMN point_price REAL DEFAULT 0")

    # Ensure position_groups table exists (for older DBs created before this table was added)
    c.executescript('''
        CREATE TABLE IF NOT EXISTS position_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );
    ''')

    # Drop positions table if it has old coingecko_id column (incompatible schema)
    pos_cols = {r[1] for r in c.execute("PRAGMA table_info(positions)").fetchall()}
    if 'coingecko_id' in pos_cols:
        c.executescript('''
            DROP TABLE IF EXISTS positions;
            CREATE TABLE positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                collateral REAL NOT NULL,
                leverage REAL NOT NULL,
                entry_price REAL NOT NULL,
                note TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            );
        ''')

    # Add group_id to positions if missing
    pos_cols2 = {r[1] for r in c.execute("PRAGMA table_info(positions)").fetchall()}
    if 'group_id' not in pos_cols2:
        c.execute("ALTER TABLE positions ADD COLUMN group_id INTEGER DEFAULT NULL")

    # Add financial columns to wallet_protocols if missing
    wp_cols = {r[1] for r in c.execute("PRAGMA table_info(wallet_protocols)").fetchall()}
    if 'spent' not in wp_cols:
        c.execute("ALTER TABLE wallet_protocols ADD COLUMN spent REAL DEFAULT 0")
    if 'deposit' not in wp_cols:
        c.execute("ALTER TABLE wallet_protocols ADD COLUMN deposit REAL DEFAULT 0")
    if 'wallet_balance' not in wp_cols:
        c.execute("ALTER TABLE wallet_protocols ADD COLUMN wallet_balance REAL DEFAULT 0")
    if 'wp_points' not in wp_cols:
        c.execute("ALTER TABLE wallet_protocols ADD COLUMN wp_points REAL DEFAULT 0")
    if 'wp_earned' not in wp_cols:
        c.execute("ALTER TABLE wallet_protocols ADD COLUMN wp_earned REAL DEFAULT 0")

    # Migrate old wallets table (with protocol column) to new many-to-many schema
    cols = {r[1] for r in c.execute("PRAGMA table_info(wallets)").fetchall()}
    if 'protocol' not in cols:
        # Add balance tracking columns if missing
        for col, typedef in [
            ('balance',  'REAL DEFAULT NULL'),
            ('volume',   'REAL DEFAULT NULL'),
            ('burn',     'REAL DEFAULT NULL'),
            ('points',   'REAL DEFAULT NULL'),
            ('p_price',  'REAL DEFAULT NULL'),
            ('sync_at',  'TEXT DEFAULT NULL'),
        ]:
            if col not in cols:
                c.execute(f'ALTER TABLE wallets ADD COLUMN {col} {typedef}')
        return  # already on new schema

    # Recreate wallets without protocol column, preserve data
    c.executescript('''
        CREATE TABLE IF NOT EXISTS wallets_new (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            address  TEXT NOT NULL UNIQUE,
            label    TEXT DEFAULT '',
            added_at TEXT DEFAULT (datetime('now'))
        );
        INSERT OR IGNORE INTO wallets_new (id, address, label, added_at)
            SELECT id, address, label, added_at FROM wallets;

        INSERT OR IGNORE INTO wallet_protocols (wallet_id, protocol)
            SELECT id, protocol FROM wallets WHERE protocol IS NOT NULL;

        DROP TABLE wallets;
        ALTER TABLE wallets_new RENAME TO wallets;
    ''')


# ── Protocols ─────────────────────────────────────────────────────────────────

def get_protocols():
    with _conn() as c:
        rows = c.execute('''
            SELECT p.*,
                COALESCE(agg.total_deposit, 0)   AS total_deposit,
                COALESCE(agg.total_balance, 0)   AS total_balance,
                COALESCE(agg.total_wp_points, 0) AS total_wp_points,
                COALESCE(agg.total_wp_earned, 0) AS total_wp_earned,
                COALESCE(wc.cnt, 0)              AS wallet_count
            FROM protocols p
            LEFT JOIN (
                SELECT protocol,
                    SUM(COALESCE(deposit, 0))       AS total_deposit,
                    SUM(COALESCE(wallet_balance, 0)) AS total_balance,
                    SUM(COALESCE(wp_points, 0))      AS total_wp_points,
                    SUM(COALESCE(wp_earned, 0))      AS total_wp_earned
                FROM wallet_protocols
                GROUP BY protocol
            ) agg ON agg.protocol = p.name
            LEFT JOIN (
                SELECT protocol, COUNT(*) AS cnt
                FROM wallet_protocols GROUP BY protocol
            ) wc ON wc.protocol = p.name
            ORDER BY p.updated_at DESC
        ''').fetchall()
        return [dict(r) for r in rows]


def add_protocol(name, spent=0, earned=0, status='фармлю', note='', color='#10b981', points=0):
    with _conn() as c:
        c.execute(
            'INSERT INTO protocols (name, spent, earned, status, note, color, points) VALUES (?,?,?,?,?,?,?)',
            (name, spent, earned, status, note, color, points)
        )


def update_protocol(pid, spent, earned, status, note, color='#10b981', points=0, point_price=0):
    with _conn() as c:
        c.execute(
            "UPDATE protocols SET spent=?, earned=?, status=?, note=?, color=?, points=?, point_price=?, updated_at=datetime('now') WHERE id=?",
            (spent, earned, status, note, color, points, point_price, pid)
        )


def delete_protocol(pid):
    with _conn() as c:
        row = c.execute('SELECT name FROM protocols WHERE id=?', (pid,)).fetchone()
        if row:
            c.execute('DELETE FROM protocols WHERE id=?', (pid,))
            c.execute('DELETE FROM wallet_protocols WHERE protocol=?', (row['name'],))


def get_stats():
    with _conn() as c:
        r = c.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'фармлю' THEN 1 ELSE 0 END) as active,
                COALESCE(SUM(earned), 0) as total_earned
            FROM protocols
        ''').fetchone()
        agg = c.execute('''
            SELECT
                COALESCE(SUM(COALESCE(deposit, 0)), 0)        AS total_deposit,
                COALESCE(SUM(COALESCE(wallet_balance, 0)), 0) AS total_balance,
                COALESCE(SUM(COALESCE(wp_earned, 0)), 0)      AS total_wp_earned
            FROM wallet_protocols
        ''').fetchone()
        # Manual spent for protocols with no wallet financial data
        manual = c.execute('''
            SELECT COALESCE(SUM(p.spent), 0) AS manual_spent
            FROM protocols p
            LEFT JOIN (
                SELECT protocol,
                    SUM(COALESCE(deposit,0)+COALESCE(wallet_balance,0)+COALESCE(wp_earned,0)) AS wsum
                FROM wallet_protocols GROUP BY protocol
            ) wp ON wp.protocol = p.name
            WHERE COALESCE(wp.wsum, 0) = 0
        ''').fetchone()
        w = c.execute('SELECT COUNT(*) as cnt FROM wallets').fetchone()
        wallet_spent = max(0, (agg['total_deposit'] or 0) - (agg['total_balance'] or 0) - (agg['total_wp_earned'] or 0))
        total_spent = wallet_spent + (manual['manual_spent'] or 0)
        result = dict(r)
        result['total_wallets'] = w['cnt']
        result['total_spent'] = total_spent
        result['total_deposit'] = agg['total_deposit'] or 0
        result['total_balance'] = agg['total_balance'] or 0
        result['pnl'] = (agg['total_wp_earned'] or 0) + (agg['total_balance'] or 0) - (agg['total_deposit'] or 0) - (manual['manual_spent'] or 0)
        return result


def get_wallet_counts():
    with _conn() as c:
        rows = c.execute(
            'SELECT protocol, COUNT(*) as cnt FROM wallet_protocols GROUP BY protocol'
        ).fetchall()
        return {r['protocol']: r['cnt'] for r in rows}


def get_protocol_wallets_detail(protocol):
    """Return wallets in a protocol with per-protocol deposit, balance, points."""
    with _conn() as c:
        rows = c.execute('''
            SELECT w.id, w.address, w.label,
                   COALESCE(wp.deposit, 0)        AS deposit,
                   COALESCE(wp.wallet_balance, 0) AS wallet_balance,
                   COALESCE(wp.wp_points, 0)      AS wp_points,
                   COALESCE(wp.wp_earned, 0)      AS wp_earned
            FROM wallets w
            JOIN wallet_protocols wp ON wp.wallet_id = w.id AND wp.protocol = ?
            ORDER BY w.added_at ASC
        ''', (protocol,)).fetchall()
        return [dict(r) for r in rows]


def import_protocol_wallet_data(protocol, rows, add_points=False, add_deposit=False):
    """Match wallets in protocol by address and bulk-update their data.
    rows: list of dicts with optional keys: address, deposit, wallet_balance, wp_points, wp_earned.
    Address may be full or shortened (0x1234..5678).
    add_points: if True, wp_points are added to existing value instead of replacing.
    add_deposit: if True, deposit is added to existing value instead of replacing.
    Returns {matched, unmatched_addresses}.
    """
    matched = 0
    unmatched = []
    with _conn() as c:
        wallets = c.execute('''
            SELECT w.id, w.address FROM wallets w
            JOIN wallet_protocols wp ON wp.wallet_id = w.id AND wp.protocol = ?
        ''', (protocol,)).fetchall()
        wallets = [(w['id'], w['address'].lower()) for w in wallets]

        for row in rows:
            raw_addr = (row.get('address') or '').strip()
            if not raw_addr:
                continue
            addr = raw_addr.lower()
            found_id = None

            # Normalize ellipsis variants: '…' → '..', '...' → '..'
            addr_norm = addr.replace('\u2026', '..').replace('...', '..')

            for wid, wa in wallets:
                # 1. Exact match (case-insensitive)
                if wa == addr:
                    found_id = wid; break
                # 2. Shortened with '..' separator (any variant)
                if '..' in addr_norm:
                    parts = addr_norm.split('..')
                    if len(parts) == 2 and parts[0] and parts[1]:
                        if wa.startswith(parts[0]) and wa.endswith(parts[1]):
                            found_id = wid; break
                        # Also try case-sensitive stored address
                        wa_orig = wa  # already lowercased via wallets list
                # 3. Full address partial match: first 6 + last 4 chars
                if not found_id and len(addr) >= 10:
                    if wa.startswith(addr[:6]) and wa.endswith(addr[-4:]):
                        found_id = wid; break
                # 4. Longer prefix match for non-Ethereum addresses (Solana etc.)
                if not found_id and len(addr) >= 16:
                    if wa.startswith(addr[:8]) and wa.endswith(addr[-6:]):
                        found_id = wid; break
            if not found_id:
                # Not in protocol wallets — try to find or create in wallets table
                # Only possible for full (non-shortened) addresses
                is_short = '..' in addr_norm or '\u2026' in addr_norm
                if not is_short:
                    existing = c.execute(
                        'SELECT id FROM wallets WHERE LOWER(address)=?', (addr,)
                    ).fetchone()
                    if existing:
                        found_id = existing['id']
                    else:
                        c.execute('INSERT OR IGNORE INTO wallets (address) VALUES (?)', (raw_addr,))
                        found_id = c.execute(
                            'SELECT id FROM wallets WHERE LOWER(address)=?', (addr,)
                        ).fetchone()['id']
                    # Link wallet to protocol if not already linked
                    c.execute(
                        'INSERT OR IGNORE INTO wallet_protocols (wallet_id, protocol) VALUES (?,?)',
                        (found_id, protocol)
                    )
                    # Add to wallets list so later rows can match it
                    wallets.append((found_id, addr))

            if found_id:
                sets, vals = [], []
                if row.get('deposit') is not None:
                    if add_deposit:
                        sets.append('deposit=deposit+?')
                    else:
                        sets.append('deposit=?')
                    vals.append(float(row['deposit']))
                for col in ('wallet_balance', 'wp_earned'):
                    if row.get(col) is not None:
                        sets.append(f'{col}=?')
                        vals.append(float(row[col]))
                if row.get('wp_points') is not None:
                    if add_points:
                        sets.append('wp_points=wp_points+?')
                    else:
                        sets.append('wp_points=?')
                    vals.append(float(row['wp_points']))
                if sets:
                    vals += [found_id, protocol]
                    c.execute(f"UPDATE wallet_protocols SET {','.join(sets)} WHERE wallet_id=? AND protocol=?", vals)
                matched += 1
            else:
                unmatched.append(row.get('address', ''))
    return {'matched': matched, 'unmatched': unmatched}


def update_wallet_protocol(wallet_id, protocol, deposit=None, wallet_balance=None, wp_points=None, wp_earned=None):
    with _conn() as c:
        if deposit is not None:
            c.execute('UPDATE wallet_protocols SET deposit=? WHERE wallet_id=? AND protocol=?',
                      (deposit, wallet_id, protocol))
        if wallet_balance is not None:
            c.execute('UPDATE wallet_protocols SET wallet_balance=? WHERE wallet_id=? AND protocol=?',
                      (wallet_balance, wallet_id, protocol))
        if wp_points is not None:
            c.execute('UPDATE wallet_protocols SET wp_points=? WHERE wallet_id=? AND protocol=?',
                      (wp_points, wallet_id, protocol))
        if wp_earned is not None:
            c.execute('UPDATE wallet_protocols SET wp_earned=? WHERE wallet_id=? AND protocol=?',
                      (wp_earned, wallet_id, protocol))


# ── Wallets ───────────────────────────────────────────────────────────────────

def _attach_protocols(c, wallets):
    if not wallets:
        return wallets
    ids = [w['id'] for w in wallets]
    rows = c.execute(
        f"SELECT wallet_id, protocol FROM wallet_protocols WHERE wallet_id IN ({','.join('?'*len(ids))})",
        ids
    ).fetchall()
    proto_map = {}
    for r in rows:
        proto_map.setdefault(r['wallet_id'], []).append(r['protocol'])
    for w in wallets:
        w['protocols'] = sorted(proto_map.get(w['id'], []))
    return wallets


def get_wallets(protocol=None, unassigned_only=False):
    with _conn() as c:
        if unassigned_only:
            rows = c.execute('''
                SELECT w.* FROM wallets w
                LEFT JOIN wallet_protocols wp ON w.id = wp.wallet_id
                WHERE wp.wallet_id IS NULL
                ORDER BY w.added_at DESC
            ''').fetchall()
        elif protocol:
            rows = c.execute('''
                SELECT w.* FROM wallets w
                JOIN wallet_protocols wp ON w.id = wp.wallet_id AND wp.protocol = ?
                ORDER BY w.added_at DESC
            ''', (protocol,)).fetchall()
        else:
            rows = c.execute('SELECT * FROM wallets ORDER BY added_at DESC').fetchall()

        wallets = [dict(r) for r in rows]
        return _attach_protocols(c, wallets)


def bulk_add_wallets(addresses, protocols=None, label=''):
    """Insert wallets (UNIQUE address — duplicates skipped). Optionally assign protocols."""
    added = 0
    with _conn() as c:
        for addr in addresses:
            addr = addr.strip()
            if not addr:
                continue
            c.execute('INSERT OR IGNORE INTO wallets (address, label) VALUES (?,?)', (addr, label))
            if c.execute('SELECT changes()').fetchone()[0]:
                added += 1
            if protocols:
                wid = c.execute('SELECT id FROM wallets WHERE address=?', (addr,)).fetchone()['id']
                for proto in protocols:
                    if proto:
                        c.execute(
                            'INSERT OR IGNORE INTO wallet_protocols (wallet_id, protocol) VALUES (?,?)',
                            (wid, proto)
                        )
    return added


def set_wallet_protocols(wallet_id, protocols):
    """Replace all protocol assignments for a single wallet."""
    with _conn() as c:
        c.execute('DELETE FROM wallet_protocols WHERE wallet_id=?', (wallet_id,))
        for proto in protocols:
            if proto:
                c.execute(
                    'INSERT OR IGNORE INTO wallet_protocols (wallet_id, protocol) VALUES (?,?)',
                    (wallet_id, proto)
                )


def add_protocol_to_wallets(wallet_ids, protocol):
    """Add a single protocol to multiple wallets (additive)."""
    if not protocol:
        return
    with _conn() as c:
        c.executemany(
            'INSERT OR IGNORE INTO wallet_protocols (wallet_id, protocol) VALUES (?,?)',
            [(wid, protocol) for wid in wallet_ids]
        )



def import_balances(rows):
    """Update wallet balance stats from imported data.
    rows: list of dicts with keys: address_short, balance, volume, burn, points, p_price
    address_short is truncated like '0x1504..3d8D' — matched by prefix+suffix.
    Returns count of matched wallets.
    """
    now = datetime.now().strftime('%Y-%m-%dT%H:%M')
    matched = 0
    with _conn() as c:
        wallets = [dict(r) for r in c.execute('SELECT id, address FROM wallets').fetchall()]
        for row in rows:
            short = row['address_short']
            if '..' not in short:
                continue
            prefix = short[:6].lower()
            suffix = short.split('..')[-1].lower()
            for w in wallets:
                addr = w['address'].lower()
                if addr.startswith(prefix) and addr.endswith(suffix):
                    c.execute(
                        'UPDATE wallets SET balance=?, volume=?, burn=?, points=?, p_price=?, sync_at=? WHERE id=?',
                        (row.get('balance'), row.get('volume'), row.get('burn'),
                         row.get('points'), row.get('p_price'), now, w['id'])
                    )
                    matched += 1
                    break
    return matched


def update_wallet_label(wid, label):
    with _conn() as c:
        c.execute('UPDATE wallets SET label=? WHERE id=?', (label, wid))


def delete_wallet(wid):
    with _conn() as c:
        c.execute('DELETE FROM wallets WHERE id=?', (wid,))


# ── Reminders ─────────────────────────────────────────────────────────────────

def get_reminders(include_done=False):
    with _conn() as c:
        if include_done:
            rows = c.execute('SELECT * FROM reminders ORDER BY done ASC, remind_at ASC').fetchall()
        else:
            rows = c.execute('SELECT * FROM reminders WHERE done=0 ORDER BY remind_at ASC').fetchall()
        return [dict(r) for r in rows]


def add_reminder(protocol, remind_at):
    with _conn() as c:
        c.execute('INSERT INTO reminders (protocol, remind_at) VALUES (?,?)', (protocol, remind_at))


def delete_reminder(rid):
    with _conn() as c:
        c.execute('DELETE FROM reminders WHERE id=?', (rid,))


def mark_done(rid):
    with _conn() as c:
        c.execute('UPDATE reminders SET done=1 WHERE id=?', (rid,))


def get_due_reminders():
    now = datetime.now().strftime('%Y-%m-%dT%H:%M')
    with _conn() as c:
        rows = c.execute(
            'SELECT * FROM reminders WHERE done=0 AND remind_at<=?', (now,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── Positions (calculator) ────────────────────────────────────────────────────

def get_positions():
    with _conn() as c:
        return [dict(r) for r in c.execute('SELECT * FROM positions ORDER BY created_at DESC').fetchall()]


def add_position(symbol, direction, collateral, leverage, entry_price, note='', group_id=None):
    with _conn() as c:
        c.execute(
            'INSERT INTO positions (symbol, direction, collateral, leverage, entry_price, note, group_id) VALUES (?,?,?,?,?,?,?)',
            (symbol.upper(), direction, collateral, leverage, entry_price, note, group_id)
        )


def update_position(pid, symbol, direction, collateral, leverage, entry_price, note='', group_id=None):
    with _conn() as c:
        c.execute(
            'UPDATE positions SET symbol=?, direction=?, collateral=?, leverage=?, entry_price=?, note=?, group_id=? WHERE id=?',
            (symbol.upper(), direction, collateral, leverage, entry_price, note, group_id, pid)
        )


def delete_position(pid):
    with _conn() as c:
        c.execute('DELETE FROM positions WHERE id=?', (pid,))


# ── Position groups ───────────────────────────────────────────────────────────

def get_position_groups():
    with _conn() as c:
        return [dict(r) for r in c.execute('SELECT * FROM position_groups ORDER BY created_at ASC').fetchall()]


def add_position_group(name):
    with _conn() as c:
        c.execute('INSERT INTO position_groups (name) VALUES (?)', (name,))
        return c.execute('SELECT last_insert_rowid()').fetchone()[0]


def rename_position_group(gid, name):
    with _conn() as c:
        c.execute('UPDATE position_groups SET name=? WHERE id=?', (name, gid))


def delete_position_group(gid):
    with _conn() as c:
        c.execute('UPDATE positions SET group_id=NULL WHERE group_id=?', (gid,))
        c.execute('DELETE FROM position_groups WHERE id=?', (gid,))


# ── HL accounts ───────────────────────────────────────────────────────────────

def get_hl_accounts():
    with _conn() as c:
        return [dict(r) for r in c.execute('SELECT * FROM hl_accounts ORDER BY created_at ASC').fetchall()]


def add_hl_account(label, address):
    with _conn() as c:
        c.execute('INSERT OR IGNORE INTO hl_accounts (label, address) VALUES (?,?)', (label, address))


def delete_hl_account(aid):
    with _conn() as c:
        c.execute('DELETE FROM hl_accounts WHERE id=?', (aid,))


# ── Weekly points ──────────────────────────────────────────────────────────────

def get_weekly_points(protocol, week):
    """Return all wallets for the protocol with their points for the given week.
    week: ISO date string 'YYYY-MM-DD' (Friday).
    """
    with _conn() as c:
        rows = c.execute('''
            SELECT w.id, w.address, w.label,
                   COALESCE(wp.points, 0) as points
            FROM wallets w
            JOIN wallet_protocols wpr ON wpr.wallet_id = w.id AND wpr.protocol = ?
            LEFT JOIN weekly_points wp ON wp.wallet_id = w.id
                AND wp.protocol = ? AND wp.week = ?
            ORDER BY w.added_at ASC
        ''', (protocol, protocol, week)).fetchall()
        return [dict(r) for r in rows]


def upsert_weekly_points(protocol, week, entries):
    """Batch upsert. entries: list of {wallet_id, points}."""
    with _conn() as c:
        for e in entries:
            c.execute('''
                INSERT INTO weekly_points (wallet_id, protocol, week, points)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(wallet_id, protocol, week) DO UPDATE SET points=excluded.points
            ''', (e['wallet_id'], protocol, week, e['points']))


def get_weekly_summary(protocol):
    """Return per-week totals for a protocol, newest first."""
    with _conn() as c:
        rows = c.execute('''
            SELECT week,
                   ROUND(SUM(points), 2) as total_points,
                   COUNT(DISTINCT wallet_id) as wallet_count
            FROM weekly_points
            WHERE protocol = ?
            GROUP BY week
            ORDER BY week DESC
        ''', (protocol,)).fetchall()
        return [dict(r) for r in rows]


def get_weekly_points_prev(protocol, week):
    """Return points for the week immediately before `week`."""
    with _conn() as c:
        prev = c.execute('''
            SELECT week FROM weekly_points
            WHERE protocol = ? AND week < ?
            GROUP BY week ORDER BY week DESC LIMIT 1
        ''', (protocol, week)).fetchone()
        if not prev:
            return {}
        rows = c.execute('''
            SELECT wallet_id, points FROM weekly_points
            WHERE protocol = ? AND week = ?
        ''', (protocol, prev['week'])).fetchall()
        return {r['wallet_id']: r['points'] for r in rows}
