use std::sync::Mutex;
use std::time::{Duration, Instant};

use lru::LruCache;
use std::num::NonZeroUsize;

/// Bounding box from forward geocoding.
#[derive(Debug, Clone)]
pub struct BoundingBox {
    pub min_lat: f64,
    pub max_lat: f64,
    pub min_lon: f64,
    pub max_lon: f64,
    pub center_lat: f64,
    pub center_lon: f64,
}

/// Place information from reverse geocoding.
#[derive(Debug, Clone, Default)]
pub struct PlaceInfo {
    pub city: Option<String>,
    pub state: Option<String>,
    pub country: Option<String>,
    pub place_name: String,
}

/// Geocoding service using Nominatim API with caching and rate limiting.
pub struct GeocodingService {
    inner: Mutex<GeocodingInner>,
}

struct GeocodingInner {
    forward_cache: LruCache<String, Option<BoundingBox>>,
    reverse_cache: LruCache<String, PlaceInfo>,
    last_request: Option<Instant>,
    client: Option<reqwest::blocking::Client>,
}

impl GeocodingInner {
    /// Lazily initialize the HTTP client on first use to avoid blocking the main thread
    /// during engine init (reqwest::blocking::Client spawns a tokio runtime thread which
    /// causes a priority inversion when called from the UI thread).
    fn client(&mut self) -> &reqwest::blocking::Client {
        self.client.get_or_insert_with(|| {
            reqwest::blocking::Client::builder()
                .user_agent("PhotoSearch/1.0")
                .timeout(Duration::from_secs(10))
                .build()
                .unwrap()
        })
    }
}

impl GeocodingService {
    pub fn new() -> Self {
        Self {
            inner: Mutex::new(GeocodingInner {
                forward_cache: LruCache::new(NonZeroUsize::new(500).unwrap()),
                reverse_cache: LruCache::new(NonZeroUsize::new(1000).unwrap()),
                last_request: None,
                client: None,
            }),
        }
    }

    /// Forward geocode: place name → bounding box.
    pub fn geocode(&self, place_name: &str) -> Option<BoundingBox> {
        let key = place_name.to_lowercase().trim().to_string();
        if key.is_empty() {
            return None;
        }

        let mut inner = self.inner.lock().unwrap();

        // Check cache
        if let Some(cached) = inner.forward_cache.get(&key) {
            return cached.clone();
        }

        // Rate limit: 1 request per second (Nominatim policy)
        Self::rate_limit(&mut inner);

        let url = format!(
            "https://nominatim.openstreetmap.org/search?q={}&format=json&limit=1",
            urlencoding(&key)
        );

        let result = inner
            .client()
            .get(&url)
            .send()
            .ok()
            .and_then(|resp| resp.json::<Vec<serde_json::Value>>().ok())
            .and_then(|results| {
                let first = results.into_iter().next()?;
                let lat = first["lat"].as_str()?.parse::<f64>().ok()?;
                let lon = first["lon"].as_str()?.parse::<f64>().ok()?;

                let bbox = if let Some(bb) = first["boundingbox"].as_array() {
                    if bb.len() == 4 {
                        let min_lat = bb[0].as_str()?.parse::<f64>().ok()?;
                        let max_lat = bb[1].as_str()?.parse::<f64>().ok()?;
                        let min_lon = bb[2].as_str()?.parse::<f64>().ok()?;
                        let max_lon = bb[3].as_str()?.parse::<f64>().ok()?;
                        BoundingBox {
                            min_lat,
                            max_lat,
                            min_lon,
                            max_lon,
                            center_lat: lat,
                            center_lon: lon,
                        }
                    } else {
                        // Fallback: create a ~10km box around the center
                        Self::bbox_around(lat, lon, 0.1)
                    }
                } else {
                    Self::bbox_around(lat, lon, 0.1)
                };

                Some(bbox)
            });

        // Cache result (including None)
        inner.forward_cache.put(key, result.clone());
        result
    }

    /// Reverse geocode: GPS coordinates → place info.
    pub fn reverse_geocode(&self, lat: f64, lon: f64) -> Option<PlaceInfo> {
        // Round to 3 decimal places for cache hits (~100m precision)
        let cache_key = format!("{:.3},{:.3}", lat, lon);

        let mut inner = self.inner.lock().unwrap();

        // Check cache
        if let Some(cached) = inner.reverse_cache.get(&cache_key) {
            return Some(cached.clone());
        }

        // Rate limit
        Self::rate_limit(&mut inner);

        let url = format!(
            "https://nominatim.openstreetmap.org/reverse?lat={}&lon={}&format=json&zoom=10",
            lat, lon
        );

        let result = inner
            .client()
            .get(&url)
            .send()
            .ok()
            .and_then(|resp| resp.json::<serde_json::Value>().ok())
            .and_then(|data| {
                let addr = &data["address"];
                let city = addr["city"]
                    .as_str()
                    .or_else(|| addr["town"].as_str())
                    .or_else(|| addr["village"].as_str())
                    .map(|s| s.to_string());
                let state = addr["state"].as_str().map(|s| s.to_string());
                let country = addr["country"].as_str().map(|s| s.to_string());

                let display_name = data["display_name"]
                    .as_str()
                    .unwrap_or("")
                    .to_string();

                // Build a concise place name
                let place_name = match (&city, &state, &country) {
                    (Some(c), Some(s), _) => format!("{}, {}", c, s),
                    (Some(c), None, Some(co)) => format!("{}, {}", c, co),
                    (None, Some(s), Some(co)) => format!("{}, {}", s, co),
                    (None, None, Some(co)) => co.clone(),
                    _ => display_name,
                };

                Some(PlaceInfo {
                    city,
                    state,
                    country,
                    place_name,
                })
            });

        if let Some(ref info) = result {
            inner.reverse_cache.put(cache_key, info.clone());
        }

        result
    }

    fn rate_limit(inner: &mut GeocodingInner) {
        if let Some(last) = inner.last_request {
            let elapsed = last.elapsed();
            if elapsed < Duration::from_secs(1) {
                std::thread::sleep(Duration::from_secs(1) - elapsed);
            }
        }
        inner.last_request = Some(Instant::now());
    }

    fn bbox_around(lat: f64, lon: f64, delta: f64) -> BoundingBox {
        BoundingBox {
            min_lat: lat - delta,
            max_lat: lat + delta,
            min_lon: lon - delta,
            max_lon: lon + delta,
            center_lat: lat,
            center_lon: lon,
        }
    }
}

/// Simple URL encoding for query parameters.
fn urlencoding(s: &str) -> String {
    let mut result = String::new();
    for b in s.bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                result.push(b as char);
            }
            b' ' => result.push('+'),
            _ => {
                result.push_str(&format!("%{:02X}", b));
            }
        }
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_urlencoding() {
        assert_eq!(urlencoding("hello world"), "hello+world");
        assert_eq!(urlencoding("New York"), "New+York");
    }

    #[test]
    fn test_bbox_around() {
        let bb = GeocodingService::bbox_around(37.0, -122.0, 0.1);
        assert!((bb.min_lat - 36.9).abs() < 0.001);
        assert!((bb.max_lat - 37.1).abs() < 0.001);
    }
}
