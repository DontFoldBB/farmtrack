import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database
from database import _detect_chain


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def db(tmp_path):
    """Each test gets a fresh isolated SQLite database."""
    original = database.DB_PATH
    database.DB_PATH = str(tmp_path / 'test.db')
    database.init()
    yield
    database.DB_PATH = original


# ── _detect_chain ──────────────────────────────────────────────────────────────

class TestDetectChain:
    def test_evm(self):
        assert _detect_chain('0xAbCd1234567890AbCd1234567890AbCd12345678') == 'evm'
        assert _detect_chain('0xabcdef1234567890abcdef1234567890abcdef12') == 'evm'

    def test_aptos(self):
        assert _detect_chain('0x' + 'a' * 64) == 'apt'

    def test_starknet(self):
        assert _detect_chain('0x' + 'b' * 62) == 'stark'
        assert _detect_chain('0x' + 'b' * 63) == 'stark'

    def test_tron(self):
        # T + 33 valid base58 chars (set [1-9A-HJ-NP-Za-km-z], 'a' is valid)
        assert _detect_chain('T' + 'a' * 33) == 'trx'

    def test_solana(self):
        assert _detect_chain('So11111111111111111111111111111111111111112') == 'sol'

    def test_solana_all_ones_misdetected_as_btc(self):
        # Known limitation: '1' * 32 matches the Bitcoin regex (starts with [13])
        # before reaching the Solana fallback. This is a bug in _detect_chain.
        assert _detect_chain('11111111111111111111111111111111') == 'btc'

    def test_bitcoin_bech32(self):
        assert _detect_chain('bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq') == 'btc'

    def test_bitcoin_legacy(self):
        # Genesis block coinbase address
        assert _detect_chain('1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf') == 'btc'

    def test_cosmos(self):
        assert _detect_chain('cosmos1' + 'a' * 38) == 'cosmos'

    def test_garbage_returns_none(self):
        assert _detect_chain('garbage') is None
        assert _detect_chain('not-an-address') is None
        assert _detect_chain('12345') is None

    def test_empty_returns_none(self):
        assert _detect_chain('') is None
        assert _detect_chain(None) is None
        assert _detect_chain('   ') is None

    def test_whitespace_stripped(self):
        # Spaces around a valid EVM address should still be detected
        assert _detect_chain('  0xAbCd1234567890AbCd1234567890AbCd12345678  ') == 'evm'

    def test_evm_wrong_length_not_matched(self):
        # 0x + 39 hex chars → not EVM (too short), not Stark (too short), falls through
        assert _detect_chain('0x' + 'a' * 39) is None
        # 0x + 41 hex chars → not EVM, not Stark, not Aptos
        assert _detect_chain('0x' + 'a' * 41) is None


# ── import_protocol_wallet_data ────────────────────────────────────────────────

# Realistic EVM address used across all import tests
ADDR = '0x1111222233334444555566667777888899990000'


class TestImportMatching:
    def _setup(self, addr=ADDR):
        database.add_protocol('Proto')
        database.bulk_add_wallets([addr], protocols=['Proto'])

    def test_exact_match(self, db):
        self._setup()
        result = database.import_protocol_wallet_data('Proto', [
            {'address': ADDR, 'wallet_balance': 100.0}
        ])
        assert result['matched'] == 1
        assert result['unmatched'] == []

    def test_exact_match_case_insensitive(self, db):
        self._setup()
        result = database.import_protocol_wallet_data('Proto', [
            {'address': ADDR.upper(), 'wallet_balance': 42.0}
        ])
        assert result['matched'] == 1

    def test_shortened_dotdot(self, db):
        self._setup()
        short = ADDR[:6] + '..' + ADDR[-4:]
        result = database.import_protocol_wallet_data('Proto', [
            {'address': short, 'wallet_balance': 55.0}
        ])
        assert result['matched'] == 1
        assert result['unmatched'] == []

    def test_shortened_three_dots(self, db):
        self._setup()
        short = ADDR[:6] + '...' + ADDR[-4:]
        result = database.import_protocol_wallet_data('Proto', [
            {'address': short, 'wallet_balance': 55.0}
        ])
        assert result['matched'] == 1

    def test_shortened_unicode_ellipsis(self, db):
        self._setup()
        short = ADDR[:6] + '…' + ADDR[-4:]  # … character
        result = database.import_protocol_wallet_data('Proto', [
            {'address': short, 'wallet_balance': 55.0}
        ])
        assert result['matched'] == 1

    def test_unmatched_shortened_address(self, db):
        self._setup()
        wrong = '0xDEAD' + '..' + 'BEEF'
        result = database.import_protocol_wallet_data('Proto', [
            {'address': wrong, 'wallet_balance': 1.0}
        ])
        assert result['matched'] == 0
        assert len(result['unmatched']) == 1

    def test_new_full_address_auto_added_to_protocol(self, db):
        database.add_protocol('Proto')
        new = '0xAAAABBBBCCCCDDDDEEEEFFFF0000111122223333'
        result = database.import_protocol_wallet_data('Proto', [
            {'address': new, 'wallet_balance': 77.0}
        ])
        assert result['matched'] == 1
        wallets = database.get_protocol_wallets_detail('Proto')
        assert len(wallets) == 1
        assert wallets[0]['wallet_balance'] == 77.0

    def test_empty_address_skipped(self, db):
        self._setup()
        result = database.import_protocol_wallet_data('Proto', [
            {'address': '', 'wallet_balance': 1.0},
            {'address': '   ', 'wallet_balance': 1.0},
        ])
        assert result['matched'] == 0

    def test_multiple_wallets_all_matched(self, db):
        a1 = '0x1111111111111111111111111111111111111111'
        a2 = '0x2222222222222222222222222222222222222222'
        database.add_protocol('Proto')
        database.bulk_add_wallets([a1, a2], protocols=['Proto'])
        result = database.import_protocol_wallet_data('Proto', [
            {'address': a1, 'wallet_balance': 10.0},
            {'address': a2, 'wallet_balance': 20.0},
        ])
        assert result['matched'] == 2
        assert result['unmatched'] == []

    def test_partial_match_some_unmatched(self, db):
        self._setup()
        result = database.import_protocol_wallet_data('Proto', [
            {'address': ADDR, 'wallet_balance': 10.0},
            {'address': '0xDEAD..BEEF', 'wallet_balance': 5.0},
        ])
        assert result['matched'] == 1
        assert len(result['unmatched']) == 1


class TestImportValues:
    def _setup(self):
        database.add_protocol('Proto')
        database.bulk_add_wallets([ADDR], protocols=['Proto'])

    def test_sets_wallet_balance(self, db):
        self._setup()
        database.import_protocol_wallet_data('Proto', [
            {'address': ADDR, 'wallet_balance': 123.45}
        ])
        wallets = database.get_protocol_wallets_detail('Proto')
        assert wallets[0]['wallet_balance'] == 123.45

    def test_sets_deposit(self, db):
        self._setup()
        database.import_protocol_wallet_data('Proto', [
            {'address': ADDR, 'deposit': 500.0}
        ])
        wallets = database.get_protocol_wallets_detail('Proto')
        assert wallets[0]['deposit'] == 500.0

    def test_replaces_points_by_default(self, db):
        self._setup()
        database.import_protocol_wallet_data('Proto', [{'address': ADDR, 'wp_points': 100.0}])
        database.import_protocol_wallet_data('Proto', [{'address': ADDR, 'wp_points': 50.0}])
        wallets = database.get_protocol_wallets_detail('Proto')
        assert wallets[0]['wp_points'] == 50.0

    def test_add_points_accumulates(self, db):
        self._setup()
        database.import_protocol_wallet_data('Proto', [{'address': ADDR, 'wp_points': 100.0}], add_points=True)
        database.import_protocol_wallet_data('Proto', [{'address': ADDR, 'wp_points': 50.0}], add_points=True)
        wallets = database.get_protocol_wallets_detail('Proto')
        assert wallets[0]['wp_points'] == 150.0

    def test_add_deposit_accumulates(self, db):
        self._setup()
        database.import_protocol_wallet_data('Proto', [{'address': ADDR, 'deposit': 200.0}], add_deposit=True)
        database.import_protocol_wallet_data('Proto', [{'address': ADDR, 'deposit': 100.0}], add_deposit=True)
        wallets = database.get_protocol_wallets_detail('Proto')
        assert wallets[0]['deposit'] == 300.0

    def test_second_import_overwrites_balance(self, db):
        self._setup()
        database.import_protocol_wallet_data('Proto', [{'address': ADDR, 'wallet_balance': 100.0}])
        database.import_protocol_wallet_data('Proto', [{'address': ADDR, 'wallet_balance': 200.0}])
        wallets = database.get_protocol_wallets_detail('Proto')
        assert wallets[0]['wallet_balance'] == 200.0


# ── bulk_add_wallets ───────────────────────────────────────────────────────────

class TestBulkAddWallets:
    def test_adds_wallets(self, db):
        added = database.bulk_add_wallets(['0x1111111111111111111111111111111111111111'])
        assert added == 1

    def test_detects_chain_on_add(self, db):
        database.bulk_add_wallets(['0x1111111111111111111111111111111111111111'])
        wallets = database.get_wallets()
        assert wallets[0]['chain'] == 'evm'

    def test_duplicate_skipped(self, db):
        addr = '0x1111111111111111111111111111111111111111'
        database.bulk_add_wallets([addr])
        added = database.bulk_add_wallets([addr])
        assert added == 0
        assert len(database.get_wallets()) == 1

    def test_assigns_protocol(self, db):
        database.add_protocol('P1')
        database.bulk_add_wallets(['0x1111111111111111111111111111111111111111'], protocols=['P1'])
        wallets = database.get_wallets(protocol='P1')
        assert len(wallets) == 1

    def test_empty_lines_skipped(self, db):
        added = database.bulk_add_wallets(['', '   ', '\n'])
        assert added == 0


# ── get_stats (Overview) ───────────────────────────────────────────────────────

class TestGetStats:
    def test_empty_db(self, db):
        s = database.get_stats()
        assert s['total'] == 0
        assert s['total_wallets'] == 0
        assert s['total_deposit'] == 0.0
        assert s['total_balance'] == 0.0
        assert s['total_spent'] == 0.0
        assert s['pnl'] == 0.0

    def test_pnl_with_loss(self, db):
        # deposit=100, balance=80 → pnl = -20, spent = 20
        database.add_protocol('P')
        database.bulk_add_wallets([ADDR], protocols=['P'])
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'deposit': 100.0, 'wallet_balance': 80.0}
        ])
        s = database.get_stats()
        assert s['total_deposit'] == 100.0
        assert s['total_balance'] == 80.0
        assert s['total_spent'] == 20.0
        assert s['pnl'] == -20.0

    def test_pnl_with_profit(self, db):
        # deposit=100, balance=100, earned=50 → pnl = +50, spent = 0
        database.add_protocol('P')
        database.bulk_add_wallets([ADDR], protocols=['P'])
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'deposit': 100.0, 'wallet_balance': 100.0, 'wp_earned': 50.0}
        ])
        s = database.get_stats()
        assert s['pnl'] == 50.0
        assert s['total_spent'] == 0.0

    def test_manual_spent_protocol_no_wallets(self, db):
        # Protocol with manual spent, no wallet data → shows in total_spent
        database.add_protocol('P', spent=75.0)
        s = database.get_stats()
        assert s['total_spent'] == 75.0

    def test_wallet_count(self, db):
        database.bulk_add_wallets([
            '0x1111111111111111111111111111111111111111',
            '0x2222222222222222222222222222222222222222',
        ])
        s = database.get_stats()
        assert s['total_wallets'] == 2

    def test_active_protocol_count(self, db):
        database.add_protocol('A', status='фармлю')
        database.add_protocol('B', status='фармлю')
        database.add_protocol('C', status='done')
        s = database.get_stats()
        assert s['total'] == 3
        assert s['active'] == 2


# ── Protocol CRUD ──────────────────────────────────────────────────────────────

class TestProtocolCRUD:
    def test_add_and_get(self, db):
        database.add_protocol('Scroll', spent=10.0, status='фармлю')
        protos = database.get_protocols()
        assert len(protos) == 1
        assert protos[0]['name'] == 'Scroll'

    def test_update(self, db):
        database.add_protocol('Scroll')
        pid = database.get_protocols()[0]['id']
        database.update_protocol(pid, spent=50.0, earned=20.0, status='done', note='finished')
        p = database.get_protocols()[0]
        assert p['spent'] == 50.0
        assert p['status'] == 'done'

    def test_delete_removes_wallet_links(self, db):
        database.add_protocol('P')
        database.bulk_add_wallets([ADDR], protocols=['P'])
        pid = database.get_protocols()[0]['id']
        database.delete_protocol(pid)
        # Wallet stays, but link to protocol is gone
        wallets = database.get_wallets()
        assert len(wallets) == 1
        assert wallets[0]['protocols'] == []

    def test_delete_nonexistent_is_safe(self, db):
        database.delete_protocol(9999)  # should not raise

    def test_get_protocols_aggregates_wallet_balances(self, db):
        a1 = '0x1111111111111111111111111111111111111111'
        a2 = '0x2222222222222222222222222222222222222222'
        database.add_protocol('P')
        database.bulk_add_wallets([a1, a2], protocols=['P'])
        database.import_protocol_wallet_data('P', [
            {'address': a1, 'wallet_balance': 30.0},
            {'address': a2, 'wallet_balance': 70.0},
        ])
        p = database.get_protocols()[0]
        assert p['total_balance'] == 100.0
        assert p['wallet_count'] == 2


# ── Wallet CRUD ────────────────────────────────────────────────────────────────

class TestWalletCRUD:
    def test_delete_wallet_removes_protocol_links(self, db):
        database.add_protocol('P')
        database.bulk_add_wallets([ADDR], protocols=['P'])
        wid = database.get_wallets()[0]['id']
        database.delete_wallet(wid)
        assert database.get_wallets() == []
        assert database.get_protocol_wallets_detail('P') == []

    def test_set_wallet_protocols_replaces_all(self, db):
        database.add_protocol('P1')
        database.add_protocol('P2')
        database.add_protocol('P3')
        database.bulk_add_wallets([ADDR], protocols=['P1', 'P2'])
        wid = database.get_wallets()[0]['id']
        database.set_wallet_protocols(wid, ['P3'])
        w = database.get_wallets()[0]
        assert w['protocols'] == ['P3']

    def test_update_wallet_label(self, db):
        database.bulk_add_wallets([ADDR])
        wid = database.get_wallets()[0]['id']
        database.update_wallet_label(wid, 'main wallet')
        assert database.get_wallets()[0]['label'] == 'main wallet'

    def test_get_wallets_filter_by_chain(self, db):
        evm = '0x1111111111111111111111111111111111111111'
        sol = 'So11111111111111111111111111111111111111112'
        database.bulk_add_wallets([evm, sol])
        evm_wallets = database.get_wallets(chain='evm')
        sol_wallets = database.get_wallets(chain='sol')
        assert len(evm_wallets) == 1
        assert len(sol_wallets) == 1

    def test_get_wallets_unassigned_only(self, db):
        database.add_protocol('P')
        a1 = '0x1111111111111111111111111111111111111111'
        a2 = '0x2222222222222222222222222222222222222222'
        database.bulk_add_wallets([a1], protocols=['P'])
        database.bulk_add_wallets([a2])
        unassigned = database.get_wallets(unassigned_only=True)
        assert len(unassigned) == 1
        assert unassigned[0]['address'] == a2


# ── Weekly snapshots ───────────────────────────────────────────────────────────

WEEK1 = '2026-01-05'
WEEK2 = '2026-01-12'


class TestWeeklySnapshots:
    def _setup(self):
        database.add_protocol('P')
        database.bulk_add_wallets([ADDR], protocols=['P'])

    def test_first_week_sets_deposit(self, db):
        self._setup()
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'deposit': 100.0, 'wallet_balance': 95.0, 'wp_points': 500.0}
        ], week=WEEK1)
        wallets = database.get_week_wallets('P', WEEK1)
        assert wallets[0]['wallet_balance'] == 95.0
        assert wallets[0]['deposit_this_week'] == 100.0

    def test_second_week_deposit_delta(self, db):
        self._setup()
        # Week 1: deposit 100, balance ends at 95
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'deposit': 100.0, 'wallet_balance': 95.0}
        ], week=WEEK1)
        # Week 2: balance starts 95, now 90 (withdraw 5) → delta = 90-95 = -5 → deposit += -5
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'deposit': 90.0, 'wallet_balance': 88.0}
        ], week=WEEK2)
        wp = database.get_protocol_wallets_detail('P')
        # total deposit = 100 + (90-95) = 95
        assert wp[0]['deposit'] == 95.0

    def test_weekly_points_sum_across_weeks(self, db):
        self._setup()
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'wallet_balance': 100.0, 'wp_points': 200.0}
        ], week=WEEK1)
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'wallet_balance': 100.0, 'wp_points': 300.0}
        ], week=WEEK2)
        wp = database.get_protocol_wallets_detail('P')
        assert wp[0]['wp_points'] == 500.0

    def test_reimport_same_week_updates_balance(self, db):
        self._setup()
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'wallet_balance': 100.0, 'wp_points': 100.0}
        ], week=WEEK1)
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'wallet_balance': 120.0, 'wp_points': 150.0}
        ], week=WEEK1)
        wallets = database.get_week_wallets('P', WEEK1)
        assert wallets[0]['wallet_balance'] == 120.0

    def test_get_weekly_summary(self, db):
        self._setup()
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'wp_points': 100.0, 'wallet_balance': 90.0}
        ], week=WEEK1)
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'wp_points': 200.0, 'wallet_balance': 85.0}
        ], week=WEEK2)
        summary = database.get_weekly_summary('P')
        assert len(summary) == 2
        weeks = {s['week']: s for s in summary}
        assert weeks[WEEK1]['total_points'] == 100.0
        assert weeks[WEEK2]['total_points'] == 200.0

    def test_protocol_week_add_and_delete(self, db):
        self._setup()
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'wallet_balance': 100.0, 'wp_points': 500.0}
        ], week=WEEK1)
        wid = database.add_protocol_week('P', WEEK1, WEEK1)
        weeks = database.get_protocol_weeks('P')
        assert len(weeks) == 1
        database.delete_protocol_week(wid)
        # After deleting week, wallet_protocols should be zeroed
        wp = database.get_protocol_wallets_detail('P')
        assert wp[0]['wp_points'] == 0.0
        assert wp[0]['wallet_balance'] == 0.0


# ── import_balances ────────────────────────────────────────────────────────────

class TestImportBalances:
    def test_matches_by_prefix_suffix(self, db):
        database.bulk_add_wallets([ADDR])
        short = ADDR[:6] + '..' + ADDR[-4:]
        result = database.import_balances([
            {'address_short': short, 'balance': 99.0, 'volume': None,
             'burn': None, 'points': None, 'p_price': None}
        ])
        assert result == 1

    def test_skips_non_shortened(self, db):
        database.bulk_add_wallets([ADDR])
        result = database.import_balances([
            {'address_short': ADDR, 'balance': 99.0, 'volume': None,
             'burn': None, 'points': None, 'p_price': None}
        ])
        assert result == 0

    def test_no_match_returns_zero(self, db):
        database.bulk_add_wallets([ADDR])
        result = database.import_balances([
            {'address_short': '0xDEAD..BEEF', 'balance': 1.0, 'volume': None,
             'burn': None, 'points': None, 'p_price': None}
        ])
        assert result == 0


# ── Import edge cases ──────────────────────────────────────────────────────────

class TestImportEdgeCases:
    def test_two_wallets_same_prefix_correct_suffix_matched(self, db):
        """'0x1234..aaaa' must not hit the wallet ending in bbbb."""
        addr_a = '0x1234' + 'a' * 36   # ends aaaa
        addr_b = '0x1234' + 'b' * 36   # ends bbbb
        database.add_protocol('P')
        database.bulk_add_wallets([addr_a, addr_b], protocols=['P'])
        database.import_protocol_wallet_data('P', [
            {'address': '0x1234..aaaa', 'wallet_balance': 111.0},
        ])
        by_addr = {w['address']: w for w in database.get_protocol_wallets_detail('P')}
        assert by_addr[addr_a]['wallet_balance'] == 111.0
        assert by_addr[addr_b]['wallet_balance'] == 0.0

    def test_whitespace_around_address_trimmed(self, db):
        database.add_protocol('P')
        database.bulk_add_wallets([ADDR], protocols=['P'])
        result = database.import_protocol_wallet_data('P', [
            {'address': f'  {ADDR}  ', 'wallet_balance': 5.0}
        ])
        assert result['matched'] == 1

    def test_row_without_address_key_skipped(self, db):
        database.add_protocol('P')
        result = database.import_protocol_wallet_data('P', [{'wallet_balance': 10.0}])
        assert result['matched'] == 0

    def test_proxy_assigned_during_import(self, db):
        database.add_protocol('P')
        database.bulk_add_wallets([ADDR], protocols=['P'])
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'proxy': 'http://user:pass@1.2.3.4:8080'}
        ])
        assert database.get_wallets()[0]['proxy'] == 'http://user:pass@1.2.3.4:8080'

    def test_same_wallet_twice_in_one_import_last_balance_wins(self, db):
        database.add_protocol('P')
        database.bulk_add_wallets([ADDR], protocols=['P'])
        result = database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'wallet_balance': 100.0},
            {'address': ADDR, 'wallet_balance': 200.0},
        ])
        assert result['matched'] == 2
        assert database.get_protocol_wallets_detail('P')[0]['wallet_balance'] == 200.0

    def test_same_wallet_twice_add_points_accumulates(self, db):
        database.add_protocol('P')
        database.bulk_add_wallets([ADDR], protocols=['P'])
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'wp_points': 100.0},
            {'address': ADDR, 'wp_points': 50.0},
        ], add_points=True)
        assert database.get_protocol_wallets_detail('P')[0]['wp_points'] == 150.0

    def test_solana_address_shortened_match(self, db):
        sol = 'So11111111111111111111111111111111111111112'
        database.add_protocol('P')
        database.bulk_add_wallets([sol], protocols=['P'])
        result = database.import_protocol_wallet_data('P', [
            {'address': sol[:6] + '..' + sol[-4:], 'wallet_balance': 33.0}
        ])
        assert result['matched'] == 1

    def test_empty_rows_list(self, db):
        database.add_protocol('P')
        result = database.import_protocol_wallet_data('P', [])
        assert result == {'matched': 0, 'unmatched': []}

    def test_new_wallet_auto_created_gets_chain(self, db):
        database.add_protocol('P')
        database.import_protocol_wallet_data('P', [{'address': ADDR, 'wallet_balance': 1.0}])
        assert database.get_wallets()[0]['chain'] == 'evm'

    def test_existing_wallet_not_in_protocol_gets_linked(self, db):
        """Full address already in wallets but not in protocol → auto-linked."""
        database.add_protocol('P')
        database.bulk_add_wallets([ADDR])  # not assigned to P
        result = database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'wallet_balance': 42.0}
        ])
        assert result['matched'] == 1
        assert len(database.get_protocol_wallets_detail('P')) == 1


# ── Stats edge cases ───────────────────────────────────────────────────────────

class TestStatsEdgeCases:
    def test_protocol_with_zero_wallet_data_uses_manual_spent(self, db):
        """Wallet linked but all financial data = 0 → protocol.spent counts as manual."""
        database.add_protocol('P', spent=40.0)
        database.bulk_add_wallets([ADDR], protocols=['P'])
        # No financial import → deposit=0, balance=0, earned=0
        assert database.get_stats()['total_spent'] == 40.0

    def test_protocol_with_wallet_data_ignores_manual_spent(self, db):
        """Once wallet has financial data, protocol.spent is NOT double-counted."""
        database.add_protocol('P', spent=999.0)
        database.bulk_add_wallets([ADDR], protocols=['P'])
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'deposit': 100.0, 'wallet_balance': 80.0}
        ])
        s = database.get_stats()
        assert s['total_spent'] == 20.0   # 100-80, not 999

    def test_multiple_protocols_aggregated(self, db):
        a1 = '0x1111111111111111111111111111111111111111'
        a2 = '0x2222222222222222222222222222222222222222'
        database.add_protocol('P1')
        database.add_protocol('P2')
        database.bulk_add_wallets([a1], protocols=['P1'])
        database.bulk_add_wallets([a2], protocols=['P2'])
        database.import_protocol_wallet_data('P1', [
            {'address': a1, 'deposit': 100.0, 'wallet_balance': 90.0}
        ])
        database.import_protocol_wallet_data('P2', [
            {'address': a2, 'deposit': 200.0, 'wallet_balance': 180.0}
        ])
        s = database.get_stats()
        assert s['total_deposit'] == 300.0
        assert s['total_balance'] == 270.0
        assert s['total_spent'] == 30.0
        assert s['total_wallets'] == 2

    def test_spent_never_negative(self, db):
        """If balance > deposit (profit), spent = 0, not negative."""
        database.add_protocol('P')
        database.bulk_add_wallets([ADDR], protocols=['P'])
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'deposit': 100.0, 'wallet_balance': 150.0}
        ])
        assert database.get_stats()['total_spent'] == 0.0

    def test_pnl_includes_earned(self, db):
        database.add_protocol('P')
        database.bulk_add_wallets([ADDR], protocols=['P'])
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'deposit': 100.0, 'wallet_balance': 90.0, 'wp_earned': 30.0}
        ])
        s = database.get_stats()
        assert s['pnl'] == 20.0   # 30 + 90 - 100

    def test_get_wallet_counts_per_protocol(self, db):
        a1 = '0x1111111111111111111111111111111111111111'
        a2 = '0x2222222222222222222222222222222222222222'
        a3 = '0x3333333333333333333333333333333333333333'
        database.add_protocol('P1')
        database.add_protocol('P2')
        database.bulk_add_wallets([a1, a2], protocols=['P1'])
        database.bulk_add_wallets([a3], protocols=['P2'])
        counts = database.get_wallet_counts()
        assert counts['P1'] == 2
        assert counts['P2'] == 1


# ── Protocol CRUD extras ───────────────────────────────────────────────────────

class TestProtocolCRUDExtra:
    def test_add_protocol_to_wallets_bulk(self, db):
        a1 = '0x1111111111111111111111111111111111111111'
        a2 = '0x2222222222222222222222222222222222222222'
        database.add_protocol('P')
        database.bulk_add_wallets([a1, a2])
        ids = [w['id'] for w in database.get_wallets()]
        database.add_protocol_to_wallets(ids, 'P')
        assert len(database.get_wallets(protocol='P')) == 2

    def test_add_protocol_to_wallets_empty_protocol_noop(self, db):
        database.bulk_add_wallets([ADDR])
        wid = database.get_wallets()[0]['id']
        database.add_protocol_to_wallets([wid], '')  # should not raise

    def test_update_wallet_protocol_deposit(self, db):
        database.add_protocol('P')
        database.bulk_add_wallets([ADDR], protocols=['P'])
        wid = database.get_wallets()[0]['id']
        database.update_wallet_protocol(wid, 'P', deposit=500.0)
        assert database.get_protocol_wallets_detail('P')[0]['deposit'] == 500.0

    def test_update_wallet_protocol_balance(self, db):
        database.add_protocol('P')
        database.bulk_add_wallets([ADDR], protocols=['P'])
        wid = database.get_wallets()[0]['id']
        database.update_wallet_protocol(wid, 'P', wallet_balance=333.0)
        assert database.get_protocol_wallets_detail('P')[0]['wallet_balance'] == 333.0

    def test_update_wallet_protocol_points_and_earned(self, db):
        database.add_protocol('P')
        database.bulk_add_wallets([ADDR], protocols=['P'])
        wid = database.get_wallets()[0]['id']
        database.update_wallet_protocol(wid, 'P', wp_points=1000.0, wp_earned=25.0)
        wp = database.get_protocol_wallets_detail('P')[0]
        assert wp['wp_points'] == 1000.0
        assert wp['wp_earned'] == 25.0

    def test_clear_protocol_wallet_data(self, db):
        database.add_protocol('P')
        database.bulk_add_wallets([ADDR], protocols=['P'])
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'deposit': 100.0, 'wallet_balance': 80.0, 'wp_points': 500.0}
        ])
        database.clear_protocol_wallet_data('P')
        wp = database.get_protocol_wallets_detail('P')[0]
        assert wp['deposit'] == 0.0
        assert wp['wallet_balance'] == 0.0
        assert wp['wp_points'] == 0.0


# ── Wallet CRUD extras ─────────────────────────────────────────────────────────

class TestWalletCRUDExtra:
    def test_update_wallet_proxy(self, db):
        database.bulk_add_wallets([ADDR])
        wid = database.get_wallets()[0]['id']
        database.update_wallet_proxy(wid, 'http://1.2.3.4:8080')
        assert database.get_wallets()[0]['proxy'] == 'http://1.2.3.4:8080'

    def test_update_wallet_proxy_to_none(self, db):
        database.bulk_add_wallets([ADDR])
        wid = database.get_wallets()[0]['id']
        database.update_wallet_proxy(wid, 'http://1.2.3.4:8080')
        database.update_wallet_proxy(wid, None)
        assert database.get_wallets()[0]['proxy'] is None

    def test_bulk_add_wallets_multiple_protocols(self, db):
        database.add_protocol('P1')
        database.add_protocol('P2')
        database.bulk_add_wallets([ADDR], protocols=['P1', 'P2'])
        w = database.get_wallets()[0]
        assert 'P1' in w['protocols']
        assert 'P2' in w['protocols']

    def test_get_wallets_by_protocol(self, db):
        a1 = '0x1111111111111111111111111111111111111111'
        a2 = '0x2222222222222222222222222222222222222222'
        database.add_protocol('P1')
        database.add_protocol('P2')
        database.bulk_add_wallets([a1], protocols=['P1'])
        database.bulk_add_wallets([a2], protocols=['P2'])
        p1_wallets = database.get_wallets(protocol='P1')
        assert len(p1_wallets) == 1
        assert p1_wallets[0]['address'] == a1

    def test_set_wallet_protocols_to_empty_removes_all(self, db):
        database.add_protocol('P1')
        database.bulk_add_wallets([ADDR], protocols=['P1'])
        wid = database.get_wallets()[0]['id']
        database.set_wallet_protocols(wid, [])
        assert database.get_wallets()[0]['protocols'] == []

    def test_bulk_add_existing_wallet_updates_label(self, db):
        database.bulk_add_wallets([ADDR], label='old')
        database.bulk_add_wallets([ADDR], label='new')
        assert database.get_wallets()[0]['label'] == 'new'


# ── Proxies ────────────────────────────────────────────────────────────────────

PROXY = 'http://user:pass@1.2.3.4:8080'
PROXY2 = 'http://user:pass@5.6.7.8:9090'


class TestProxies:
    def test_bulk_add(self, db):
        added = database.bulk_add_proxies([PROXY, PROXY2])
        assert added == 2
        assert len(database.get_proxies()) == 2

    def test_bulk_add_duplicate_skipped(self, db):
        database.bulk_add_proxies([PROXY])
        assert database.bulk_add_proxies([PROXY]) == 0

    def test_bulk_add_empty_lines_skipped(self, db):
        assert database.bulk_add_proxies(['', '  ', PROXY]) == 1

    def test_assign_links_both_tables(self, db):
        database.bulk_add_wallets([ADDR])
        database.bulk_add_proxies([PROXY])
        wid = database.get_wallets()[0]['id']
        pid = database.get_proxies()[0]['id']
        database.assign_proxy(pid, wid)
        assert database.get_proxies()[0]['wallet_id'] == wid
        assert database.get_wallets()[0]['proxy'] == PROXY

    def test_unassign_clears_both_tables(self, db):
        database.bulk_add_wallets([ADDR])
        database.bulk_add_proxies([PROXY])
        wid = database.get_wallets()[0]['id']
        pid = database.get_proxies()[0]['id']
        database.assign_proxy(pid, wid)
        database.unassign_proxy(pid)
        assert database.get_proxies()[0]['wallet_id'] is None
        assert database.get_wallets()[0]['proxy'] is None

    def test_delete_proxy_clears_wallet_field(self, db):
        database.bulk_add_wallets([ADDR])
        database.bulk_add_proxies([PROXY])
        wid = database.get_wallets()[0]['id']
        pid = database.get_proxies()[0]['id']
        database.assign_proxy(pid, wid)
        database.delete_proxy(pid)
        assert database.get_proxies() == []
        assert database.get_wallets()[0]['proxy'] is None

    def test_update_proxy_label(self, db):
        database.bulk_add_proxies([PROXY])
        pid = database.get_proxies()[0]['id']
        database.update_proxy_label(pid, 'main')
        assert database.get_proxies()[0]['label'] == 'main'

    def test_reassign_proxy_updates_old_wallet(self, db):
        """Assigning proxy to wallet B should clear it from wallet A."""
        a1 = '0x1111111111111111111111111111111111111111'
        a2 = '0x2222222222222222222222222222222222222222'
        database.bulk_add_wallets([a1, a2])
        database.bulk_add_proxies([PROXY])
        wallets = {w['address']: w['id'] for w in database.get_wallets()}
        pid = database.get_proxies()[0]['id']
        database.assign_proxy(pid, wallets[a1])
        database.assign_proxy(pid, wallets[a2])
        by_addr = {w['address']: w for w in database.get_wallets()}
        assert by_addr[a1]['proxy'] is None
        assert by_addr[a2]['proxy'] == PROXY

    def test_bulk_add_auto_links_existing_wallet_proxy(self, db):
        """If wallet already has proxy string, bulk_add_proxies should link them."""
        database.bulk_add_wallets([ADDR])
        wid = database.get_wallets()[0]['id']
        database.update_wallet_proxy(wid, PROXY)
        database.bulk_add_proxies([PROXY])
        proxy = database.get_proxies()[0]
        assert proxy['wallet_id'] == wid


# ── HL Accounts ────────────────────────────────────────────────────────────────

HL_ADDR = '0x' + 'a' * 40


class TestHLAccounts:
    def test_add_and_get(self, db):
        database.add_hl_account('main', HL_ADDR)
        accs = database.get_hl_accounts()
        assert len(accs) == 1
        assert accs[0]['label'] == 'main'
        assert accs[0]['address'] == HL_ADDR

    def test_duplicate_address_ignored(self, db):
        database.add_hl_account('main', HL_ADDR)
        database.add_hl_account('copy', HL_ADDR)
        assert len(database.get_hl_accounts()) == 1

    def test_delete(self, db):
        database.add_hl_account('main', HL_ADDR)
        aid = database.get_hl_accounts()[0]['id']
        database.delete_hl_account(aid)
        assert database.get_hl_accounts() == []

    def test_bulk_add(self, db):
        accounts = [
            {'label': 'a1', 'address': '0x' + '1' * 40},
            {'label': 'a2', 'address': '0x' + '2' * 40},
        ]
        assert database.bulk_add_hl_accounts(accounts) == 2
        assert len(database.get_hl_accounts()) == 2

    def test_bulk_add_duplicate_not_counted(self, db):
        database.add_hl_account('orig', HL_ADDR)
        assert database.bulk_add_hl_accounts([{'label': 'copy', 'address': HL_ADDR}]) == 0

    def test_update_group_name(self, db):
        database.add_hl_account('main', HL_ADDR)
        aid = database.get_hl_accounts()[0]['id']
        database.update_hl_account_group(aid, 'GroupA')
        assert database.get_hl_accounts()[0]['group_name'] == 'GroupA'

    def test_update_group_name_to_none(self, db):
        database.add_hl_account('main', HL_ADDR)
        aid = database.get_hl_accounts()[0]['id']
        database.update_hl_account_group(aid, 'GroupA')
        database.update_hl_account_group(aid, None)
        assert database.get_hl_accounts()[0]['group_name'] is None


# ── Nado / Extended / Pacifica accounts ───────────────────────────────────────

class TestNadoAccounts:
    def test_add_get_delete(self, db):
        database.add_nado_account('trader', HL_ADDR)
        assert len(database.get_nado_accounts()) == 1
        aid = database.get_nado_accounts()[0]['id']
        database.delete_nado_account(aid)
        assert database.get_nado_accounts() == []

    def test_duplicate_ignored(self, db):
        database.add_nado_account('a', HL_ADDR)
        database.add_nado_account('b', HL_ADDR)
        assert len(database.get_nado_accounts()) == 1

    def test_group_name(self, db):
        database.add_nado_account('a', HL_ADDR)
        aid = database.get_nado_accounts()[0]['id']
        database.update_nado_account_group(aid, 'G1')
        assert database.get_nado_accounts()[0]['group_name'] == 'G1'


class TestExtendedAccounts:
    def test_add_get_delete(self, db):
        database.add_extended_account('trader', 'secret-api-key-123')
        accs = database.get_extended_accounts()
        assert len(accs) == 1
        assert accs[0]['api_key'] == 'secret-api-key-123'
        database.delete_extended_account(accs[0]['id'])
        assert database.get_extended_accounts() == []

    def test_duplicate_api_key_ignored(self, db):
        database.add_extended_account('a', 'key')
        database.add_extended_account('b', 'key')
        assert len(database.get_extended_accounts()) == 1

    def test_group_name(self, db):
        database.add_extended_account('a', 'key')
        aid = database.get_extended_accounts()[0]['id']
        database.update_extended_account_group(aid, 'G2')
        assert database.get_extended_accounts()[0]['group_name'] == 'G2'


class TestPacificaAccounts:
    def test_add_get_delete(self, db):
        database.add_pacifica_account('main', HL_ADDR)
        assert len(database.get_pacifica_accounts()) == 1
        aid = database.get_pacifica_accounts()[0]['id']
        database.delete_pacifica_account(aid)
        assert database.get_pacifica_accounts() == []

    def test_group_name(self, db):
        database.add_pacifica_account('a', HL_ADDR)
        aid = database.get_pacifica_accounts()[0]['id']
        database.update_pacifica_account_group(aid, 'G3')
        assert database.get_pacifica_accounts()[0]['group_name'] == 'G3'


# ── Positions ──────────────────────────────────────────────────────────────────

class TestPositions:
    def test_add_and_get(self, db):
        database.add_position('BTC', 'long', 1000.0, 10.0, 95000.0)
        p = database.get_positions()[0]
        assert p['symbol'] == 'BTC'
        assert p['direction'] == 'long'
        assert p['collateral'] == 1000.0
        assert p['leverage'] == 10.0
        assert p['entry_price'] == 95000.0

    def test_symbol_uppercased(self, db):
        database.add_position('eth', 'short', 500.0, 5.0, 3000.0)
        assert database.get_positions()[0]['symbol'] == 'ETH'

    def test_update(self, db):
        database.add_position('BTC', 'long', 1000.0, 10.0, 95000.0)
        pid = database.get_positions()[0]['id']
        database.update_position(pid, 'ETH', 'short', 500.0, 5.0, 3000.0, note='test')
        p = database.get_positions()[0]
        assert p['symbol'] == 'ETH'
        assert p['direction'] == 'short'
        assert p['note'] == 'test'

    def test_delete(self, db):
        database.add_position('BTC', 'long', 100.0, 5.0, 90000.0)
        pid = database.get_positions()[0]['id']
        database.delete_position(pid)
        assert database.get_positions() == []

    def test_multiple_positions_ordered_newest_first(self, db):
        database.add_position('BTC', 'long', 100.0, 5.0, 90000.0)
        database.add_position('ETH', 'short', 50.0, 3.0, 3000.0)
        positions = database.get_positions()
        assert positions[0]['symbol'] == 'ETH'  # newest first

    def test_with_group_id(self, db):
        gid = database.add_position_group('Alpha')
        database.add_position('BTC', 'long', 100.0, 5.0, 90000.0, group_id=gid)
        assert database.get_positions()[0]['group_id'] == gid

    def test_note_stored(self, db):
        database.add_position('BTC', 'long', 100.0, 5.0, 90000.0, note='hedge')
        assert database.get_positions()[0]['note'] == 'hedge'


# ── Position groups ────────────────────────────────────────────────────────────

class TestPositionGroups:
    def test_add_and_get(self, db):
        database.add_position_group('Alpha')
        groups = database.get_position_groups()
        assert len(groups) == 1
        assert groups[0]['name'] == 'Alpha'

    def test_add_returns_id(self, db):
        gid = database.add_position_group('Alpha')
        assert isinstance(gid, int)
        assert gid > 0

    def test_rename(self, db):
        gid = database.add_position_group('Alpha')
        database.rename_position_group(gid, 'Beta')
        assert database.get_position_groups()[0]['name'] == 'Beta'

    def test_delete_group_orphans_positions(self, db):
        gid = database.add_position_group('G')
        database.add_position('BTC', 'long', 100.0, 5.0, 90000.0, group_id=gid)
        database.delete_position_group(gid)
        assert database.get_position_groups() == []
        assert database.get_positions()[0]['group_id'] is None

    def test_multiple_groups(self, db):
        database.add_position_group('G1')
        database.add_position_group('G2')
        assert len(database.get_position_groups()) == 2


# ── Reminders ──────────────────────────────────────────────────────────────────

class TestReminders:
    def test_add_and_get(self, db):
        database.add_reminder('Scroll', '2026-05-01T10:00')
        reminders = database.get_reminders(include_done=True)
        assert len(reminders) == 1
        assert reminders[0]['protocol'] == 'Scroll'
        assert reminders[0]['done'] == 0

    def test_get_excludes_done_by_default(self, db):
        database.add_reminder('Scroll', '2026-05-01T10:00')
        rid = database.get_reminders(include_done=True)[0]['id']
        database.mark_done(rid)
        assert database.get_reminders() == []
        assert len(database.get_reminders(include_done=True)) == 1

    def test_mark_done(self, db):
        database.add_reminder('X', '2026-05-01T10:00')
        rid = database.get_reminders(include_done=True)[0]['id']
        database.mark_done(rid)
        r = database.get_reminders(include_done=True)[0]
        assert r['done'] == 1

    def test_delete(self, db):
        database.add_reminder('X', '2026-05-01T10:00')
        rid = database.get_reminders(include_done=True)[0]['id']
        database.delete_reminder(rid)
        assert database.get_reminders(include_done=True) == []

    def test_due_reminders_past_only(self, db):
        database.add_reminder('A', '2020-01-01T00:00')   # past → due
        database.add_reminder('B', '2099-01-01T00:00')   # future → not due
        due = database.get_due_reminders()
        assert len(due) == 1
        assert due[0]['protocol'] == 'A'

    def test_done_reminder_not_in_due(self, db):
        database.add_reminder('A', '2020-01-01T00:00')
        rid = database.get_reminders(include_done=True)[0]['id']
        database.mark_done(rid)
        assert database.get_due_reminders() == []

    def test_multiple_reminders_ordered_by_date(self, db):
        database.add_reminder('B', '2026-06-01T10:00')
        database.add_reminder('A', '2026-05-01T10:00')
        reminders = database.get_reminders()
        assert reminders[0]['protocol'] == 'A'  # earlier date first


# ── Weekly snapshot edge cases ─────────────────────────────────────────────────

class TestWeeklySnapshotEdgeCases:
    def _setup(self):
        database.add_protocol('P')
        database.bulk_add_wallets([ADDR], protocols=['P'])

    def test_wallet_with_no_week_data_appears_in_get_week_wallets(self, db):
        self._setup()
        wallets = database.get_week_wallets('P', WEEK1)
        assert len(wallets) == 1
        assert wallets[0]['wallet_balance'] == 0.0
        assert wallets[0]['points'] == 0.0

    def test_deposit_this_week_falls_back_to_previous_week_balance(self, db):
        self._setup()
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'wallet_balance': 95.0}
        ], week=WEEK1)
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'wallet_balance': 88.0}
        ], week=WEEK2)
        w2 = database.get_week_wallets('P', WEEK2)
        assert w2[0]['deposit_this_week'] == 95.0   # previous week's balance

    def test_first_week_no_deposit_auto_set_from_balance(self, db):
        self._setup()
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'wallet_balance': 100.0}  # no deposit field
        ], week=WEEK1)
        assert database.get_protocol_wallets_detail('P')[0]['deposit'] == 100.0

    def test_first_week_explicit_deposit_used(self, db):
        self._setup()
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'deposit': 150.0, 'wallet_balance': 100.0}
        ], week=WEEK1)
        w1 = database.get_week_wallets('P', WEEK1)
        assert w1[0]['deposit_this_week'] == 150.0

    def test_two_wallets_week_delete_zeroes_both(self, db):
        a1 = '0x1111111111111111111111111111111111111111'
        a2 = '0x2222222222222222222222222222222222222222'
        database.add_protocol('P')
        database.bulk_add_wallets([a1, a2], protocols=['P'])
        database.import_protocol_wallet_data('P', [
            {'address': a1, 'wallet_balance': 50.0, 'wp_points': 100.0},
            {'address': a2, 'wallet_balance': 70.0, 'wp_points': 200.0},
        ], week=WEEK1)
        wid = database.add_protocol_week('P', WEEK1, WEEK1)
        database.delete_protocol_week(wid)
        for w in database.get_protocol_wallets_detail('P'):
            assert w['wp_points'] == 0.0
            assert w['wallet_balance'] == 0.0

    def test_delete_week_restores_previous_week_data(self, db):
        """After deleting WEEK2, wallet_protocols should reflect WEEK1 data."""
        self._setup()
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'wallet_balance': 90.0, 'wp_points': 100.0}
        ], week=WEEK1)
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'wallet_balance': 80.0, 'wp_points': 50.0}
        ], week=WEEK2)
        database.add_protocol_week('P', WEEK1, WEEK1)
        wid2 = database.add_protocol_week('P', WEEK2, WEEK2)
        database.delete_protocol_week(wid2)
        wp = database.get_protocol_wallets_detail('P')[0]
        assert wp['wallet_balance'] == 90.0
        assert wp['wp_points'] == 100.0  # only WEEK1 points remain

    def test_upsert_weekly_points(self, db):
        self._setup()
        wid = database.get_wallets()[0]['id']
        database.upsert_weekly_points('P', WEEK1, [{'wallet_id': wid, 'points': 777.0}])
        summary = database.get_weekly_summary('P')
        assert summary[0]['total_points'] == 777.0

    def test_get_weekly_points_prev(self, db):
        self._setup()
        wid = database.get_wallets()[0]['id']
        database.upsert_weekly_points('P', WEEK1, [{'wallet_id': wid, 'points': 100.0}])
        database.upsert_weekly_points('P', WEEK2, [{'wallet_id': wid, 'points': 200.0}])
        prev = database.get_weekly_points_prev('P', WEEK2)
        assert prev[wid] == 100.0

    def test_get_weekly_points_prev_no_prior_week(self, db):
        self._setup()
        assert database.get_weekly_points_prev('P', WEEK1) == {}


# ── import_balances extra ──────────────────────────────────────────────────────

class TestImportBalancesExtra:
    def test_multiple_wallets_all_matched(self, db):
        a1 = '0x1111111111111111111111111111111111111111'
        a2 = '0x2222222222222222222222222222222222222222'
        database.bulk_add_wallets([a1, a2])
        rows = [
            {'address_short': a1[:6] + '..' + a1[-4:], 'balance': 10.0,
             'volume': None, 'burn': None, 'points': None, 'p_price': None},
            {'address_short': a2[:6] + '..' + a2[-4:], 'balance': 20.0,
             'volume': None, 'burn': None, 'points': None, 'p_price': None},
        ]
        assert database.import_balances(rows) == 2

    def test_partial_match(self, db):
        database.bulk_add_wallets([ADDR])
        rows = [
            {'address_short': ADDR[:6] + '..' + ADDR[-4:], 'balance': 5.0,
             'volume': None, 'burn': None, 'points': None, 'p_price': None},
            {'address_short': '0xDEAD..BEEF', 'balance': 5.0,
             'volume': None, 'burn': None, 'points': None, 'p_price': None},
        ]
        assert database.import_balances(rows) == 1


# ── HL Accounts extended ────────────────────────────────────────────────────────

HL1 = '0x' + '1' * 40
HL2 = '0x' + '2' * 40
HL3 = '0x' + '3' * 40


class TestHLAccountsExtended:
    def test_multiple_accounts_all_returned(self, db):
        database.add_hl_account('alpha', HL1)
        database.add_hl_account('beta', HL2)
        accs = database.get_hl_accounts()
        assert len(accs) == 2
        labels = {a['label'] for a in accs}
        assert labels == {'alpha', 'beta'}

    def test_duplicate_add_keeps_original_label(self, db):
        database.add_hl_account('original', HL1)
        database.add_hl_account('copy', HL1)
        assert database.get_hl_accounts()[0]['label'] == 'original'

    def test_group_name_none_by_default(self, db):
        database.add_hl_account('a', HL1)
        assert database.get_hl_accounts()[0]['group_name'] is None

    def test_empty_string_group_name_stored_as_none(self, db):
        database.add_hl_account('a', HL1)
        aid = database.get_hl_accounts()[0]['id']
        database.update_hl_account_group(aid, 'G')
        database.update_hl_account_group(aid, '')
        assert database.get_hl_accounts()[0]['group_name'] is None

    def test_bulk_add_empty_list_returns_zero(self, db):
        assert database.bulk_add_hl_accounts([]) == 0
        assert database.get_hl_accounts() == []

    def test_bulk_add_partial_duplicates_only_new_counted(self, db):
        database.add_hl_account('existing', HL1)
        result = database.bulk_add_hl_accounts([
            {'label': 'dup', 'address': HL1},
            {'label': 'new1', 'address': HL2},
            {'label': 'new2', 'address': HL3},
        ])
        assert result == 2
        assert len(database.get_hl_accounts()) == 3

    def test_get_from_nonexistent_profile_returns_empty(self, db):
        assert database.get_hl_accounts_from_profile('no_such_profile_xyz_999') == []

    def test_delete_nonexistent_id_no_crash(self, db):
        database.delete_hl_account(99999)  # should not raise

    def test_three_accounts_all_present(self, db):
        database.add_hl_account('a', HL1)
        database.add_hl_account('b', HL2)
        database.add_hl_account('c', HL3)
        assert len(database.get_hl_accounts()) == 3

    def test_group_name_shared_across_accounts(self, db):
        database.add_hl_account('a', HL1)
        database.add_hl_account('b', HL2)
        accs = database.get_hl_accounts()
        for acc in accs:
            database.update_hl_account_group(acc['id'], 'SharedGroup')
        for acc in database.get_hl_accounts():
            assert acc['group_name'] == 'SharedGroup'


# ── Nado Accounts extended ──────────────────────────────────────────────────────

class TestNadoAccountsExtended:
    def test_multiple_accounts(self, db):
        database.add_nado_account('a', HL1)
        database.add_nado_account('b', HL2)
        assert len(database.get_nado_accounts()) == 2

    def test_group_name_none_by_default(self, db):
        database.add_nado_account('a', HL1)
        assert database.get_nado_accounts()[0]['group_name'] is None

    def test_empty_string_group_name_stored_as_none(self, db):
        database.add_nado_account('a', HL1)
        aid = database.get_nado_accounts()[0]['id']
        database.update_nado_account_group(aid, 'G')
        database.update_nado_account_group(aid, '')
        assert database.get_nado_accounts()[0]['group_name'] is None

    def test_group_name_cleared_to_none(self, db):
        database.add_nado_account('a', HL1)
        aid = database.get_nado_accounts()[0]['id']
        database.update_nado_account_group(aid, 'G1')
        database.update_nado_account_group(aid, None)
        assert database.get_nado_accounts()[0]['group_name'] is None

    def test_delete_nonexistent_no_crash(self, db):
        database.delete_nado_account(99999)


# ── Extended Accounts extended ──────────────────────────────────────────────────

class TestExtendedAccountsExtended:
    def test_multiple_accounts(self, db):
        database.add_extended_account('a', 'key1')
        database.add_extended_account('b', 'key2')
        assert len(database.get_extended_accounts()) == 2

    def test_group_name_none_by_default(self, db):
        database.add_extended_account('a', 'key1')
        assert database.get_extended_accounts()[0]['group_name'] is None

    def test_empty_string_group_name_stored_as_none(self, db):
        database.add_extended_account('a', 'key1')
        aid = database.get_extended_accounts()[0]['id']
        database.update_extended_account_group(aid, 'G')
        database.update_extended_account_group(aid, '')
        assert database.get_extended_accounts()[0]['group_name'] is None

    def test_group_name_cleared_to_none(self, db):
        database.add_extended_account('a', 'key1')
        aid = database.get_extended_accounts()[0]['id']
        database.update_extended_account_group(aid, 'G2')
        database.update_extended_account_group(aid, None)
        assert database.get_extended_accounts()[0]['group_name'] is None


# ── Pacifica Accounts extended ──────────────────────────────────────────────────

class TestPacificaAccountsExtended:
    def test_duplicate_address_ignored(self, db):
        database.add_pacifica_account('a', HL1)
        database.add_pacifica_account('b', HL1)
        assert len(database.get_pacifica_accounts()) == 1

    def test_multiple_accounts(self, db):
        database.add_pacifica_account('a', HL1)
        database.add_pacifica_account('b', HL2)
        assert len(database.get_pacifica_accounts()) == 2

    def test_group_name_none_by_default(self, db):
        database.add_pacifica_account('a', HL1)
        assert database.get_pacifica_accounts()[0]['group_name'] is None

    def test_empty_string_group_name_stored_as_none(self, db):
        database.add_pacifica_account('a', HL1)
        aid = database.get_pacifica_accounts()[0]['id']
        database.update_pacifica_account_group(aid, 'G')
        database.update_pacifica_account_group(aid, '')
        assert database.get_pacifica_accounts()[0]['group_name'] is None

    def test_group_name_cleared_to_none(self, db):
        database.add_pacifica_account('a', HL1)
        aid = database.get_pacifica_accounts()[0]['id']
        database.update_pacifica_account_group(aid, 'G3')
        database.update_pacifica_account_group(aid, None)
        assert database.get_pacifica_accounts()[0]['group_name'] is None


# ── Positions extended ──────────────────────────────────────────────────────────

class TestPositionsExtended:
    def test_get_empty_initially(self, db):
        assert database.get_positions() == []

    def test_update_clears_group_id(self, db):
        gid = database.add_position_group('G')
        database.add_position('BTC', 'long', 100.0, 5.0, 90000.0, group_id=gid)
        pid = database.get_positions()[0]['id']
        database.update_position(pid, 'BTC', 'long', 100.0, 5.0, 90000.0, group_id=None)
        assert database.get_positions()[0]['group_id'] is None

    def test_three_positions_correct_count(self, db):
        database.add_position('BTC', 'long', 100.0, 5.0, 90000.0)
        database.add_position('ETH', 'short', 50.0, 3.0, 3000.0)
        database.add_position('SOL', 'long', 200.0, 10.0, 150.0)
        assert len(database.get_positions()) == 3

    def test_group_positions_separate_from_ungrouped(self, db):
        gid = database.add_position_group('G')
        database.add_position('BTC', 'long', 100.0, 5.0, 90000.0, group_id=gid)
        database.add_position('ETH', 'short', 50.0, 3.0, 3000.0)
        positions = database.get_positions()
        grouped = [p for p in positions if p['group_id'] == gid]
        ungrouped = [p for p in positions if p['group_id'] is None]
        assert len(grouped) == 1
        assert len(ungrouped) == 1


# ── Weekly snapshots comprehensive ─────────────────────────────────────────────

WEEK3 = '2026-01-19'

A1 = '0x1111111111111111111111111111111111111111'
A2 = '0x2222222222222222222222222222222222222222'


class TestWeeklyFull:
    def _setup(self, addr=ADDR):
        database.add_protocol('P')
        database.bulk_add_wallets([addr], protocols=['P'])

    def _setup_two(self):
        database.add_protocol('P')
        database.bulk_add_wallets([A1, A2], protocols=['P'])

    # ── Protocol weeks CRUD ──

    def test_get_protocol_weeks_empty(self, db):
        database.add_protocol('P')
        assert database.get_protocol_weeks('P') == []

    def test_add_protocol_week_returns_id(self, db):
        database.add_protocol('P')
        wid = database.add_protocol_week('P', WEEK1, WEEK1)
        assert isinstance(wid, int) and wid > 0

    def test_protocol_weeks_ordered_newest_first(self, db):
        database.add_protocol('P')
        database.add_protocol_week('P', WEEK1, WEEK1)
        database.add_protocol_week('P', WEEK2, WEEK2)
        weeks = database.get_protocol_weeks('P')
        assert weeks[0]['week_start'] == WEEK2
        assert weeks[1]['week_start'] == WEEK1

    def test_update_protocol_week_changes_dates(self, db):
        database.add_protocol('P')
        wid = database.add_protocol_week('P', WEEK1, WEEK1)
        database.update_protocol_week(wid, WEEK2, WEEK2)
        assert database.get_protocol_weeks('P')[0]['week_start'] == WEEK2

    # ── Points accumulation ──

    def test_three_weeks_points_accumulate(self, db):
        self._setup()
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'wallet_balance': 100.0, 'wp_points': 100.0}
        ], week=WEEK1)
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'wallet_balance': 90.0, 'wp_points': 200.0}
        ], week=WEEK2)
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'wallet_balance': 80.0, 'wp_points': 150.0}
        ], week=WEEK3)
        wp = database.get_protocol_wallets_detail('P')[0]
        assert wp['wp_points'] == 450.0

    def test_reimport_same_week_updates_balance_not_deposit(self, db):
        self._setup()
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'deposit': 100.0, 'wallet_balance': 100.0}
        ], week=WEEK1)
        # Re-import with different balance and a new deposit value (should be ignored)
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'deposit': 999.0, 'wallet_balance': 120.0}
        ], week=WEEK1)
        wp = database.get_protocol_wallets_detail('P')[0]
        assert wp['deposit'] == 100.0   # unchanged
        assert wp['wallet_balance'] == 120.0  # updated

    def test_reimport_same_week_updates_points(self, db):
        self._setup()
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'wallet_balance': 100.0, 'wp_points': 100.0}
        ], week=WEEK1)
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'wallet_balance': 100.0, 'wp_points': 250.0}
        ], week=WEEK1)
        wp = database.get_protocol_wallets_detail('P')[0]
        assert wp['wp_points'] == 250.0  # replaced, not doubled

    # ── Deposit delta logic ──

    def test_week2_explicit_deposit_adds_delta(self, db):
        """deposit field in W2 represents the start balance of W2.
        delta = start_W2 - balance_W1 is added to wallet_protocols.deposit."""
        self._setup()
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'deposit': 100.0, 'wallet_balance': 100.0}
        ], week=WEEK1)
        # W2 start = 130 (added 30 more), balance ends at 125
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'deposit': 130.0, 'wallet_balance': 125.0}
        ], week=WEEK2)
        # delta = 130 - 100 = 30 → deposit = 100 + 30 = 130
        wp = database.get_protocol_wallets_detail('P')[0]
        assert wp['deposit'] == 130.0

    def test_week2_no_deposit_field_deposit_unchanged(self, db):
        """Importing W2 without a deposit field leaves wallet_protocols.deposit unchanged."""
        self._setup()
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'deposit': 100.0, 'wallet_balance': 100.0}
        ], week=WEEK1)
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'wallet_balance': 80.0}  # no deposit
        ], week=WEEK2)
        wp = database.get_protocol_wallets_detail('P')[0]
        assert wp['deposit'] == 100.0  # unchanged

    def test_week2_zero_delta_deposit_unchanged(self, db):
        """If balance didn't change between weeks, deposit delta = 0, deposit stays."""
        self._setup()
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'deposit': 100.0, 'wallet_balance': 100.0}
        ], week=WEEK1)
        # W2 starts at same balance as W1 ended → no change
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'deposit': 100.0, 'wallet_balance': 95.0}
        ], week=WEEK2)
        wp = database.get_protocol_wallets_detail('P')[0]
        assert wp['deposit'] == 100.0  # delta = 0, unchanged

    # ── get_week_wallets ──

    def test_get_week_wallets_deposit_from_explicit_start_balance(self, db):
        self._setup()
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'deposit': 150.0, 'wallet_balance': 100.0}
        ], week=WEEK1)
        w1 = database.get_week_wallets('P', WEEK1)
        assert w1[0]['deposit_this_week'] == 150.0

    def test_get_week_wallets_missing_wallet_shows_zeros(self, db):
        self._setup_two()
        # Only import data for A1 in W1
        database.import_protocol_wallet_data('P', [
            {'address': A1, 'wallet_balance': 50.0, 'wp_points': 100.0}
        ], week=WEEK1)
        wallets = database.get_week_wallets('P', WEEK1)
        by_addr = {w['address']: w for w in wallets}
        assert by_addr[A1]['wallet_balance'] == 50.0
        assert by_addr[A2]['wallet_balance'] == 0.0
        assert by_addr[A2]['points'] == 0.0

    # ── get_protocol_weeks stats ──

    def test_get_protocol_weeks_stats(self, db):
        self._setup()
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'deposit': 100.0, 'wallet_balance': 90.0, 'wp_points': 500.0}
        ], week=WEEK1)
        database.add_protocol_week('P', WEEK1, WEEK1)
        weeks = database.get_protocol_weeks('P')
        assert len(weeks) == 1
        w = weeks[0]
        assert w['total_points'] == 500.0
        assert w['total_balance'] == 90.0
        assert w['total_start_balance'] == 100.0
        assert w['total_spent'] == 10.0    # 100 - 90
        assert w['wallet_count'] == 1

    def test_get_protocol_weeks_no_points_price_zero(self, db):
        self._setup()
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'deposit': 100.0, 'wallet_balance': 90.0}
        ], week=WEEK1)
        database.add_protocol_week('P', WEEK1, WEEK1)
        w = database.get_protocol_weeks('P')[0]
        assert w['price_per_point'] == 0

    def test_get_protocol_weeks_two_wallets_aggregated(self, db):
        self._setup_two()
        database.import_protocol_wallet_data('P', [
            {'address': A1, 'deposit': 100.0, 'wallet_balance': 90.0, 'wp_points': 200.0},
            {'address': A2, 'deposit': 50.0, 'wallet_balance': 45.0, 'wp_points': 100.0},
        ], week=WEEK1)
        database.add_protocol_week('P', WEEK1, WEEK1)
        w = database.get_protocol_weeks('P')[0]
        assert w['total_points'] == 300.0
        assert w['total_balance'] == 135.0
        assert w['total_start_balance'] == 150.0
        assert w['wallet_count'] == 2

    def test_get_protocol_weeks_fallback_start_balance_from_prev_week(self, db):
        """When W2 has no explicit start_balance, fallback uses W1's balance."""
        self._setup()
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'wallet_balance': 90.0, 'wp_points': 100.0}  # no deposit
        ], week=WEEK1)
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'wallet_balance': 80.0, 'wp_points': 200.0}  # no deposit
        ], week=WEEK2)
        database.add_protocol_week('P', WEEK2, WEEK2)
        w = database.get_protocol_weeks('P')[0]
        # start_balance for W2 falls back to W1's wallet_balance = 90
        assert w['total_start_balance'] == 90.0
        assert w['total_spent'] == 10.0   # 90 - 80

    # ── weekly_summary ──

    def test_weekly_summary_two_wallets(self, db):
        self._setup_two()
        database.import_protocol_wallet_data('P', [
            {'address': A1, 'wallet_balance': 50.0, 'wp_points': 100.0},
            {'address': A2, 'wallet_balance': 70.0, 'wp_points': 300.0},
        ], week=WEEK1)
        summary = database.get_weekly_summary('P')
        assert summary[0]['total_points'] == 400.0
        assert summary[0]['wallet_count'] == 2

    def test_weekly_summary_newest_first(self, db):
        self._setup()
        wid = database.get_wallets()[0]['id']
        database.upsert_weekly_points('P', WEEK1, [{'wallet_id': wid, 'points': 100.0}])
        database.upsert_weekly_points('P', WEEK2, [{'wallet_id': wid, 'points': 200.0}])
        summary = database.get_weekly_summary('P')
        assert summary[0]['week'] == WEEK2

    # ── delete_protocol_week edge cases ──

    def test_delete_week_auto_set_deposit_preserved(self, db):
        """Deleting W2 when W1 had auto-set deposit (no explicit deposit) must restore W1 deposit, not 0."""
        self._setup()
        # W1: no explicit deposit → auto-set from balance=100
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'wallet_balance': 100.0}
        ], week=WEEK1)
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'wallet_balance': 80.0}
        ], week=WEEK2)
        database.add_protocol_week('P', WEEK1, WEEK1)
        wid2 = database.add_protocol_week('P', WEEK2, WEEK2)
        database.delete_protocol_week(wid2)
        wp = database.get_protocol_wallets_detail('P')[0]
        assert wp['wallet_balance'] == 100.0
        assert wp['deposit'] == 100.0   # must NOT be 0

    def test_delete_first_week_reflects_second_week(self, db):
        self._setup()
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'deposit': 100.0, 'wallet_balance': 100.0, 'wp_points': 100.0}
        ], week=WEEK1)
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'wallet_balance': 90.0, 'wp_points': 200.0}
        ], week=WEEK2)
        wid1 = database.add_protocol_week('P', WEEK1, WEEK1)
        database.add_protocol_week('P', WEEK2, WEEK2)
        database.delete_protocol_week(wid1)
        wp = database.get_protocol_wallets_detail('P')[0]
        assert wp['wallet_balance'] == 90.0
        assert wp['wp_points'] == 200.0   # only W2 points remain

    def test_delete_only_week_zeroes_wallet_protocols(self, db):
        self._setup()
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'deposit': 100.0, 'wallet_balance': 90.0, 'wp_points': 500.0}
        ], week=WEEK1)
        wid = database.add_protocol_week('P', WEEK1, WEEK1)
        database.delete_protocol_week(wid)
        wp = database.get_protocol_wallets_detail('P')[0]
        assert wp['wallet_balance'] == 0.0
        assert wp['wp_points'] == 0.0
        assert wp['deposit'] == 0.0

    def test_delete_middle_week_restores_from_first_and_last(self, db):
        """Deleting W2 when W1 and W3 exist → wallet_protocols reflects W3, deposit from W1."""
        self._setup()
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'deposit': 100.0, 'wallet_balance': 100.0, 'wp_points': 100.0}
        ], week=WEEK1)
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'wallet_balance': 95.0, 'wp_points': 150.0}
        ], week=WEEK2)
        database.import_protocol_wallet_data('P', [
            {'address': ADDR, 'wallet_balance': 85.0, 'wp_points': 200.0}
        ], week=WEEK3)
        database.add_protocol_week('P', WEEK1, WEEK1)
        wid2 = database.add_protocol_week('P', WEEK2, WEEK2)
        database.add_protocol_week('P', WEEK3, WEEK3)
        database.delete_protocol_week(wid2)
        wp = database.get_protocol_wallets_detail('P')[0]
        assert wp['wallet_balance'] == 85.0   # from W3 (latest)
        assert wp['wp_points'] == 300.0       # W1 + W3 (W2 removed)
        assert wp['deposit'] == 100.0         # from W1 start_balance
