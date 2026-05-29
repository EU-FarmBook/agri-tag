# Themes Consolidation Analysis

## Executive Summary (Verified)

The source file contains **1,022 themes**. The consolidated file currently contains **888 themes**, including **14 consolidation entries** that merge related terms. This yields a **net reduction of 134 themes (13.1%)**.

**Verified counts:**

| Metric | Count |
|---|---|
| Original themes | 1,022 |
| Consolidated themes | 888 |
| Removed names | 145 |
| New consolidated labels added | 8 |
| Consolidation entries | 14 |

**What this means:** The consolidation work is correct and internally consistent with the consolidated file, but it is a **moderate reduction**, not the **60-65% reduction** previously suggested. If the target is ~350-400 themes, additional consolidation steps are still required.

---

## Phase 1: Remove Overly Generic Terms (Implemented)

**Result:** 145 terms removed.

**Rationale:** Meta-concepts and process terms are not useful as user-facing themes. They create noise in tagging/filtering and reduce discoverability.

**Examples removed:**

- ability
- Accuracy
- Activities
- Approaches
- Constraints
- Consumption
- Data
- Equipment
- Policies
- development
- Agricultural statistics
- Air quality
- Agricultural practices

This matches the intent of the original recommendation, but the actual removal count is **145**, not ~50.

---

## Phase 2: Consolidate Domain Variants (Implemented)

These groups are explicitly represented in `data_model.themes_consolidated.json` as consolidation entries with `consolidated_from` lists.

### Group 1: Statistics → Consolidate into `Statistics` (16 → 1)

**Consolidated from:** Agricultural statistics, Aquaculture statistics, catch statistics, Economic statistics, fishery statistics, Food consumption statistics, Food statistics, forestry statistics, Health statistics, Nutrition statistics, production statistics, Social statistics, statistics, vital statistics, Water statistics, wave statistics.

**Rationale:** The domain (agriculture, aquaculture, fishery) is metadata. The theme is “Statistics.”

---

### Group 2: Data Types → Consolidate into `Data & Databases` (12 → 1)

**Consolidated from:** Acoustic data, biological data, Data, Databases, Fishery data, Genetic databases, geological data, geotechnical data, hydrographic data, Pollution data, Statistical data, wave data.

**Rationale:** Data types are better treated as attributes or tags. The theme is “Data & Databases.”

---

### Group 3: Equipment → Consolidate into `Agricultural Equipment` (10 → 1)

**Consolidated from:** Acoustic equipment, aquaculture equipment, Diving equipment, Equipment, Equipment certification, Farm equipment, Geological equipment, mining equipment, Safety equipment, Surveying equipment.

**Rationale:** Equipment type is a facet. The platform context is agriculture, so a single equipment theme improves usability.

---

### Group 4: Quality → Consolidate into `Quality` (12 → 1)

**Consolidated from:** Air quality, Crop quality, Feed quality, fibre quality, Food quality, Keeping quality, product quality, Quality, soil quality, Water quality, water quality control, water quality standards.

**Rationale:** “Quality” is the primary concept; the domain can be captured by tags or metadata.

---

### Group 5: Resilience → Consolidate into `Resilience` (5 → 1)

**Consolidated from:** Climate resilience, Ecosystem resilience, Landscape resilience, Resilience, social-ecological resilience.

**Rationale:** Resilience is a single concept with different application domains.

---

### Group 6: Extension → Consolidate into `Extension Services` (4 → 1)

**Consolidated from:** Agricultural extension systems, Extension, Extension programmes, Extension systems.

**Rationale:** “Extension” is the theme; “programmes/systems” are implementation details.

---

### Group 7: Certification → Consolidate into `Certification` (3 → 1)

**Consolidated from:** Certification, Equipment certification, Organic certification.

**Rationale:** Domain-specific certification can be captured via tags or content attributes.

---

### Group 8: Policies → Consolidate into `Policies & Governance` (10 → 1)

**Consolidated from:** Agricultural policies, Development policies, Economic policies, Environmental policies, Fishery policies, Innovation policies, International policies, Policies, Production policies, Seed policies.

**Rationale:** Policy domain is a facet. The theme is “Policies & Governance.”

---

### Group 9: Development → Consolidate into `Development` (12 → 1)

**Consolidated from:** Agricultural development, Aquaculture development, Capacity development, Development economics, Development policies, Development projects, Economic development, Rural development, Socioeconomic development, Sustainable development, biological development, development.

**Rationale:** “Development” is the common concept; domain qualifiers can be handled elsewhere.

---

### Group 10: Practices → Consolidate into `Agricultural Practices` (3 → 1)

**Consolidated from:** Agricultural practices, Good agricultural practices, agronomic practices.

**Rationale:** Practices can be sub-tagged; the top-level theme is “Agricultural Practices.”

---

## Phase 3: Consolidate Highly Specific Terms (Implemented)

### Group 11: Wave Terms → Consolidate into `Waves & Wave Energy` (8 → 1)

**Consolidated from:** wave data, wave generation, wave generators, wave properties, wave statistics, wave trains, Surface water waves, Water waves.

**Rationale:** These are highly specific technical variants of the same concept.

---

### Group 12: Contamination → Consolidate into `Contamination` (5 → 1)

**Consolidated from:** biological contamination, chemical contamination, Feed contamination, food contamination, Sample contamination.

**Rationale:** Contamination is a unified concept; source/type is a facet.

---

### Group 13: Restoration → Consolidate into `Restoration` (3 → 1)

**Consolidated from:** ecosystem restoration, Environmental restoration, River restoration.

**Rationale:** Restoration type can be treated as a sub-tag.

---

### Group 14: Sampling → Consolidate into `Sampling` (3 → 1)

**Consolidated from:** biological sampling, sediment sampling, Water sampling.

**Rationale:** Sampling is the concept; context can be metadata.

---

## Net Impact (Verified)

| Change Type | Count |
|---|---|
| Removed themes | 145 |
| Added consolidated labels | 8 |
| Net reduction | 134 |
| Final size | 888 |

**Observed outcome:** This consolidation delivers a **moderate reduction**, making the list more manageable while preserving coverage. It does **not** reach the previously suggested ~350-400 target.

---

## If You Want to Go Further (Optional Next Step)

To reach ~350-400 themes, you would need a **second consolidation pass** focused on:

- Ecosystem terms (e.g., services, health, conservation, restoration)
- Climate terms (climate, climate change, adaptation, mitigation, impacts)
- Additional process/meta-terms still present
- Additional “domain variants” beyond the 14 groups above

This is a policy decision more than a technical one; it depends on the desired balance between **discoverability** and **precision**.
