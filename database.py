import sqlite3
import os
import re
from contextlib import contextmanager
from datetime import datetime


def _detect_chain(address):
    """Detect blockchain network from address format."""
    a = (address or '').strip()
    if re.match(r'^0x[0-9a-fA-F]{64}$', a):
        return 'apt'      # Aptos: 0x + 64 hex
    if re.match(r'^0x[0-9a-fA-F]{62,63}$', a):
        return 'stark'    # Starknet: 0x + 62-63 hex
    if re.match(r'^0x[0-9a-fA-F]{40}$', a, re.IGNORECASE):
        return 'evm'      # EVM: 0x + 40 hex
    if re.match(r'^T[1-9A-HJ-NP-Za-km-z]{33}$', a):
        return 'trx'      # Tron
    if re.match(r'^(bc1|[13])[a-zA-HJ-NP-Z0-9]{25,62}$', a):
        return 'btc'      # Bitcoin
    if re.match(r'^cosmos1[a-z0-9]{38}$', a):
        return 'cosmos'   # Cosmos
    if re.match(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$', a):
        return 'sol'      # Solana (base58 fallback)
    return None

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
                proxy TEXT DEFAULT NULL,
                chain TEXT DEFAULT NULL,
                added_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS proxies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proxy TEXT NOT NULL UNIQUE,
                label TEXT DEFAULT '',
                wallet_id INTEGER DEFAULT NULL,
                added_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE SET NULL
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
                group_name TEXT DEFAULT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS nado_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL,
                address TEXT NOT NULL UNIQUE,
                group_name TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS extended_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL,
                api_key TEXT NOT NULL UNIQUE,
                group_name TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS pacifica_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL,
                address TEXT NOT NULL UNIQUE,
                group_name TEXT,
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
            CREATE TABLE IF NOT EXISTS telegram_config (
                id INTEGER PRIMARY KEY,
                bot_token TEXT DEFAULT '',
                chat_id TEXT DEFAULT '',
                alert_threshold_pct REAL DEFAULT 10.0,
                alert_cooldown_minutes INTEGER DEFAULT 60,
                report_interval_minutes INTEGER DEFAULT 60,
                check_interval_minutes INTEGER DEFAULT 5,
                alerts_enabled INTEGER DEFAULT 1,
                reports_enabled INTEGER DEFAULT 1,
                enabled INTEGER DEFAULT 0
            );
        ''')
        _migrate(c)


def _rebuild_positions_table(c, existing_cols):
    """Recreate positions table while preserving compatible rows."""
    desired_cols = ['id', 'symbol', 'direction', 'collateral', 'leverage', 'entry_price', 'note', 'created_at']
    insert_cols = [col for col in desired_cols if col in existing_cols]
    select_exprs = []
    for col in desired_cols:
        if col in existing_cols:
            select_exprs.append(col)
        elif col == 'note':
            select_exprs.append("'' AS note")
        elif col == 'created_at':
            select_exprs.append("datetime('now') AS created_at")

    c.executescript('''
        ALTER TABLE positions RENAME TO positions_legacy;
        CREATE TABLE positions (
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
    ''')
    if insert_cols:
        c.execute(
            f"INSERT INTO positions ({', '.join(insert_cols)}) "
            f"SELECT {', '.join(select_exprs)} FROM positions_legacy"
        )
    c.execute('DROP TABLE positions_legacy')


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

    # Rebuild positions table if it has old incompatible columns, but preserve existing rows.
    pos_cols = {r[1] for r in c.execute("PRAGMA table_info(positions)").fetchall()}
    if 'coingecko_id' in pos_cols:
        _rebuild_positions_table(c, pos_cols)

    # Add chain column to wallets if missing
    w_cols = {r[1] for r in c.execute("PRAGMA table_info(wallets)").fetchall()}
    if 'chain' not in w_cols:
        c.execute("ALTER TABLE wallets ADD COLUMN chain TEXT DEFAULT NULL")
        # Auto-detect chain for existing wallets
        for row in c.execute("SELECT id, address FROM wallets").fetchall():
            ch = _detect_chain(row['address'])
            if ch:
                c.execute("UPDATE wallets SET chain=? WHERE id=?", (ch, row['id']))

    # Create proxies table if missing (migration for existing DBs)
    c.execute('''
        CREATE TABLE IF NOT EXISTS proxies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proxy TEXT NOT NULL UNIQUE,
            label TEXT DEFAULT '',
            wallet_id INTEGER DEFAULT NULL,
            added_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE SET NULL
        )
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

    # Create protocol_weeks table (week containers)
    c.executescript('''
        CREATE TABLE IF NOT EXISTS protocol_weeks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            protocol TEXT NOT NULL,
            week_start TEXT NOT NULL,
            week_end TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );
        DROP TABLE IF EXISTS protocol_weekly;
    ''')

    # Extend weekly_points with balance/earned/start_balance columns if missing
    wp2_cols = {r[1] for r in c.execute("PRAGMA table_info(weekly_points)").fetchall()}
    if 'wallet_balance' not in wp2_cols:
        c.execute("ALTER TABLE weekly_points ADD COLUMN wallet_balance REAL DEFAULT 0")
    if 'wp_earned' not in wp2_cols:
        c.execute("ALTER TABLE weekly_points ADD COLUMN wp_earned REAL DEFAULT 0")
    if 'start_balance' not in wp2_cols:
        c.execute("ALTER TABLE weekly_points ADD COLUMN start_balance REAL DEFAULT NULL")

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
            ('proxy',    'TEXT DEFAULT NULL'),
        ]:
            if col not in cols:
                c.execute(f'ALTER TABLE wallets ADD COLUMN {col} {typedef}')

    # Add group_name to nado_accounts if missing (must run for all DB versions)
    nado_cols = {r[1] for r in c.execute("PRAGMA table_info(nado_accounts)").fetchall()}
    if 'group_name' not in nado_cols:
        c.execute("ALTER TABLE nado_accounts ADD COLUMN group_name TEXT DEFAULT NULL")

    # Add group_name to hl_accounts if missing (must run for all DB versions)
    hl_cols = {r[1] for r in c.execute("PRAGMA table_info(hl_accounts)").fetchall()}
    if 'group_name' not in hl_cols:
        c.execute("ALTER TABLE hl_accounts ADD COLUMN group_name TEXT DEFAULT NULL")

    # Create extended_accounts if missing (migration for older DBs)
    c.execute('''
        CREATE TABLE IF NOT EXISTS extended_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL,
            api_key TEXT NOT NULL UNIQUE,
            group_name TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    ''')

    # Create pacifica_accounts if missing (migration for older DBs)
    c.execute('''
        CREATE TABLE IF NOT EXISTS pacifica_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL,
            address TEXT NOT NULL UNIQUE,
            group_name TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    ''')

    if 'protocol' not in cols:
        return  # already on new schema

    legacy_protocol_links = c.execute(
        'SELECT id, protocol FROM wallets WHERE protocol IS NOT NULL'
    ).fetchall()

    # Recreate wallets without protocol column, preserve data
    c.executescript('''
        ALTER TABLE wallets RENAME TO wallets_legacy;
        CREATE TABLE wallets (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            address  TEXT NOT NULL UNIQUE,
            label    TEXT DEFAULT '',
            proxy    TEXT DEFAULT NULL,
            chain    TEXT DEFAULT NULL,
            balance  REAL DEFAULT NULL,
            volume   REAL DEFAULT NULL,
            burn     REAL DEFAULT NULL,
            points   REAL DEFAULT NULL,
            p_price  REAL DEFAULT NULL,
            sync_at  TEXT DEFAULT NULL,
            added_at TEXT DEFAULT (datetime('now'))
        );
        INSERT OR IGNORE INTO wallets
            (id, address, label, proxy, chain, balance, volume, burn, points, p_price, sync_at, added_at)
        SELECT
            id,
            address,
            label,
            proxy,
            chain,
            balance,
            volume,
            burn,
            points,
            p_price,
            sync_at,
            added_at
        FROM wallets_legacy;
        DROP TABLE wallets_legacy;
        DROP TABLE wallet_protocols;
        CREATE TABLE wallet_protocols (
            wallet_id INTEGER NOT NULL,
            protocol TEXT NOT NULL,
            spent REAL DEFAULT 0,
            deposit REAL DEFAULT 0,
            wallet_balance REAL DEFAULT 0,
            wp_points REAL DEFAULT 0,
            wp_earned REAL DEFAULT 0,
            PRIMARY KEY (wallet_id, protocol),
            FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
        );
    ''')
    c.executemany(
        'INSERT OR IGNORE INTO wallet_protocols (wallet_id, protocol) VALUES (?,?)',
        [(row['id'], row['protocol']) for row in legacy_protocol_links]
    )


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


def import_protocol_wallet_data(protocol, rows, add_points=False, add_deposit=False, week=None):
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
                        c.execute('INSERT OR IGNORE INTO wallets (address, chain) VALUES (?,?)', (raw_addr, _detect_chain(raw_addr)))
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
                # Check if this week's snapshot already exists (re-import case)
                existing_week_row = None
                if week:
                    existing_week_row = c.execute(
                        'SELECT 1 FROM weekly_points WHERE wallet_id=? AND protocol=? AND week=?',
                        (found_id, protocol, week)
                    ).fetchone()
                if row.get('deposit') is not None:
                    if week:
                        if existing_week_row:
                            # Re-import: skip deposit delta, only update start_balance in weekly_points
                            pass
                        else:
                            # First time importing this week
                            # First weekly import → SET deposit directly
                            # Subsequent weeks → add delta vs previous week's balance
                            prev = c.execute(
                                'SELECT wallet_balance FROM weekly_points WHERE wallet_id=? AND protocol=? AND week<? ORDER BY week DESC LIMIT 1',
                                (found_id, protocol, week)
                            ).fetchone()
                            if prev:
                                diff = float(row['deposit']) - prev['wallet_balance']
                                if diff != 0:
                                    sets.append('deposit=deposit+?')
                                    vals.append(diff)
                            else:
                                # First week: set deposit to explicitly provided value
                                sets.append('deposit=?')
                                vals.append(float(row['deposit']))
                    elif add_deposit:
                        sets.append('deposit=deposit+?')
                        vals.append(float(row['deposit']))
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
                # Handle proxy (string field on wallets table)
                if row.get('proxy'):
                    proxy_val = str(row['proxy']).strip()
                    c.execute('UPDATE wallets SET proxy=? WHERE id=?', (proxy_val, found_id))
                    _sync_proxy_link(c, found_id, proxy_val)
                # Auto-set deposit from first week's balance if deposit never set
                _auto_deposit = None
                if week and row.get('deposit') is None and row.get('wallet_balance') is not None:
                    has_prior = c.execute(
                        'SELECT 1 FROM weekly_points WHERE wallet_id=? AND protocol=? LIMIT 1',
                        (found_id, protocol)
                    ).fetchone()
                    if not has_prior:
                        cur_dep = c.execute(
                            'SELECT deposit FROM wallet_protocols WHERE wallet_id=? AND protocol=?',
                            (found_id, protocol)
                        ).fetchone()
                        if not cur_dep or (cur_dep['deposit'] or 0) == 0:
                            _auto_deposit = float(row['wallet_balance'])
                            c.execute("UPDATE wallet_protocols SET deposit=? WHERE wallet_id=? AND protocol=?",
                                      [_auto_deposit, found_id, protocol])

                # Save weekly snapshot if week provided
                if week and found_id:
                    wk_points  = float(row.get('wp_points') or 0)
                    wk_balance = float(row.get('wallet_balance') or 0)
                    wk_earned  = float(row.get('wp_earned') or 0)
                    # start_balance: explicit deposit, or auto-set value (so delete_protocol_week can restore it)
                    wk_start = float(row['deposit']) if row.get('deposit') is not None else _auto_deposit
                    c.execute('''
                        INSERT INTO weekly_points (wallet_id, protocol, week, points, wallet_balance, wp_earned, start_balance)
                        VALUES (?,?,?,?,?,?,?)
                        ON CONFLICT(wallet_id, protocol, week) DO UPDATE SET
                            points=excluded.points,
                            wallet_balance=excluded.wallet_balance,
                            wp_earned=excluded.wp_earned,
                            start_balance=COALESCE(excluded.start_balance, weekly_points.start_balance)
                    ''', (found_id, protocol, week, wk_points, wk_balance, wk_earned, wk_start))
                    # Recalculate total wp_points in wallet_protocols as SUM across all weeks
                    c.execute('''
                        UPDATE wallet_protocols
                        SET wp_points = (
                            SELECT COALESCE(SUM(points), 0)
                            FROM weekly_points
                            WHERE wallet_id=? AND protocol=?
                        )
                        WHERE wallet_id=? AND protocol=?
                    ''', (found_id, protocol, found_id, protocol))
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


def get_wallets(protocol=None, unassigned_only=False, chain=None):
    with _conn() as c:
        chain_clause = ' AND w.chain=?' if chain else ''
        chain_args   = (chain,) if chain else ()
        if unassigned_only:
            rows = c.execute(f'''
                SELECT w.* FROM wallets w
                LEFT JOIN wallet_protocols wp ON w.id = wp.wallet_id
                WHERE wp.wallet_id IS NULL {chain_clause}
                ORDER BY w.added_at DESC
            ''', chain_args).fetchall()
        elif protocol:
            rows = c.execute(f'''
                SELECT w.* FROM wallets w
                JOIN wallet_protocols wp ON w.id = wp.wallet_id AND wp.protocol = ?
                WHERE 1=1 {chain_clause}
                ORDER BY w.added_at DESC
            ''', (protocol,) + chain_args).fetchall()
        else:
            if chain:
                rows = c.execute('SELECT * FROM wallets WHERE chain=? ORDER BY added_at DESC', (chain,)).fetchall()
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
            chain = _detect_chain(addr)
            c.execute('INSERT OR IGNORE INTO wallets (address, label, chain) VALUES (?,?,?)', (addr, label, chain))
            if c.execute('SELECT changes()').fetchone()[0]:
                added += 1
            elif label:
                # wallet already existed — overwrite label
                c.execute('UPDATE wallets SET label=? WHERE address=?', (label, addr))
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


def _sync_proxy_link(c, wallet_id, proxy_val):
    """Keep proxies.wallet_id in sync when wallets.proxy changes."""
    # Clear any existing proxies row pointing to this wallet
    c.execute('UPDATE proxies SET wallet_id=NULL WHERE wallet_id=?', (wallet_id,))
    if proxy_val:
        # If this proxy string exists in proxies table, link it
        c.execute('UPDATE proxies SET wallet_id=? WHERE proxy=?', (wallet_id, proxy_val))


def update_wallet_proxy(wid, proxy):
    with _conn() as c:
        proxy_val = proxy or None
        c.execute('UPDATE wallets SET proxy=? WHERE id=?', (proxy_val, wid))
        _sync_proxy_link(c, wid, proxy_val)


# ── Proxies ───────────────────────────────────────────────────────────────────

def get_proxies():
    with _conn() as c:
        rows = c.execute('''
            SELECT p.*, w.address AS wallet_address
            FROM proxies p
            LEFT JOIN wallets w ON w.id = p.wallet_id
            ORDER BY p.added_at DESC
        ''').fetchall()
        return [dict(r) for r in rows]


def bulk_add_proxies(proxy_list):
    added = 0
    with _conn() as c:
        for proxy in proxy_list:
            proxy = proxy.strip()
            if not proxy:
                continue
            try:
                cur = c.execute('INSERT OR IGNORE INTO proxies (proxy) VALUES (?)', (proxy,))
                if cur.rowcount:
                    added += 1
            except Exception:
                pass
        # Sync: if any wallet already has this proxy string, link it
        c.execute('''
            UPDATE proxies SET wallet_id = (
                SELECT id FROM wallets WHERE wallets.proxy = proxies.proxy LIMIT 1
            )
            WHERE wallet_id IS NULL
        ''')
    return added


def assign_proxy(proxy_id, wallet_id):
    """Assign proxy to wallet — updates both proxies.wallet_id and wallets.proxy."""
    with _conn() as c:
        proxy_row = c.execute('SELECT proxy FROM proxies WHERE id=?', (proxy_id,)).fetchone()
        if not proxy_row:
            return
        proxy_val = proxy_row['proxy']
        # Unassign from previous wallet if any
        old = c.execute('SELECT wallet_id FROM proxies WHERE id=?', (proxy_id,)).fetchone()
        if old and old['wallet_id']:
            c.execute('UPDATE wallets SET proxy=NULL WHERE id=? AND proxy=?', (old['wallet_id'], proxy_val))
        c.execute('UPDATE proxies SET wallet_id=? WHERE id=?', (wallet_id, proxy_id))
        if wallet_id:
            c.execute('UPDATE wallets SET proxy=? WHERE id=?', (proxy_val, wallet_id))


def unassign_proxy(proxy_id):
    with _conn() as c:
        row = c.execute('SELECT proxy, wallet_id FROM proxies WHERE id=?', (proxy_id,)).fetchone()
        if not row:
            return
        if row['wallet_id']:
            c.execute('UPDATE wallets SET proxy=NULL WHERE id=? AND proxy=?', (row['wallet_id'], row['proxy']))
        c.execute('UPDATE proxies SET wallet_id=NULL WHERE id=?', (proxy_id,))


def delete_proxy(proxy_id):
    with _conn() as c:
        row = c.execute('SELECT proxy, wallet_id FROM proxies WHERE id=?', (proxy_id,)).fetchone()
        if row and row['wallet_id']:
            c.execute('UPDATE wallets SET proxy=NULL WHERE id=? AND proxy=?', (row['wallet_id'], row['proxy']))
        c.execute('DELETE FROM proxies WHERE id=?', (proxy_id,))


def update_proxy_label(proxy_id, label):
    with _conn() as c:
        c.execute('UPDATE proxies SET label=? WHERE id=?', (label or '', proxy_id))


def sync_proxies():
    """Sync proxies.wallet_id with wallets.proxy in both directions."""
    with _conn() as c:
        # 1. Link proxies to wallets that already have matching proxy string
        c.execute('''
            UPDATE proxies SET wallet_id = (
                SELECT id FROM wallets WHERE wallets.proxy = proxies.proxy LIMIT 1
            )
            WHERE wallet_id IS NULL
        ''')
        # 2. Clear proxy links where wallet no longer has that proxy string
        c.execute('''
            UPDATE proxies SET wallet_id = NULL
            WHERE wallet_id IS NOT NULL
              AND (SELECT proxy FROM wallets WHERE id = proxies.wallet_id) != proxies.proxy
        ''')


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
        return [dict(r) for r in c.execute('SELECT * FROM positions ORDER BY created_at DESC, id DESC').fetchall()]


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


def update_hl_account_group(aid, group_name):
    with _conn() as c:
        c.execute('UPDATE hl_accounts SET group_name=? WHERE id=?',
                  (group_name or None, aid))


def get_nado_accounts():
    with _conn() as c:
        return [dict(r) for r in c.execute('SELECT * FROM nado_accounts ORDER BY created_at ASC').fetchall()]

def add_nado_account(label, address):
    with _conn() as c:
        c.execute('INSERT OR IGNORE INTO nado_accounts (label, address) VALUES (?,?)', (label, address))

def delete_nado_account(aid):
    with _conn() as c:
        c.execute('DELETE FROM nado_accounts WHERE id=?', (aid,))

def update_nado_account_group(aid, group_name):
    with _conn() as c:
        c.execute('UPDATE nado_accounts SET group_name=? WHERE id=?',
                  (group_name or None, aid))


def get_extended_accounts():
    with _conn() as c:
        return [dict(r) for r in c.execute('SELECT * FROM extended_accounts ORDER BY created_at ASC').fetchall()]

def add_extended_account(label, api_key):
    with _conn() as c:
        c.execute('INSERT OR IGNORE INTO extended_accounts (label, api_key) VALUES (?,?)', (label, api_key))

def delete_extended_account(aid):
    with _conn() as c:
        c.execute('DELETE FROM extended_accounts WHERE id=?', (aid,))

def update_extended_account_group(aid, group_name):
    with _conn() as c:
        c.execute('UPDATE extended_accounts SET group_name=? WHERE id=?', (group_name or None, aid))


def get_pacifica_accounts():
    with _conn() as c:
        return [dict(r) for r in c.execute('SELECT * FROM pacifica_accounts ORDER BY created_at ASC').fetchall()]

def add_pacifica_account(label, address):
    with _conn() as c:
        c.execute('INSERT OR IGNORE INTO pacifica_accounts (label, address) VALUES (?,?)', (label, address))

def delete_pacifica_account(aid):
    with _conn() as c:
        c.execute('DELETE FROM pacifica_accounts WHERE id=?', (aid,))

def update_pacifica_account_group(aid, group_name):
    with _conn() as c:
        c.execute('UPDATE pacifica_accounts SET group_name=? WHERE id=?', (group_name or None, aid))


def get_hl_accounts_from_profile(profile_name):
    """Read HL accounts from another profile's DB (read-only)."""
    path = os.path.join(_DATA_DIR, f'{profile_name}.db')
    if not os.path.exists(path):
        return []
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute('SELECT label, address FROM hl_accounts ORDER BY created_at ASC').fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def bulk_add_hl_accounts(accounts):
    """accounts: list of {label, address}. Returns count added."""
    added = 0
    with _conn() as c:
        for acc in accounts:
            try:
                cur = c.execute('INSERT OR IGNORE INTO hl_accounts (label, address) VALUES (?,?)',
                                (acc['label'], acc['address']))
                if cur.rowcount:
                    added += 1
            except Exception:
                pass
    return added


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


# ── Protocol weeks ─────────────────────────────────────────────────────────────

def get_protocol_weeks(protocol):
    with _conn() as c:
        weeks = c.execute(
            'SELECT * FROM protocol_weeks WHERE protocol=? ORDER BY week_start DESC',
            (protocol,)
        ).fetchall()
        result = []
        for w in weeks:
            ws = w['week_start']
            stats = c.execute('''
                SELECT
                    COALESCE(SUM(wp.points), 0)         AS total_points,
                    COALESCE(SUM(wp.wallet_balance), 0) AS total_balance,
                    COUNT(DISTINCT wp.wallet_id)         AS wallet_count,
                    COALESCE(SUM(
                        COALESCE(
                            wp.start_balance,
                            (SELECT p2.wallet_balance FROM weekly_points p2
                             WHERE p2.wallet_id=wp.wallet_id AND p2.protocol=wp.protocol
                               AND p2.week < ?
                             ORDER BY p2.week DESC LIMIT 1),
                            wpr.deposit, 0
                        )
                    ), 0) AS total_start_balance
                FROM weekly_points wp
                JOIN wallet_protocols wpr
                  ON wpr.wallet_id=wp.wallet_id AND wpr.protocol=wp.protocol
                WHERE wp.protocol=? AND wp.week=?
            ''', (ws, protocol, ws)).fetchone()
            row = dict(w)
            pts   = stats['total_points'] or 0
            bal   = stats['total_balance'] or 0
            start = stats['total_start_balance'] or 0
            spent = max(0, start - bal)
            row['total_points']        = pts
            row['total_balance']       = bal
            row['total_start_balance'] = start
            row['wallet_count']        = stats['wallet_count'] or 0
            row['total_spent']         = spent
            row['price_per_point']     = round(spent / pts, 6) if pts > 0 else 0
            result.append(row)
        return result


def update_protocol_week(wid, week_start, week_end):
    with _conn() as c:
        c.execute(
            'UPDATE protocol_weeks SET week_start=?, week_end=? WHERE id=?',
            (week_start, week_end, wid)
        )


def add_protocol_week(protocol, week_start, week_end):
    with _conn() as c:
        c.execute(
            'INSERT INTO protocol_weeks (protocol, week_start, week_end) VALUES (?,?,?)',
            (protocol, week_start, week_end)
        )
        return c.execute('SELECT last_insert_rowid()').fetchone()[0]


def delete_protocol_week(wid):
    with _conn() as c:
        row = c.execute('SELECT protocol, week_start FROM protocol_weeks WHERE id=?', (wid,)).fetchone()
        if row:
            protocol = row['protocol']
            week = row['week_start']

            # Collect wallets that have data in this week
            affected = [r['wallet_id'] for r in c.execute(
                'SELECT DISTINCT wallet_id FROM weekly_points WHERE protocol=? AND week=?',
                (protocol, week)
            ).fetchall()]

            c.execute('DELETE FROM weekly_points WHERE protocol=? AND week=?', (protocol, week))
            c.execute('DELETE FROM protocol_weeks WHERE id=?', (wid,))

            # Recalculate wallet_protocols from remaining weekly_points for affected wallets only.
            # Wallets imported directly (not via weekly_points) are not in affected → untouched.
            if affected:
                for wallet_id in affected:
                    latest = c.execute('''
                        SELECT wallet_balance, wp_earned, points
                        FROM weekly_points
                        WHERE wallet_id=? AND protocol=?
                        ORDER BY week DESC LIMIT 1
                    ''', (wallet_id, protocol)).fetchone()

                    first = c.execute('''
                        SELECT start_balance
                        FROM weekly_points
                        WHERE wallet_id=? AND protocol=?
                        ORDER BY week ASC LIMIT 1
                    ''', (wallet_id, protocol)).fetchone()

                    if latest:
                        deposit = (first['start_balance'] or 0) if first else 0
                        total_points = c.execute(
                            'SELECT COALESCE(SUM(points), 0) AS s FROM weekly_points WHERE wallet_id=? AND protocol=?',
                            (wallet_id, protocol)
                        ).fetchone()['s']
                        c.execute('''
                            UPDATE wallet_protocols
                            SET wallet_balance=?, wp_earned=?, wp_points=?, deposit=?
                            WHERE wallet_id=? AND protocol=?
                        ''', (latest['wallet_balance'], latest['wp_earned'], total_points,
                              deposit, wallet_id, protocol))
                    else:
                        c.execute('''
                            UPDATE wallet_protocols
                            SET wallet_balance=0, wp_earned=0, wp_points=0, deposit=0
                            WHERE wallet_id=? AND protocol=?
                        ''', (wallet_id, protocol))
        else:
            c.execute('DELETE FROM protocol_weeks WHERE id=?', (wid,))


def clear_protocol_wallet_data(protocol):
    """Zero out all wallet_protocols financial data for a protocol."""
    with _conn() as c:
        c.execute('''
            UPDATE wallet_protocols
            SET wallet_balance=0, wp_earned=0, wp_points=0, deposit=0
            WHERE protocol=?
        ''', (protocol,))


def get_week_wallets(protocol, week_start):
    """Return wallets with their weekly snapshot data for the given week.
    deposit_this_week = previous week's balance_end (or original deposit for first week).
    """
    with _conn() as c:
        rows = c.execute('''
            SELECT w.id, w.address, w.label,
                   COALESCE(wp.points, 0)         AS points,
                   COALESCE(wp.wallet_balance, 0) AS wallet_balance,
                   COALESCE(wp.wp_earned, 0)      AS wp_earned,
                   COALESCE(
                       wp.start_balance,
                       (SELECT prev.wallet_balance
                        FROM weekly_points prev
                        WHERE prev.wallet_id = w.id
                          AND prev.protocol = ?
                          AND prev.week < ?
                        ORDER BY prev.week DESC LIMIT 1),
                       wpr.deposit,
                       0
                   ) AS deposit_this_week
            FROM wallets w
            JOIN wallet_protocols wpr ON wpr.wallet_id = w.id AND wpr.protocol = ?
            LEFT JOIN weekly_points wp ON wp.wallet_id = w.id
                AND wp.protocol = ? AND wp.week = ?
            ORDER BY w.label ASC, w.address ASC
        ''', (protocol, week_start, protocol, protocol, week_start)).fetchall()
        return [dict(r) for r in rows]


def get_telegram_config() -> dict:
    with _conn() as c:
        row = c.execute('SELECT * FROM telegram_config WHERE id=1').fetchone()
        if row:
            return dict(row)
        return {
            'id': 1, 'bot_token': '', 'chat_id': '',
            'alert_threshold_pct': 10.0, 'alert_cooldown_minutes': 60,
            'report_interval_minutes': 60, 'check_interval_minutes': 5,
            'alerts_enabled': 1, 'reports_enabled': 1, 'enabled': 0,
        }


def set_telegram_config(**kwargs) -> None:
    allowed = {
        'bot_token', 'chat_id', 'alert_threshold_pct', 'alert_cooldown_minutes',
        'report_interval_minutes', 'check_interval_minutes',
        'alerts_enabled', 'reports_enabled', 'enabled',
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    with _conn() as c:
        exists = c.execute('SELECT 1 FROM telegram_config WHERE id=1').fetchone()
        if exists:
            sets = ', '.join(f'{k}=?' for k in fields)
            c.execute(f'UPDATE telegram_config SET {sets} WHERE id=1', list(fields.values()))
        else:
            cols = ', '.join(['id'] + list(fields.keys()))
            placeholders = ', '.join(['1'] + ['?'] * len(fields))
            c.execute(f'INSERT INTO telegram_config ({cols}) VALUES ({placeholders})', list(fields.values()))
