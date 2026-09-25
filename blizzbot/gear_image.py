"""Builds a composite gear-grid image (real item icons + quality-color borders)
for the Character Lookup embed, since Discord embeds can only show one image
each -- there's no way to show 16 inline icons any other way."""

import asyncio
import io

import httpx
from PIL import Image, ImageDraw

GEAR_SLOT_ORDER = [
    "HEAD", "NECK", "SHOULDER", "BACK", "CHEST", "SHIRT", "TABARD", "WRIST",
    "HANDS", "WAIST", "LEGS", "FEET", "FINGER_1", "FINGER_2",
    "TRINKET_1", "TRINKET_2", "MAIN_HAND", "OFF_HAND", "RANGED",
]

QUALITY_COLOR = {
    "POOR": (157, 157, 157),
    "COMMON": (255, 255, 255),
    "UNCOMMON": (30, 255, 0),
    "RARE": (0, 112, 221),
    "EPIC": (163, 53, 238),
    "LEGENDARY": (255, 128, 0),
}
EMPTY_SLOT_COLOR = (45, 45, 48)

CELL = 80
PAD = 6
COLS = 5


async def _fetch_icon_bytes(bnet_client, item: dict | None) -> bytes | None:
    if not item:
        return None
    href = item.get("media", {}).get("key", {}).get("href")
    if not href:
        return None
    icon_url = await bnet_client.resolve_icon_url(href)
    if not icon_url:
        return None
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(icon_url)
        if resp.status_code == 200:
            return resp.content
    return None


async def build_gear_image(bnet_client, equipment: dict) -> io.BytesIO | None:
    by_slot = {i["slot"]["type"]: i for i in equipment.get("equipped_items", [])}
    items = [by_slot.get(slot) for slot in GEAR_SLOT_ORDER]

    icon_bytes_list = await asyncio.gather(*(_fetch_icon_bytes(bnet_client, item) for item in items))

    if not any(icon_bytes_list):
        return None

    rows = (len(items) + COLS - 1) // COLS
    width = COLS * (CELL + PAD) + PAD
    height = rows * (CELL + PAD) + PAD
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    for idx, (item, icon_bytes) in enumerate(zip(items, icon_bytes_list)):
        col, row = idx % COLS, idx // COLS
        x = PAD + col * (CELL + PAD)
        y = PAD + row * (CELL + PAD)
        border = QUALITY_COLOR.get((item or {}).get("quality", {}).get("type"), EMPTY_SLOT_COLOR)
        draw.rectangle([x - 3, y - 3, x + CELL + 3, y + CELL + 3], fill=border)
        if icon_bytes:
            try:
                icon = Image.open(io.BytesIO(icon_bytes)).convert("RGBA").resize((CELL, CELL))
                canvas.paste(icon, (x, y))
            except Exception:
                draw.rectangle([x, y, x + CELL, y + CELL], fill=EMPTY_SLOT_COLOR)
        else:
            draw.rectangle([x, y, x + CELL, y + CELL], fill=EMPTY_SLOT_COLOR)

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    buf.seek(0)
    return buf
