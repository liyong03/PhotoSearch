# Test Fixtures

This directory contains test images for EXIF extraction tests.

## Auto-generated Fixtures

Run the following to generate test images with EXIF data:

```bash
cd Backend
source venv/bin/activate
python tests/fixtures/generate_fixtures.py
```

## Manual Testing with Real Photos

For more thorough testing, add real photos to this directory:

- `real_iphone.jpg` - Photo from iPhone with GPS
- `real_android.jpg` - Photo from Android device
- `real_dslr.jpg` - Photo from DSLR camera
- `real_heic.heic` - HEIC format photo

These will be automatically picked up by the integration tests.
