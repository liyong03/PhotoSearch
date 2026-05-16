# Test Image Data

## `coco_sample/`

1,000 photos sampled (seed=42) from the **MS-COCO val2017** dataset.

- Source: http://images.cocodataset.org/zips/val2017.zip
- License: Images retain their original Flickr licenses (CC variants).
- Size: ~155 MB, JPEGs of varied dimensions.
- Content: highly diverse — people, food, animals, vehicles, indoor and outdoor scenes, sports, household objects.

## `coco_sample_captions.json`

Ground-truth captions, keyed by image filename. Each photo has 5 human-written captions
(from COCO's `captions_val2017.json`). Useful for:

- **Precision/recall evaluation**: build a query from a caption, check whether the
  source photo appears in top-K results.
- **Hard-negative analysis**: pick a query word ("food"), inspect which photos
  return without that word in any caption.

```json
{
  "000000179765.jpg": [
    "A black Honda motorcycle parked in front of a garage.",
    "A Honda motorcycle parked in a grass driveway",
    "...",
  ]
}
```

## Reproducing the sample

```python
import json, random, os
random.seed(42)
images = sorted(os.listdir("val2017"))
sample = random.sample(images, 1000)
```
