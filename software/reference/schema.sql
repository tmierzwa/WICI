PRAGMA foreign_keys = ON;
-- Reception keys (source, id, revision, sha256) are kept after CLOSE EVENT; only payload is cleared.
CREATE TABLE IF NOT EXISTS received (
    source BLOB NOT NULL CHECK(length(source)=16),
    id TEXT NOT NULL CHECK(length(id)=32),
    revision INTEGER NOT NULL CHECK(revision BETWEEN 0 AND 65535),
    sha256 BLOB NOT NULL CHECK(length(sha256)=32),
    payload BLOB,
    PRIMARY KEY(source,id,revision)
);
CREATE TABLE IF NOT EXISTS ack_outbox (
    source BLOB NOT NULL,
    id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    payload BLOB NOT NULL,
    PRIMARY KEY(source,id,revision),
    FOREIGN KEY(source,id,revision) REFERENCES received(source,id,revision)
);
-- Trusted stations come only from station cards with the full public identity key.
CREATE TABLE IF NOT EXISTS trusted (
    source BLOB PRIMARY KEY CHECK(length(source)=16),
    pubkey BLOB NOT NULL CHECK(length(pubkey)=64)
);
-- Stations removed from the trusted list: their messages go to quarantine flagged as a possible takeover.
CREATE TABLE IF NOT EXISTS removed (
    source BLOB PRIMARY KEY CHECK(length(source)=16),
    messages INTEGER NOT NULL DEFAULT 0
);
-- Limits (4 per sender, 256 in total) are enforced by the model before insertion.
CREATE TABLE IF NOT EXISTS quarantine (
    source BLOB NOT NULL CHECK(length(source)=16),
    id TEXT NOT NULL CHECK(length(id)=32),
    revision INTEGER NOT NULL CHECK(revision BETWEEN 0 AND 65535),
    sha256 BLOB NOT NULL CHECK(length(sha256)=32),
    payload BLOB NOT NULL,
    PRIMARY KEY(source,id,revision)
);
CREATE TABLE IF NOT EXISTS replies (
    dest BLOB NOT NULL,
    id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    event INTEGER NOT NULL,
    text TEXT,
    PRIMARY KEY(dest,id,revision,event),
    FOREIGN KEY(dest,id,revision) REFERENCES received(source,id,revision)
);
CREATE TABLE IF NOT EXISTS statuses (
    dest BLOB NOT NULL,
    id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    event INTEGER NOT NULL,
    state INTEGER NOT NULL CHECK(state BETWEEN 1 AND 6),
    PRIMARY KEY(dest,id,revision),
    FOREIGN KEY(dest,id,revision) REFERENCES received(source,id,revision)
);
