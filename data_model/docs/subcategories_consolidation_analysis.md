# Subcategories Consolidation Analysis

## Executive Summary

The metadata guide defines **78 category-subcategory associations** across **7 categories**.
The current raw JSON (`data_model.subcategories.json`) contains **77 associations**, not 78, because **`Problem-solving presentation` appears in the PDF guide but is missing from the JSON source**.

This revised consolidation keeps the taxonomy usable for later automation:

1. Keep **category** as an operational field for now.
2. Remove **`Slideshow/Presentation`** as a standalone category in the consolidated model and fold slide-based content into **`Document`**.
3. Consolidate noisy or redundant subcategories within the remaining categories.
4. Preserve distinctions that are genuinely useful to users, especially for academic document types.
5. Keep `Software Application` in the taxonomy, but expose it only in the `URL-based KO` flow under the current policy.

## Recommended Outcome

- Source taxonomy in guide: `78` category-subcategory associations
- Current raw JSON: `77` associations
- Proposed consolidated taxonomy: `44` category-subcategory associations across `6` categories
- Proposed consolidated unique subcategory concepts: `38`

This gives a material simplification without collapsing important user-facing distinctions.

---

## Why This Direction Fits The Product

The next intended workflow is:

1. infer or lock the category from the uploaded object type,
2. then suggest likely subcategories with probabilities/confidence scores.

That means the taxonomy should avoid two failure modes:

1. category choices that are impossible or arbitrary for the uploader,
2. subcategory distinctions that mostly reflect jargon, UI implementation, or packaging instead of true semantic differences.

The current model has both issues:

- `Slideshow/Presentation` is operationally weak because the same physical upload may be a PDF that is either a document or a slide deck.
- several subcategories are near-synonyms or differ only by project workflow labels, not by retrieval intent.

So the immediate cleanup should simplify **subcategories first**, while keeping categories stable enough for later auto-selection logic.

This is now explicitly aligned with [category_auto_selection_policy.md](./category_auto_selection_policy.md):

- for `file-based KOs`, operational categories are `Document`, `Video`, `Audio`, `Image`, and `Dataset`
- for `URL-based KOs`, `Software Application` is additionally available
- `Slideshow/Presentation` is not kept as a standalone top-level category

---

## Source Inventory

### Categories In Metadata Guide

1. `Document`
2. `Slideshow/Presentation`
3. `Video`
4. `Image`
5. `Audio`
6. `Dataset`
7. `Software Application`

### Source Discrepancy

The metadata guide includes:

- `Problem-solving presentation`

The raw JSON does not.

This matters because the PDF guide should be treated as canonical input for the consolidation exercise. In the proposed model, that missing subtype is absorbed into the consolidated `Presentation` target.

---

## Proposed Category-Level Decision

### Keep

- `Document`
- `Video`
- `Audio`
- `Image`
- `Dataset`
- `Software Application`

### Remove As Standalone Category

- `Slideshow/Presentation`

### Rationale

`Slideshow/Presentation` is the weakest operational category in the current scheme:

- it is often uploaded as the same file types as ordinary documents,
- its existing subcategories are purpose labels rather than stable content forms,
- and later category auto-selection by file type becomes much cleaner if slide decks are treated as a document subtype (`Presentation`) rather than as a separate top-level category.

This does **not** mean presentations disappear.
It means they become a document subcategory where they are easier to classify and easier to explain to users.

### Operational note

Under the current category policy:

- `Software Application` is retained in the taxonomy,
- but it is available only for `URL-based KOs`,
- and it should not be available in the normal `file-based KO` flow.

---

## Final Proposed Consolidated Taxonomy

Before the category-by-category detail, the guiding consolidation rule is:

- merge labels when the distinction is mainly wording, packaging, project workflow jargon, or UI implementation detail
- keep labels separate when they have materially different user meaning and can later be supported by measurable classification signals

## 1. Document

### Keep separate

- `Article in conference proceedings`
- `Journal article`
- `Chapter in edited volume`
- `Book`
- `Thesis`
- `Tutorial`

### Consolidate

- `Booklet` + `Brochure` + `Factsheet` + `Flyer`
  -> `Informational Booklet`

- `Handbook` + `Manual` + `Guide`
  -> `Guide/Manual`

- `Deliverable report` + `Milestone report` + `Report/paper` + `Review document` + `Technical/technology article` + `Technical information/specifications card`
  -> `Technical Report`

- `Practice abstract` + `Decision-making presentation` + `Educational/training presentation` + `Informative presentation` + `Motivational presentation` + `Problem-solving presentation`
  -> `Presentation`

- `Newsletter` + `Press release` + `Policy brief`
  -> `News & Communication`

### Why these decisions are valid

- academic publication types are distinct and useful for search and analytics,
- `Tutorial` is worth keeping separate because step-by-step instructional intent is clearer than in `Guide/Manual`,
- the merged groups mostly remove terminology variation, project jargon, or purpose-only splits.

### Measurable classification direction

These document subcategories can later be classified with reproducible signals such as:

- page count and short-form layout for `Informational Booklet`
- slide-like page structure, low text density, and presentation markers for `Presentation`
- thesis markers, university/degree cues, and formal structure for `Thesis`
- citation density, IMRaD structure, and reference sections for academic publication types
- procedural language and ordered steps for `Tutorial`
- deliverable/project markers, section structure, and technical terminology for `Technical Report`
- news/update language, release cues, and timeliness markers for `News & Communication`

### Result

- current guide-based associations affecting document-like material:
  `23 Document + 7 Slideshow = 30`
- proposed consolidated `Document` associations:
  `11`

---

## 2. Video

### Keep separate

- `Case study`
- `Documentary video`
- `Simulation video`
- `Vlog`

### Consolidate

- `Educational/training video` + non-document use of `Guide`
  -> `Educational/Training Media`

- `Event capturing video` + `Presentation/live talk capturing video` + `Webinar` + `Event capturing podcast` + `On-demand seminar` + `Panel discussion`
  -> `Recorded Session`

- `Interview video` + `Interview`
  -> `Interview`

- `Product/feature review video` + `Testimonial`
  -> `Product Review/Testimonial`

- `Question-and-answer video` + `Question-and-answer podcast`
  -> `Q&A Session`

- `Tutorial/how-to video` + `Tutorial` (audio/document uses)
  -> `Tutorial`

### Why these decisions are valid

- `Recorded Session` is a stronger user-facing concept than splitting by webinar vs event capture vs live talk recording,
- `Interview` and `Q&A` are format concepts that should not be duplicated just because medium changes,
- `Product review` and `Testimonial` are both evaluative/promotional showcases and work well together.

### Measurable classification direction

Candidate signals for later video classification:

- speech-turn patterns and interview framing for `Interview`
- presence of audience or session framing for `Recorded Session`
- explicit question/answer structure for `Q&A Session`
- tutorial verbs, demonstrations, and instructional sequencing for `Tutorial`
- visual product showcase and evaluative language for `Product Review/Testimonial`

### Result

- current video associations: `14`
- proposed video associations: `10`

---

## 3. Audio

### Consolidate

- `Audio magazine` + `Commentary` + `Solo podcast`
  -> `Audio Program`

- `Educational/training podcast` + non-document use of `Guide`
  -> `Educational/Training Media`

- `Event capturing podcast` + `On-demand seminar` + `Panel discussion` + video-side session captures
  -> `Recorded Session`

- `Interview`
  -> consolidated cross-media `Interview`

- `Question-and-answer podcast`
  -> consolidated cross-media `Q&A Session`

- `Tutorial/guide`
  -> consolidated cross-media `Tutorial`

### Why these decisions are valid

- the current audio taxonomy over-emphasises episode packaging and host setup,
- users usually care more about whether the audio is instructional, interview-based, recorded session content, or general audio programming.

### Measurable classification direction

Candidate signals for later audio classification:

- question/answer turn structure for `Q&A Session`
- host/guest interview framing for `Interview`
- session/lecture/webinar framing for `Recorded Session`
- instructional sequencing and procedural language for `Tutorial`
- magazine/editorial or commentary style for `Audio Program`

### Result

- current audio associations: `11`
- proposed audio associations: `6`

---

## 4. Image

### Consolidate

- `Chart/graph` + `Infographic`
  -> `Data Visualization`

- `Interactive figure/image` + `Static figure/image`
  -> `Figure/Image`

- `Interactive map` + `Static map`
  -> `Map`

### Why these decisions are valid

- static vs interactive is an implementation property, not a strong subtype boundary,
- chart/graph vs infographic is mainly a design distinction within visual communication of information.

### Measurable classification direction

Candidate signals for later image classification:

- map-like geographic structure for `Map`
- axes, legends, numeric encodings, and chart geometry for `Data Visualization`
- illustration/photo/diagram composition for `Figure/Image`

### Result

- current image associations: `6`
- proposed image associations: `3`

---

## 5. Dataset

### Keep separate

- `Geospatial data`
- `Video data`

### Rename for consistency

- `Auditory data`
  -> `Audio Data`

- `Imagery data`
  -> `Image Data`

- `Textual data`
  -> `Text Data`

### Consolidate

- `Graph-related data` + `Network-related data`
  -> `Graph/Network Data`

- `Crop-related data` + `Input-related data` + `Yield-related data`
  -> `Agricultural Production Data`

- `Temporal data` + `Weather/climate data`
  -> `Environmental & Temporal Data`

### Why these decisions are valid

- the current dataset list mixes modality, structure, domain, and time behaviour,
- some entries are obviously overlapping (`Graph` vs `Network`; `Crop` vs `Yield` vs `Input`),
- `Temporal data` is too generic on its own because time is a property of many datasets, not a strong standalone subtype.

### Alignment with category policy

Under the current file upload policy, `Dataset` is effectively a tabular or structured-data category, mainly supported by:

- `.csv`
- `.tsv`
- `.xls`
- `.xlsx`
- `.txt` after inspection
- `.json` only if enabled later

So the dataset taxonomy is broader than the current ingestion pipeline, but still worth keeping for future expansion and URL-based data resources.

### Measurable classification direction

Candidate signals for later dataset classification:

- coordinate fields and GIS-style schema for `Geospatial data`
- edge/node schema or adjacency structure for `Graph/Network Data`
- crop, input, yield, and farm-production fields for `Agricultural Production Data`
- time-indexed environmental variables for `Environmental & Temporal Data`
- modality-specific records for `Audio Data`, `Image Data`, and `Video data`

### Result

- current dataset associations: `12`
- proposed dataset associations: `8`

---

## 6. Software Application

### Keep separate

- `Business software`
- `Data repository/database`

### Consolidate

- `AI software` + `Data analysis software` + `Scientific software`
  -> `Analytical & Scientific Software`

- `Decision support tool` + `Farm Management Information System (FMIS)`
  -> `Farm Management & Decision Support Software`

- `Educational/training software` + `Game`
  -> `Educational/Training Software`

- `Simulation`
  -> `Simulation Software`

### Why these decisions are valid

- `Game` is explicitly defined in the guide as a serious educational/training game, so keeping it separate is not useful,
- FMIS is a domain-specific management/decision-support tool and belongs with DSS,
- AI/data analysis/scientific software are better treated as one analytical-software family.

### Alignment with category policy

This category remains part of the taxonomy, but under the current policy it should be exposed only for `URL-based KOs`.

That is because:

- the current file upload allow-list does not support safe software ingestion,
- the public upload flow should not become a binary distribution channel,
- software is better represented for now by repository URLs, release pages, product pages, or hosted app URLs.

### Measurable classification direction

Candidate signals for later software classification from URLs/metadata:

- repository and dependency metadata for `Analytical & Scientific Software`
- farm operations, planning, and decision-support terminology for `Farm Management & Decision Support Software`
- training/serious-game framing for `Educational/Training Software`
- simulation/modelling framing for `Simulation Software`

### Result

- current software associations: `10`
- proposed software associations: `6`

---

## Count Summary

| Category | Guide / Current Basis | Proposed |
|----------|-----------------------|----------|
| Document | 23 | 11 |
| Slideshow/Presentation | 7 in guide, 6 in JSON | 0 |
| Video | 14 | 10 |
| Audio | 11 | 6 |
| Image | 6 | 3 |
| Dataset | 12 | 8 |
| Software Application | 10 | 6 |
| Total associations | 78 in guide / 77 in JSON | 44 |

Note:
- `44` is the number of category-subcategory associations visible in a category-bound UI.
- the consolidated model contains `38` unique subcategory concepts because some concepts are reused across categories (`Tutorial`, `Interview`, `Q&A Session`, `Recorded Session`, `Educational/Training Media`).

Operational note:
- in the current platform design, not all six categories are exposed in all KO modes
- `Software Application` is reserved for `URL-based KOs`

---

## Implications For The Next Phase

This consolidation is intentionally compatible with the next product step you described:

1. category should be **locked or auto-suggested** from file/object characteristics,
2. subcategories should then be **ranked probabilistically** within the allowed category.

### Practical direction

- a PDF or DOCX should not be manually assignable to `Dataset` or `Software Application`,
- slide decks should be treated as `Document > Presentation`,
- video/audio uploads should only see subcategories valid for those media,
- `Software Application` should only be selectable in the `URL-based KO` flow,
- the classifier can then rank consolidated subcategories instead of trying to score a noisy, over-granular label set.

### Recommendation

For the next implementation phase:

1. freeze the consolidated taxonomy proposed here,
2. make category selection constrained by upload/file type,
3. run classification only inside the valid category space,
4. surface top-N subcategory suggestions with confidence and probability.

That will give cleaner user behaviour and better model performance than trying to score the old unrestricted taxonomy.

---

## Assessment Of `Document_type_list_review_suggestion.md`

The colleague suggestion is useful as a sanity check, but it should not be adopted verbatim.

### Useful takeaways

- it correctly identifies redundancy among short informational materials
- it correctly separates project-report labels from technical-report labels
- it recognises that `Tutorial` and `Guide/Manual` need deliberate treatment

### Where it is weaker than the current proposal

- `Information/promotional material` mixes `newsletter` and `press release` with booklet/flyer-style artifacts, but these have different measurable properties and retrieval use
- `Instructional material` merges `tutorial` with `guide/manual`, but that reduces classifier clarity because `Tutorial` has stronger procedural signals
- `Scientific publication/grey literature` is too broad; books, chapters, journal articles, and conference proceedings are distinct enough to classify and retrieve separately
- the proposed `Education/training material` and `Template` labels are new vocabulary rather than consolidations grounded in the metadata guide

### Conclusion on usefulness

The colleague document is useful as supporting evidence that consolidation is needed, especially for documents.
However, the current proposal is stronger because it stays closer to:

- the source metadata guide,
- operational category constraints,
- and future measurable classification criteria.

---

## Explicit Consolidation Principle

For consortium review, the proposal can be summarised in one sentence:

- each source subcategory was either:
  - consolidated into a broader target because the original distinction was too weak or too hard to classify reproducibly, or
  - kept unchanged because it carries a meaningful distinction that can plausibly be measured later.

The most explicit document-level mapping is provided in [document_subcategories_consolidation.md](./document_subcategories_consolidation.md).
