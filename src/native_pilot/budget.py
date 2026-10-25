"""Transactional USD ledger. Reservations survive crashes and uncertain transports."""
import json
import math
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from .util import canonical, utcnow

CAP_MICRO_USD = 40_000_000
# Rates in micro-USD/token equal USD/million tokens. Fixed Standard, short-context.
RATES = {"input": 2, "cached_input": 0.10, "cache_write_30m": 2.50,
         "cache_write_12h": 5, "output": 10}
MAX_INPUT_TOKENS = 272000
EXPLORATORY_SCOPE_ID = 'user-2026-10-24-exploratory-four-case-v6'
EXPLORATORY_CAP_MICRO_USD = 5_000_000
EXPLORATORY_DURATION_SECONDS = 1800
LOW_EFFORT_SCOPE_ID = 'user-2026-10-24-low-effort-followup-v7'
LOW_EFFORT_CAP_MICRO_USD = 2_000_000
LOW_EFFORT_DURATION_SECONDS = 1800
# Only these separate, fixed authorizations exist. A new manifest, process, or
# arbitrary scope label cannot replenish an existing authorization.
_SCOPES = MappingProxyType({
    EXPLORATORY_SCOPE_ID: (EXPLORATORY_CAP_MICRO_USD, EXPLORATORY_DURATION_SECONDS),
    LOW_EFFORT_SCOPE_ID: (LOW_EFFORT_CAP_MICRO_USD, LOW_EFFORT_DURATION_SECONDS),
})


def _scope_key(scope_id):
    if scope_id not in _SCOPES:
        raise BudgetRefused('Unknown exploratory budget scope; a new label cannot reset limits')
    return 'budget_scope/' + scope_id


def _wall_time():
    """Wall time is patchable in tests; persisted timestamps survive resumes."""
    return time.time()


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

    def _scope(self, scope_id, manifest_hash=None):
        key = _scope_key(scope_id)
        cap, duration = _SCOPES[scope_id]
        row = self.db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
        if row is None:
            raise BudgetRefused('Exploratory budget scope must be bound before reservation')
        try:
            scope = json.loads(row[0])
            required = {'schema_version', 'scope_id', 'manifest_hash', 'cap_micro_usd',
                        'duration_seconds', 'started_at', 'deadline_at', 'last_observed_at', 'halted_reason'}
            if (not isinstance(scope, dict) or set(scope) != required or scope['schema_version'] != 1
                    or scope['scope_id'] != scope_id
                    or type(scope['cap_micro_usd']) is not int or scope['cap_micro_usd'] != cap
                    or type(scope['duration_seconds']) is not int or scope['duration_seconds'] != duration
                    or not isinstance(scope['manifest_hash'], str) or not scope['manifest_hash']
                    or scope['halted_reason'] not in (None, 'deadline_elapsed', 'clock_moved_backwards', 'invalid_clock')):
                raise ValueError('Invalid scope record')
            timestamps = [scope[key] for key in ('started_at', 'deadline_at', 'last_observed_at')]
            if timestamps != [None, None, None]:
                if (not all(type(value) in (int, float) and math.isfinite(value) and value > 0 for value in timestamps)
                        or scope['deadline_at'] != scope['started_at'] + scope['duration_seconds']
                        or scope['last_observed_at'] < scope['started_at']):
                    raise ValueError('Invalid scope timestamps')
        except (ValueError, TypeError, KeyError):
            raise BudgetRefused('Exploratory budget scope record is invalid') from None
        if manifest_hash is not None and scope['manifest_hash'] != manifest_hash:
            raise BudgetRefused('Exploratory budget scope already bound to another manifest')
        return scope

    def _save_scope(self, scope):
        self.db.execute('UPDATE meta SET value=? WHERE key=?',
                        (canonical(scope).decode(), _scope_key(scope['scope_id'])))

    def bind_scope(self, scope_id, manifest_hash, *, cap_micro_usd=EXPLORATORY_CAP_MICRO_USD,
                   duration_seconds=EXPLORATORY_DURATION_SECONDS):
        """Bind a fixed authorization persistently; do not start its clock.

        The defaults retain the v6 API. The v7 follow-up must explicitly supply
        its smaller cap; neither scope can be rebound or extended on resume.
        """
        key = _scope_key(scope_id)
        cap, duration = _SCOPES[scope_id]
        if (type(cap_micro_usd) is not int or cap_micro_usd != cap
                or type(duration_seconds) is not int or duration_seconds != duration):
            raise BudgetRefused('Exploratory authorization fixes its scope cap and duration')
        if not isinstance(manifest_hash, str) or not manifest_hash:
            raise ValueError('A manifest hash is required')
        with self.transaction():
            exists = self.db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
            if exists:
                self._scope(scope_id, manifest_hash)
            else:
                for other_id in _SCOPES:
                    if (other_id != scope_id and self.db.execute(
                            'SELECT 1 FROM meta WHERE key=?', (_scope_key(other_id),)).fetchone()
                            and self._scope(other_id)['manifest_hash'] == manifest_hash):
                        raise BudgetRefused('Manifest is already bound to another exploratory scope')
                if self.db.execute('SELECT 1 FROM attempts WHERE manifest_hash=? LIMIT 1', (manifest_hash,)).fetchone():
                    raise BudgetRefused('Cannot bind an exploratory scope after unscoped attempts exist')
                scope = {'schema_version': 1, 'scope_id': scope_id, 'manifest_hash': manifest_hash,
                         'cap_micro_usd': cap_micro_usd, 'duration_seconds': duration_seconds,
                         'started_at': None, 'deadline_at': None, 'last_observed_at': None,
                         'halted_reason': None}
                self.db.execute('INSERT INTO meta VALUES (?,?)', (key, canonical(scope).decode()))

    def _scope_accounting(self, scope):
        row = self.db.execute('''SELECT COUNT(*) AS attempts,
            COALESCE(SUM(charged),0) AS known,
            COALESCE(SUM(CASE WHEN charged IS NULL THEN reserved ELSE 0 END),0) AS outstanding
            FROM attempts WHERE manifest_hash=?''', (scope['manifest_hash'],)).fetchone()
        return row['attempts'], row['known'], row['outstanding']

    @staticmethod
    def _observe_scope(scope, now):
        """Return a reason and latch clock violations, including failed checks."""
        if scope['halted_reason']:
            return scope['halted_reason']
        if type(now) not in (int, float) or not math.isfinite(now) or now <= 0:
            scope['halted_reason'] = 'invalid_clock'
        elif scope['started_at'] is not None:
            if now < scope['last_observed_at']:
                scope['halted_reason'] = 'clock_moved_backwards'
            else:
                scope['last_observed_at'] = now
                if now >= scope['deadline_at']:
                    scope['halted_reason'] = 'deadline_elapsed'
        return scope['halted_reason']

    @staticmethod
    def _scope_refusal(reason):
        return {'deadline_elapsed': 'Exploratory scope dispatch deadline elapsed',
                'clock_moved_backwards': 'Exploratory scope clock moved backwards; dispatch blocked',
                'invalid_clock': 'Exploratory scope clock is invalid; dispatch blocked'}[reason]

    def scope_status(self, scope_id):
        """Read-only accounting and timing; never bind, start, or extend a scope."""
        key = _scope_key(scope_id)
        if not self.db.execute('SELECT 1 FROM meta WHERE key=?', (key,)).fetchone():
            return None
        scope = self._scope(scope_id)
        now = _wall_time()
        reason = self._observe_scope(scope, now)  # Only the in-memory copy changes.
        attempts, known, outstanding = self._scope_accounting(scope)
        accounted, shared = known + outstanding, self.total()
        elapsed = (max(0, now - scope['started_at']) if scope['started_at'] is not None
                   and type(now) in (int, float) and math.isfinite(now) else 0)
        def timestamp(value):
            return datetime.fromtimestamp(value, timezone.utc).isoformat() if value is not None else None
        return {'scope_id': scope_id, 'manifest_hash': scope['manifest_hash'],
                'cap_micro_usd': scope['cap_micro_usd'], 'duration_seconds': scope['duration_seconds'],
                'started_at': timestamp(scope['started_at']), 'deadline_at': timestamp(scope['deadline_at']),
                'started_at_epoch_seconds': scope['started_at'], 'deadline_epoch_seconds': scope['deadline_at'],
                'elapsed_seconds': elapsed, 'remaining_seconds': max(0, scope['duration_seconds'] - elapsed),
                'status': reason or ('active' if scope['started_at'] is not None else 'not_started'),
                'dispatch_allowed': not reason and accounted <= scope['cap_micro_usd'] and shared <= CAP_MICRO_USD,
                'reservation_available': not reason and accounted < scope['cap_micro_usd'] and shared < CAP_MICRO_USD,
                'attempts': attempts, 'known_charges_micro_usd': known, 'known_charges_usd': known/1e6,
                'outstanding_reservations_micro_usd': outstanding, 'outstanding_reservations_usd': outstanding/1e6,
                'accounted_micro_usd': accounted, 'accounted_usd': accounted/1e6,
                'remaining_unreserved_micro_usd': max(0, scope['cap_micro_usd'] - accounted),
                'remaining_unreserved_usd': max(0, scope['cap_micro_usd'] - accounted)/1e6,
                'shared_accounted_micro_usd': shared, 'shared_accounted_usd': shared/1e6,
                'shared_remaining_unreserved_micro_usd': max(0, CAP_MICRO_USD - shared),
                'shared_remaining_unreserved_usd': max(0, CAP_MICRO_USD - shared)/1e6}

    def assert_scope_dispatch(self, scope_id, manifest_hash, call_id, attempt):
        """Recheck the persistent deadline immediately before an actual send.

        Refusal preserves the reservation. A clock violation is committed before
        raising, so a later clock change or resume cannot reopen an expired scope.
        """
        refusal = None
        with self.transaction():
            scope = self._scope(scope_id, manifest_hash)
            row = self.latest(call_id)
            if (not row or row['attempt'] != attempt or row['manifest_hash'] != manifest_hash
                    or row['state'] != 'dispatched' or scope['started_at'] is None):
                raise BudgetRefused('Exploratory dispatch requires its current reserved and dispatched attempt')
            reason = self._observe_scope(scope, _wall_time())
            self._save_scope(scope)
            if reason:
                refusal = self._scope_refusal(reason)
            elif self.db.execute("SELECT value FROM meta WHERE key='halted'").fetchone():
                refusal = 'Ledger halted after accounting invariant failure'
            elif sum(self._scope_accounting(scope)[1:]) > scope['cap_micro_usd'] or self.total() > CAP_MICRO_USD:
                refusal = 'Exploratory scope or shared budget cap exceeded'
        if refusal:
            raise BudgetRefused(refusal)

    def reserve(self, call_id, manifest_hash, request, amount, kind='pilot', *, scope_id=None):
        if type(amount) is not int or amount <= 0:
            raise ValueError('Positive integer reservation required')
        refusal = None
        with self.transaction():
            scope = self._scope(scope_id, manifest_hash) if scope_id is not None else None
            if scope is None:
                for bound_id in _SCOPES:
                    bound = self.db.execute('SELECT 1 FROM meta WHERE key=?', (_scope_key(bound_id),)).fetchone()
                    if bound and self._scope(bound_id)['manifest_hash'] == manifest_hash:
                        raise BudgetRefused('Bound exploratory manifest requires its scope on every reservation')
            if self.db.execute("SELECT value FROM meta WHERE key='halted'").fetchone():
                raise BudgetRefused('Ledger halted after accounting invariant failure')
            previous = self.latest(call_id)
            if previous:
                if (previous['state'] != 'transport_uncertain' or previous['attempt'] >= 2
                        or previous['manifest_hash'] != manifest_hash):
                    raise BudgetRefused('Call already assigned/completed or retry exhausted')
                attempt = previous['attempt'] + 1
            else:
                attempt = 1
            now = _wall_time() if scope is not None else None
            reason = self._observe_scope(scope, now) if scope is not None else None
            if reason:
                refusal = self._scope_refusal(reason)
            elif self.total() + amount > CAP_MICRO_USD:
                refusal = 'Insufficient unreserved budget under hard $40 cap'
            elif scope is not None and sum(self._scope_accounting(scope)[1:]) + amount > scope['cap_micro_usd']:
                refusal = f"Insufficient unreserved budget under additional ${scope['cap_micro_usd']/1e6:g} scope cap"
            if scope is not None:
                if refusal is None and scope['started_at'] is None:
                    scope.update(started_at=now, deadline_at=now + scope['duration_seconds'], last_observed_at=now)
                self._save_scope(scope)
            if refusal is None:
                self.db.execute('''INSERT INTO attempts
                  (call_id,attempt,manifest_hash,kind,state,reserved,started,request)
                  VALUES (?,?,?,?,?,?,?,?)''',
                  (call_id, attempt, manifest_hash, kind, 'reserved', amount, utcnow(), canonical(request).decode()))
        if refusal:
            raise BudgetRefused(refusal)
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

    def recover_interrupted(self, manifest_hash=None):
        # Call only under the campaign file lock. A crash may have occurred after
        # dispatch; reserve worst-case charges and permit only one transport retry.
        with self.transaction():
            query = "UPDATE attempts SET state='transport_uncertain', error_kind='interrupted_unknown_charge',finished=? WHERE state IN ('reserved','dispatched')"
            args = (utcnow(),)
            if manifest_hash is not None:
                if not isinstance(manifest_hash, str) or not manifest_hash:
                    raise ValueError('A nonempty manifest hash is required for targeted recovery')
                query += ' AND manifest_hash=?'
                args += (manifest_hash,)
            self.db.execute(query, args)

