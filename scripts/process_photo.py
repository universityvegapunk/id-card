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

FONT_ITALIC_PATH = Path("PlayfairDisplay-Italic.ttf")
FONT_ITALIC_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/playfairdisplay/PlayfairDisplay-Italic%5Bwght%5D.ttf"

BG_TEXTURE_PATH = Path("assets/card-bg.jpg")


def ensure_font():
    if not FONT_PATH.exists():
        print("Downloading free Archivo Black font (Google Fonts, open license)...")
        urllib.request.urlretrieve(FONT_URL, FONT_PATH)
    if not FONT_ITALIC_PATH.exists():
        print("Downloading free Playfair Display Italic font (Google Fonts, open license)...")
        urllib.request.urlretrieve(FONT_ITALIC_URL, FONT_ITALIC_PATH)


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

    # Background: your provided texture, scaled to fully cover the card.
    # Falls back to a plain dark navy if the texture asset isn't found.
    if BG_TEXTURE_PATH.exists():
        bg = Image.open(BG_TEXTURE_PATH).convert("RGB")
        ratio = max(W / bg.width, H / bg.height)
        bg = bg.resize((int(bg.width * ratio) + 1, int(bg.height * ratio) + 1))
        bg = bg.crop((0, 0, W, H))
        card = bg.convert("RGBA")
    else:
        card = Image.new("RGBA", (W, H), (8, 8, 16, 255))

    draw = ImageDraw.Draw(card)

    # 1. Header — small "EIE" mark top-left, "SAHE" + subtitle top-right
    font_mark = ImageFont.truetype(str(FONT_PATH), 40)
    draw.text((44, 44), "EIE", font=font_mark, fill=(255, 255, 255, 255))

    font_inst = ImageFont.truetype(str(FONT_PATH), 46)
    font_inst_sub = ImageFont.truetype(str(FONT_ITALIC_PATH), 20)
    inst = INSTITUTION
    bbox = draw.textbbox((0, 0), inst, font=font_inst)
    draw.text((W - 44 - (bbox[2] - bbox[0]), 40), inst, font=font_inst, fill=(255, 255, 255, 255))
    sub = "Deemed to be University"
    bbox2 = draw.textbbox((0, 0), sub, font=font_inst_sub)
    draw.text((W - 44 - (bbox2[2] - bbox2[0]), 92), sub, font=font_inst_sub, fill=(210, 210, 210, 255))

    # 2. Giant light-gray initials, bleeding toward the edges
    font_big = ImageFont.truetype(str(FONT_PATH), 560)
    initials = "EIE"
    bbox = draw.textbbox((0, 0), initials, font=font_big)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) / 2, 170), initials, font=font_big, fill=(210, 210, 212, 235))

    # 3. Photo cutout (with the white sticker outline), large, overlapping the letters
    target_h = int(H * 0.62)
    ratio = target_h / cutout_img.height
    resized = cutout_img.resize((int(cutout_img.width * ratio), target_h))
    px = (W - resized.width) // 2
    py = int(H * 0.30)
    card.alpha_composite(resized, (px, py))

    # 4. Translucent black fog rising from the footer — unifies the texture
    #    and the bottom of the photo into a dark base so the name/role
    #    text stays readable, matching the reference's bottom fade
    fog = Image.new("L", (1, H), 0)
    for y in range(H):
        t = (y - H * 0.58) / (H * 0.35)
        t = max(0.0, min(1.0, t))
        fog.putpixel((0, y), int(255 * (t ** 1.4)))
    fog = fog.resize((W, H))
    fog_layer = Image.new("RGBA", (W, H), (4, 4, 10, 255))
    fog_layer.putalpha(fog)
    card.alpha_composite(fog_layer)

    # 5. Name, bold, right under the photo
    name = (data.get("name") or "Your Name").strip().title()
    font_name = ImageFont.truetype(str(FONT_PATH), 66)
    bbox = draw.textbbox((0, 0), name, font=font_name)
    tw = bbox[2] - bbox[0]
    name_y = py + target_h - 20
    draw.text(((W - tw) / 2, name_y), name, font=font_name, fill=(255, 255, 255, 255))

    # 6. Role/title, italic serif, anchored near the bottom
    role = data.get("role") or "Student"
    font_role = ImageFont.truetype(str(FONT_ITALIC_PATH), 34)
    bbox = draw.textbbox((0, 0), role, font=font_role)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) / 2, H - 80), role, font=font_role, fill=(225, 225, 225, 255))

    card.convert("RGB").save(out_path)


def generate_card_back(qr_img: Image.Image, data: dict, out_path: Path):
    ensure_font()
    W, H = 1013, 1600
    card = Image.new("RGBA", (W, H), (10, 10, 10, 255))
    draw = ImageDraw.Draw(card)

    # 1. Top lanyard clearance gap, then the Bauhaus checkerboard pattern
    top_gap = int(H * 0.10)
    pattern_h = int(H * 0.40)
    tile = W // 4
    rows = (pattern_h // tile) + 1
    for row in range(rows):
        for col in range(4):
            x0, y0 = col * tile, top_gap + row * tile
            if y0 > top_gap + pattern_h:
                continue
            flip = (row + col) % 2 == 0
            bg = (255, 255, 255, 255) if flip else (10, 10, 10, 255)
            fg = (10, 10, 10, 255) if flip else (255, 255, 255, 255)
            draw.rectangle([x0, y0, x0 + tile, y0 + tile], fill=bg)
            if flip:
                draw.pieslice([x0 - tile, y0, x0 + tile, y0 + 2 * tile], 0, 90, fill=fg)
            else:
                draw.pieslice([x0, y0 - tile, x0 + 2 * tile, y0 + tile], 180, 270, fill=fg)

    # 2. QR code with rounded corners + white padding frame for scanner contrast
    qr_size = 380
    qr_resized = qr_img.convert("RGBA").resize((qr_size, qr_size))
    frame_pad = 24
    frame_size = qr_size + frame_pad * 2
    frame = Image.new("RGBA", (frame_size, frame_size), (0, 0, 0, 0))
    fd = ImageDraw.Draw(frame)
    fd.rounded_rectangle([0, 0, frame_size, frame_size], radius=28, fill=(255, 255, 255, 255))
    frame.alpha_composite(qr_resized, (frame_pad, frame_pad))
    mask = Image.new("L", (frame_size, frame_size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, frame_size, frame_size], radius=28, fill=255)
    frame.putalpha(mask)

    qx = (W - frame_size) // 2
    qy = top_gap + pattern_h + 70
    card.alpha_composite(frame, (qx, qy))

    # 3. Department + phone
    font_label = ImageFont.truetype(str(FONT_PATH), 24)
    font_dept = ImageFont.truetype(str(FONT_PATH), 32)
    dept = (data.get("dept") or "").upper()
    phone = data.get("phone") or ""

    y = qy + frame_size + 45
    lines = [
        ("DEPARTMENT OF", font_label, (150, 150, 150, 255)),
        (dept, font_dept, (255, 255, 255, 255)),
        (str(phone), font_label, (170, 170, 170, 255)),
    ]
    for text, font, color in lines:
        if not text:
            continue
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((W - tw) / 2, y), text, font=font, fill=color)
        y += (bbox[3] - bbox[1]) + 18

    # 4. Institutional branding stack — small geometric mark + stacked caps text
    y += 20
    mark_r = 10
    draw.regular_polygon((W / 2, y + mark_r, mark_r), n_sides=4, rotation=45, fill=(255, 255, 255, 255))
    y += mark_r * 2 + 14

    font_inst1 = ImageFont.truetype(str(FONT_PATH), 20)
    font_inst2 = ImageFont.truetype(str(FONT_PATH), 16)
    for text, font, color in [(INSTITUTION, font_inst1, (220, 220, 220, 255)),
                               ("DEEMED TO BE UNIVERSITY", font_inst2, (130, 130, 130, 255))]:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((W - tw) / 2, y), text, font=font, fill=color)
        y += (bbox[3] - bbox[1]) + 10

    card.convert("RGB").save(out_path)


def main():
    jpgs = sorted(SRC_DIR.glob("*.jpg"))
    if not jpgs:
        print("No photos found in profiles/images/.")
        return
    for jpg in jpgs:
        process_one(jpg)


if __name__ == "__main__":
    main()
