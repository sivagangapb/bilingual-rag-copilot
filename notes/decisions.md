# Decision Log

## Documents
- Laws: EU AI Act (Reg. 2024/1689) + GDPR (Reg. 2016/679)
- Languages: German + English
- Source: EUR-Lex, consolidated versions (HTML)
- Why these: official DE/EN versions with identical structure, free to reuse, long and cross-referenced like real company documents
- Why consolidated: original versions miss corrections (GDPR DE: 3, EN: 1) and the 2026 AI Act amendment
- Why HTML over PDF: keeps structure (articles, paragraphs, ids); PDF has broken line breaks, headers, hyphenation

## Versions
| File | Version | Amendments | Corrections |
|---|---|---|---|
| gdpr_en_20160504.html | 04.05.2016 — 000.002 | none | C1 |
| gdpr_de_20160504.html | 04.05.2016 — 000.003 | none | C1–C3 |
| aiact_en_20260727.html | 27.07.2026 — 001.001 | M1 (2026/1744) | none |
| aiact_de_20260727.html | 27.07.2026 — 001.002 | M1 (2026/1744) | C1, C2 (C2 = corrigendum to 2026/1744, Sept 2026) |

## HTML structure (same in all 4 files)
- Chapter: div#cpt_I (titles: p.title-division-1 / -2)
- Article: div.eli-subdivision#art_N (N can be "4a" → store as string)
  - Heading: p.title-article-norm ("Article 1" / "Artikel 1")
  - Title: div.eli-title#art_N.tit_1
  - Paragraph: div.norm, number in span.no-parag, text in p.norm
  - Points (a), (b): div.grid-list → column-1 letter, column-2 text
- Annex: #anx_I … #anx_XIV (AI Act only; GDPR has no annexes)
- Markers ►C1 / ►M1 … ◄ → remove markers, keep text
- Skip: header table ("Corrected by"), disclaimer
- Stable ids (art_N, cpt_X, anx_X) are identical in EN + DE → free cross-lingual alignment
- Ignore id-<uuid> ids (random, differ per file)

## AI Act amendment 2026/1744
- Added articles: 4a, 60a, 75a, 75b, 75c, 75d; added Annex XIV
- TODO: one sentence on what the amendment is about (look up CELEX 32026R1744)

## Repo decisions
- Raw HTML committed to Git: TODO yes/no + why

## Lessons
- Verify file content, not file names
- Laws change → record version + date, mention in README
- Consolidated texts are documentation only, not legally binding