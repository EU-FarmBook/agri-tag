# Image Identification And Validation Logic

This document describes the current image-classification logic in the KO classifier.

The image branch now follows the same pattern as dataset, software, and document:

- code
  - extracts measurable evidence from OCR text, filenames, and lightweight structural cues
  - runs generic scoring and fusion
- data-driven spec
  - defines image feature signals
  - supports signal strength and confuser handling
  - defines broad-fallback suppression policy

The current image signal specification lives in:

- `data_model/runtime/subcategories/signal_specs/image_signal_spec.json`

## 1. Scope

This logic applies to assets routed to the `Image` category.

Current supported uploaded image file types:

- `.jpg`
- `.jpeg`
- `.png`

## 2. Category Routing

Category and subcategory are intentionally decoupled.

- `category`
  - derived operationally from MIME type and extension
- `subcategory`
  - derived from evidence in the image asset

For images, that evidence is currently a blend of:

- OCR text
- filename text
- lightweight textual/structural cues
- optional vision-model support elsewhere in the pipeline

## 3. Image Profile Scoring

Image subtype scoring is profile-first.

The current image source profiles are:

- `Chart/graph`
- `Infographic`
- `Diagram/schematic`
- `Map`
- `Field/observational photograph`
- `Diagnostic photograph`
- `Equipment/infrastructure photograph`
- `Aerial/remote-sensing image`

Each profile is scored using measurable feature signals externalized in:

- `data_model/runtime/subcategories/signal_specs/image_signal_spec.json`

## 4. Implemented Image Feature Detectors

The runtime currently includes explicit detectors for:

- `quantitative_plot_encoding`
- `visual_summary_composition`
- `abstract_explanatory_rendering`
- `geospatial_reference_structure`
- `field_observation_context`
- `diagnostic_detail_salience`
- `equipment_infrastructure_presence`
- `remote_sensing_signature`

Each detector can declare:

- `Strong`
- `Partial`
- `Weak`
- `Weak/Partial`

The image spec also supports:

- positive text signals
- structural bonuses
  - e.g. axis/orientation/callout counts
- paired-term bonuses
- negative/confuser signals

## 5. Evidence Sources Used By Image Detectors

The current image scorer uses:

- extracted OCR text
- filename text
- numeric token count
- axis/legend term count
- map/orientation term count
- callout/summary term count
- process/component term count
- diagnostic term count
- field-context term count
- equipment term count
- remote-sensing term count

This is still text-assisted rather than fully vision-native. The signal-spec layer is meant to make that logic explicit until deeper vision features are added.

## 6. Typical Signal Examples

### Chart / Graph

Strong cues:

- `x-axis`
- `y-axis`
- `legend`
- `series`
- `bar`
- `line`
- `plot`

Supportive combinations:

- `x-axis + y-axis`
- `legend + series`

Confusers:

- `lesion`
- `field photo`

### Infographic

Strong cues:

- `key message`
- `fact`
- `summary`
- `did you know`
- `highlights`

Supportive combinations:

- `key + message`
- `summary + highlights`

Confusers:

- `x-axis`
- `wkt`

### Diagram / Schematic

Strong cues:

- `component`
- `process`
- `system`
- `input`
- `output`
- `flow`
- `diagram`

Supportive combinations:

- `input + output`
- `process + flow`

Confusers:

- `close-up`
- `bar chart`

### Map

Strong cues:

- `latitude`
- `longitude`
- `north`
- `scale`
- `legend`
- `parcel`
- `map`

Supportive combinations:

- `latitude + longitude`
- `map + legend`
- `scale + north`

Confusers:

- `lesion`
- `x-axis`

### Field / Observational Photograph

Strong cues:

- `field`
- `crop`
- `farm`
- `plot`
- `soil`
- `grazing`

Supportive combinations:

- `field + crop`
- `farm + plot`

Confusers:

- `legend`
- `close-up lesion`

### Diagnostic Photograph

Strong cues:

- `symptom`
- `lesion`
- `disease`
- `damage`
- `defect`
- `close-up`

Supportive combinations:

- `close-up + symptom`
- `disease + lesion`

Confusers:

- `x-axis`
- `workflow`

### Equipment / Infrastructure Photograph

Strong cues:

- `machine`
- `equipment`
- `tractor`
- `implement`
- `irrigation`
- `sensor`

Supportive combinations:

- `tractor + implement`
- `irrigation + control`

Confusers:

- `lesion`
- `x-axis`

### Aerial / Remote-Sensing Image

Strong cues:

- `ndvi`
- `satellite`
- `drone`
- `remote sensing`
- `thermal`
- `multispectral`

Supportive combinations:

- `satellite + ndvi`
- `drone + aerial`

Confusers:

- `workflow`
- `step 1`

## 7. Broad Fallback Suppression

`photographs_and_field_images` is useful as a broad fallback, but it should not dominate when a more specific image subtype has strong evidence.

The suppression rule is defined in:

- `data_model/runtime/subcategories/signal_specs/image_signal_spec.json`

Current policy:

- broad subcategory:
  - `photographs_and_field_images`
- specific competing subcategories:
  - `charts_and_data_visualisations`
  - `infographics_and_visual_summaries`
  - `diagrams_and_schematics`
  - `maps_and_geospatial_content`
  - `diagnostic_and_inspection_images`

When a specific image subtype is strong enough, the broad photograph fallback is capped below it.

## 8. Image Vision / Text LLM Role

The signal spec is not meant to replace the vision model.

The intended split is:

- rule-based signal layer
  - interpretable first-pass scoring
- vision model
  - arbitration and richer visual discrimination when enabled
- text/OCR support
  - auxiliary evidence, not the only source of truth

## 9. Known Limitations

Current known limitations:

- the image signal layer is still heavily text-assisted
- OCR-poor images may rely more on the vision branch than on these heuristics
- field photographs and equipment photographs still overlap substantially
- remote-sensing imagery remains only partially captured by text cues

## 10. Validation Guidance

Recommended image validation set:

- one chart or graph
- one infographic
- one diagram or schematic
- one map
- one field/observational photograph
- one diagnostic close-up
- one equipment/infrastructure photograph
- one aerial/remote-sensing image
