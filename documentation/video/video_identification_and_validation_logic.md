# Video Identification And Validation Logic

This document describes the current video-classification logic in the KO classifier.

The video branch now follows the same pattern as the other calibrated modalities:

- code
  - extracts measurable evidence from transcripts and related text
  - runs generic scoring and fusion
- data-driven spec
  - defines video feature signals
  - supports signal strength and confuser handling

The current video signal specification lives in:

- `data_model/runtime/subcategories/signal_specs/video_signal_spec.json`

## 1. Scope

This logic applies to assets routed to the `Video` category.

Current supported uploaded video file types include:

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

## 2. Category Routing

Category and subcategory are intentionally decoupled.

- `category`
  - derived operationally from MIME type and extension
- `subcategory`
  - derived from evidence in transcript text and related signals

## 3. Video Profile Scoring

Video subtype scoring is profile-first.

The current video source profiles are:

- `Field demonstration/walkthrough`
- `How-to/procedure demonstration`
- `Case study`
- `Explainer/documentary`
- `Interview/practitioner perspective`
- `Expert Q&A session`
- `Panel discussion`
- `Recorded presentation/webinar`
- `Tool/machinery/software walkthrough`
- `Simulation/animation/model visualisation`

Each profile is scored using measurable feature signals externalized in:

- `data_model/runtime/subcategories/signal_specs/video_signal_spec.json`

## 4. Implemented Video Feature Detectors

The runtime currently includes explicit detectors for:

- `situated_field_context`
- `tool_operation_interface_focus`
- `stepwise_action_demonstration`
- `single_case_problem_solution_arc`
- `explanatory_contextual_narration`
- `speaker_testimonial_centrality`
- `explicit_question_answer_turntaking`
- `moderated_multi_speaker_exchange`
- `slide_or_screen_led_delivery`
- `animation_model_based_representation`

Each detector can declare:

- `Strong`
- `Partial`
- `Weak`
- `Weak/Partial`

The video spec also supports:

- positive transcript signals
- structural/context bonuses
- paired-term bonuses
- negative/confuser signals

## 5. Evidence Sources Used By Video Detectors

The current video scorer uses transcript-derived cues such as:

- question count
- question/answer phrase count
- speaker marker count
- first-person/testimonial density
- procedural step terms
- field-context terms
- slide/webinar terms
- panel/moderator terms
- simulation/model terms
- tool/interface terms

This remains transcript-first. It does not replace the vision branch; it makes the transcript-side rules explicit.

## 6. Typical Signal Examples

### Field Demonstration / Walkthrough

Strong cues:

- `in the field`
- `on the farm`
- `field visit`
- `plot`
- `demonstration plot`

Supportive combinations:

- `field + crop`
- `farm + plot`

### How-To / Procedure Demonstration

Strong cues:

- `step`
- `first`
- `next`
- `then`
- `demonstrate`
- `how to`

### Case Study

Strong cues:

- `challenge`
- `problem`
- `solution`
- `outcome`
- `lesson learned`

### Explainer / Documentary

Strong cues:

- `overview`
- `explainer`
- `how it works`
- `context`
- `narration`

### Interview / Practitioner Perspective

Strong cues:

- `in my experience`
- `on our farm`
- `what we did`
- `from my perspective`

### Expert Q&A Session

Strong cues:

- `question`
- `answer`
- `q&a`
- `ask the expert`
- `audience question`

### Panel Discussion

Strong cues:

- `moderator`
- `panel`
- `audience`
- `joining us`

### Recorded Presentation / Webinar

Strong cues:

- `slide`
- `screen`
- `webinar`
- `presentation`
- `next slide`
- `screen share`

### Tool / Machinery / Software Walkthrough

Strong cues:

- `tool`
- `machine`
- `app`
- `software`
- `interface`
- `dashboard`
- `button`
- `menu`

### Simulation / Animation / Model Visualisation

Strong cues:

- `simulation`
- `animation`
- `model`
- `forecast`
- `scenario`
- `prediction`

## 7. Video Vision / Text LLM Role

The intended split is:

- rule-based transcript signal layer
  - interpretable first-pass scoring
- vision model
  - richer visual arbitration when enabled
- text LLM
  - arbitration when transcript/video evidence remains ambiguous

Neither the LLM nor the vision model should replace the authoritative video rule base.

## 8. Known Limitations

Current known limitations:

- transcript quality strongly affects video subtype scoring
- slide-driven webinars and expert lectures can overlap heavily
- field demonstrations and tool walkthroughs often share vocabulary
- deeper visual evidence is still handled elsewhere rather than in this signal spec

## 9. Validation Guidance

Recommended video validation set:

- one field demonstration
- one procedure demonstration
- one case-study video
- one explainer/documentary
- one interview
- one expert Q&A
- one panel discussion
- one recorded webinar/presentation
- one tool/software walkthrough
- one simulation/animation/model visualisation
