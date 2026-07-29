"""Table-aware HTML → text extraction.

The OCR model returns markdown whose tables are HTML. We strip ``style``
attributes (which bloat text and carry no semantic value) while preserving the
``<table>`` HTML itself, and extract surrounding text. Tables are protected via
placeholders so they survive the text extraction pass intact.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

import html_text

_STYLE_ATTRS = ("style",)


def _strip_table_styles(table: Tag) -> Tag:
    """Remove style attributes from a table and its cells (in place)."""
    for attr in _STYLE_ATTRS:
        if attr in table.attrs:
            del table[attr]
    for tag in table.find_all(True):
        if isinstance(tag, Tag) and tag.name not in ("td", "th"):
            continue
        for attr in _STYLE_ATTRS:
            if attr in tag.attrs:
                del tag[attr]
    return table


def extract_text_with_tables(html_content: str) -> str:
    """Convert HTML to text, preserving ``<table>`` HTML verbatim.

    Steps:
      1. Parse HTML; for each ``<table>``, strip styles and stash its HTML
         behind a unique placeholder.
      2. Extract formatted text from the table-less HTML.
      3. Restore each table HTML at its placeholder.
    """
    if not html_content:
        return ""

    soup = BeautifulSoup(html_content, "html.parser")

    tables: list[tuple[str, str]] = []
    for idx, table in enumerate(soup.find_all("table")):
        placeholder = f"[TABLE_{idx}]"
        tables.append((placeholder, str(_strip_table_styles(table))))
        table.replace_with(BeautifulSoup(placeholder, "html.parser"))

    text = html_text.extract_text(str(soup))

    for placeholder, table_html in tables:
        text = text.replace(placeholder, table_html)

    return text
