"""Renders a WoW-classic-styled character sheet: gear columns flanking a centered
character render, inside a carved stone/metal frame with beveled item slots and a
circular portrait -- like the in-game paperdoll UI, but with item names/enchants
annotated like a modern armory site. All textures/bevels are generated
programmatically (no Blizzard UI art is used)."""

import asyncio
import io
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
ASSETS_DIR = Path(__file__).parent / "assets"

SCALE = 1.7


def s(px: int) -> int:
    return int(px * SCALE)


QUALITY_COLOR = {
    "POOR": (157, 157, 157),
    "COMMON": (255, 255, 255),
    "UNCOMMON": (30, 255, 0),
    "RARE": (60, 148, 255),
    "EPIC": (189, 100, 255),
    "LEGENDARY": (255, 145, 20),
}
EMPTY_SLOT_COLOR = (70, 64, 56)

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

FACTION_ASSET = {"ALLIANCE": "alliance.png", "HORDE": "horde.png"}

LEFT_SLOTS = ["HEAD", "NECK", "SHOULDER", "BACK", "CHEST", "SHIRT", "TABARD", "WRIST", "HANDS"]
RIGHT_SLOTS = ["WAIST", "LEGS", "FEET", "FINGER_1", "FINGER_2", "TRINKET_1", "TRINKET_2", "MAIN_HAND", "OFF_HAND"]

SLOT_LABEL = {
    "HEAD": "Head", "NECK": "Neck", "SHOULDER": "Shoulder", "BACK": "Back",
    "CHEST": "Chest", "SHIRT": "Shirt", "TABARD": "Tabard", "WRIST": "Wrist",
    "HANDS": "Hands", "WAIST": "Waist", "LEGS": "Legs", "FEET": "Feet",
    "FINGER_1": "Ring", "FINGER_2": "Ring", "TRINKET_1": "Trinket",
    "TRINKET_2": "Trinket", "MAIN_HAND": "Main Hand", "OFF_HAND": "Off Hand",
}

W, H = s(940), s(700)
ROW_H = s(58)
ICON = s(44)
COL_W = s(310)
BODY_TOP = s(190) - s(24)
BODY_X_SHIFT = s(12)
RENDER_X_NUDGE = s(16)   # shifts just the character model left, independent of the gear columns
PORTRAIT_BOX = (s(270), s(480))
PORTRAIT_D = s(96)   # circular class-icon badge diameter
PORTRAIT_X_OFFSET = s(24)
PORTRAIT_Y_OFFSET = s(8)
FACTION_D = s(56)
FACTION_Y_OFFSET = s(24)

STONE_DARK = (20, 20, 20)
BEVEL_LIGHT = (25, 25, 25)
BEVEL_DARK = (0, 0, 0)
ACCENT = (180, 180, 180)
TEXT_GREY = (176, 168, 156)
TEXT_ENCHANT = (60, 210, 80)
SHADOW = (0, 0, 0)


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(f"{FONT_DIR}/{name}", size)
    except OSError:
        return ImageFont.load_default()


def F_TITLE(): return _font("DejaVuSerif-Bold.ttf", s(32))
def F_SUBTITLE(): return _font("DejaVuSans-Bold.ttf", s(18))
def F_STATS(): return _font("DejaVuSans.ttf", s(16))
def F_ITEM(): return _font("DejaVuSans-Bold.ttf", s(14))
def F_SMALL(): return _font("DejaVuSans.ttf", s(12))


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


def _strip_enchant_label(text: str) -> str:
    for prefix in ("enchanted:", "enchant:"):
        if text.lower().startswith(prefix):
            return text[len(prefix):].strip()
    return text


def _truncate(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    while text and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1]
    return text + "…"


def _shadow_text(draw, xy, text, font, fill):
    x, y = xy
    off = max(1, s(1))
    draw.text((x + off, y + off), text, font=font, fill=SHADOW)
    draw.text((x, y), text, font=font, fill=fill)


def _stone_texture(w: int, h: int, dark, light) -> Image.Image:
    noise = Image.effect_noise((w, h), 30)
    tex = ImageOps.colorize(noise, black=dark, white=light).convert("RGB")
    return tex.filter(ImageFilter.GaussianBlur(s(1) or 1))


def _bevel_box(draw, x0, y0, x1, y1, depth, raised=True, fill=None):
    """Draws a carved (raised or sunken) beveled rectangle."""
    if fill:
        draw.rectangle([x0, y0, x1, y1], fill=fill)
    light, dark = (BEVEL_LIGHT, BEVEL_DARK) if raised else (BEVEL_DARK, BEVEL_LIGHT)
    for i in range(depth):
        draw.line([(x0 + i, y1 - i), (x0 + i, y0 + i), (x1 - i, y0 + i)], fill=light)
        draw.line([(x0 + i, y1 - i), (x1 - i, y1 - i), (x1 - i, y0 + i)], fill=dark)


def _circle_mask(diameter: int) -> Image.Image:
    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, diameter - 1, diameter - 1], fill=255)
    return mask


def _draw_frame(canvas: Image.Image, draw: ImageDraw.ImageDraw) -> None:
    bg = _stone_texture(W, H, (10, 10, 10), (26, 26, 26))
    canvas.paste(bg, (0, 0))
    margin = s(8)
    _bevel_box(draw, margin, margin, W - margin, H - margin, depth=s(4) or 3, raised=True, fill=None)
    inner = s(16)
    panel_tex = _stone_texture(W - inner * 2, H - inner * 2, (16, 16, 16), (36, 36, 36))
    canvas.paste(panel_tex, (inner, inner))
    _bevel_box(draw, inner, inner, W - inner, H - inner, depth=s(2) or 2, raised=False)


def _header_bar(canvas: Image.Image, draw: ImageDraw.ImageDraw) -> None:
    x0, y0, x1, y1 = s(24), s(24), W - s(24), s(150)
    bar = _stone_texture(x1 - x0, y1 - y0, (14, 14, 14), (42, 42, 42))
    canvas.paste(bar, (x0, y0))
    _bevel_box(draw, x0, y0, x1, y1, depth=s(3) or 2, raised=False)


def _draw_row(canvas: Image.Image, draw: ImageDraw.ImageDraw, x: int, y: int,
              slot: str, item: dict | None, icon_bytes: bytes | None) -> None:
    quality = (item or {}).get("quality", {}).get("type")
    rim = QUALITY_COLOR.get(quality, EMPTY_SLOT_COLOR)

    draw.rectangle([x - s(3), y - s(3), x + ICON + s(3), y + ICON + s(3)], fill=rim)
    _bevel_box(draw, x - 1, y - 1, x + ICON + 1, y + ICON + 1, depth=s(2) or 2, raised=False, fill=(12, 10, 8))
    if icon_bytes:
        try:
            icon = Image.open(io.BytesIO(icon_bytes)).convert("RGBA").resize((ICON, ICON), Image.LANCZOS)
            canvas.paste(icon, (x, y), icon)
        except Exception:
            draw.rectangle([x, y, x + ICON, y + ICON], fill=EMPTY_SLOT_COLOR)
    else:
        draw.rectangle([x, y, x + ICON, y + ICON], fill=EMPTY_SLOT_COLOR)

    text_x = x + ICON + s(12)
    text_w = COL_W - ICON - s(24)
    if item:
        name_color = QUALITY_COLOR.get(quality, (255, 255, 255))
        draw.text((text_x, y - s(2)), _truncate(draw, item["name"], F_ITEM(), text_w), font=F_ITEM(), fill=name_color)
        draw.text((text_x, y + s(18)), SLOT_LABEL.get(slot, slot), font=F_SMALL(), fill=TEXT_GREY)
        enchants = item.get("enchantments") or []
        if enchants:
            enchant_text = _strip_enchant_label(enchants[0].get("display_string", ""))
            draw.text((text_x, y + s(33)), _truncate(draw, enchant_text, F_SMALL(), text_w),
                       font=F_SMALL(), fill=TEXT_ENCHANT)
    else:
        draw.text((text_x, y - s(2)), "(empty)", font=F_ITEM(), fill=TEXT_GREY)
        draw.text((text_x, y + s(18)), SLOT_LABEL.get(slot, slot), font=F_SMALL(), fill=TEXT_GREY)


def _paste_circular(canvas: Image.Image, img_bytes: bytes | None, center_xy, diameter: int, ring_color) -> None:
    cx, cy = center_xy
    x0, y0 = cx - diameter // 2, cy - diameter // 2
    if img_bytes:
        try:
            img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
            side = min(img.width, img.height)
            left, top = (img.width - side) // 2, (img.height - side) // 2
            img = img.crop((left, top, left + side, top + side)).resize((diameter, diameter), Image.LANCZOS)
            mask = _circle_mask(diameter)
            canvas.paste(img, (x0, y0), mask)
        except Exception:
            pass
    draw = ImageDraw.Draw(canvas)
    ring_w = max(2, s(3))
    draw.ellipse([x0 - ring_w, y0 - ring_w, x0 + diameter + ring_w, y0 + diameter + ring_w],
                 outline=ring_color, width=ring_w)
    draw.ellipse([x0 - ring_w - 1, y0 - ring_w - 1, x0 + diameter + ring_w + 1, y0 + diameter + ring_w + 1],
                 outline=BEVEL_DARK, width=1)


def _draw_faction_badge(canvas: Image.Image, center_xy, faction_type: str | None) -> None:
    asset_name = FACTION_ASSET.get(faction_type or "")
    if not asset_name:
        return
    try:
        crest = Image.open(ASSETS_DIR / asset_name).convert("RGBA")
    except OSError:
        return
    target_h = FACTION_D * 2
    scale = target_h / crest.height
    crest = crest.resize((int(crest.width * scale), target_h), Image.LANCZOS)
    cx, cy = center_xy
    canvas.paste(crest, (cx - crest.width // 2, cy - crest.height // 2), crest)


async def build_character_sheet(bnet_client, *, name: str, level: int, race: str, char_class: str,
                                 spec: str | None, guild_name: str | None, item_level, achievement_points,
                                 faction: str | None, equipment: dict,
                                 render_url: str | None, class_icon_url: str | None) -> io.BytesIO:
    by_slot = {i["slot"]["type"]: i for i in equipment.get("equipped_items", [])}
    all_slots = LEFT_SLOTS + RIGHT_SLOTS
    icon_bytes_list, render_bytes, class_icon_bytes = await asyncio.gather(
        asyncio.gather(*(_fetch_item_icon(bnet_client, by_slot.get(slot)) for slot in all_slots)),
        _fetch(render_url) if render_url else _noop(),
        _fetch(class_icon_url) if class_icon_url else _noop(),
    )
    icons_by_slot = dict(zip(all_slots, icon_bytes_list))

    canvas = Image.new("RGB", (W, H), STONE_DARK)
    draw = ImageDraw.Draw(canvas)
    _draw_frame(canvas, draw)
    _header_bar(canvas, draw)

    class_color = CLASS_COLOR.get(char_class, (235, 230, 220))
    tf = F_TITLE()
    tw = draw.textlength(name, font=tf)
    _shadow_text(draw, ((W - tw) / 2, s(32)), name, tf, class_color)

    subtitle = f"Level {level} {race} {char_class}" + (f" — {spec}" if spec else "")
    sf = F_SUBTITLE()
    sw = draw.textlength(subtitle, font=sf)
    _shadow_text(draw, ((W - sw) / 2, s(72)), subtitle, sf, ACCENT)

    stats = f"Item Level {item_level or '?'}   •   {achievement_points:,} Achievement Points"
    if guild_name:
        stats += f"   •   <{guild_name}>"
    stf = F_STATS()
    stw = draw.textlength(stats, font=stf)
    draw.text(((W - stw) / 2, s(102)), stats, font=stf, fill=TEXT_GREY)

    _paste_circular(
        canvas, class_icon_bytes,
        (s(24) + PORTRAIT_D // 2 + s(10) + PORTRAIT_X_OFFSET, s(24) + PORTRAIT_D // 2 + s(10) + PORTRAIT_Y_OFFSET),
        PORTRAIT_D, class_color,
    )
    _draw_faction_badge(
        canvas,
        (W - s(24) - FACTION_D // 2 - s(10), s(24) + FACTION_D // 2 + s(10) + FACTION_Y_OFFSET),
        faction,
    )

    for i, slot in enumerate(LEFT_SLOTS):
        y = BODY_TOP + i * ROW_H
        _draw_row(canvas, draw, s(30) + BODY_X_SHIFT, y, slot, by_slot.get(slot), icons_by_slot.get(slot))

    for i, slot in enumerate(RIGHT_SLOTS):
        y = BODY_TOP + i * ROW_H
        _draw_row(canvas, draw, W - COL_W - s(30) + BODY_X_SHIFT, y, slot, by_slot.get(slot), icons_by_slot.get(slot))

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
            box_w, box_h = PORTRAIT_BOX
            scale = min(box_w / portrait.width, box_h / portrait.height)
            portrait = portrait.resize(
                (int(portrait.width * scale), int(portrait.height * scale)), Image.LANCZOS
            )
            px = (W - portrait.width) // 2 + BODY_X_SHIFT - RENDER_X_NUDGE
            py = BODY_TOP + (len(LEFT_SLOTS) * ROW_H - portrait.height) // 2
            canvas.paste(portrait, (px, py), portrait)
        except Exception:
            pass

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    buf.seek(0)
    return buf


async def _noop():
    return None
