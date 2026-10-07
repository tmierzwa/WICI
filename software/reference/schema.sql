PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS received (
    source BLOB NOT NULL CHECK(length(source)=16),
    id TEXT NOT NULL CHECK(length(id)=32),
    revision INTEGER NOT NULL CHECK(revision BETWEEN 0 AND 65535),
    payload BLOB NOT NULL,
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
CREATE TABLE IF NOT EXISTS trusted (
    source BLOB PRIMARY KEY CHECK(length(source)=16)
);
CREATE TABLE IF NOT EXISTS quarantine (
    source BLOB NOT NULL CHECK(length(source)=16),
    id TEXT NOT NULL CHECK(length(id)=32),
    revision INTEGER NOT NULL CHECK(revision BETWEEN 0 AND 65535),
    payload BLOB NOT NULL,
    PRIMARY KEY(source,id,revision)
);
