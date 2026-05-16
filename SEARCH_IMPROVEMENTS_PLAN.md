# Search Quality Improvements

Two upgrades to address the precision/recall trade-off in semantic search:
- **Pure CLIP** is noisy in the result tail (unrelated photos appear).
- **Strict synonym keyword gate** over-filters (e.g. "girls in waterpolo" misses "kids in swimming pool").

---

## Improvement 1: Hybrid CLIP scoring (image + caption)

**Status:** ✅ Implemented on branch `feat/hybrid-caption-rerank`.

### Idea
Combine two CLIP signals per candidate photo:
- `image_score` = cosine(query_text_emb, image_emb) — what we have today.
- `caption_score` = cosine(query_text_emb, caption_text_emb) — new.

`final_score = 0.6 · image_score + 0.4 · caption_score`

### Why it works
A photo unrelated to the query that scored high on image-CLIP almost always scores low on caption-CLIP, so the combined score drops it. The synonym dictionary becomes irrelevant — CLIP itself knows "girls" ≈ "kids", "waterpolo" ≈ "swimming pool".

### Implementation
- **Index time** (`lib.rs::index_photo`): also encode the BLIP caption with `clip.encode_text()` and store via `VectorIndex::add_caption`.
- **Search time** (`lib.rs::search`): compute combined score, apply `min_score` floor, re-sort by combined score, take top_k.
- **Storage** (`search/mod.rs`): `VectorIndex` now holds parallel `embeddings` + `caption_embeddings` HashMaps. New v2 file format: `[magic "PSVI"][version u32][image_map][caption_map]`. Atomic write via tmp+rename. Backward compatible — files without the magic header load as v1 (image-only) and the caption map starts empty.
- **Backfill** (`lib.rs::backfill_caption_embeddings`): on engine startup, any photo with a description but no caption embedding gets one. One-time migration of the existing index.
- **API**: `keyword_filter` flag repurposed — `true` (default) = hybrid, `false` = pure image CLIP for A/B comparison. Swift side unchanged.

### Tuning knobs
- `IMAGE_WEIGHT` (currently 0.6) — raise to trust image more, lower to trust caption more.
- `min_score` floor (currently 0.0) — raise to drop weak combined scores entirely.

---

## Improvement 2: Structured channels via Apple Vision

**Status:** Proposed, not implemented. Matches iPhone Photos' precision by adding signals beyond CLIP.

### What gets indexed (Swift-side, free on Neural Engine)
| Channel | API | Stored as |
|---|---|---|
| Scene classification (~1,300 fixed labels) | `VNClassifyImageRequest` | `photos.scene_tags` (CSV) |
| OCR (text in images) | `VNRecognizeTextRequest` | `photos.ocr_text` (FTS-indexed) |
| Face clustering | `VNDetectFaceRectangles` + `VNGenerateImageFeaturePrint` on cropped faces, incremental clustering | `photos.face_cluster_ids` + `face_clusters` table with user-assignable names |

### Schema additions
```sql
ALTER TABLE photos ADD COLUMN scene_tags TEXT;
ALTER TABLE photos ADD COLUMN ocr_text TEXT;
ALTER TABLE photos ADD COLUMN face_cluster_ids TEXT;

CREATE TABLE face_clusters (
  cluster_id INTEGER PRIMARY KEY,
  name TEXT,
  representative_photo_id TEXT
);
```

### Query understanding (rule-based router, no LLM)
For each query:
1. **Tokenize**, lowercase, strip stop words.
2. **Extract person names** matching named face clusters → peel from query, become hard filter.
3. **Extract dates** via chrono → peel, become time filter.
4. **Extract location** ("in X" / "from X") → peel, become geo filter (existing `query_parser`).
5. **Match scene labels** against the classifier's known vocab — keep in residual *and* fire as soft bonus.
6. **Out-of-vocab fuzzy scenes**: for words not in the scene vocab, do CLIP text-text similarity against scene labels; matches > 0.7 add a soft bonus. Example: "waterpolo" → "swimming" (0.71), "pool" (0.68).
7. **Residual** → CLIP query.

### Search-time use of each channel
| Channel | How it's used |
|---|---|
| Person cluster | Hard filter: candidate must contain that face cluster |
| Scene label (in vocab) | Soft bonus: `+0.05` on hybrid score if photo has matching `scene_tags` |
| Scene label (fuzzy CLIP-matched) | Same soft bonus, with the closest-vocab label |
| OCR | Union channel: photos found by FTS over `ocr_text` are eligible even if CLIP missed them |

Final score: `0.6·image + 0.4·caption + 0.05·scene_bonus`, with hard filters intersected, OCR hits unioned in.

### Worked examples
- **"Emma at the beach"**: face filter = Emma's cluster; scene bonus on "beach"; CLIP residual = "at the beach".
- **"girls in waterpolo"**: no person/location hit; fuzzy scene bonus on "swimming"/"pool"; CLIP residual = full query.
- **"starbucks receipts from last year"**: time filter = 2024; OCR hit set = photos with "starbucks"; CLIP residual = "starbucks receipts"; union OCR ∪ CLIP candidates.

### Architecture split
- **Swift**: runs Vision (scenes, OCR, face detection + feature prints), does face clustering, owns the People naming UI. Passes enriched fields into `IndexPhoto` request.
- **Rust**: stores new fields in SQLite, exposes `filter_by_face_clusters` / `filter_by_scenes` / `filter_by_ocr`, extends `parse_query` to extract structured terms, adds scene-bonus to the hybrid score.

### Suggested build order
1. **Scene tags as soft bonus** — half day. Smallest code, immediate win on the waterpolo case, no UI work. Best ROI.
2. **OCR as union channel** — half day. Cheap, very high "wow" factor (finds receipts, signs, menus).
3. **Face clustering + naming UI** — multi-day. Highest user impact ("photos of Emma"), but requires clustering algorithm + People view + naming flow.

### When to reach for an LLM-based query rewriter
Only needed for compositional queries the rule-based router can't handle:
- Negation ("Emma *not* at school")
- Composition ("trips Mom and I took without Dad")
- Implicit references ("the time we visited that vineyard")

iOS 18+ on-device foundation model would do this for free; macOS would need a quantized local LLM. Latency cost ~100–500 ms per query, so reserve for the ~5% hard tail.
