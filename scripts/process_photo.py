"""
process_photo.py
-----------------
Runs automatically inside GitHub Actions every time a new raw photo is
pushed to profiles/images/. For each new photo it:
  1. Removes the background (rembg — free, open-source, offline)
  2. Auto-crops tightly to the subject
  3. Adds a white "emboss" outline around the cutout (sticker effect)
  4. Generates that person's QR code, pointing at their live profile page

Nothing here needs to be run by hand — GitHub Actions runs this file
automatically on every push. It's only listed here so you can see
exactly what's happening, and edit the look (outline thickness, etc.)
if you ever want to.
"""

import io
from pathlib import Path

from PIL import Image, ImageFilter
from rembg import remove
import qrcode

# ============ CONFIG ============
REPO_OWNER = "universityvegapunk"   # your GitHub username
REPO_NAME  = "id-card"              # your repo name
OUTLINE_PX = 14                     # thickness of the white outline
PADDING_PX = 24                     # transparent breathing room around the cutout
# =================================

SRC_DIR = Path("profiles/images")
OUT_DIR = Path("profiles/images/processed")
QR_DIR  = Path("profiles/qr")
OUT_DIR.mkdir(parents=True, exist_ok=True)
QR_DIR.mkdir(parents=True, exist_ok=True)


def process_one(jpg_path: Path):
    slug = jpg_path.stem
    out_path = OUT_DIR / f"{slug}.png"
    qr_path = QR_DIR / f"{slug}.png"

    if out_path.exists() and qr_path.exists():
        return  # already processed earlier — skip, keeps this safe to re-run

    print(f"Processing {slug} ...")

    # 1. Remove the background
    with open(jpg_path, "rb") as f:
        cutout_bytes = remove(f.read())
    cutout = Image.open(io.BytesIO(cutout_bytes)).convert("RGBA")

    # 2. Auto-crop to the subject's bounding box
    bbox = cutout.getbbox()
    if bbox:
        cutout = cutout.crop(bbox)

    # 3. Build a padded canvas with room for the outline to grow into
    margin = OUTLINE_PX + PADDING_PX
    canvas = Image.new("RGBA", (cutout.width + margin * 2, cutout.height + margin * 2), (0, 0, 0, 0))
    canvas.alpha_composite(cutout, (margin, margin))

    # 4. White emboss/outline halo, built from the dilated alpha shape
    alpha = canvas.split()[-1]
    dilated = alpha.filter(ImageFilter.MaxFilter(OUTLINE_PX * 2 + 1))
    white_layer = Image.new("RGBA", canvas.size, (255, 255, 255, 255))
    transparent = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    halo = Image.composite(white_layer, transparent, dilated)

    final = Image.alpha_composite(halo, canvas)
    final.save(out_path)

    # 5. This person's QR code -> their live profile page
    url = f"https://{REPO_OWNER}.github.io/{REPO_NAME}/profiles/{slug}/"
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    qr.make_image(fill_color="black", back_color="white").save(qr_path)

    print(f"  -> {out_path}")
    print(f"  -> {qr_path}  (encodes {url})")


def main():
    jpgs = sorted(SRC_DIR.glob("*.jpg"))
    if not jpgs:
        print("No photos found in profiles/images/.")
        return
    for jpg in jpgs:
        process_one(jpg)


if __name__ == "__main__":
    main()
