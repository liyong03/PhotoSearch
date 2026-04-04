use anyhow::{Context, Result};
use rusqlite::{Connection, params};
use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};
use std::sync::Mutex;

pub struct Database {
    conn: Mutex<Connection>,
}

#[derive(Debug, Clone)]
pub struct PhotoRecord {
    pub id: String,
    pub path: String,
    pub timestamp: Option<i64>,
    pub latitude: Option<f64>,
    pub longitude: Option<f64>,
    pub description: Option<String>,
    pub tags: Option<String>,
    pub camera_make: Option<String>,
    pub camera_model: Option<String>,
}

/// Generate a deterministic photo ID from a file path.
pub fn generate_photo_id(path: &str) -> String {
    let mut hasher = DefaultHasher::new();
    path.hash(&mut hasher);
    format!("{:016x}", hasher.finish())
}

impl Database {
    pub fn new(db_path: &str) -> Result<Self> {
        if let Some(parent) = std::path::Path::new(db_path).parent() {
            std::fs::create_dir_all(parent)?;
        }

        let conn = Connection::open(db_path)
            .context("Failed to open database")?;

        // Migrate from legacy Python schema if needed.
        // The old schema uses "file_path" instead of "path" and has extra columns.
        let needs_migration = conn
            .prepare("SELECT sql FROM sqlite_master WHERE type='table' AND name='photos'")
            .and_then(|mut stmt| stmt.query_row([], |row| row.get::<_, String>(0)))
            .map(|sql| sql.contains("file_path"))
            .unwrap_or(false);

        if needs_migration {
            conn.execute_batch(
                "DROP TRIGGER IF EXISTS photos_ai;
                 DROP TRIGGER IF EXISTS photos_ad;
                 DROP TRIGGER IF EXISTS photos_au;
                 DROP TABLE IF EXISTS photos_fts;
                 DROP TABLE IF EXISTS caption_embeddings;
                 DROP TABLE IF EXISTS embeddings;
                 DROP TABLE IF EXISTS photos;"
            ).context("Failed to drop legacy tables")?;
        }

        // Create tables
        conn.execute_batch(
            "CREATE TABLE IF NOT EXISTS photos (
                id TEXT PRIMARY KEY,
                path TEXT NOT NULL UNIQUE,
                timestamp INTEGER,
                latitude REAL,
                longitude REAL,
                description TEXT,
                tags TEXT,
                camera_make TEXT,
                camera_model TEXT,
                indexed_at INTEGER DEFAULT (strftime('%s', 'now'))
            );

            CREATE INDEX IF NOT EXISTS idx_photos_timestamp ON photos(timestamp);
            CREATE INDEX IF NOT EXISTS idx_photos_latitude ON photos(latitude);
            CREATE INDEX IF NOT EXISTS idx_photos_longitude ON photos(longitude);
            CREATE INDEX IF NOT EXISTS idx_photos_path ON photos(path);

            CREATE VIRTUAL TABLE IF NOT EXISTS photos_fts USING fts5(
                description, tags, content='photos', content_rowid='rowid'
            );

            CREATE TRIGGER IF NOT EXISTS photos_ai AFTER INSERT ON photos BEGIN
                INSERT INTO photos_fts(rowid, description, tags)
                VALUES (new.rowid, new.description, new.tags);
            END;

            CREATE TRIGGER IF NOT EXISTS photos_ad AFTER DELETE ON photos BEGIN
                INSERT INTO photos_fts(photos_fts, rowid, description, tags)
                VALUES ('delete', old.rowid, old.description, old.tags);
            END;

            CREATE TRIGGER IF NOT EXISTS photos_au AFTER UPDATE ON photos BEGIN
                INSERT INTO photos_fts(photos_fts, rowid, description, tags)
                VALUES ('delete', old.rowid, old.description, old.tags);
                INSERT INTO photos_fts(rowid, description, tags)
                VALUES (new.rowid, new.description, new.tags);
            END;"
        ).context("Failed to create tables")?;

        Ok(Self {
            conn: Mutex::new(conn),
        })
    }

    pub fn insert_photo(&self, photo: &PhotoRecord) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute(
            "INSERT OR REPLACE INTO photos (id, path, timestamp, latitude, longitude, description, tags, camera_make, camera_model)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)",
            params![
                photo.id, photo.path, photo.timestamp, photo.latitude, photo.longitude,
                photo.description, photo.tags, photo.camera_make, photo.camera_model
            ],
        )?;
        Ok(())
    }

    pub fn get_photo(&self, photo_id: &str) -> Result<Option<PhotoRecord>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT id, path, timestamp, latitude, longitude, description, tags, camera_make, camera_model
             FROM photos WHERE id = ?1"
        )?;

        let result = stmt.query_row(params![photo_id], |row| {
            Ok(PhotoRecord {
                id: row.get(0)?,
                path: row.get(1)?,
                timestamp: row.get(2)?,
                latitude: row.get(3)?,
                longitude: row.get(4)?,
                description: row.get(5)?,
                tags: row.get(6)?,
                camera_make: row.get(7)?,
                camera_model: row.get(8)?,
            })
        });

        match result {
            Ok(photo) => Ok(Some(photo)),
            Err(rusqlite::Error::QueryReturnedNoRows) => Ok(None),
            Err(e) => Err(e.into()),
        }
    }

    pub fn delete_photo(&self, photo_id: &str) -> Result<bool> {
        let conn = self.conn.lock().unwrap();
        let rows = conn.execute("DELETE FROM photos WHERE id = ?1", params![photo_id])?;
        Ok(rows > 0)
    }

    pub fn get_photos(&self, limit: u32, offset: u32) -> Result<Vec<PhotoRecord>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT id, path, timestamp, latitude, longitude, description, tags, camera_make, camera_model
             FROM photos ORDER BY timestamp DESC LIMIT ?1 OFFSET ?2"
        )?;

        let photos = stmt.query_map(params![limit, offset], |row| {
            Ok(PhotoRecord {
                id: row.get(0)?,
                path: row.get(1)?,
                timestamp: row.get(2)?,
                latitude: row.get(3)?,
                longitude: row.get(4)?,
                description: row.get(5)?,
                tags: row.get(6)?,
                camera_make: row.get(7)?,
                camera_model: row.get(8)?,
            })
        })?.collect::<std::result::Result<Vec<_>, _>>()?;

        Ok(photos)
    }

    pub fn filter_by_time_range(&self, start: i64, end: i64) -> Result<Vec<String>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT id FROM photos WHERE timestamp >= ?1 AND timestamp <= ?2"
        )?;
        let ids = stmt.query_map(params![start, end], |row| row.get(0))?
            .collect::<std::result::Result<Vec<String>, _>>()?;
        Ok(ids)
    }

    pub fn filter_by_location(&self, min_lat: f64, max_lat: f64, min_lon: f64, max_lon: f64) -> Result<Vec<String>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT id FROM photos WHERE latitude >= ?1 AND latitude <= ?2 AND longitude >= ?3 AND longitude <= ?4"
        )?;
        let ids = stmt.query_map(params![min_lat, max_lat, min_lon, max_lon], |row| row.get(0))?
            .collect::<std::result::Result<Vec<String>, _>>()?;
        Ok(ids)
    }

    pub fn filter_by_folder(&self, folder_path: &str) -> Result<Vec<String>> {
        let conn = self.conn.lock().unwrap();
        let pattern = format!("{}%", folder_path);
        let mut stmt = conn.prepare(
            "SELECT id FROM photos WHERE path LIKE ?1"
        )?;
        let ids = stmt.query_map(params![pattern], |row| row.get(0))?
            .collect::<std::result::Result<Vec<String>, _>>()?;
        Ok(ids)
    }

    pub fn full_text_search(&self, query: &str) -> Result<Vec<String>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT photos.id FROM photos_fts
             JOIN photos ON photos.rowid = photos_fts.rowid
             WHERE photos_fts MATCH ?1
             ORDER BY rank"
        )?;
        let ids = stmt.query_map(params![query], |row| row.get(0))?
            .collect::<std::result::Result<Vec<String>, _>>()?;
        Ok(ids)
    }

    pub fn photo_count(&self) -> Result<u32> {
        let conn = self.conn.lock().unwrap();
        let count: u32 = conn.query_row("SELECT COUNT(*) FROM photos", [], |row| row.get(0))?;
        Ok(count)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_db() -> Database {
        Database::new(":memory:").unwrap()
    }

    #[test]
    fn test_insert_and_get() {
        let db = test_db();
        let photo = PhotoRecord {
            id: "test1".to_string(),
            path: "/photos/test.jpg".to_string(),
            timestamp: Some(1700000000),
            latitude: Some(37.7749),
            longitude: Some(-122.4194),
            description: Some("Golden Gate Bridge".to_string()),
            tags: Some("bridge,san francisco".to_string()),
            camera_make: Some("Apple".to_string()),
            camera_model: Some("iPhone 15".to_string()),
        };

        db.insert_photo(&photo).unwrap();
        let retrieved = db.get_photo("test1").unwrap().unwrap();
        assert_eq!(retrieved.path, "/photos/test.jpg");
        assert_eq!(retrieved.description, Some("Golden Gate Bridge".to_string()));
    }

    #[test]
    fn test_delete() {
        let db = test_db();
        let photo = PhotoRecord {
            id: "test1".to_string(),
            path: "/photos/test.jpg".to_string(),
            timestamp: None, latitude: None, longitude: None,
            description: None, tags: None, camera_make: None, camera_model: None,
        };
        db.insert_photo(&photo).unwrap();
        assert!(db.delete_photo("test1").unwrap());
        assert!(db.get_photo("test1").unwrap().is_none());
    }

    #[test]
    fn test_filter_by_time() {
        let db = test_db();
        for i in 0..5 {
            let photo = PhotoRecord {
                id: format!("photo{}", i),
                path: format!("/photos/{}.jpg", i),
                timestamp: Some(1700000000 + i * 100),
                latitude: None, longitude: None, description: None,
                tags: None, camera_make: None, camera_model: None,
            };
            db.insert_photo(&photo).unwrap();
        }

        let ids = db.filter_by_time_range(1700000100, 1700000300).unwrap();
        assert_eq!(ids.len(), 3);
    }

    #[test]
    fn test_photo_count() {
        let db = test_db();
        assert_eq!(db.photo_count().unwrap(), 0);
        let photo = PhotoRecord {
            id: "test1".to_string(),
            path: "/photos/test.jpg".to_string(),
            timestamp: None, latitude: None, longitude: None,
            description: None, tags: None, camera_make: None, camera_model: None,
        };
        db.insert_photo(&photo).unwrap();
        assert_eq!(db.photo_count().unwrap(), 1);
    }
}
