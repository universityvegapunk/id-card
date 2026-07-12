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
import json
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from rembg import remove
import qrcode

# ============ CONFIG ============
REPO_OWNER = "universityvegapunk"   # your GitHub username
REPO_NAME  = "id-card"              # your repo name
OUTLINE_PX = 14                     # thickness of the white outline
PADDING_PX = 24                     # transparent breathing room around the cutout
INSTITUTION = "SAHE"
DEPT_LINE_1 = "DEPARTMENT OF"
DEPT_LINE_2 = "ELECTRONICS & INSTRUMENTATION"
# =================================

SRC_DIR   = Path("profiles/images")
DATA_DIR  = Path("profiles/data")
OUT_DIR   = Path("profiles/images/processed")
QR_DIR    = Path("profiles/qr")
CARD_DIR  = Path("profiles/cards")
for d in (OUT_DIR, QR_DIR, CARD_DIR):
    d.mkdir(parents=True, exist_ok=True)

FONT_PATH = Path("ArchivoBlack-Regular.ttf")
FONT_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/archivoblack/ArchivoBlack-Regular.ttf"


def ensure_font():
    if not FONT_PATH.exists():
        print("Downloading free Archivo Black font (Google Fonts, open license)...")
        urllib.request.urlretrieve(FONT_URL, FONT_PATH)


def process_one(jpg_path: Path):
    slug = jpg_path.stem
    out_path = OUT_DIR / f"{slug}.png"
    qr_path = QR_DIR / f"{slug}.png"
    card_front_path = CARD_DIR / f"{slug}-front.png"
    card_back_path = CARD_DIR / f"{slug}-back.png"

    if out_path.exists() and qr_path.exists() and card_front_path.exists() and card_back_path.exists():
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
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    qr_img.save(qr_path)

    # 6. Load this person's text fields (name, role, dept, phone...) pushed by AutoPublish.gs
    data_path = DATA_DIR / f"{slug}.json"
    data = {}
    if data_path.exists():
        with open(data_path) as f:
            data = json.load(f)

    generate_card_front(final, data, card_front_path)
    generate_card_back(qr_img, data, card_back_path)

    print(f"  -> {out_path}")
    print(f"  -> {qr_path}")
    print(f"  -> {card_front_path}")
    print(f"  -> {card_back_path}")


def generate_card_front(cutout_img: Image.Image, data: dict, out_path: Path):
    ensure_font()
    W, H = 1013, 1600
    card = Image.new("RGBA", (W, H), (10, 10, 10, 255))
    draw = ImageDraw.Draw(card)

    # 1. Giant stretched initials, starting below the top clearance gap
    #    (that gap is left clean for the physical lanyard slot punch)
    initials = "EIE"
    font_big = ImageFont.truetype(str(FONT_PATH), 620)
    bbox = draw.textbbox((0, 0), initials, font=font_big)
    tw = bbox[2] - bbox[0]
    top_gap = int(H * 0.16)
    draw.text(((W - tw) / 2, top_gap), initials, font=font_big, fill=(255, 255, 255, 255))

    # 2. Micro-logos near the very top edge
    font_micro = ImageFont.truetype(str(FONT_PATH), 26)
    draw.text((36, 40), "EIE", font=font_micro, fill=(255, 255, 255, 230))
    tag = INSTITUTION
    bbox2 = draw.textbbox((0, 0), tag, font=font_micro)
    draw.text((W - 36 - (bbox2[2] - bbox2[0]), 40), tag, font=font_micro, fill=(255, 255, 255, 230))

    # 3. Photo cutout, overlapping the giant letters
    target_h = int(H * 0.56)
    ratio = target_h / cutout_img.height
    resized = cutout_img.resize((int(cutout_img.width * ratio), target_h))
    px = (W - resized.width) // 2
    py = H - target_h - 210
    card.alpha_composite(resized, (px, py))

    # 4. Black gradient fog rising from the footer — unifies photo + letters
    #    into a dark base so the name/role text stays readable
    gradient = Image.new("L", (1, H), 0)
    for y in range(H):
        t = (y - H * 0.5) / (H * 0.42)
        t = max(0.0, min(1.0, t))
        gradient.putpixel((0, y), int(255 * (t ** 1.6)))
    gradient = gradient.resize((W, H))
    black_layer = Image.new("RGBA", (W, H), (5, 5, 8, 255))
    black_layer.putalpha(gradient)
    card.alpha_composite(black_layer)

    # 5. Name — medium, bold, title case
    name = (data.get("name") or "Your Name").strip().title()
    font_name = ImageFont.truetype(str(FONT_PATH), 62)
    bbox = draw.textbbox((0, 0), name, font=font_name)
    tw = bbox[2] - bbox[0]
    name_y = H - 250
    draw.text(((W - tw) / 2, name_y), name, font=font_name, fill=(255, 255, 255, 255))

    # 6. Role capsule — thin blue-bordered box directly under the name
    role = (data.get("role") or "STUDENT").upper()
    font_role = ImageFont.truetype(str(FONT_PATH), 22)
    bbox = draw.textbbox((0, 0), role, font=font_role)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad_x, pad_y = 18, 10
    cap_y = name_y + 78
    cap_box = [(W - tw) / 2 - pad_x, cap_y, (W + tw) / 2 + pad_x, cap_y + th + pad_y * 2]
    draw.rounded_rectangle(cap_box, radius=4, outline=(90, 120, 255, 255), width=2)
    draw.text(((W - tw) / 2, cap_y + pad_y - 2), role, font=font_role, fill=(150, 175, 255, 255))

    # 7. Department footer — italic-style via a slight shear transform
    dept = data.get("dept") or ""
    if dept:
        font_dept = ImageFont.truetype(str(FONT_PATH), 30)
        dept_txt = Image.new("RGBA", (300, 60), (0, 0, 0, 0))
        d2 = ImageDraw.Draw(dept_txt)
        d2.text((10, 5), dept, font=font_dept, fill=(220, 220, 220, 255))
        shear = 0.25
        dept_txt = dept_txt.transform((300, 60), Image.AFFINE, (1, shear, -shear * 30, 0, 1, 0), resample=Image.BICUBIC)
        card.alpha_composite(dept_txt, (int(W / 2 - 70), H - 90))

    # 8. Small double-arrow accent, bottom right corner
    ax, ay = W - 70, H - 56
    draw.polygon([(ax, ay - 10), (ax + 12, ay), (ax, ay + 10)], fill=(120, 120, 120, 255))
    draw.polygon([(ax + 14, ay - 10), (ax + 26, ay), (ax + 14, ay + 10)], fill=(120, 120, 120, 255))

    card.convert("RGB").save(out_path)


def generate_card_back(qr_img: Image.Image, data: dict, out_path: Path):
    ensure_font()
    W, H = 1013, 1600
    card = Image.new("RGB", (W, H), (10, 10, 10))
    draw = ImageDraw.Draw(card)

    tile = W // 4
    for row in range(2):
        for col in range(4):
            x0, y0 = col * tile, row * tile
            flip = (row + col) % 2 == 0
            bg = (255, 255, 255) if flip else (10, 10, 10)
            fg = (10, 10, 10) if flip else (255, 255, 255)
            draw.rectangle([x0, y0, x0 + tile, y0 + tile], fill=bg)
            if flip:
                draw.pieslice([x0 - tile, y0, x0 + tile, y0 + 2 * tile], 0, 90, fill=fg)
            else:
                draw.pieslice([x0, y0 - tile, x0 + 2 * tile, y0 + tile], 180, 270, fill=fg)

    qr_size = 420
    qr_resized = qr_img.resize((qr_size, qr_size))
    qx = (W - qr_size) // 2
    qy = tile * 2 + 90
    card.paste(qr_resized, (qx, qy))

    font_dept = ImageFont.truetype(str(FONT_PATH), 34)
    font_small = ImageFont.truetype(str(FONT_PATH), 26)

    phone = data.get("phone") or ""
    lines = [
        (DEPT_LINE_1, font_small, (150, 150, 150)),
        (DEPT_LINE_2, font_dept, (255, 255, 255)),
        (phone, font_small, (150, 150, 150)),
    ]
    y = qy + qr_size + 50
    for line, font, color in lines:
        if not line:
            continue
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((W - tw) / 2, y), line, font=font, fill=color)
        y += (bbox[3] - bbox[1]) + 20

    # Reserved space for your college logo — add it here later
    placeholder = "[ LOGO SPACE ]"
    bbox = draw.textbbox((0, 0), placeholder, font=font_small)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) / 2, H - 90), placeholder, font=font_small, fill=(90, 90, 90))

    card.save(out_path)


def main():
    jpgs = sorted(SRC_DIR.glob("*.jpg"))
    if not jpgs:
        print("No photos found in profiles/images/.")
        return
    for jpg in jpgs:
        process_one(jpg)


if __name__ == "__main__":
    main()
