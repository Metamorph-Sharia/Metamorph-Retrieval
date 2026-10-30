-- The part of the platform's published schema the stand-in reads (published-schema.md). provision_unit is a view
-- there; a table holding the same columns here.
CREATE SCHEMA published;

CREATE TABLE published.document (
    id text PRIMARY KEY, issuer text NOT NULL, family text NOT NULL, number text NOT NULL, year integer NOT NULL,
    citation text NOT NULL, title text NOT NULL, language text NOT NULL DEFAULT 'id', kind text NOT NULL,
    id_confidence text NOT NULL DEFAULT 'exact', status text NOT NULL, status_as_of date, enacted_on date,
    promulgated_on date, effective_on date, aliases text[] NOT NULL DEFAULT '{}', curated boolean NOT NULL DEFAULT false,
    published_at timestamptz NOT NULL
);

CREATE TABLE published.provision_unit (
    document_id text NOT NULL REFERENCES published.document (id), address text NOT NULL, kind text NOT NULL,
    label text, heading text, heading_path text[] NOT NULL, wording text NOT NULL, text_sha256 text NOT NULL,
    page_start integer, page_end integer, valid_from date, valid_to date, under_review boolean NOT NULL,
    PRIMARY KEY (document_id, address)
);
