# Audio Identification And Validation Logic

This document describes the current audio-classification logic in the KO classifier.

The audio branch now follows the same pattern as dataset, software, document, and image:

- code
  - extracts measurable evidence from transcripts
  - runs generic scoring and fusion
- data-driven spec
  - defines audio feature signals
  - supports signal strength and confuser handling

The current audio signal specification lives in:

- `data_model/runtime/subcategories/signal_specs/audio_signal_spec.json`

## 1. Scope

This logic applies to assets routed to the `Audio` category.

Current supported uploaded audio file types:

- `.mp3`
- `.wav`
- `.m4a`

## 2. Category Routing

Category and subcategory are intentionally decoupled.

- `category`
  - derived operationally from MIME type and extension
- `subcategory`
  - derived from evidence in the transcript and related text

## 3. Audio Profile Scoring

Audio subtype scoring is profile-first.

The current audio source profiles are:

- `Interview/practitioner perspective`
- `Expert commentary/explainer`
- `Case study/practice story`
- `Panel discussion`
- `Q&A`
- `Talk/lecture`
- `How-to/procedure guide`

Each profile is scored using measurable feature signals externalized in:

- `data_model/runtime/subcategories/signal_specs/audio_signal_spec.json`

## 4. Implemented Audio Feature Detectors

The runtime currently includes explicit detectors for:

- `speaker_experience_centrality`
- `expert_explanatory_monologue`
- `case_narrative_arc`
- `moderated_multi_voice_exchange`
- `explicit_question_answer_format`
- `sustained_single_speaker_presentation`
- `stepwise_procedural_instruction`

Each detector can declare:

- `Strong`
- `Partial`
- `Weak`
- `Weak/Partial`

The audio spec also supports:

- positive transcript signals
- structural/context bonuses
- paired-term bonuses
- negative/confuser signals

## 5. Evidence Sources Used By Audio Detectors

The current audio scorer uses transcript-derived cues such as:

- question count
- question/answer phrase count
- speaker marker count
- first-person density
- testimonial phrases
- procedural step terms
- field-context terms
- panel/moderator terms

## 6. Typical Signal Examples

### Interview / Practitioner Perspective

Strong cues:

- `in my experience`
- `on our farm`
- `what we did`
- `from my perspective`

Supportive combinations:

- `my + experience`
- `our + farm`

Confusers:

- `step 1`
- `panel`

### Expert Commentary / Explainer

Strong cues:

- `let me explain`
- `overview`
- `how it works`
- `concept`
- `system`

Confusers:

- `question`
- `moderator`

### Case Study / Practice Story

Strong cues:

- `challenge`
- `problem`
- `solution`
- `outcome`
- `lesson learned`

Supportive combinations:

- `problem + solution`
- `solution + outcome`

### Panel Discussion

Strong cues:

- `moderator`
- `panel`
- `audience`
- `joining us`

Supportive combinations:

- `moderator + panel`
- `audience + question`

### Q&A

Strong cues:

- `question`
- `answer`
- `q&a`
- `q:`
- `a:`

Supportive combinations:

- `question + answer`
- `q: + a:`

### Talk / Lecture

Strong cues:

- `today I will present`
- `lecture`
- `seminar`
- `presentation`
- `talk`

### How-To / Procedure Guide

Strong cues:

- `step`
- `first`
- `next`
- `then`
- `finally`
- `how to`

Supportive combinations:

- `first + next`
- `then + finally`

## 7. Audio Text LLM Role

The intended role of the LLM is:

- arbitration when transcript signals are close or mixed
- support when transcript text is informative but rule coverage is incomplete
- not authorship of the authoritative audio rule base

The authoritative audio rule base should remain in the audio signal spec and source model.

## 8. Known Limitations

Current known limitations:

- transcript quality strongly affects audio subtype scoring
- weak speaker segmentation can blur interview, panel, and lecture distinctions
- short clips may not provide enough structure for confident subtype assignment

## 9. Validation Guidance

Recommended audio validation set:

- one interview
- one expert explainer
- one case-study narrative
- one panel discussion
- one Q&A session
- one lecture/talk
- one procedural guide
