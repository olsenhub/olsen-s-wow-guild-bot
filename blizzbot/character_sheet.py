"""Renders a classic WoW-style character sheet: gear columns flanking a centered
character render, in a dark ornate frame -- like the in-game paperdoll, but with
item names/enchants annotated like a modern armory site."""

import asyncio
import io

import httpx
from PIL import Image, ImageDraw, ImageFont

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
QUALITY_COLOR = {
    "POOR": (157, 157, 157),
    "COMMON": (255, 255, 255),
    "UNCOMMON": (30, 255, 0),
    "RARE": (60, 148, 255),
    "EPIC": (189, 100, 255),
    "LEGENDARY": (255, 145, 20),
}
EMPTY_SLOT_COLOR = (55, 50, 45)

CLASS_COLOR = {
    "Warrior": (199, 156, 110),
    "Paladin": (245, 140, 186),
    "Hunter": (171, 212, 115),
    "Rogue": (255, 245, 105),
    "Priest": (255, 255, 255),
    "Death Knight": (196, 31, 59),
    "Shaman": (45, 130, 240),
    "Mage": (105, 204, 240),
    "Warlock": (148, 130, 201),
    "Monk": (0, 255, 150),
    "Druid": (255, 125, 10),
}

LEFT_SLOTS = ["HEAD", "NECK", "SHOULDER", "BACK", "CHEST", "SHIRT", "TABARD", "WRIST", "HANDS"]
RIGHT_SLOTS = ["WAIST", "LEGS", "FEET", "FINGER_1", "FINGER_2", "TRINKET_1", "TRINKET_2", "MAIN_HAND", "OFF_HAND"]

SLOT_LABEL = {
    "HEAD": "Head", "NECK": "Neck", "SHOULDER": "Shoulder", "BACK": "Back",
    "CHEST": "Chest", "SHIRT": "Shirt", "TABARD": "Tabard", "WRIST": "Wrist",
    "HANDS": "Hands", "WAIST": "Waist", "LEGS": "Legs", "FEET": "Feet",
    "FINGER_1": "Ring", "FINGER_2": "Ring", "TRINKET_1": "Trinket",
    "TRINKET_2": "Trinket", "MAIN_HAND": "Main Hand", "OFF_HAND": "Off Hand",
}

W, H = 900, 680
ROW_H = 54
ICON = 42
COL_W = 300
BODY_TOP = 150

BG_OUTER = (8, 7, 6)
BG_PANEL = (24, 19, 15)
BORDER_GOLD = (198, 170, 110)
BORDER_DARK = (55, 42, 24)
TEXT_GREY = (168, 162, 152)
TEXT_ENCHANT = (40, 200, 60)


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(f"{FONT_DIR}/{name}", size)
    except OSError:
        return ImageFont.load_default()


F_TITLE = lambda: _font("DejaVuSerif-Bold.ttf", 30)
F_SUBTITLE = lambda: _font("DejaVuSans.ttf", 16)
F_STATS = lambda: _font("DejaVuSans.ttf", 14)
F_ITEM = lambda: _font("DejaVuSans-Bold.ttf", 13)
F_SMALL = lambda: _font("DejaVuSans.ttf", 11)


async def _fetch(url: str) -> bytes | None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        return resp.content if resp.status_code == 200 else None


async def _fetch_item_icon(bnet_client, item: dict | None) -> bytes | None:
    if not item:
        return None
    href = item.get("media", {}).get("key", {}).get("href")
    if not href:
        return None
    icon_url = await bnet_client.resolve_icon_url(href)
    return await _fetch(icon_url) if icon_url else None


def _truncate(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    while text and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1]
    return text + "…"


def _draw_frame(draw: ImageDraw.ImageDraw) -> None:
    draw.rectangle([0, 0, W - 1, H - 1], fill=BG_OUTER)
    draw.rectangle([6, 6, W - 7, H - 7], fill=BG_PANEL, outline=BORDER_GOLD, width=3)
    draw.rectangle([12, 12, W - 13, H - 13], outline=BORDER_DARK, width=1)


def _draw_row(canvas: Image.Image, draw: ImageDraw.ImageDraw, x: int, y: int,
              slot: str, item: dict | None, icon_bytes: bytes | None) -> None:
    quality = (item or {}).get("quality", {}).get("type")
    border = QUALITY_COLOR.get(quality, EMPTY_SLOT_COLOR)
    draw.rectangle([x - 2, y - 2, x + ICON + 2, y + ICON + 2], fill=border)
    if icon_bytes:
        try:
            icon = Image.open(io.BytesIO(icon_bytes)).convert("RGBA").resize((ICON, ICON))
            canvas.paste(icon, (x, y))
        except Exception:
            draw.rectangle([x, y, x + ICON, y + ICON], fill=EMPTY_SLOT_COLOR)
    else:
        draw.rectangle([x, y, x + ICON, y + ICON], fill=EMPTY_SLOT_COLOR)

    text_x = x + ICON + 10
    text_w = COL_W - ICON - 20
    if item:
        name_color = QUALITY_COLOR.get(quality, (255, 255, 255))
        draw.text((text_x, y - 2), _truncate(draw, item["name"], F_ITEM(), text_w), font=F_ITEM(), fill=name_color)
        draw.text((text_x, y + 16), SLOT_LABEL.get(slot, slot), font=F_SMALL(), fill=TEXT_GREY)
        enchants = item.get("enchantments") or []
        if enchants:
            enchant_text = enchants[0].get("display_string", "")
            draw.text((text_x, y + 30), _truncate(draw, enchant_text, F_SMALL(), text_w),
                       font=F_SMALL(), fill=TEXT_ENCHANT)
    else:
        draw.text((text_x, y - 2), "(empty)", font=F_ITEM(), fill=TEXT_GREY)
        draw.text((text_x, y + 16), SLOT_LABEL.get(slot, slot), font=F_SMALL(), fill=TEXT_GREY)


async def build_character_sheet(bnet_client, *, name: str, level: int, race: str, char_class: str,
                                 spec: str | None, guild_name: str | None, item_level, achievement_points,
                                 equipment: dict, render_url: str | None) -> io.BytesIO:
    by_slot = {i["slot"]["type"]: i for i in equipment.get("equipped_items", [])}
    all_slots = LEFT_SLOTS + RIGHT_SLOTS
    icon_bytes_list = await asyncio.gather(
        *(_fetch_item_icon(bnet_client, by_slot.get(slot)) for slot in all_slots)
    )
    icons_by_slot = dict(zip(all_slots, icon_bytes_list))
    render_bytes = await _fetch(render_url) if render_url else None

    canvas = Image.new("RGB", (W, H), BG_OUTER)
    draw = ImageDraw.Draw(canvas)
    _draw_frame(draw)

    class_color = CLASS_COLOR.get(char_class, (235, 230, 220))
    title = name
    tf = F_TITLE()
    tw = draw.textlength(title, font=tf)
    draw.text(((W - tw) / 2, 20), title, font=tf, fill=class_color)

    subtitle = f"Level {level} {race} {char_class}" + (f" — {spec}" if spec else "")
    sf = F_SUBTITLE()
    sw = draw.textlength(subtitle, font=sf)
    draw.text(((W - sw) / 2, 60), subtitle, font=sf, fill=TEXT_GREY)

    draw.line([(40, 96), (W - 40, 96)], fill=BORDER_GOLD, width=1)

    stats = f"Item Level {item_level or '?'}   •   {achievement_points:,} Achievement Points"
    if guild_name:
        stats += f"   •   {guild_name}"
    stf = F_STATS()
    stw = draw.textlength(stats, font=stf)
    draw.text(((W - stw) / 2, 108), stats, font=stf, fill=(230, 200, 140))

    for i, slot in enumerate(LEFT_SLOTS):
        y = BODY_TOP + i * ROW_H
        _draw_row(canvas, draw, 30, y, slot, by_slot.get(slot), icons_by_slot.get(slot))

    for i, slot in enumerate(RIGHT_SLOTS):
        y = BODY_TOP + i * ROW_H
        _draw_row(canvas, draw, W - COL_W - 10, y, slot, by_slot.get(slot), icons_by_slot.get(slot))

    if render_bytes:
        try:
            portrait = Image.open(io.BytesIO(render_bytes)).convert("RGBA")
            bbox = portrait.getbbox()
            if bbox:
                pad = 12
                bbox = (
                    max(0, bbox[0] - pad), max(0, bbox[1] - pad),
                    min(portrait.width, bbox[2] + pad), min(portrait.height, bbox[3] + pad),
                )
                portrait = portrait.crop(bbox)
            box_w, box_h = 260, 470
            scale = min(box_w / portrait.width, box_h / portrait.height)
            portrait = portrait.resize((int(portrait.width * scale), int(portrait.height * scale)))
            px = (W - portrait.width) // 2
            py = BODY_TOP + (len(LEFT_SLOTS) * ROW_H - portrait.height) // 2
            canvas.paste(portrait, (px, py), portrait)
        except Exception:
            pass

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    buf.seek(0)
    return buf
