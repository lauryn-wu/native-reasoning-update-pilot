"""Transactional USD ledger. Reservations survive crashes and uncertain transports."""
import json
import math
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from .util import canonical, utcnow

CAP_MICRO_USD = 40_000_000
# Rates in micro-USD/token equal USD/million tokens. Fixed Standard, short-context.
RATES = {"input": 2, "cached_input": 0.10, "cache_write_30m": 2.50,
         "cache_write_12h": 5, "output": 10}
MAX_INPUT_TOKENS = 272000


class BudgetRefused(RuntimeError):
    pass


def input_upper_bound(request, checkpoint=None):
    # UTF-8 bytes overcounts text BPE tokens; retain ciphertext bytes AND all prior
    # output tokens, since encrypted native reasoning is not visible text. Add
    # conservative protocol/item framing. Never truncate to make a call fit.
    prior = 0
    if checkpoint:
        prior = checkpoint['response']['usage']['output_tokens']
    return len(canonical(request)) + prior + 4096 + 64 * len(request.get('input', []))


def reservation(request, checkpoint=None):
    bound = input_upper_bound(request, checkpoint)
    if bound > MAX_INPUT_TOKENS:
        raise BudgetRefused("Conservative input bound exceeds frozen short-context limit")
    # Even unexpected 12-hour writes fit the reservation; no cache savings assumed.
    return {"input_tokens_bound": bound, "output_tokens_bound": request['max_output_tokens'],
            "micro_usd": math.ceil(bound * RATES['cache_write_12h'] +
                                   request['max_output_tokens'] * RATES['output'])}


def usage_cost(usage):
    """Reconcile documented usage; output_tokens already includes reasoning."""
    inp, out = usage['input_tokens'], usage['output_tokens']
    detail = usage['input_tokens_details']
    cached, written = detail['cached_tokens'], detail['cache_write_tokens']
    if any(type(n) is not int or n < 0 for n in (inp, out, cached, written)) or cached + written > inp:
        raise ValueError("Malformed provider usage")
    if inp > MAX_INPUT_TOKENS:
        raise ValueError("Usage exceeds frozen short-context tier")
    # TTL is frozen at 30m. Unexpected writes are still charged conservatively at
    # the highest supported write rate, and separately invalidate the protocol.
    return math.ceil((inp-cached-written)*RATES['input'] + cached*RATES['cached_input'] +
                     written*RATES['cache_write_12h'] + out*RATES['output'])


class Ledger:
    """One repository-wide cap shared by smoke, retries, and all manifest versions.

    Every write is SQLite FULL synchronous + an immediate transaction. Active and
    uncertain attempts consume their full reservation. The CLI never changes cap
    or creates per-campaign ledgers. Sensitive request/response data stays ignored.
    """
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = path
        self.db = sqlite3.connect(path, timeout=30)
        os.chmod(path, 0o600)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('PRAGMA journal_mode=DELETE')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS attempts (
          call_id TEXT NOT NULL, attempt INTEGER NOT NULL, manifest_hash TEXT NOT NULL,
          kind TEXT NOT NULL, state TEXT NOT NULL, reserved INTEGER NOT NULL,
          charged INTEGER, started TEXT NOT NULL, finished TEXT,
          request TEXT NOT NULL, response TEXT, outcome TEXT, error_kind TEXT,
          PRIMARY KEY(call_id, attempt));
        ''')
        with self.transaction():
            self.db.execute("INSERT OR IGNORE INTO meta VALUES ('cap_micro_usd', ?)", (str(CAP_MICRO_USD),))
            if self.db.execute("SELECT value FROM meta WHERE key='cap_micro_usd'").fetchone()[0] != str(CAP_MICRO_USD):
                raise BudgetRefused("Ledger cap mismatch; never silently increase/reset")

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def close(self):
        self.db.close()

    def total(self):
        return self.db.execute('SELECT COALESCE(SUM(COALESCE(charged,reserved)),0) FROM attempts').fetchone()[0]

    def rows(self, manifest_hash=None):
        query = 'SELECT * FROM attempts'
        args = ()
        if manifest_hash:
            query += ' WHERE manifest_hash=?'
            args = (manifest_hash,)
        return [dict(r) for r in self.db.execute(query + ' ORDER BY rowid', args)]

    def latest(self, call_id):
        row = self.db.execute('SELECT * FROM attempts WHERE call_id=? ORDER BY attempt DESC LIMIT 1', (call_id,)).fetchone()
        return dict(row) if row else None

    def reserve(self, call_id, manifest_hash, request, amount, kind='pilot'):
        if type(amount) is not int or amount <= 0:
            raise ValueError('Positive integer reservation required')
        with self.transaction():
            if self.db.execute("SELECT value FROM meta WHERE key='halted'").fetchone():
                raise BudgetRefused('Ledger halted after accounting invariant failure')
            previous = self.latest(call_id)
            if previous:
                if previous['state'] != 'transport_uncertain' or previous['attempt'] >= 2:
                    raise BudgetRefused('Call already assigned/completed or retry exhausted')
                attempt = previous['attempt'] + 1
            else:
                attempt = 1
            if self.total() + amount > CAP_MICRO_USD:
                raise BudgetRefused('Insufficient unreserved budget under hard $40 cap')
            self.db.execute('''INSERT INTO attempts
              (call_id,attempt,manifest_hash,kind,state,reserved,started,request)
              VALUES (?,?,?,?,?,?,?,?)''',
              (call_id, attempt, manifest_hash, kind, 'reserved', amount, utcnow(), canonical(request).decode()))
        return attempt

    def dispatched(self, call_id, attempt):
        with self.transaction():
            cur = self.db.execute("UPDATE attempts SET state='dispatched' WHERE call_id=? AND attempt=? AND state='reserved'", (call_id,attempt))
            if cur.rowcount != 1:
                raise RuntimeError('Dispatch is not a fresh reserved attempt')

    def uncertain(self, call_id, attempt, error_kind='transport_failure'):
        with self.transaction():
            self.db.execute("UPDATE attempts SET state='transport_uncertain',error_kind=?,finished=? WHERE call_id=? AND attempt=? AND state IN ('reserved','dispatched')",
                            (error_kind,utcnow(),call_id,attempt))

    def finish(self, call_id, attempt, response, outcome):
        try:
            model = response.get('model','')
            if (not (model == 'gpt-6.1-sol' or model.startswith('gpt-6.1-sol-')) or
                response.get('service_tier') != 'default' or
                (response.get('reasoning') or {}).get('mode') != 'standard'):
                raise ValueError('Unverified effective billing configuration')
            cost = usage_cost(response['usage'])
        except (KeyError, TypeError, ValueError):
            cost = None  # Missing usage must never be interpreted as a free call.
        with self.transaction():
            row = self.latest(call_id)
            if not row or row['attempt'] != attempt or row['state'] != 'dispatched':
                raise RuntimeError('Attempt is not awaiting reconciliation')
            if cost is not None and cost > row['reserved']:
                self.db.execute("INSERT OR REPLACE INTO meta VALUES ('halted','usage exceeded reservation')")
                outcome = dict(outcome, status='protocol_failure', protocol_valid=False,
                               accounting_failure='Actual usage exceeded conservative reservation')
            self.db.execute("UPDATE attempts SET state='completed',charged=?,response=?,outcome=?,finished=? WHERE call_id=? AND attempt=?",
                            (cost,canonical(response).decode(),canonical(outcome).decode(),utcnow(),call_id,attempt))

    def provider_failure(self, call_id, attempt, kind, outcome=None):
        # Without authoritative billable usage, preserve the full reservation.
        with self.transaction():
            self.db.execute("UPDATE attempts SET state='provider_failure',error_kind=?,outcome=?,finished=? WHERE call_id=? AND attempt=? AND state='dispatched'",
                            (kind,canonical(outcome).decode() if outcome else None,utcnow(),call_id,attempt))

    def recover_interrupted(self):
        # Call only under the campaign file lock. A crash may have occurred after
        # dispatch; reserve worst-case charges and permit only one transport retry.
        with self.transaction():
            self.db.execute("UPDATE attempts SET state='transport_uncertain', error_kind='interrupted_unknown_charge',finished=? WHERE state IN ('reserved','dispatched')", (utcnow(),))
