-- PhotoSearch Database Schema

-- Main photos table
CREATE TABLE IF NOT EXISTS photos (
    id TEXT PRIMARY KEY,
    file_path TEXT UNIQUE NOT NULL,
    filename TEXT NOT NULL,
    timestamp DATETIME,
    latitude REAL,
    longitude REAL,
    city TEXT,
    state TEXT,
    country TEXT,
    place_name TEXT,
    description TEXT,
    tags TEXT,  -- JSON array stored as string
    indexed_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_photos_timestamp ON photos(timestamp);
CREATE INDEX IF NOT EXISTS idx_photos_latitude ON photos(latitude);
CREATE INDEX IF NOT EXISTS idx_photos_longitude ON photos(longitude);
CREATE INDEX IF NOT EXISTS idx_photos_city ON photos(city);
CREATE INDEX IF NOT EXISTS idx_photos_country ON photos(country);
CREATE INDEX IF NOT EXISTS idx_photos_indexed_at ON photos(indexed_at);

-- Full-text search virtual table
CREATE VIRTUAL TABLE IF NOT EXISTS photos_fts USING fts5(
    id,
    description,
    city,
    state,
    country,
    place_name,
    tags,
    content='photos',
    content_rowid='rowid'
);

-- Triggers to keep FTS index in sync with photos table
CREATE TRIGGER IF NOT EXISTS photos_ai AFTER INSERT ON photos BEGIN
    INSERT INTO photos_fts(rowid, id, description, city, state, country, place_name, tags)
    VALUES (NEW.rowid, NEW.id, NEW.description, NEW.city, NEW.state, NEW.country, NEW.place_name, NEW.tags);
END;

CREATE TRIGGER IF NOT EXISTS photos_ad AFTER DELETE ON photos BEGIN
    INSERT INTO photos_fts(photos_fts, rowid, id, description, city, state, country, place_name, tags)
    VALUES ('delete', OLD.rowid, OLD.id, OLD.description, OLD.city, OLD.state, OLD.country, OLD.place_name, OLD.tags);
END;

CREATE TRIGGER IF NOT EXISTS photos_au AFTER UPDATE ON photos BEGIN
    INSERT INTO photos_fts(photos_fts, rowid, id, description, city, state, country, place_name, tags)
    VALUES ('delete', OLD.rowid, OLD.id, OLD.description, OLD.city, OLD.state, OLD.country, OLD.place_name, OLD.tags);
    INSERT INTO photos_fts(rowid, id, description, city, state, country, place_name, tags)
    VALUES (NEW.rowid, NEW.id, NEW.description, NEW.city, NEW.state, NEW.country, NEW.place_name, NEW.tags);
END;

-- Embeddings tracking table (actual vectors stored in FAISS)
CREATE TABLE IF NOT EXISTS embeddings (
    photo_id TEXT PRIMARY KEY REFERENCES photos(id) ON DELETE CASCADE,
    faiss_index INTEGER NOT NULL,  -- Index position in FAISS
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_embeddings_faiss_index ON embeddings(faiss_index);
