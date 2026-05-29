# Why Subcategory-to-Category Binding Is a Poor Metadata Design

## Purpose

This document provides scientific, technical, and practical justification for decoupling `subcategory` from strict `category` binding in Knowledge Object (KO) metadata.

Core claim:
- A strict hierarchy where each subcategory belongs to one category is not robust for real-world KO classification.
- A faceted, reusable concept model is more accurate, more maintainable, and more useful in production.

---

## 1) Scientific Rationale

Science of classification says one basic thing: a good category system should follow one clear rule at a time.

In the current model, one subcategory list mixes many different kinds of rules:
- file/media type (document, video, audio)
- content style (presentation, tutorial, interview)
- purpose (educational, informative, motivational)
- capture method (event recording, live talk capture)
- behavior (interactive, static)

Because these are different types of meaning, the list becomes confusing and inconsistent.

Example:
- `Educational/training presentation` is mainly about purpose.
- `Event capturing video` is mainly about how it was recorded.
- `Interactive map` is mainly about behavior.

These are not the same type of label, so they do not fit cleanly under one single subcategory axis.

Another issue is that many labels naturally work across media:
- `Presentation`
- `Tutorial`
- `Guide`
- `Q&A`

For instance, a presentation can be:
- a `.pptx` deck,
- a `.pdf` slide document, or
- a `.mp4` video recording of a talk.

So binding `Presentation` to only one parent category is scientifically weak, because the concept itself is cross-format.

The standard solution in metadata design is to separate dimensions (facets):
- keep one field for media type,
- and separate fields for content form, purpose, delivery method, and behavior.

This gives cleaner, more accurate classification and avoids forcing one concept into the wrong parent.

---

## 2) Technical Rationale (Data Model, Search, and System Behavior)

## 2.1 Hard binding causes schema brittleness
When subcategories are bound to categories, new edge cases force either:
- duplicate labels across categories, or
- artificial constraints that misclassify content.

Both increase maintenance cost and model entropy.

## 2.2 Duplicate concepts fragment analytics and retrieval
If `Tutorial` exists separately under Document, Video, and Audio, analytics split one semantic concept into multiple buckets.

Practical impact:
- query "all tutorials" needs complex unions
- dashboards undercount or over-segment similar content
- governance decisions become noisy

## 2.3 Ambiguous UI and lower annotation consistency
Uploaders must choose between category semantics and content semantics.
This increases inter-annotator disagreement and inconsistent tagging behavior.

Example decision conflict:
- KO is an `.mp4` webinar teaching a process.
- Should it be `Video > Webinar`, `Video > Tutorial/how-to`, or `Slideshow > Educational presentation` if slides are shown?

## 2.4 Weak automation and ML support
Model-assisted tagging performs best when labels are orthogonal and stable.
Mixed-semantics subcategories reduce classification quality because target labels encode multiple latent dimensions.

## 2.5 Difficult interoperability
Integration with external metadata systems is easier when fields map cleanly:
- `type/content form`
- `format`
- `genre`
- `intended use`

A bound hierarchy obscures these mappings.

---

## 3) Practical Rationale (Operational KO Use)

## 3.1 User search behavior is multi-entry, not hierarchy-first
Users search by different intents:
- format-first: "show PPTX presentations"
- purpose-first: "show tutorials on irrigation"
- context-first: "show recordings of live talks"

A single bound hierarchy cannot satisfy all three without compromises.

## 3.2 Same concept across media is common in real pipelines
Knowledge objects are often republished in multiple forms:
- slide deck
- recording of delivery
- transcript/document summary
- audio extract

If subcategories are bound to one category, equivalent assets become difficult to retrieve together.

## 3.3 Curation quality degrades over time
Curators start applying workarounds:
- overuse of generic labels
- inconsistent local conventions
- category-based tagging bias ("choose what fits the dropdown")

The result is lower trust in metadata and lower discoverability.

## 3.4 Consolidation cycles repeat without structural fix
Renaming and merging labels helps temporarily, but ambiguity reappears because the root cause is design coupling, not vocabulary size.

---

## 4) Industry-Standard Modeling Direction

A practical industry pattern is:

1. Keep `category` for operational media class
- Document, Video, Audio, Image, Dataset, Software

2. Promote subcategory-like labels to reusable concepts/facets
- `content_form`: Presentation, Tutorial, Guide, Interview, Q&A
- `intent`: Informative, Instructional, Decision-support, Motivational
- `delivery_context`: Standalone artifact, Recorded event, Live capture
- `interaction_mode`: Static, Interactive

3. Use many-to-many linking
- one concept can apply to many categories
- one KO can have multiple semantic facets

This approach is standard in enterprise content architecture because it balances usability, governance, and extensibility.

---

## 5) Concrete Examples

## Example A: Presentation deck
KO: `Soil_Health_Overview.pptx`
- category: Document
- content_form: Presentation
- intent: Informative
- delivery_context: Standalone artifact

## Example B: Video of same presentation
KO: `Soil_Health_Overview_Talk.mp4`
- category: Video
- content_form: Presentation
- intent: Informative
- delivery_context: Recorded event

Bound hierarchy problem:
- these appear as different subcategory universes
- users cannot reliably retrieve both under one semantic filter

Decoupled model benefit:
- `content_form = Presentation` returns both
- `category` and `format` still allow precise filtering

## Example C: Tutorial across media
- PDF tutorial manual
- how-to video
- podcast tutorial

Decoupled model:
- shared `content_form = Tutorial`
- medium-specific category remains intact

---

## 6) Risks of Decoupling and Practical Mitigations

## Risk 1: Migration complexity
Mitigation:
- build deterministic mapping table from legacy subcategory to concept/facet tuples
- preserve lineage fields (`consolidated_from`, legacy IDs)

## Risk 2: Short-term user confusion
Mitigation:
- keep legacy labels visible as derived/read-only during transition
- provide tooltip examples in upload UI

## Risk 3: Inconsistent facet usage initially
Mitigation:
- enforce required fields for key facets
- add validation and curator QA sampling

---

## 7) Recommended Decision

Decision:
- Stop treating subcategory as category-bound taxonomy nodes.
- Adopt a decoupled concept + facet model.

Why this is the correct practical decision:
1. Scientifically coherent (orthogonal dimensions)
2. Technically robust (cleaner schema and query logic)
3. Operationally effective (better tagging and retrieval)
4. Scalable for future KO formats and publishing channels

---

## 8) Minimum Viable Implementation Path

1. Freeze legacy subcategory additions.
2. Define canonical concept dictionary (unique IDs, preferred labels, aliases).
3. Add facet fields (`content_form`, `intent`, `delivery_context`, `interaction_mode`).
4. Backfill existing KOs via mapping table.
5. Update UI/API to write canonical concepts and facets.
6. Keep dual-read mode for a transition period, then deprecate legacy write path.
