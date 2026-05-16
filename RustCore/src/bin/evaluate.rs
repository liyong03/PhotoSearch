//! Search-quality evaluation harness.
//!
//! Indexes the 1000-image COCO sample (tests/data/coco_sample/) once into a
//! persistent index, then runs a query battery and measures precision against
//! COCO's object annotations as ground truth (tests/data/coco_sample_labels.json).
//!
//! Compares two retrieval modes:
//!   - hybrid: 0.6*image + 0.4*caption CLIP score      (keyword_filter = true)
//!   - pure:   image-only CLIP score                   (keyword_filter = false)
//!
//! Run from the RustCore/ directory:
//!   cargo run --release --bin evaluate
//!
//! Indexing 1000 images takes ~15-30 min on first run; subsequent runs reuse
//! the persisted index and only re-run the (fast) query battery.

use std::collections::HashMap;
use std::path::Path;

use serde::Deserialize;

#[derive(Deserialize)]
struct Labels {
    categories: Vec<String>,
    supercategories: Vec<String>,
}

type LabelMap = HashMap<String, Labels>;

fn data_path(rel: &str) -> String {
    // CARGO_MANIFEST_DIR is RustCore/; test data lives at ../tests/data/.
    format!("{}/../tests/data/{}", env!("CARGO_MANIFEST_DIR"), rel)
}

fn filename(path: &str) -> String {
    Path::new(path)
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or(path)
        .to_string()
}

fn search(
    engine: &rust_core::PhotoSearchEngine,
    query: &str,
    top_k: u32,
    hybrid: bool,
) -> Vec<rust_core::SearchResult> {
    engine
        .search(rust_core::SearchRequest {
            query: query.to_string(),
            top_k,
            time_start: None,
            time_end: None,
            location: None,
            folder_path: None,
            min_score: None,
            keyword_filter: Some(hybrid),
        })
        .unwrap_or_default()
}

/// A photo is relevant to a query term if the term appears among its COCO
/// category names or supercategory names.
fn is_relevant(labels: &LabelMap, file: &str, query: &str) -> bool {
    match labels.get(file) {
        Some(l) => {
            l.categories.iter().any(|c| c == query)
                || l.supercategories.iter().any(|s| s == query)
        }
        None => false,
    }
}

fn count_relevant(labels: &LabelMap, query: &str) -> usize {
    labels
        .keys()
        .filter(|f| is_relevant(labels, f, query))
        .count()
}

struct QueryMetrics {
    p_at_5: f64,
    p_at_10: f64,
    recall_at_10: f64,
}

fn evaluate_query(
    engine: &rust_core::PhotoSearchEngine,
    labels: &LabelMap,
    query: &str,
    hybrid: bool,
) -> QueryMetrics {
    let results = search(engine, query, 10, hybrid);
    let files: Vec<String> = results.iter().map(|r| filename(&r.path)).collect();

    let hits_5 = files
        .iter()
        .take(5)
        .filter(|f| is_relevant(labels, f, query))
        .count();
    let hits_10 = files
        .iter()
        .take(10)
        .filter(|f| is_relevant(labels, f, query))
        .count();
    let total_relevant = count_relevant(labels, query).max(1);

    QueryMetrics {
        p_at_5: hits_5 as f64 / 5.0,
        p_at_10: hits_10 as f64 / 10.0,
        recall_at_10: hits_10 as f64 / total_relevant as f64,
    }
}

fn main() {
    env_logger::init();

    let index_dir = data_path("eval_index");
    let images_dir = data_path("coco_sample");
    let labels_file = data_path("coco_sample_labels.json");

    // --- Load ground-truth labels --------------------------------------
    let labels: LabelMap = {
        let raw = std::fs::read_to_string(&labels_file)
            .unwrap_or_else(|e| panic!("Cannot read {labels_file}: {e}"));
        serde_json::from_str(&raw).expect("Cannot parse labels JSON")
    };
    println!("Loaded ground truth for {} photos", labels.len());

    // --- Engine (persistent index) -------------------------------------
    std::fs::create_dir_all(&index_dir).unwrap();
    println!("Initializing engine (loads CLIP + BLIP, may download models)...");
    let engine = rust_core::PhotoSearchEngine::new(index_dir.clone())
        .expect("Failed to create engine");

    // --- Index (skip if already done) ----------------------------------
    let already = engine.indexed_count();
    if already >= 1000 {
        println!("Index already has {already} photos — skipping indexing.");
    } else {
        println!("Indexing photos from {images_dir} (this is the slow part)...");
        let mut images: Vec<String> = std::fs::read_dir(&images_dir)
            .expect("Cannot read coco_sample dir")
            .filter_map(|e| e.ok())
            .map(|e| e.path().to_string_lossy().to_string())
            .filter(|p| p.ends_with(".jpg") || p.ends_with(".jpeg"))
            .collect();
        images.sort();

        let total = images.len();
        let start = std::time::Instant::now();
        let mut ok = 0u32;
        let mut failed = 0u32;
        for (i, img) in images.iter().enumerate() {
            match engine.index_photo(img.clone()) {
                Ok(r) if r.success => ok += 1,
                Ok(r) => {
                    failed += 1;
                    eprintln!("  skip {}: {}", filename(img),
                        r.error.as_deref().unwrap_or("unknown"));
                }
                Err(e) => {
                    failed += 1;
                    eprintln!("  err  {}: {e:?}", filename(img));
                }
            }
            if (i + 1) % 50 == 0 {
                let elapsed = start.elapsed().as_secs_f64();
                let rate = (i + 1) as f64 / elapsed;
                let eta = (total - i - 1) as f64 / rate;
                println!(
                    "  {}/{}  ({:.1}/s, ETA {:.0}m {:.0}s)",
                    i + 1, total, rate, eta / 60.0, eta % 60.0
                );
            }
        }
        println!(
            "Indexed {ok} photos ({failed} failed) in {:.1} min",
            start.elapsed().as_secs_f64() / 60.0
        );
    }

    // --- Query battery -------------------------------------------------
    // Terms chosen to be exact COCO category / supercategory names so the
    // ground-truth match is unambiguous. "abstract" = supercategory-level.
    let abstract_queries = ["food", "animal", "vehicle", "sports", "furniture", "kitchen"];
    let concrete_queries = [
        "dog", "cat", "car", "pizza", "bicycle", "horse", "airplane",
        "clock", "umbrella", "bird", "boat", "elephant",
    ];

    println!("\n{}", "=".repeat(72));
    println!("EVALUATION — precision@K vs COCO object annotations");
    println!("{}", "=".repeat(72));

    let run_battery = |label: &str, queries: &[&str]| {
        println!("\n--- {label} ---");
        println!(
            "{:<12} {:>8} | {:>8} {:>8} {:>8} | {:>8} {:>8} {:>8}",
            "query", "#rel", "H:P@5", "H:P@10", "H:R@10", "P:P@5", "P:P@10", "P:R@10"
        );
        let mut sum = [0.0f64; 6];
        for &q in queries {
            let h = evaluate_query(&engine, &labels, q, true);
            let p = evaluate_query(&engine, &labels, q, false);
            let nrel = count_relevant(&labels, q);
            println!(
                "{:<12} {:>8} | {:>8.2} {:>8.2} {:>8.2} | {:>8.2} {:>8.2} {:>8.2}",
                q, nrel,
                h.p_at_5, h.p_at_10, h.recall_at_10,
                p.p_at_5, p.p_at_10, p.recall_at_10
            );
            sum[0] += h.p_at_5;  sum[1] += h.p_at_10; sum[2] += h.recall_at_10;
            sum[3] += p.p_at_5;  sum[4] += p.p_at_10; sum[5] += p.recall_at_10;
        }
        let n = queries.len() as f64;
        println!(
            "{:<12} {:>8} | {:>8.2} {:>8.2} {:>8.2} | {:>8.2} {:>8.2} {:>8.2}",
            "AVERAGE", "",
            sum[0] / n, sum[1] / n, sum[2] / n,
            sum[3] / n, sum[4] / n, sum[5] / n
        );
        (sum, n)
    };

    let (abs_sum, abs_n) = run_battery("Abstract queries (supercategory)", &abstract_queries);
    let (con_sum, con_n) = run_battery("Concrete queries (category)", &concrete_queries);

    // --- Overall summary ----------------------------------------------
    let tot_n = abs_n + con_n;
    let h_p10 = (abs_sum[1] + con_sum[1]) / tot_n;
    let p_p10 = (abs_sum[4] + con_sum[4]) / tot_n;
    println!("\n{}", "=".repeat(72));
    println!("SUMMARY  (H = hybrid, P = pure image-CLIP)");
    println!("  Overall P@10   hybrid={h_p10:.3}   pure={p_p10:.3}");
    if h_p10 > p_p10 {
        println!("  → hybrid improves precision@10 by {:.1}%",
            (h_p10 - p_p10) / p_p10.max(0.001) * 100.0);
    } else {
        println!("  → hybrid does NOT improve precision@10 ({:.1}%)",
            (h_p10 - p_p10) / p_p10.max(0.001) * 100.0);
    }
    println!("{}", "=".repeat(72));
}
