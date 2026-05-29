# Software Identification And Validation Logic

This document describes the current software-classification logic in the KO classifier.

The software branch follows the same pattern now used for datasets:

- code
  - extracts measurable evidence from software descriptions and related text
  - runs generic scoring and fusion
- data-driven spec
  - defines software feature signals
  - defines profile-to-unified mapping overrides
  - defines broad-fallback suppression policy

The current software signal specification lives in:

- `data_model/runtime/subcategories/signal_specs/software_signal_spec.json`

## 1. Scope

This logic applies to assets routed to the `Software Application` category.

In runtime normalization, `Software Application` is treated as the `Software` modality for profile loading and signal scoring.

## 2. Category Routing

Software is currently mostly URL-first and text-first.

The category is derived operationally, while the subcategory is inferred from evidence in:

- title text
- page text
- metadata text
- product descriptions
- software-related documentation text

## 3. Software Profile Scoring

Software subtype scoring is profile-first.

The current software source profiles are:

- `Farm Management System (FMIS)`
- `Monitoring & Recording Tools`
- `Field Data Collection Apps`
- `Mapping & GIS Tools`
- `Data Analysis & Dashboard Tools`
- `Simulation & Forecasting Tools`
- `Automation & Control Systems`
- `Training & Learning Applications`

Each profile is scored using measurable feature signals externalized in:

- `data_model/runtime/subcategories/signal_specs/software_signal_spec.json`

## 4. Implemented Software Feature Detectors

The runtime currently includes explicit detectors for:

- `workflow_role_and_scope`
- `integration_and_interoperability_connectivity`
- `temporal_recording_orientation`
- `input_modality_and_capture_mode`
- `field_capture_and_observation_structure`
- `spatial_interaction_and_georeferenced_analysis`
- `analysis_visualisation_and_insight_generation`
- `model_prediction_and_scenario_logic`
- `automation_control_and_triggering`
- `learning_mechanics_and_training_design`

Each detector can declare a signal strength:

- `Strong`
- `Partial`
- `Weak`
- `Weak/Partial`

The runtime uses signal strength as a multiplier so broad software cues do not compete too strongly with subtype-defining ones.

The expanded software spec also supports:

- positive text signals
- paired-term bonuses
- negative/confuser signals

## 5. Typical Signal Examples

### FMIS / broad software platform

Strong cues:

- `workflow`
- `planning`
- `records`
- `management`
- `dashboard`
- `farm management system`

Supportive combinations:

- `planning + records`
- `operations + dashboard`

Confusers:

- `tutorial`
- `quiz`
- `forecast`

### Monitoring & Recording Tools

Strong cues:

- `tracking`
- `record`
- `logging`
- `history`
- `monitoring`

Supportive combinations:

- `track + history`
- `record + time`

Confusers:

- `tutorial`
- `forecast`

### Field Data Collection Apps

Strong cues:

- `field`
- `scouting`
- `inspection`
- `observation`
- `capture`
- `mobile app`

Supportive combinations:

- `field + capture`
- `crop + scouting`

Confusers:

- `forecast`
- `quiz`

### Mapping & GIS Tools

Strong cues:

- `map`
- `gis`
- `geospatial`
- `parcel`
- `layer`
- `spatial`

Supportive combinations:

- `map + layer`
- `gis + parcel`

Confusers:

- `tutorial`
- `lesson`

### Data Analysis & Dashboard Tools

Strong cues:

- `analysis`
- `analytics`
- `dashboard`
- `insight`
- `kpi`
- `chart`

Supportive combinations:

- `dashboard + analytics`
- `chart + reporting`

Confusers:

- `automation`
- `quiz`

### Simulation & Forecasting Tools

Strong cues:

- `simulation`
- `forecast`
- `prediction`
- `scenario`
- `model`

Supportive combinations:

- `simulation + scenario`
- `forecast + prediction`

Confusers:

- `tutorial`
- `field capture`

### Automation & Control Systems

Strong cues:

- `automation`
- `control`
- `trigger`
- `alert`
- `actuator`

Supportive combinations:

- `automation + control`
- `irrigation + control`

Confusers:

- `tutorial`
- `lesson`

### Training & Learning Applications

Strong cues:

- `training`
- `learning`
- `lesson`
- `quiz`
- `tutorial`
- `assessment`

Supportive combinations:

- `training + assessment`
- `lesson + quiz`

Confusers:

- `api`
- `automation`
- `forecast`

## 6. Unified Subcategory Roll-Up

Software profiles are rolled into unified subcategories through the v5 model plus runtime mapping overrides in:

- `data_model/runtime/subcategories/signal_specs/software_signal_spec.json`

Key runtime intent:

- `software_tools_and_applications`
  - broad software fallback / umbrella label
- `monitoring_operations_and_sensor_records`
  - specific target for monitoring/recording tools
- `maps_and_geospatial_content`
  - specific target for mapping/GIS tools
- `simulations_forecasts_and_model_visualisations`
  - specific target for simulation/forecasting tools

Some software profiles still intentionally retain the broad software label as primary because the current unified taxonomy does not yet expose a more software-native specific subtype for every tool class.

## 7. Broad Fallback Suppression

`software_tools_and_applications` is useful as a fallback, but it should not dominate when a more specific software subtype has strong evidence.

The suppression rule is defined in:

- `data_model/runtime/subcategories/signal_specs/software_signal_spec.json`

Current policy:

- broad subcategory:
  - `software_tools_and_applications`
- specific competing subcategories:
  - `monitoring_operations_and_sensor_records`
  - `maps_and_geospatial_content`
  - `simulations_forecasts_and_model_visualisations`

When a specific software subtype is strong enough, the broad fallback is capped below it.

## 8. Software Text LLM

Software can also use a software-specific text LLM classifier.

The intended role of the LLM is:

- arbitration when heuristic signals are close or mixed
- recovery when software descriptions are informative but structured signal coverage is incomplete
- not authorship of the authoritative software rule base

The authoritative software rule base should remain in the software signal spec and source model.

## 9. Known Limitations

Current known limitations:

- some software profiles still collapse to the broad `software_tools_and_applications` bucket because the unified taxonomy is not equally specific across all software classes
- FMIS-like platforms often overlap with monitoring, dashboard, and field-capture language
- some software pages are sparse marketing pages with limited discriminative signals

## 10. Validation Guidance

Recommended software validation set:

- one FMIS / farm platform page
- one monitoring / recording tool page
- one field data collection app page
- one mapping / GIS tool page
- one dashboard / analytics tool page
- one simulation / forecasting tool page
- one automation / control system page
- one training / learning application page
