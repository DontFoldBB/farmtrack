import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database


@pytest.fixture
def temp_db_path(tmp_path):
    original = database.DB_PATH
    database.DB_PATH = str(tmp_path / 'migration.db')
    yield database.DB_PATH
    database.DB_PATH = original


def test_positions_migration_preserves_existing_rows(temp_db_path):
    conn = sqlite3.connect(temp_db_path)
    conn.execute(
        '''
        CREATE TABLE positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL,
            collateral REAL NOT NULL,
            leverage REAL NOT NULL,
            entry_price REAL NOT NULL,
            coingecko_id TEXT,
            note TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        )
        '''
    )
    conn.execute(
        '''
        INSERT INTO positions
            (symbol, direction, collateral, leverage, entry_price, coingecko_id, note, created_at)
        VALUES
            (?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        ('BTC', 'long', 100.0, 5.0, 25000.0, 'bitcoin', 'legacy row', '2026-01-02 03:04:05'),
    )
    conn.commit()
    conn.close()

    database.init()

    rows = database.get_positions()
    assert len(rows) == 1
    assert rows[0]['symbol'] == 'BTC'
    assert rows[0]['direction'] == 'long'
    assert rows[0]['collateral'] == 100.0
    assert rows[0]['leverage'] == 5.0
    assert rows[0]['entry_price'] == 25000.0
    assert rows[0]['note'] == 'legacy row'


def test_old_wallets_schema_migration_preserves_protocol_links_and_wallet_fields(temp_db_path):
    conn = sqlite3.connect(temp_db_path)
    conn.executescript(
        '''
        CREATE TABLE protocols (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            spent REAL DEFAULT 0,
            earned REAL DEFAULT 0,
            status TEXT DEFAULT 'фармлю',
            note TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE wallets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            address TEXT NOT NULL UNIQUE,
            label TEXT DEFAULT '',
            protocol TEXT DEFAULT NULL,
            balance REAL DEFAULT NULL,
            volume REAL DEFAULT NULL,
            burn REAL DEFAULT NULL,
            points REAL DEFAULT NULL,
            p_price REAL DEFAULT NULL,
            sync_at TEXT DEFAULT NULL,
            proxy TEXT DEFAULT NULL,
            chain TEXT DEFAULT NULL,
            added_at TEXT DEFAULT (datetime('now'))
        );
        INSERT INTO protocols (name) VALUES ('Proto');
        INSERT INTO wallets
            (address, label, protocol, balance, volume, burn, points, p_price, sync_at, proxy, chain, added_at)
        VALUES
            ('0x1111111111111111111111111111111111111111', 'seed', 'Proto', 12.5, 3.0, 1.0, 9.0, 0.25, '2026-01-02T03:04', 'http://proxy:1', 'evm', '2026-01-01 00:00:00');
        '''
    )
    conn.commit()
    conn.close()

    database.init()

    wallets = database.get_wallets(protocol='Proto')
    assert len(wallets) == 1
    wallet = wallets[0]
    assert wallet['label'] == 'seed'
    assert wallet['balance'] == 12.5
    assert wallet['volume'] == 3.0
    assert wallet['burn'] == 1.0
    assert wallet['points'] == 9.0
    assert wallet['p_price'] == 0.25
    assert wallet['sync_at'] == '2026-01-02T03:04'
    assert wallet['proxy'] == 'http://proxy:1'
    assert wallet['chain'] == 'evm'
    assert wallet['protocols'] == ['Proto']
