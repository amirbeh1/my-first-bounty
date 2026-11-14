#!/usr/bin/env python3
"""
main.py - Reuters World headlines (13 Nov 2026) -> output.png

Steps:
  1. Download the Reuters "World" section page and, if that fails, the
     Reuters news sitemap (which lists article titles + publication dates).
  2. Keep only articles dated 2026-11-13 and extract their headlines.
  3. Draw the headlines on a white PNG canvas with Pillow.

Usage:
    python main.py            # live fetch from Reuters
    python main.py --demo     # skip the network, render sample text
                              # (only to test the image-drawing part)

Requires: Python 3.11, requests, Pillow
"""

import html
import re
import sys
import xml.etree.ElementTree as ET

import requests
from PIL import Image, ImageDraw, ImageFont

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
TARGET_DATE = "2026-11-13"                      # the day we want news for
WORLD_URL = "https://www.reuters.com/world/"
NEWS_SITEMAP_URL = (
    "https://www.reuters.com/arc/outboundfeeds/news-sitemap/?outputType=xml"
)
MAX_HEADLINES = 10                              # how many headlines to draw
OUTPUT_FILE = "output.png"

# Used ONLY when Reuters cannot be reached (403, timeout, no headlines...).
# These are deliberately generic placeholders, NOT real news, and the
# rendered image is clearly labelled as sample data (see FALLBACK_NOTE).
FALLBACK_HEADLINES = [
    "Sample headline 1: placeholder for a top world news story",
    "Sample headline 2: placeholder for a diplomacy or politics story",
    "Sample headline 3: placeholder for an economy or markets story",
    "Sample headline 4: placeholder for a conflict or security story",
    "Sample headline 5: placeholder for a climate or science story",
]
FALLBACK_NOTE = (
    "SAMPLE DATA - Reuters was unreachable, these are not real headlines"
)

# A browser-like User-Agent; Reuters often rejects the default requests UA.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# --------------------------------------------------------------------------
# Step 1 + 2: fetching and extracting headlines
# --------------------------------------------------------------------------
def fetch(url: str) -> str:
    """Download a URL and return its text; raises on HTTP errors."""
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def slug_to_title(slug: str) -> str:
    """Fallback: turn a URL slug into a readable title."""
    slug = re.sub(r"-" + TARGET_DATE + r"/?$", "", slug.rstrip("/").split("/")[-1])
    return slug.replace("-", " ").capitalize()


def headlines_from_world_page(page_html: str) -> list[str]:
    """
    Find links like /world/some-story-2026-11-13/ in the section page.
    Reuters article URLs end with the publication date, so the date in the
    URL is a reliable filter.
    """
    pattern = re.compile(
        r'href="(/world/[^"]*?-' + TARGET_DATE + r'/?)"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    seen, results = set(), []
    for path, inner in pattern.findall(page_html):
        if path in seen:
            continue
        seen.add(path)
        text = html.unescape(re.sub(r"<[^>]+>", "", inner)).strip()
        # Link text is sometimes empty or just an image -> use the slug.
        results.append(text if len(text) > 15 else slug_to_title(path))
    return results


def headlines_from_sitemap(xml_text: str) -> list[str]:
    """Parse the Google-News-style sitemap and keep World stories of TARGET_DATE."""
    ns = {
        "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
        "news": "http://www.google.com/schemas/sitemap-news/0.9",
    }
    root = ET.fromstring(xml_text)
    results = []
    for url in root.findall("sm:url", ns):
        loc = url.findtext("sm:loc", default="", namespaces=ns)
        date = url.findtext("news:news/news:publication_date", default="", namespaces=ns)
        title = url.findtext("news:news/news:title", default="", namespaces=ns)
        if "/world/" in loc and date.startswith(TARGET_DATE) and title:
            results.append(title.strip())
    return results


def get_headlines() -> list[str]:
    """Try the section page first, then the sitemap."""
    errors = []
    for name, url, parser in (
        ("section page", WORLD_URL, headlines_from_world_page),
        ("news sitemap", NEWS_SITEMAP_URL, headlines_from_sitemap),
    ):
        try:
            found = parser(fetch(url))
            if found:
                return found[:MAX_HEADLINES]
            errors.append(f"{name}: no headlines dated {TARGET_DATE}")
        except Exception as exc:  # network error, 401/403, bad XML, ...
            errors.append(f"{name}: {exc}")
    raise RuntimeError("Could not get headlines:\n  " + "\n  ".join(errors))


# --------------------------------------------------------------------------
# Step 3: drawing the PNG
# --------------------------------------------------------------------------
def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Try a few common TTF fonts; fall back to Pillow's built-in font."""
    names = (
        ["DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf"]
        if bold
        else ["DejaVuSans.ttf", "arial.ttf", "Arial.ttf"]
    )
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)  # Pillow >= 10.1


def wrap(text: str, font, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    """Greedy word-wrap so each line fits within max_width pixels."""
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def render(headlines: list[str], path: str, note: str | None = None) -> None:
    """Draw headlines on a white canvas; `note` is an optional red banner."""
    width, margin = 1200, 60
    title_font = load_font(40, bold=True)
    body_font = load_font(28)
    note_font = load_font(24, bold=True)
    line_h, gap = 38, 22

    # Measure first so the canvas height fits the content.
    probe = ImageDraw.Draw(Image.new("RGB", (width, 10), "white"))
    wrapped = [
        wrap(f"{i}. {h}", body_font, width - 2 * margin, probe)
        for i, h in enumerate(headlines, 1)
    ]
    height = margin * 2 + 90 + sum(len(w) * line_h + gap for w in wrapped)
    if note:
        height += 50  # room for the banner

    img = Image.new("RGB", (width, height), "white")      # white background
    draw = ImageDraw.Draw(img)

    y = margin
    draw.text((margin, y), f"Reuters World - Top Headlines ({TARGET_DATE})",
              font=title_font, fill="black")
    y += 70
    draw.line([(margin, y), (width - margin, y)], fill="black", width=2)
    y += 25

    if note:
        draw.text((margin, y), note, font=note_font, fill="red")
        y += 50

    for lines in wrapped:
        for line in lines:
            draw.text((margin, y), line, font=body_font, fill="black")
            y += line_h
        y += gap

    img.save(path, "PNG")
    print(f"Saved {path} ({width}x{height}, {len(headlines)} headlines)")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def main() -> None:
    note = None
    if "--demo" in sys.argv:
        # Skip the network entirely (handy for testing the drawing code).
        headlines, note = FALLBACK_HEADLINES, FALLBACK_NOTE
    else:
        try:
            headlines = get_headlines()
            print("Headlines found:")
            for h in headlines:
                print(" -", h)
        except Exception as exc:
            # Never crash: report the problem and use the placeholder list
            # so that output.png is always produced.
            print(f"WARNING: {exc}", file=sys.stderr)
            print("Using fallback sample headlines instead.", file=sys.stderr)
            headlines, note = FALLBACK_HEADLINES, FALLBACK_NOTE
    render(headlines, OUTPUT_FILE, note)


if __name__ == "__main__":
    main()
