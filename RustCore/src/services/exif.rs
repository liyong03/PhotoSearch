#[derive(Debug, Default)]
pub struct ExifData {
    pub timestamp: Option<i64>,
    pub latitude: Option<f64>,
    pub longitude: Option<f64>,
    pub camera_make: Option<String>,
    pub camera_model: Option<String>,
}

/// Extract EXIF metadata from an image file.
/// Returns default values if EXIF data cannot be read.
pub fn extract_exif(path: &str) -> Option<ExifData> {
    let file = std::fs::File::open(path).ok()?;
    let mut buf_reader = std::io::BufReader::new(&file);

    let exif_reader = exif::Reader::new();
    let exif = exif_reader.read_from_container(&mut buf_reader).ok()?;

    let mut data = ExifData::default();

    // Camera info
    if let Some(field) = exif.get_field(exif::Tag::Make, exif::In::PRIMARY) {
        data.camera_make = Some(field.display_value().to_string().trim_matches('"').to_string());
    }
    if let Some(field) = exif.get_field(exif::Tag::Model, exif::In::PRIMARY) {
        data.camera_model = Some(field.display_value().to_string().trim_matches('"').to_string());
    }

    // Timestamp
    if let Some(field) = exif.get_field(exif::Tag::DateTimeOriginal, exif::In::PRIMARY) {
        let dt_str = field.display_value().to_string().trim_matches('"').to_string();
        data.timestamp = parse_exif_datetime(&dt_str);
    }

    // GPS coordinates
    data.latitude = extract_gps_coord(&exif, exif::Tag::GPSLatitude, exif::Tag::GPSLatitudeRef);
    data.longitude = extract_gps_coord(&exif, exif::Tag::GPSLongitude, exif::Tag::GPSLongitudeRef);

    Some(data)
}

fn parse_exif_datetime(dt_str: &str) -> Option<i64> {
    // EXIF format: "2024:01:15 14:30:00"
    let formats = ["%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%d"];
    for fmt in &formats {
        if let Ok(dt) = chrono::NaiveDateTime::parse_from_str(dt_str, fmt) {
            return Some(dt.and_utc().timestamp());
        }
    }
    // Try date-only formats
    for fmt in &["%Y:%m:%d", "%Y-%m-%d"] {
        if let Ok(d) = chrono::NaiveDate::parse_from_str(dt_str, fmt) {
            return Some(d.and_hms_opt(0, 0, 0)?.and_utc().timestamp());
        }
    }
    None
}

fn extract_gps_coord(exif: &exif::Exif, coord_tag: exif::Tag, ref_tag: exif::Tag) -> Option<f64> {
    let coord_field = exif.get_field(coord_tag, exif::In::PRIMARY)?;
    let ref_field = exif.get_field(ref_tag, exif::In::PRIMARY)?;

    let ref_str = ref_field.display_value().to_string().trim_matches('"').to_string();

    match &coord_field.value {
        exif::Value::Rational(vals) if vals.len() >= 3 => {
            let degrees = vals[0].to_f64();
            let minutes = vals[1].to_f64();
            let seconds = vals[2].to_f64();
            let mut coord = degrees + minutes / 60.0 + seconds / 3600.0;

            if ref_str == "S" || ref_str == "W" {
                coord = -coord;
            }

            Some(coord)
        }
        _ => None,
    }
}
