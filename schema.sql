-- EventHall PostgreSQL booking schema starter
-- For a fresh development database. Not a complete production migration.
-- PostgreSQL is required; use a migration tool to manage subsequent changes.
-- Application code must authenticate and authorize every operation.

BEGIN;
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE venues (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  time_zone text NOT NULL, -- validate against IANA time zones in the application
  currency char(3) NOT NULL, -- validate supported ISO currency and minor-unit rules
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  identity_subject text NOT NULL UNIQUE,
  email text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE staff_roles (
  venue_id uuid NOT NULL REFERENCES venues(id),
  user_id uuid NOT NULL REFERENCES users(id),
  role text NOT NULL CHECK (role IN ('coordinator', 'manager', 'administrator')),
  PRIMARY KEY (venue_id, user_id, role)
);

CREATE TABLE spaces (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  venue_id uuid NOT NULL REFERENCES venues(id),
  name text NOT NULL,
  published boolean NOT NULL DEFAULT false,
  UNIQUE (venue_id, id)
);

CREATE TABLE layouts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  venue_id uuid NOT NULL,
  space_id uuid NOT NULL,
  name text NOT NULL,
  capacity integer NOT NULL CHECK (capacity > 0),
  FOREIGN KEY (venue_id, space_id) REFERENCES spaces (venue_id, id),
  UNIQUE (venue_id, id)
);

CREATE TABLE resources (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  venue_id uuid NOT NULL REFERENCES venues(id),
  name text NOT NULL,
  UNIQUE (venue_id, id),
  UNIQUE (venue_id, name)
);

-- A combined space lists every constituent bookable resource.
CREATE TABLE space_resources (
  venue_id uuid NOT NULL,
  space_id uuid NOT NULL,
  resource_id uuid NOT NULL,
  PRIMARY KEY (space_id, resource_id),
  FOREIGN KEY (venue_id, space_id) REFERENCES spaces (venue_id, id),
  FOREIGN KEY (venue_id, resource_id) REFERENCES resources (venue_id, id)
);

CREATE TABLE inquiries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  venue_id uuid NOT NULL REFERENCES venues(id),
  customer_id uuid REFERENCES users(id),
  contact_name text NOT NULL,
  contact_email text NOT NULL,
  event_type text NOT NULL,
  guests integer NOT NULL CHECK (guests > 0),
  desired_start timestamptz NOT NULL,
  desired_end timestamptz NOT NULL,
  space_id uuid NOT NULL,
  status text NOT NULL DEFAULT 'new' CHECK (status IN ('new','reviewing','quoted','converted','closed')),
  required_consent_at timestamptz,
  marketing_consent boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (desired_end > desired_start),
  FOREIGN KEY (venue_id, space_id) REFERENCES spaces (venue_id, id),
  UNIQUE (venue_id, id)
);

CREATE TABLE quotes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  venue_id uuid NOT NULL,
  inquiry_id uuid NOT NULL,
  version integer NOT NULL CHECK (version > 0),
  status text NOT NULL CHECK (status IN ('draft','sent','accepted','expired','superseded')),
  expires_at timestamptz NOT NULL,
  amount_minor bigint NOT NULL CHECK (amount_minor >= 0),
  deposit_minor bigint NOT NULL CHECK (deposit_minor >= 0 AND deposit_minor <= amount_minor),
  currency char(3) NOT NULL,
  price_snapshot jsonb NOT NULL,
  terms_snapshot jsonb NOT NULL,
  accepted_by uuid REFERENCES users(id),
  accepted_at timestamptz,
  FOREIGN KEY (venue_id, inquiry_id) REFERENCES inquiries (venue_id, id),
  UNIQUE (inquiry_id, version),
  UNIQUE (venue_id, id),
  CHECK (status <> 'accepted' OR (accepted_by IS NOT NULL AND accepted_at IS NOT NULL))
);

CREATE TABLE reservations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  venue_id uuid NOT NULL REFERENCES venues(id),
  customer_id uuid NOT NULL REFERENCES users(id),
  quote_id uuid NOT NULL,
  layout_id uuid,
  status text NOT NULL CHECK (status IN ('held','awaiting_payment','confirmed','canceled','completed','expired')),
  event_start timestamptz NOT NULL,
  event_end timestamptz NOT NULL,
  guests integer NOT NULL CHECK (guests > 0),
  hold_expires_at timestamptz,
  staff_approved_by uuid REFERENCES users(id),
  staff_approved_at timestamptz,
  policy_snapshot jsonb NOT NULL,
  price_snapshot jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (event_end > event_start),
  CHECK (status NOT IN ('held','awaiting_payment') OR hold_expires_at IS NOT NULL),
  CHECK ((staff_approved_by IS NULL) = (staff_approved_at IS NULL)),
  FOREIGN KEY (venue_id, quote_id) REFERENCES quotes (venue_id, id),
  FOREIGN KEY (venue_id, layout_id) REFERENCES layouts (venue_id, id),
  UNIQUE (venue_id, id)
);
CREATE UNIQUE INDEX one_active_reservation_per_quote ON reservations (quote_id)
  WHERE status IN ('held','awaiting_payment','confirmed');
CREATE INDEX reservations_hold_expiry ON reservations (hold_expires_at)
  WHERE status IN ('held','awaiting_payment');

CREATE TABLE blackouts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  venue_id uuid NOT NULL REFERENCES venues(id),
  reason text NOT NULL,
  created_by uuid NOT NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (venue_id, id)
);

-- Every hold, confirmed booking, and maintenance block must have allocations
-- for ALL affected resources. The range includes setup/cleanup and uses [).
-- Expiry is reconciled under resource locks; active is NEVER derived from now().
CREATE TABLE allocations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  venue_id uuid NOT NULL,
  resource_id uuid NOT NULL,
  reservation_id uuid,
  blackout_id uuid,
  blocked_range tstzrange NOT NULL,
  active boolean NOT NULL DEFAULT true,
  FOREIGN KEY (venue_id, resource_id) REFERENCES resources (venue_id, id),
  FOREIGN KEY (venue_id, reservation_id) REFERENCES reservations (venue_id, id),
  FOREIGN KEY (venue_id, blackout_id) REFERENCES blackouts (venue_id, id),
  CHECK ((reservation_id IS NOT NULL) <> (blackout_id IS NOT NULL)),
  CHECK (NOT isempty(blocked_range) AND NOT lower_inf(blocked_range)
         AND NOT upper_inf(blocked_range) AND lower_inc(blocked_range)
         AND NOT upper_inc(blocked_range)),
  EXCLUDE USING gist (resource_id WITH =, blocked_range WITH &&) WHERE (active)
);
CREATE INDEX allocation_reservation_idx ON allocations (reservation_id) WHERE reservation_id IS NOT NULL;
CREATE INDEX allocation_blackout_idx ON allocations (blackout_id) WHERE blackout_id IS NOT NULL;

CREATE TABLE payments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  venue_id uuid NOT NULL,
  reservation_id uuid NOT NULL,
  provider text NOT NULL,
  provider_payment_id text,
  amount_minor bigint NOT NULL CHECK (amount_minor >= 0),
  currency char(3) NOT NULL,
  status text NOT NULL CHECK (status IN ('pending','succeeded','failed','partially_refunded','refunded')),
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (venue_id, reservation_id) REFERENCES reservations (venue_id, id),
  UNIQUE (venue_id, id),
  UNIQUE (provider, provider_payment_id)
);

CREATE TABLE refunds (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  venue_id uuid NOT NULL,
  payment_id uuid NOT NULL,
  amount_minor bigint NOT NULL CHECK (amount_minor > 0),
  status text NOT NULL CHECK (status IN ('pending','succeeded','failed')),
  approved_by uuid NOT NULL REFERENCES users(id),
  reason text NOT NULL,
  provider_refund_id text,
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (venue_id, payment_id) REFERENCES payments (venue_id, id)
  -- Service must lock payment and ensure total refunds do not exceed settlement.
);

CREATE TABLE provider_events (
  provider text NOT NULL,
  event_id text NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now(),
  processed_at timestamptz,
  PRIMARY KEY (provider, event_id)
  -- Verify raw-body signatures before inserting or processing.
);

CREATE TABLE idempotency_keys (
  actor_id uuid NOT NULL REFERENCES users(id),
  operation text NOT NULL,
  key text NOT NULL,
  request_hash text NOT NULL,
  response_status integer,
  response_body jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (actor_id, operation, key)
);

CREATE TABLE outbox_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type text NOT NULL,
  aggregate_id uuid NOT NULL,
  payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  published_at timestamptz,
  attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0)
);
CREATE INDEX pending_outbox ON outbox_events (created_at) WHERE published_at IS NULL;

CREATE TABLE audit_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  venue_id uuid NOT NULL REFERENCES venues(id),
  actor_id uuid REFERENCES users(id),
  action text NOT NULL,
  entity_id uuid NOT NULL,
  reason text,
  before_value jsonb,
  after_value jsonb,
  occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_entity ON audit_events (venue_id, entity_id, occurred_at);
COMMIT;

-- Implementation contract, not a completed service:
-- 1. In a transaction lock required resource rows in stable UUID order.
-- 2. Reconcile expired holds AND deactivate their allocations under those locks.
-- 3. Validate room/layout capacity, approval, accepted quote version and policy.
-- 4. Insert ALL buffered resource allocations. Catch exclusion_violation (23P01)
--    and return HTTP 409 without exposing other customers' information.
-- 5. Confirm only after revalidating availability, approval, terms and deposit;
--    write the confirmation and outbox event in the same transaction.
-- 6. Process verified webhook events idempotently. Late settled payments require
--    a staff exception; do not confirm an expired or conflicting reservation.
-- 7. This starter does not implement state-transition enforcement, background
--    workers, immutable-audit permissions, encryption, retention, row-level
--    authorization, notification delivery, or complete migrations/tests.
