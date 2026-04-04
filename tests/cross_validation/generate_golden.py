#!/usr/bin/env python3
"""
Generate golden outputs from the Python backend for cross-validation testing.

Runs the Python CLIP and BLIP models and saves reference embeddings, captions,
and search results that the Rust implementation must match.

Usage:
    python generate_golden.py --images fixtures/test_images/ --output fixtures/golden_outputs/
"""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

# Add the Backend directory to the path
backend_dir = Path(__file__).resolve().parent.parent.parent / "Backend"
sys.path.insert(0, str(backend_dir))

from photosearch.core.clip_processor import CLIPProcessor
from photosearch.core.caption_generator import CaptionGenerator
from photosearch.core.synonym_service import SynonymService
from photosearch.core.query_parser import QueryParser


def generate_clip_embeddings(clip: CLIPProcessor, image_dir: Path, output_dir: Path):
    """Generate CLIP image and text embeddings."""
    clip_dir = output_dir / "clip"
    clip_dir.mkdir(parents=True, exist_ok=True)

    # Image embeddings
    image_files = sorted(
        f for f in image_dir.iterdir()
        if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".heic", ".tiff", ".webp"}
    )
    print(f"Generating CLIP embeddings for {len(image_files)} images...")

    image_embeddings = {}
    for img_path in image_files:
        try:
            embedding = clip.encode_image(str(img_path))
            np.save(clip_dir / f"{img_path.stem}_image.npy", embedding)
            image_embeddings[img_path.name] = embedding.tolist()
            print(f"  {img_path.name}: OK (dim={len(embedding)})")
        except Exception as e:
            print(f"  {img_path.name}: FAILED ({e})")

    # Text embeddings for standard queries
    test_queries = [
        "a photo of a cat",
        "a photo of a dog",
        "sunset on the beach",
        "mountain landscape",
        "city skyline at night",
        "person riding a bicycle",
        "red sports car",
        "flowers in a garden",
        "snow covered trees",
        "underwater coral reef",
        "birthday cake with candles",
        "airplane in the sky",
        "coffee cup on a table",
        "autumn leaves",
        "group of people smiling",
        "old brick building",
        "boat on a lake",
        "children playing in a park",
        "pizza on a plate",
        "starry night sky",
    ]

    print(f"\nGenerating CLIP text embeddings for {len(test_queries)} queries...")
    text_embeddings = {}
    for query in test_queries:
        embedding = clip.encode_text(query)
        np.save(clip_dir / f"text_{query.replace(' ', '_')[:50]}.npy", embedding)
        text_embeddings[query] = embedding.tolist()
        print(f"  '{query}': OK (dim={len(embedding)})")

    # Cross-modal similarity scores
    print("\nComputing cross-modal similarity scores...")
    scores = {}
    for query in test_queries[:5]:  # First 5 queries
        query_emb = np.array(text_embeddings[query])
        for img_name, img_emb in image_embeddings.items():
            img_emb = np.array(img_emb)
            score = float(np.dot(query_emb, img_emb))
            scores[f"{query}||{img_name}"] = score

    with open(clip_dir / "cross_modal_scores.json", "w") as f:
        json.dump(scores, f, indent=2)

    # Save query list
    with open(clip_dir / "test_queries.json", "w") as f:
        json.dump(test_queries, f, indent=2)

    print(f"Saved to {clip_dir}/")


def generate_blip_captions(caption_gen: CaptionGenerator, image_dir: Path, output_dir: Path):
    """Generate BLIP captions and tags."""
    blip_dir = output_dir / "blip"
    blip_dir.mkdir(parents=True, exist_ok=True)

    image_files = sorted(
        f for f in image_dir.iterdir()
        if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".heic", ".tiff", ".webp"}
    )
    print(f"\nGenerating BLIP captions for {len(image_files)} images...")

    captions = {}
    for img_path in image_files:
        try:
            caption, tags = caption_gen.generate(str(img_path))
            captions[img_path.name] = {
                "caption": caption,
                "tags": tags,
            }
            print(f"  {img_path.name}: '{caption}' tags={tags}")
        except Exception as e:
            print(f"  {img_path.name}: FAILED ({e})")

    with open(blip_dir / "captions.json", "w") as f:
        json.dump(captions, f, indent=2)

    print(f"Saved to {blip_dir}/")


def generate_query_parser_outputs(output_dir: Path):
    """Generate query parser outputs."""
    parser_dir = output_dir / "query_parser"
    parser_dir.mkdir(parents=True, exist_ok=True)

    parser = QueryParser()

    test_cases = [
        "sunset from Hawaii",
        "dogs in Central Park",
        "birthday party",
        "taken in Paris at night",
        "beautiful mountain near Denver",
        "flowers at the park",
        "wedding shot in Italy",
        "cars",
        "people at the beach",
        "food from Japan",
        "",
        "landscape",
        "birds in flight",
        "concert at Madison Square Garden",
        "snow in Colorado",
    ]

    results = {}
    print(f"\nGenerating query parser outputs for {len(test_cases)} queries...")
    for query in test_cases:
        parsed = parser.parse(query)
        results[query] = {
            "semantic_query": parsed.semantic_query,
            "location": parsed.location,
        }
        print(f"  '{query}' -> semantic='{parsed.semantic_query}', location={parsed.location}")

    with open(parser_dir / "parsed_queries.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"Saved to {parser_dir}/")


def generate_synonym_outputs(output_dir: Path):
    """Generate synonym service outputs."""
    syn_dir = output_dir / "synonyms"
    syn_dir.mkdir(parents=True, exist_ok=True)

    service = SynonymService()

    test_words = [
        "dog", "cat", "car", "tree", "flower", "ocean", "mountain",
        "sunset", "beach", "food", "person", "child", "building",
        "sky", "road", "bird", "snow", "rain", "garden", "river",
        "happy", "night", "spring", "summer", "red", "blue",
        "wedding", "birthday", "concert", "sport", "travel", "camping",
        "xyzunknown",  # Unknown word
    ]

    results = {}
    print(f"\nGenerating synonym outputs for {len(test_words)} words...")
    for word in test_words:
        synonyms = service.get_synonyms(word)
        results[word] = sorted(list(synonyms))
        print(f"  '{word}' -> {len(synonyms)} synonyms")

    with open(syn_dir / "synonyms.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"Saved to {syn_dir}/")


def main():
    parser = argparse.ArgumentParser(description="Generate golden outputs for cross-validation")
    parser.add_argument("--images", required=True, help="Path to test images directory")
    parser.add_argument("--output", required=True, help="Path to output directory")
    parser.add_argument("--skip-models", action="store_true", help="Skip CLIP/BLIP (only generate service outputs)")
    args = parser.parse_args()

    image_dir = Path(args.images)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_models:
        print("=== Loading CLIP model ===")
        clip = CLIPProcessor()

        print("\n=== Loading BLIP model ===")
        caption_gen = CaptionGenerator()

        print("\n=== Generating CLIP embeddings ===")
        generate_clip_embeddings(clip, image_dir, output_dir)

        print("\n=== Generating BLIP captions ===")
        generate_blip_captions(caption_gen, image_dir, output_dir)

    print("\n=== Generating query parser outputs ===")
    generate_query_parser_outputs(output_dir)

    print("\n=== Generating synonym outputs ===")
    generate_synonym_outputs(output_dir)

    print("\n=== Done! ===")
    print(f"Golden outputs saved to: {output_dir}")


if __name__ == "__main__":
    main()
