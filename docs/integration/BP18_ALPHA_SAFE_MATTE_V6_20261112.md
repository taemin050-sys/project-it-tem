# Alpha-safe model glyph compositing

Actual Sunburst2.6 returned RGBA black ink with transparent background.
Dropping alpha produced an opaque black rectangle despite correct glyph output.
New alpha-safe-matte-text-edit-v6 composites RGBA over white before calculating
coverage; regression verifies transparent and white-backed equivalents are equal.
Existing source-stroke retouch and v1-v5 records remain unchanged.
Compatible fallback673561e9e7e6c5bce26e11b8b325172c4ff0b9b4.
The model still supplies glyph shape; server matte compositing is explicitly
recorded separately from pure Freeform. Human acceptance remains required.
