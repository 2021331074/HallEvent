"""EventHall booking API starter — LOCAL DEVELOPMENT ONLY.

This is the first runnable vertical slice, not the full EventHall project.
It implements inquiry -> approved quote -> accepted quote -> timed hold ->
confirmation for NO-DEPOSIT bookings, backed by PostgreSQL constraints.
It does not implement production authentication, hosted payments, webhooks,
notifications, a staff UI, a Flutter app, or deployment infrastructure.

Setup (Python 3.10+ and PostgreSQL required):
    pip install fastapi 'uvicorn[standard]' 'psycopg[binary]' pydantic
    export DATABASE_URL='postgresql://postgres:postgres@localhost:5432/eventhall'
    export EVENTHALL_LOCAL_DEMO=1
    python eventhall_api.py

Open http://127.0.0.1:8000/docs for the interactive API documentation.
The database user must be able to create the btree_gist extension on first run.

Security: the role and customer headers are deliberately fake local-demo
identity. Anyone who can reach this server can impersonate any role. Bind to
localhost only; NEVER deploy this file or use real customer data. Before any
production use, replace this identity mechanism with verified OIDC, enforce
real roles/object ownership, add migrations, tests, monitoring, and security
reviews. This is a starter, not an implementation of the complete blueprint.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from uuid import UUID, uuid4

import psycopg
from fastapi import FastAPI, Header, HTTPException, Query
from psycopg.errors import ExclusionViolation
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

# EmailStr requires email-validator. Install with:
# pip install email-validator

DATABASE_URL = os.environ.get('DATABASE_URL', '')
if not DATABASE_URL:
    raise RuntimeError('Set DATABASE_URL to a local PostgreSQL connection URL.')
if os.environ.get('EVENTHALL_LOCAL_DEMO') != '1':
    raise RuntimeError('Local demo only. Set EVENTHALL_LOCAL_DEMO=1 to start.')

app = FastAPI(
    title='EventHall local booking API',
    version='0.1.0-local',
    description='Unsafe demo identity. Local use only. No real payments or notifications.',
)

SCHEMA = r'''
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE IF NOT EXISTS resources (
    id uuid PRIMARY KEY,
    name text NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS spaces (
    id uuid PRIMARY KEY,
    name text NOT NULL UNIQUE,
    capacity_seated integer NOT NULL CHECK (capacity_seated > 0),
    published boolean NOT NULL DEFAULT true
);
CREATE TABLE IF NOT EXISTS space_resources (
    space_id uuid NOT NULL REFERENCES spaces(id),
    resource_id uuid NOT NULL REFERENCES resources(id),
    PRIMARY KEY(space_id, resource_id)
);
CREATE TABLE IF NOT EXISTS inquiries (
    id uuid PRIMARY KEY,
    customer_id text NOT NULL,
    customer_name text NOT NULL,
    email text NOT NULL,
    event_type text NOT NULL,
    space_id uuid NOT NULL REFERENCES spaces(id),
    starts_at timestamptz NOT NULL,
    ends_at timestamptz NOT NULL,
    guest_count integer NOT NULL CHECK (guest_count > 0),
    message text NOT NULL DEFAULT '',
    status text NOT NULL CHECK (status IN ('new','quoted','converted','closed')),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (ends_at > starts_at)
);
CREATE TABLE IF NOT EXISTS quotes (
    id uuid PRIMARY KEY,
    inquiry_id uuid NOT NULL REFERENCES inquiries(id),
    version integer NOT NULL CHECK (version > 0),
    status text NOT NULL CHECK (status IN ('sent','accepted','expired','superseded')),
    amount_minor bigint NOT NULL CHECK (amount_minor >= 0),
    currency char(3) NOT NULL,
    deposit_minor bigint NOT NULL CHECK (deposit_minor >= 0 AND deposit_minor <= amount_minor),
    description text NOT NULL,
    terms_version text NOT NULL,
    approved_by text NOT NULL,
    expires_at timestamptz NOT NULL,
    accepted_at timestamptz,
    UNIQUE(inquiry_id, version)
);
CREATE TABLE IF NOT EXISTS reservations (
    id uuid PRIMARY KEY,
    quote_id uuid NOT NULL UNIQUE REFERENCES quotes(id),
    customer_id text NOT NULL,
    space_id uuid NOT NULL REFERENCES spaces(id),
    starts_at timestamptz NOT NULL,
    ends_at timestamptz NOT NULL,
    status text NOT NULL CHECK (status IN ('held','confirmed','expired','canceled')),
    hold_expires_at timestamptz NOT NULL,
    amount_minor bigint NOT NULL,
    currency char(3) NOT NULL,
    accepted_terms_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (ends_at > starts_at)
);
CREATE TABLE IF NOT EXISTS allocations (
    id uuid PRIMARY KEY,
    reservation_id uuid NOT NULL REFERENCES reservations(id),
    resource_id uuid NOT NULL REFERENCES resources(id),
    blocked_range tstzrange NOT NULL,
    active boolean NOT NULL DEFAULT true,
    CONSTRAINT allocations_no_active_overlap
        EXCLUDE USING gist (resource_id WITH =, blocked_range WITH &&)
        WHERE (active)
);
CREATE TABLE IF NOT EXISTS outbox (
    id uuid PRIMARY KEY,
    event_type text NOT NULL,
    reservation_id uuid REFERENCES reservations(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    dispatched_at timestamptz
);
CREATE INDEX IF NOT EXISTS allocations_reservation_idx ON allocations(reservation_id);
CREATE INDEX IF NOT EXISTS reservations_customer_idx ON reservations(customer_id);
'''

# Stable demo identifiers make examples easier to reproduce.
EAST = UUID('00000000-0000-4000-8000-000000000001')
WEST = UUID('00000000-0000-4000-8000-000000000002')
SALON_RESOURCE = UUID('00000000-0000-4000-8000-000000000003')
BALLROOM = UUID('10000000-0000-4000-8000-000000000001')
EAST_ROOM = UUID('10000000-0000-4000-8000-000000000002')
SALON = UUID('10000000-0000-4000-8000-000000000003')


@contextmanager
def db():
    # Psycopg connection context commits on success and rolls back on errors.
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        yield conn


def setup_demo_db() -> None:
    with db() as conn:
        conn.execute(SCHEMA)
        for resource_id, name in [(EAST, 'Ballroom east'), (WEST, 'Ballroom west'),
                                  (SALON_RESOURCE, 'Garden salon')]:
            conn.execute('INSERT INTO resources (id, name) VALUES (%s,%s) ON CONFLICT DO NOTHING',
                         (resource_id, name))
        for space_id, name, capacity in [(BALLROOM, 'Grand Ballroom', 300),
                                         (EAST_ROOM, 'Ballroom East', 120),
                                         (SALON, 'Garden Salon', 120)]:
            conn.execute('INSERT INTO spaces (id,name,capacity_seated) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',
                         (space_id, name, capacity))
        for space_id, resource_id in [(BALLROOM, EAST), (BALLROOM, WEST),
                                      (EAST_ROOM, EAST), (SALON, SALON_RESOURCE)]:
            conn.execute('INSERT INTO space_resources VALUES (%s,%s) ON CONFLICT DO NOTHING',
                         (space_id, resource_id))


@app.on_event('startup')
def startup() -> None:
    setup_demo_db()


class InquiryIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    customer_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    event_type: str = Field(min_length=1, max_length=60)
    space_id: UUID
    starts_at: datetime
    ends_at: datetime
    guest_count: int = Field(gt=0, le=10000)
    message: str = Field(default='', max_length=2000)
    terms_consent: Literal[True]
    marketing_consent: bool = False

    @model_validator(mode='after')
    def validate_interval(self):
        if self.starts_at.utcoffset() is None or self.ends_at.utcoffset() is None:
            raise ValueError('Supply timezone-aware timestamps with explicit offsets.')
        if self.ends_at <= self.starts_at:
            raise ValueError('End must be after start.')
        if self.starts_at <= datetime.now(timezone.utc):
            raise ValueError('Start must be in the future.')
        if self.ends_at - self.starts_at > timedelta(days=3):
            raise ValueError('The demo supports events of at most three days.')
        return self


class QuoteIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    inquiry_id: UUID
    amount_minor: int = Field(ge=0, le=100_000_000)
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    deposit_minor: int = Field(default=0, ge=0)
    description: str = Field(min_length=1, max_length=3000)
    terms_version: str = Field(min_length=1, max_length=100)
    expires_at: datetime

    @model_validator(mode='after')
    def validate_quote(self):
        if self.deposit_minor > self.amount_minor:
            raise ValueError('Deposit cannot exceed total.')
        if self.expires_at.utcoffset() is None or self.expires_at <= datetime.now(timezone.utc):
            raise ValueError('Expiry must be a future timezone-aware timestamp.')
        return self


class AcceptQuoteIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(gt=0)
    terms_version: str = Field(min_length=1, max_length=100)
    accept_terms: Literal[True]


def customer_id(value: Annotated[str | None, Header(alias='X-Demo-Customer')] = None) -> str:
    value = (value or '').strip()
    if not value or len(value) > 100:
        raise HTTPException(401, 'Provide X-Demo-Customer for local testing; it is not authentication.')
    return value


def staff_id(value: Annotated[str | None, Header(alias='X-Demo-Staff')] = None) -> str:
    value = (value or '').strip()
    if not value or len(value) > 100:
        raise HTTPException(401, 'Provide X-Demo-Staff for local testing; it is not authentication.')
    return value


def get_space(conn, space_id: UUID):
    row = conn.execute('SELECT * FROM spaces WHERE id=%s AND published=true', (space_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Space not found.')
    return row


def lock_resources(conn, space_id: UUID) -> list[UUID]:
    rows = conn.execute('''
        SELECT r.id FROM resources r
        JOIN space_resources sr ON sr.resource_id=r.id
        WHERE sr.space_id=%s ORDER BY r.id FOR UPDATE OF r
    ''', (space_id,)).fetchall()
    if not rows:
        raise HTTPException(409, 'Space has no configured bookable resources.')
    return [r['id'] for r in rows]


def release_expired_holds_for_resources(conn, resources: list[UUID]) -> None:
    # All relevant resources must already be locked in deterministic UUID order.
    # Lock entire affected reservation resource sets too would be needed if a
    # single hold could extend beyond the caller's locked resource set. Here,
    # expiry only deactivates rows for locked resources; later requests on other
    # resources reconcile their own stale rows. The reservation status is still
    # correctly marked expired. No allocation can be incorrectly newly active.
    conn.execute('''UPDATE reservations SET status='expired'
        WHERE status='held' AND hold_expires_at <= now()
        AND id IN (SELECT reservation_id FROM allocations WHERE resource_id=ANY(%s) AND active)''',
        (resources,))
    conn.execute('''UPDATE allocations SET active=false
        WHERE active AND resource_id=ANY(%s)
        AND reservation_id IN (SELECT id FROM reservations WHERE status='expired')''',
        (resources,))


def lock_all_reservation_resources(conn, reservation_id: UUID) -> list[UUID]:
    rows = conn.execute('''SELECT r.id FROM resources r JOIN allocations a ON a.resource_id=r.id
        WHERE a.reservation_id=%s ORDER BY r.id FOR UPDATE OF r''', (reservation_id,)).fetchall()
    return [r['id'] for r in rows]


@app.get('/health')
def health():
    with db() as conn:
        conn.execute('SELECT 1')
    return {'status': 'ok', 'environment': 'local-demo-only'}


@app.get('/api/v1/spaces')
def list_spaces():
    with db() as conn:
        return conn.execute('SELECT id,name,capacity_seated FROM spaces WHERE published ORDER BY name').fetchall()


@app.get('/api/v1/availability')
def availability(space_id: UUID, starts_at: datetime, ends_at: datetime,
                 guest_count: int = Query(gt=0, le=10000)):
    if starts_at.utcoffset() is None or ends_at.utcoffset() is None or ends_at <= starts_at:
        raise HTTPException(422, 'Use valid timezone-aware timestamps with end after start.')
    with db() as conn:
        space = get_space(conn, space_id)
        if guest_count > space['capacity_seated']:
            return {'available': False, 'reason': 'capacity', 'advisory_only': True}
        # Availability is a non-locking hint, never a reservation. The actual
        # allocation is checked by PostgreSQL at hold creation.
        conflict = conn.execute('''SELECT EXISTS (
          SELECT 1 FROM allocations a
          JOIN space_resources sr ON sr.resource_id=a.resource_id
          JOIN reservations r ON r.id=a.reservation_id
          WHERE sr.space_id=%s AND a.active
            AND (r.status='confirmed' OR (r.status='held' AND r.hold_expires_at > now()))
            AND a.blocked_range && tstzrange(%s::timestamptz - interval '1 hour',
                                              %s::timestamptz + interval '1 hour','[)')
        ) AS conflict''', (space_id, starts_at, ends_at)).fetchone()['conflict']
        return {'available': not conflict, 'advisory_only': True,
                'message': 'An inquiry or quote does not reserve this date.'}


@app.post('/api/v1/inquiries', status_code=201)
def create_inquiry(body: InquiryIn,
                   customer: Annotated[str | None, Header(alias='X-Demo-Customer')] = None):
    owner = customer_id(customer)
    with db() as conn:
        space = get_space(conn, body.space_id)
        if body.guest_count > space['capacity_seated']:
            raise HTTPException(422, 'Guest count exceeds the example seated capacity.')
        inquiry_id = uuid4()
        conn.execute('''INSERT INTO inquiries
          (id,customer_id,customer_name,email,event_type,space_id,starts_at,ends_at,guest_count,message,status)
          VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'new')''',
          (inquiry_id, owner, body.customer_name, str(body.email), body.event_type,
           body.space_id, body.starts_at, body.ends_at, body.guest_count, body.message))
        # Consent history and marketing consent persistence are intentionally
        # not implemented in this vertical slice; do not use for real users.
        return {'id': inquiry_id, 'status': 'new', 'date_reserved': False,
                'note': 'No email is sent by this demo.'}


@app.post('/api/v1/staff/quotes', status_code=201)
def create_quote(body: QuoteIn, staff: Annotated[str | None, Header(alias='X-Demo-Staff')] = None):
    actor = staff_id(staff)
    if body.deposit_minor:
        raise HTTPException(422, 'Deposits are not supported by this starter. Use zero until real payments are integrated.')
    with db() as conn:
        inquiry = conn.execute('SELECT * FROM inquiries WHERE id=%s FOR UPDATE', (body.inquiry_id,)).fetchone()
        if not inquiry:
            raise HTTPException(404, 'Inquiry not found.')
        if inquiry['status'] in ('converted', 'closed'):
            raise HTTPException(409, 'Inquiry is no longer open for a new quote.')
        version = conn.execute('SELECT COALESCE(MAX(version),0)+1 AS v FROM quotes WHERE inquiry_id=%s',
                               (body.inquiry_id,)).fetchone()['v']
        conn.execute("UPDATE quotes SET status='superseded' WHERE inquiry_id=%s AND status='sent'", (body.inquiry_id,))
        quote_id = uuid4()
        conn.execute('''INSERT INTO quotes
          (id,inquiry_id,version,status,amount_minor,currency,deposit_minor,description,terms_version,approved_by,expires_at)
          VALUES (%s,%s,%s,'sent',%s,%s,%s,%s,%s,%s,%s)''',
          (quote_id, body.inquiry_id, version, body.amount_minor, body.currency, body.deposit_minor,
           body.description, body.terms_version, actor, body.expires_at))
        conn.execute("UPDATE inquiries SET status='quoted' WHERE id=%s", (body.inquiry_id,))
        return {'id': quote_id, 'version': version, 'status': 'sent', 'date_reserved': False}


@app.get('/api/v1/me/quotes/{quote_id}')
def get_quote(quote_id: UUID, customer: Annotated[str | None, Header(alias='X-Demo-Customer')] = None):
    owner = customer_id(customer)
    with db() as conn:
        q = conn.execute('''SELECT q.* FROM quotes q JOIN inquiries i ON i.id=q.inquiry_id
                            WHERE q.id=%s AND i.customer_id=%s''', (quote_id, owner)).fetchone()
        if not q:
            raise HTTPException(404, 'Quote not found.')
        return q


@app.post('/api/v1/quotes/{quote_id}/accept')
def accept_quote(quote_id: UUID, body: AcceptQuoteIn,
                 customer: Annotated[str | None, Header(alias='X-Demo-Customer')] = None):
    owner = customer_id(customer)
    try:
        with db() as conn:
            # Lock inquiry first, consistently with quote creation.
            inquiry = conn.execute('''SELECT i.* FROM inquiries i JOIN quotes q ON q.inquiry_id=i.id
                WHERE q.id=%s AND i.customer_id=%s FOR UPDATE OF i''', (quote_id, owner)).fetchone()
            if not inquiry:
                raise HTTPException(404, 'Quote not found.')
            quote = conn.execute('SELECT * FROM quotes WHERE id=%s FOR UPDATE', (quote_id,)).fetchone()
            existing = conn.execute('SELECT * FROM reservations WHERE quote_id=%s', (quote_id,)).fetchone()
            if existing and quote['version'] == body.version and quote['terms_version'] == body.terms_version:
                return {'id': existing['id'], 'status': existing['status'],
                        'hold_expires_at': existing['hold_expires_at'], 'replayed': True}
            if (quote['status'] != 'sent' or quote['expires_at'] <= datetime.now(timezone.utc)
                    or quote['version'] != body.version or quote['terms_version'] != body.terms_version):
                raise HTTPException(409, 'Quote expired, changed, or no longer available. Request a fresh quote.')
            if quote['deposit_minor'] != 0 or not quote['approved_by']:
                raise HTTPException(409, 'Deposit handling or staff approval is not available.')
            space = get_space(conn, inquiry['space_id'])
            if inquiry['guest_count'] > space['capacity_seated']:
                raise HTTPException(409, 'Space capacity changed. Request staff review.')
            resources = lock_resources(conn, inquiry['space_id'])
            release_expired_holds_for_resources(conn, resources)
            reservation_id = uuid4()
            hold_expiry = datetime.now(timezone.utc) + timedelta(hours=24)
            conn.execute('''INSERT INTO reservations
              (id,quote_id,customer_id,space_id,starts_at,ends_at,status,hold_expires_at,
               amount_minor,currency,accepted_terms_version)
              VALUES (%s,%s,%s,%s,%s,%s,'held',%s,%s,%s,%s)''',
              (reservation_id, quote_id, owner, inquiry['space_id'], inquiry['starts_at'], inquiry['ends_at'],
               hold_expiry, quote['amount_minor'], quote['currency'], body.terms_version))
            for resource_id in resources:
                conn.execute('''INSERT INTO allocations (id,reservation_id,resource_id,blocked_range)
                  VALUES (%s,%s,%s,tstzrange(%s::timestamptz - interval '1 hour',
                                             %s::timestamptz + interval '1 hour','[)'))''',
                  (uuid4(), reservation_id, resource_id, inquiry['starts_at'], inquiry['ends_at']))
            conn.execute("UPDATE quotes SET status='accepted',accepted_at=now() WHERE id=%s", (quote_id,))
            conn.execute("UPDATE inquiries SET status='converted' WHERE id=%s", (inquiry['id'],))
            return {'id': reservation_id, 'status': 'held', 'hold_expires_at': hold_expiry,
                    'message': 'Temporary hold only; call confirm while the hold is valid.'}
    except ExclusionViolation:
        raise HTTPException(409, 'That space is no longer available. Please request another date or space.')


@app.post('/api/v1/reservations/{reservation_id}/confirm')
def confirm(reservation_id: UUID, customer: Annotated[str | None, Header(alias='X-Demo-Customer')] = None):
    owner = customer_id(customer)
    with db() as conn:
        # Lock resources before reservation rows so competing allocation paths
        # use a common resource ordering. No payment flow exists in this demo.
        exists = conn.execute('SELECT id FROM reservations WHERE id=%s AND customer_id=%s',
                              (reservation_id, owner)).fetchone()
        if not exists:
            raise HTTPException(404, 'Reservation not found.')
        resources = lock_all_reservation_resources(conn, reservation_id)
        if not resources:
            raise HTTPException(409, 'Reservation has no allocation. Request staff review.')
        release_expired_holds_for_resources(conn, resources)
        r = conn.execute('SELECT * FROM reservations WHERE id=%s FOR UPDATE', (reservation_id,)).fetchone()
        if r['status'] == 'confirmed':
            return {'id': r['id'], 'status': 'confirmed', 'replayed': True}
        if r['status'] != 'held' or r['hold_expires_at'] <= datetime.now(timezone.utc):
            raise HTTPException(409, 'Hold expired or reservation is not eligible for confirmation.')
        q = conn.execute('SELECT * FROM quotes WHERE id=%s', (r['quote_id'],)).fetchone()
        active_count = conn.execute('SELECT count(*) AS n FROM allocations WHERE reservation_id=%s AND active',
                                    (reservation_id,)).fetchone()['n']
        if (not q or q['status'] != 'accepted' or not q['approved_by'] or q['deposit_minor'] != 0
                or q['terms_version'] != r['accepted_terms_version'] or active_count != len(resources)):
            raise HTTPException(409, 'Confirmation conditions are not met. Request staff review.')
        conn.execute("UPDATE reservations SET status='confirmed' WHERE id=%s", (reservation_id,))
        # Atomic outbox record: there is intentionally no dispatcher yet.
        conn.execute("INSERT INTO outbox (id,event_type,reservation_id) VALUES (%s,'reservation.confirmed',%s)",
                     (uuid4(), reservation_id))
        return {'id': reservation_id, 'status': 'confirmed',
                'notification': 'Outbox record created; no worker is implemented.'}


@app.get('/api/v1/me/reservations')
def my_reservations(customer: Annotated[str | None, Header(alias='X-Demo-Customer')] = None):
    owner = customer_id(customer)
    with db() as conn:
        return conn.execute('''SELECT id,space_id,starts_at,ends_at,status,hold_expires_at,
                               amount_minor,currency FROM reservations
                               WHERE customer_id=%s ORDER BY created_at DESC LIMIT 100''', (owner,)).fetchall()


if __name__ == '__main__':
    import uvicorn
    # Intentionally never expose on 0.0.0.0 in this unsafe local-demo starter.
    uvicorn.run(app, host='127.0.0.1', port=8000)
