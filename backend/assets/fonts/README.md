# Arabic fonts for PDF reports

The bilingual PDF exporter (`app/services/pdf_report.py`) needs a TrueType
font with Arabic glyphs. Drop one of these here so Arabic renders correctly:

- **Amiri-Regular.ttf** (recommended) — https://github.com/aliftype/amiri/releases
  Permissive SIL Open Font License.
- **NotoSansArabic-Regular.ttf** — https://fonts.google.com/noto/specimen/Noto+Sans+Arabic
- **IBMPlexSansArabic-Regular.ttf** — https://github.com/IBM/plex/tree/master/IBM-Plex-Sans-Arabic

The exporter looks for the file at:
`backend/assets/fonts/<PDF_ARABIC_FONT>` (default: `Amiri-Regular.ttf`)

Override the filename via the `PDF_ARABIC_FONT` environment variable.

If no Arabic font is found, the exporter falls back to Helvetica and Arabic
text is rendered as empty boxes — the PDF still generates, it just looks wrong.
Install a font before going live.
