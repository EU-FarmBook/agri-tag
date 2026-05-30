# Document Identification And Validation Logic

This document describes the current document-classification logic in the Agri-Tag.

The document branch now follows the same pattern as dataset and software:

- code
  - extracts measurable document evidence
  - runs generic scoring and fusion
- data-driven spec
  - defines document feature signals
  - supports signal strength and confuser handling

The current document signal specification lives in:

- `data_model/runtime/subcategories/signal_specs/document_signal_spec.json`

## 1. Scope

This logic applies to assets routed to the `Document` category.

Current supported uploaded document file types:

- `.pdf`
- `.txt`
- `.docx`
- `.pptx`

## 2. Category Routing

Category and subcategory are intentionally decoupled.

- `category`
  - derived operationally from MIME type, extension, and file/url routing
- `subcategory`
  - derived from evidence in the extracted document content

## 3. Document Profile Scoring

Document subtype scoring is profile-first.

The current document source profiles are:

- `How-To / Instructional Documents`
- `Explanatory Documents`
- `Technical & Scientific Documents`
- `Case Study / Practice Documents`
- `Project Reports`
- `Policy & Regulatory Documents`
- `Summaries & Factsheets`
- `Informational / Communication Documents`
- `Templates & Reusable Documents`

Each profile is scored using measurable feature signals externalized in:

- `data_model/runtime/subcategories/signal_specs/document_signal_spec.json`

## 4. Implemented Document Feature Detectors

The runtime currently includes explicit detectors for:

- `sequential_steps`
- `action_verbs`
- `ordered_flow`
- `tools_materials_mentioned`
- `concept_breakdown`
- `examples`
- `structured_explanation`
- `data_heavy`
- `structured_sections`
- `formal_tone`
- `references`
- `problem_solution_outcome_structure`
- `milestones`
- `deliverables`
- `structured_reporting`
- `recommendations`
- `policy_framing`
- `governance_context`
- `short_format`
- `bullet_points`
- `high_info_density`
- `general_info`
- `announcements`
- `broad_audience_targeting`
- `predefined_structure`
- `placeholders`
- `repeatable_use`

Each detector can declare:

- `Strong`
- `Partial`
- `Weak`
- `Weak/Partial`

The document spec also supports:

- positive text signals
- structural bonuses
  - e.g. numbered steps, bullets, headings, citations, placeholders
- paired-term bonuses
- negative/confuser signals

## 5. Evidence Sources Used By Document Detectors

The document scorer currently uses:

- extracted text
- filename text
- line-level structure
- bullet count
- numbered-step count
- heading count
- citation count
- placeholder count
- imperative verb count
- policy-term density
- project-term density
- narrative/case-study term density

## 6. Typical Signal Examples

### How-To / Instructional Documents

Strong cues:

- `step`
- `procedure`
- `instructions`
- imperative verbs such as:
  - `use`
  - `apply`
  - `install`
  - `prepare`

Structural cues:

- numbered steps
- ordered flow markers like `first`, `next`, `finally`

Confusers:

- `policy`
- `governance`
- `background`

### Explanatory Documents

Strong cues:

- `what is`
- `overview`
- `explains`
- `components`
- `process`

Structural cues:

- explanatory sectioning
- concept breakdown language

Confusers:

- `step 1`
- `deliverable`

### Technical & Scientific Documents

Strong cues:

- `methods`
- `results`
- `discussion`
- `analysis`
- `evidence`
- `references`

Structural cues:

- headings like:
  - `Introduction`
  - `Methods`
  - `Results`
  - `Conclusion`
- citations / bibliography patterns

Confusers:

- `flyer`
- `announcement`
- `template`

### Case Study / Practice Documents

Strong cues:

- `problem`
- `challenge`
- `solution`
- `implementation`
- `outcome`
- `lesson learned`

Supportive combinations:

- `problem + solution`
- `solution + outcome`

Confusers:

- `policy`
- `template`

### Project Reports

Strong cues:

- `milestone`
- `deliverable`
- `work package`
- `reporting`
- `project output`

Supportive context:

- project-term density
- headings reflecting progress or reporting structure

Confusers:

- `tutorial`
- `questionnaire`

### Policy & Regulatory Documents

Strong cues:

- `policy`
- `regulation`
- `directive`
- `framework`
- `compliance`
- `governance`

Supportive context:

- policy-term density
- recommendation language

Confusers:

- `template`
- `case study`

### Summaries & Factsheets

Strong cues:

- `factsheet`
- `summary`
- `key points`
- `highlights`

Structural cues:

- short format
- high bullet density

Confusers:

- `methods`
- `appendix`

### Informational / Communication Documents

Strong cues:

- `announcement`
- `launch`
- `event`
- `news`
- `join us`

Supportive context:

- broad audience language
- awareness/outreach framing

Confusers:

- `references`
- `placeholder`

### Templates & Reusable Documents

Strong cues:

- `template`
- `form`
- `checklist`
- `fill in`
- `to be completed`
- placeholders

Structural cues:

- placeholder count
- repeated fillable structure

Confusers:

- `results`
- `discussion`
- `policy`

## 7. Document Text LLM

Documents can also use the text LLM for arbitration.

The intended role of the LLM is:

- arbitration when heuristic signals are close or mixed
- support when extracted text is rich but rule coverage is incomplete
- not authorship of the authoritative document rule base

The authoritative rule base should remain in the document signal spec and source model.

## 8. Known Limitations

Current known limitations:

- some extracted text loses layout detail from the original file
- strong lexical overlap can still exist between:
  - technical documents
  - project reports
  - policy documents
- short outreach documents and summaries can overlap heavily without layout-aware features

## 9. Validation Guidance

Recommended document validation set:

- one how-to guide
- one explanatory document
- one technical/scientific document
- one case study
- one project report
- one policy/regulatory document
- one summary/factsheet
- one informational/outreach document
- one template/reusable document
