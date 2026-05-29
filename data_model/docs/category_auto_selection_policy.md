# Category Auto-Selection Policy

## Purpose

This document defines how `category` should be selected for uploaded Knowledge Objects before subcategory suggestion is performed.

Upload-safety constraints for dangerous executable, installer, script, and archive payloads are documented separately in:

- [upload_security_policy.md](./upload_security_policy.md)

The policy is aligned with two KO ingestion modes:

1. `file-based KO`
2. `URL-based KO`

It is also aligned with the **currently allowed file upload types** in the frontend:

- documents: `.pdf`, `.txt`, `.doc`, `.docx`, `.ppt`, `.pptx`, `.xls`, `.xlsx`
- data-like tabular files: `.csv`, `.tsv`, `.xls`, `.xlsx`
- images: `.jpg`, `.jpeg`, `.png`
- audio: `.mp3`, `.wav`, `.m4a`
- video: `.mp4`, `.avi`, `.mov`, `.wmv`, `.mpeg`, `.mpg`, `.mkv`, `.flv`, `.webm`, `.3gp`, `.mts`, `.m2ts`, `.vob`, `.rmvb`

The policy is intentionally pragmatic:

1. category availability should depend on KO mode,
2. file-based KOs should derive category from uploaded asset type,
3. URL-based KOs may expose a broader category set,
4. only allow subcategory prediction inside the selected category,
5. do not let users choose impossible category/media combinations.

---

## Core Rule

`category` should be inferred from the **ingestion mode + asset type**, not from the topic alone.

Examples:

- thesis PDF uploaded as file -> `Document`
- thesis defense recording uploaded as file -> `Video`
- weather CSV uploaded as file -> `Dataset`
- FMIS product page submitted as URL -> `Software Application`

This means:

- KO mode answers: how is the object being contributed?
- category answers: what kind of object/asset is it?
- subcategory answers: what kind of content/object is it within that category?

---

## Category Availability By KO Mode

## 1. File-based KO

Allowed categories:

1. `Document`
2. `Video`
3. `Audio`
4. `Image`
5. `Dataset`

Not allowed:

- `Software Application`

### Rationale

Under the current file allow-list, the platform can safely and coherently support:

- documents
- videos
- audios
- images
- tabular/structured datasets

It does **not** safely support physical software delivery in the public file-upload flow.

Therefore:

- `Software Application` should not appear when a file-based KO is being uploaded
- executable, installer, and script payloads should also be blocked independently by upload-security rules

## 2. URL-based KO

Allowed categories:

1. `Document`
2. `Video`
3. `Audio`
4. `Image`
5. `Dataset`
6. `Software Application`

### Rationale

A URL-based KO can point to:

- a hosted document
- a video page
- a podcast/audio page
- an image resource
- a downloadable dataset landing page
- a software tool, repository, product page, or application landing page

This makes `Software Application` appropriate for URL-based KOs even when it is not allowed in file-based uploads.

Important safety note:

- URL-based `Software Application` should refer to software pages, repositories, documentation, or landing pages
- it should not accept direct executable or installable binary URLs

---

## UI Rule

The UI should filter categories immediately after the user selects KO mode.

### If KO mode = `file`

Show only:

- `Document`
- `Video`
- `Audio`
- `Image`
- `Dataset`

Hide:

- `Software Application`

### If KO mode = `url`

Show:

- `Document`
- `Video`
- `Audio`
- `Image`
- `Dataset`
- `Software Application`

This is the cleanest way to preserve the taxonomy without exposing impossible or unsafe options in the wrong ingestion flow.

---

## Additional Rule For File-based KOs

For file-based KOs, category should ideally be:

- auto-inferred from extension / MIME type / lightweight inspection

and then:

- locked or preselected in the UI

So for file-based KOs:

1. user selects file
2. system infers category
3. only valid category is shown or preselected
4. subcategory suggestions are generated only inside that category

This is better than asking contributors to manually choose category from a broad list.

---

## Proposed Category Set

### Operational categories for file-based KOs

1. `Document`
2. `Video`
3. `Audio`
4. `Image`
5. `Dataset`

### Additional category for URL-based KOs

6. `Software Application`

`Slideshow/Presentation` should not be a standalone top-level category.
Slide decks should be treated as:

- `Document > Presentation`

---

## File-based Category Inference Rules

## 1. Document

### Supported file types

- `.pdf`
- `.doc`
- `.docx`
- `.ppt`
- `.pptx`

### Conditionally document-like or dataset-like

- `.txt`
- `.xls`
- `.xlsx`
- `.json` if JSON is enabled in a later upload policy

### Default rule

Assign `Document` if the file is primarily:

- human-readable textual material,
- a report, paper, thesis, or guide,
- or a slide-based artifact intended for reading/presentation.

### Notes

- slide decks remain `Document`, not `Slideshow/Presentation`
- `.ppt` and `.pptx` will often map to subcategory `Presentation`
- `.txt`, `.xls`, and `.xlsx` may all behave either as documents or as datasets depending on content structure
- `.json` should be treated the same way if it is enabled later

---

## 2. Video

### Supported file types

- `.mp4`
- `.avi`
- `.mov`
- `.wmv`
- `.mpeg`
- `.mpg`
- `.mkv`
- `.flv`
- `.webm`
- `.3gp`
- `.mts`
- `.m2ts`
- `.vob`
- `.rmvb`

### Default rule

If the file is a playable moving-image asset, assign:

- `Video`

---

## 3. Audio

### Supported file types

- `.mp3`
- `.wav`
- `.m4a`

### Default rule

If the file is a playable audio-only asset, assign:

- `Audio`

---

## 4. Image

### Supported file types

- `.jpg`
- `.jpeg`
- `.png`

### Default rule

If the file is primarily a still visual artifact, assign:

- `Image`

---

## 5. Dataset

### Supported file types

- `.csv`
- `.tsv`
- `.xls`
- `.xlsx`
- `.txt` when it is clearly structured tabular/plain data export
- `.json` if JSON is enabled in a later upload policy

### Default rule

Assign `Dataset` if the uploaded file is primarily:

- machine-readable tabular data,
- spreadsheet-like records for analysis,
- or a structured export intended for reuse as data rather than for human reading as a report.

### Strong dataset-default extensions

- `.csv`
- `.tsv`

These should default to `Dataset` unless there is a very unusual reason not to.

### Conditionally document-like or dataset-like extensions

- `.txt`
- `.xls`
- `.xlsx`
- `.json` if JSON is enabled later

These formats can hold either:

- human-readable narrative/report content, or
- machine-readable structured data

So they should not be assigned purely from extension alone.
They should be resolved by lightweight inspection.

### Strong dataset indicators

- many rows and columns
- first row looks like field names
- low proportion of long narrative text cells
- repeated scalar values, IDs, dates, measurements, coordinates, or codes
- spreadsheet tabs named like `data`, `observations`, `records`, `measurements`

### Strong non-dataset indicators for `.txt` / `.xls` / `.xlsx` / `.json`

Prefer `Document` instead when the spreadsheet is mainly:

- formatted reporting
- narrative summaries
- presentation-style tables/charts for reading
- one or two sheets with report-like layout and large merged sections

### Important note

Under the current allow-list, `Dataset` is mostly a **tabular or structured-data category**.

---

## URL-based KO Rules

For URL-based KOs, category cannot be inferred from local file extension alone.
Use:

- domain/source context
- page metadata
- URL patterns
- page content inspection
- manual category confirmation if confidence is low

### Examples

- YouTube / Vimeo page -> likely `Video`
- podcast or audio-hosting page -> likely `Audio`
- PDF link or document landing page -> likely `Document`
- dataset portal / download page -> likely `Dataset`
- GitHub repo / app homepage / software landing page -> likely `Software Application`

### Important rule

For URL-based KOs:

- `Software Application` should be available
- but category confidence should still be recorded

---

## Software Application Policy

## File-based KO

- do not expose `Software Application`
- do not allow software binaries or packaged executables in the public file-upload flow

## URL-based KO

- allow `Software Application`
- especially for:
  - repository URLs
  - application landing pages
  - release pages
  - trusted hosted software tools

### Why this split is correct

It preserves the software category in the taxonomy without turning public file upload into a binary distribution channel.

---

## Security Recommendation On Executables

## Short answer

For file-based KOs:

- **do not allow raw executables or installer packages**
- **do not allow zipped executables as a workaround**

This includes:

- `.exe`
- `.msi`
- `.deb`
- `.rpm`
- `.apk`
- `.app`
- `.dmg`
- and archives containing them

## Better alternative

If software is to be contributed:

- submit it as a `URL-based KO`
- choose category `Software Application`
- provide trusted external URL / repo URL / app page

This is the safest way to support software in the platform.

---

## Recommended Mapping Table

## File-based KO

| Primary Signal | Default Category |
|----------------|------------------|
| `.pdf`, `.doc`, `.docx`, `.ppt`, `.pptx` | `Document` |
| `.txt` | inspect before assigning `Document` or `Dataset` |
| `.csv`, `.tsv` | `Dataset` |
| `.xls`, `.xlsx` | inspect before assigning `Document` or `Dataset` |
| `.json` if later enabled | inspect before assigning `Document` or `Dataset` |
| `.jpg`, `.jpeg`, `.png` | `Image` |
| `.mp3`, `.wav`, `.m4a` | `Audio` |
| video formats in allow-list | `Video` |

## URL-based KO

| Signal | Candidate Category |
|--------|--------------------|
| video hosting page | `Video` |
| audio hosting page | `Audio` |
| document/PDF page | `Document` |
| dataset repository or data download page | `Dataset` |
| software repository / software landing page / app page | `Software Application` |

---

## Subcategory Constraint After Category Selection

Once category is assigned, only score subcategories allowed for that category.

Examples:

- `Document`:
  `Thesis`, `Presentation`, `Technical Report`, `Tutorial`, `Guide/Manual`

- `Video`:
  `Recorded Session`, `Interview`, `Q&A Session`, `Educational/Training Media`

- `Audio`:
  `Audio Program`, `Recorded Session`, `Interview`, `Tutorial`

- `Dataset`:
  `Agricultural Production Data`, `Environmental & Temporal Data`, `Geospatial data`

- `Software Application`:
  `Analytical & Scientific Software`, `Educational/Training Software`, `Farm Management & Decision Support Software`, `Simulation Software`

---

## Recommended Implementation Order

1. User selects KO mode: `file` or `url`.
2. Filter category options immediately by KO mode.
3. If KO mode is `file`, infer category from file type and inspection.
4. If KO mode is `url`, infer category from URL/source metadata where possible.
5. Lock or preselect category once confidence is high enough.
6. Run subcategory ranking only within the selected category.

---

## Final Recommendation

The correct product rule is:

- `Software Application` remains in the taxonomy
- `Software Application` is available only for `URL-based KOs`
- `Software Application` does not appear for `file-based KOs`

That is the cleanest and safest design given the current upload model.
