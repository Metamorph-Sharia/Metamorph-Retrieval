-- The read contract's tables, as published-market-schema.md has them, for the read model's tests. Only the columns
-- the market provider reads; the types are the live schema's (checked 2026-10-30).
CREATE SCHEMA published_market;

CREATE TABLE published_market.register (
    id text PRIMARY KEY, issuer text NOT NULL, name text NOT NULL, governed_by text[] NOT NULL,
    newest_edition date NOT NULL, editions integer NOT NULL, published_at timestamptz NOT NULL, reports text[] NOT NULL
);
CREATE TABLE published_market.edition (
    register text NOT NULL, edition date NOT NULL, listed integer NOT NULL, joined integer NOT NULL,
    "left" integer NOT NULL, PRIMARY KEY (register, edition)
);
CREATE TABLE published_market.company (
    id text PRIMARY KEY, register text NOT NULL, legal_name text NOT NULL, names text[] NOT NULL,
    business_type text NOT NULL, status text NOT NULL, first_listed date, left_after date
);
CREATE TABLE published_market.entity (
    id text PRIMARY KEY, company_id text NOT NULL, register text NOT NULL, kind text NOT NULL,
    license_number text NOT NULL, license_date date, legal_name text NOT NULL, names text[] NOT NULL,
    business_type text NOT NULL, first_listed date, last_listed date, on_newest_list boolean NOT NULL,
    left_after date, review_notes text[] NOT NULL
);
CREATE TABLE published_market.listing (
    entity_id text NOT NULL, edition date NOT NULL, legal_name text NOT NULL, PRIMARY KEY (entity_id, edition)
);
CREATE TABLE published_market.dataset (
    id text PRIMARY KEY, source text NOT NULL, industry text, "group" text NOT NULL, metric text NOT NULL,
    register text, governed_by text[] NOT NULL, series integer NOT NULL, first_period date NOT NULL,
    last_period date NOT NULL, updated date, url text NOT NULL, published_at timestamptz NOT NULL,
    citation text NOT NULL, reports text[] NOT NULL
);
CREATE TABLE published_market.series (
    id text PRIMARY KEY, dataset text NOT NULL, measure text NOT NULL, label text NOT NULL,
    first_period date NOT NULL, last_period date NOT NULL, observations integer NOT NULL, frequency text NOT NULL,
    unit text
);
CREATE TABLE published_market.observation (
    series_id text NOT NULL, period date NOT NULL, value double precision NOT NULL, provisional boolean NOT NULL,
    PRIMARY KEY (series_id, period)
);
CREATE TABLE published_market.industry (
    source text NOT NULL, name text NOT NULL, register text, governed_by text[] NOT NULL, reports text[] NOT NULL,
    datasets text[] NOT NULL, published_at timestamptz NOT NULL, PRIMARY KEY (source, name)
);
CREATE TABLE published_market.sector (
    id text PRIMARY KEY, name text NOT NULL, name_en text, industries jsonb NOT NULL, registers text[] NOT NULL,
    governed_by text[] NOT NULL, reports text[] NOT NULL, datasets text[] NOT NULL, published_at timestamptz NOT NULL
);
CREATE TABLE published_market.report (
    id text PRIMARY KEY, issuer text NOT NULL, family text NOT NULL, edition text NOT NULL, title text NOT NULL,
    published_on date, language text NOT NULL, url text, citation text NOT NULL, pages integer NOT NULL,
    passages integer NOT NULL, method text NOT NULL, published_at timestamptz NOT NULL
);
CREATE TABLE published_market.report_passage (
    report text NOT NULL, address text NOT NULL, ordinal integer NOT NULL, page_start integer, page_end integer,
    text text NOT NULL, PRIMARY KEY (report, address)
);
CREATE TABLE published_market.release (
    id text PRIMARY KEY, issuer text NOT NULL, number text, title text NOT NULL, published_on date NOT NULL,
    language text NOT NULL, url text, citation text NOT NULL, passages integer NOT NULL,
    published_at timestamptz NOT NULL
);
CREATE TABLE published_market.release_passage (
    release text NOT NULL, address text NOT NULL, ordinal integer NOT NULL, text text NOT NULL,
    PRIMARY KEY (release, address)
);
CREATE TABLE published_market.mention (
    kind text NOT NULL, document text NOT NULL, address text NOT NULL, target_kind text NOT NULL, target text NOT NULL
);
