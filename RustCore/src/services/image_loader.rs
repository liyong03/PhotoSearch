use anyhow::{bail, Context, Result};
use image::DynamicImage;
use std::path::Path;
use std::sync::atomic::{AtomicU64, Ordering};

/// Decode an image file into a `DynamicImage`.
///
/// The `image` crate cannot decode HEIC/HEIF — Apple's default iOS photo
/// format, which is HEVC-encoded inside a HEIF container. For those files
/// this transcodes to a temporary PNG via macOS's `sips` tool (ships with
/// every macOS install, uses the system HEVC decoder) and decodes that.
pub fn load_image(path: &str) -> Result<DynamicImage> {
    if is_heic(path) {
        load_heic(path)
    } else {
        image::ImageReader::open(Path::new(path))
            .context("Failed to open image")?
            .decode()
            .context("Failed to decode image")
    }
}

fn is_heic(path: &str) -> bool {
    matches!(
        Path::new(path)
            .extension()
            .and_then(|e| e.to_str())
            .map(|e| e.to_lowercase())
            .as_deref(),
        Some("heic") | Some("heif")
    )
}

fn load_heic(path: &str) -> Result<DynamicImage> {
    // Unique temp path: process id + a monotonic counter, so sequential or
    // concurrent HEIC decodes never collide on the same file.
    static COUNTER: AtomicU64 = AtomicU64::new(0);
    let n = COUNTER.fetch_add(1, Ordering::Relaxed);
    let tmp = std::env::temp_dir().join(format!(
        "photosearch_heic_{}_{}.png",
        std::process::id(),
        n
    ));

    let output = std::process::Command::new("sips")
        .args(["-s", "format", "png", path, "--out"])
        .arg(&tmp)
        .output()
        .context("Failed to run `sips` to decode HEIC (macOS only)")?;

    if !output.status.success() {
        let _ = std::fs::remove_file(&tmp);
        bail!(
            "sips could not decode HEIC file: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        );
    }

    // Decode the transcoded PNG, then always clean up the temp file.
    let decoded = image::ImageReader::open(&tmp)
        .context("Failed to open sips-transcoded PNG")
        .and_then(|r| r.decode().context("Failed to decode sips-transcoded PNG"));
    let _ = std::fs::remove_file(&tmp);

    decoded
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_is_heic() {
        assert!(is_heic("/photos/IMG_2748.HEIC"));
        assert!(is_heic("/photos/img.heic"));
        assert!(is_heic("/photos/img.heif"));
        assert!(!is_heic("/photos/img.jpg"));
        assert!(!is_heic("/photos/img.png"));
        assert!(!is_heic("/photos/noext"));
    }

    #[test]
    fn test_load_regular_image() {
        let tmp = std::env::temp_dir()
            .join(format!("photosearch_loader_test_{}.png", std::process::id()));
        let img = image::RgbImage::from_fn(32, 24, |x, _| image::Rgb([x as u8, 0, 0]));
        img.save(&tmp).unwrap();

        let loaded = load_image(tmp.to_str().unwrap()).unwrap();
        assert_eq!(loaded.width(), 32);
        assert_eq!(loaded.height(), 24);

        let _ = std::fs::remove_file(&tmp);
    }
}
