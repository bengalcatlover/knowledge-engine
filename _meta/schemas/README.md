# Knowledge Base ID System

This document defines the stable identifier system for every artifact in the knowledge base.
ID stability is a prerequisite for provenance tracking, deduplication, and cross-artifact edges.
Do not change an ID once assigned; use `status: deprecated` to retire an artifact instead.

---

## Design Principles

1. **IDs are permanent.** Content changes; IDs do not.
2. **IDs encode type, not rank.** The prefix tells you what kind of thing it is; the suffix is opaque.
3. **IDs come from the source where possible.** Field IDs derive from the discipline taxonomy; course IDs from the MIT course number; document IDs from the YouTube video ID already embedded in each Markdown. Sequential numbers are used only when no natural key exists.
4. **Review status is separate from artifact type.** Never encode review state into the ID.

---

## ID Formats

### field_id — Academic Discipline

Format: `F-{SLUG}`

The slug is the normalized short code derived from `discipline-final.json`.
Use uppercase ASCII letters and hyphens only. No numbers.

| Example | Meaning |
|---------|---------|
| `F-EECS` | Electrical Engineering & Computer Science |
| `F-ECON` | Economics |
| `F-MATH` | Mathematics |
| `F-PHYS` | Physics |
| `F-BIOL` | Biology |
| `F-MGMT` | Management |

Assignment rule: one `field_id` per top-level discipline entry in `discipline-final.json`.
Sub-disciplines share the parent `field_id` and are distinguished by `broad_category`.

---

### course_id — MIT Course

Format: `C-MIT-{course_number}`

The course number is the official MIT OpenCourseWare identifier, including dots and letters.

| Example | Meaning |
|---------|---------|
| `C-MIT-6.034` | Artificial Intelligence (EECS) |
| `C-MIT-14.01` | Principles of Microeconomics |
| `C-MIT-18.06` | Linear Algebra |
| `C-MIT-6.042J` | Mathematics for Computer Science |

Assignment rule: taken verbatim from the OCW course URL slug or the course number field in the source Markdown front-matter.

---

### document_id — Lecture Document

Format: `D-{video_id}`

`video_id` is the 11-character YouTube video ID already present in each processed Markdown file
(field `youtube_id` or equivalent in front-matter). This makes every document ID globally
traceable to its source recording without any registry lookup.

| Example | Meaning |
|---------|---------|
| `D-EFg3wF_GUX8` | A specific MIT OCW lecture video |
| `D-7iAMHpez6Z0` | Another lecture |

Assignment rule: read `youtube_id` from the Markdown front-matter. If the field is absent,
assign `D-UNKNOWN-{sha1[:8]}` of the file content and flag for manual review.

---

### concept_id — Concept Card

Format: `K-{NNNN}`

`NNNN` is a zero-padded four-digit sequential integer, assigned in creation order.
Start from `K-0001`. Extend to five digits (`K-00001`) only after `K-9999` is reached.

| Example | Meaning |
|---------|---------|
| `K-0001` | First concept card created |
| `K-0042` | 42nd concept card |

Assignment rule: read the current counter from `_meta/counters.yaml`, increment, write back.
Never reuse a retired ID.

---

### perspective_id — User Perspective

Format: `P-{NNNN}`

Same sequential scheme as concept_id, separate counter.

| Example | Meaning |
|---------|---------|
| `P-0001` | First user perspective recorded |

Assignment rule: same as concept_id counter, separate key `perspective_counter` in `_meta/counters.yaml`.

---

### claim_id — Verifiable Claim

Format: `CL-{NNNN}`

Same sequential scheme, separate counter.

| Example | Meaning |
|---------|---------|
| `CL-0001` | First claim |
| `CL-0123` | 123rd claim |

Assignment rule: counter key `claim_counter` in `_meta/counters.yaml`.

---

### edge_id — Relationship Edge

Format: `E-{NNNN}`

Same sequential scheme, separate counter.

| Example | Meaning |
|---------|---------|
| `E-0001` | First edge |

Assignment rule: counter key `edge_counter` in `_meta/counters.yaml`.

---

## Counter File

Location: `C:/Users/akira/OneDrive/Desktop/clauce/knowledge-engine/_meta/counters.yaml`

```yaml
concept_counter: 0
perspective_counter: 0
claim_counter: 0
edge_counter: 0
```

Agents MUST read and increment this file atomically before writing a new artifact.
Do not skip numbers; do not reuse numbers.

---

## Namespacing Rules

- All IDs within a knowledge base instance are globally unique across types because prefixes differ.
- Cross-artifact references always use the full ID including prefix.
- When referencing a document section, use the locator syntax: `D-{video_id}#section-heading` or `D-{video_id}:chunk_{n}`.

---

## Versioning

This ID system is **v1.0** (2026-09-09).
Breaking changes require incrementing the version and migrating existing artifacts.
Schema changes that add optional fields are non-breaking.

---

## File Locations for Schema Definitions

| Schema file | Artifact type |
|-------------|--------------|
| `concept-card.yaml` | Concept cards (`K-*`) |
| `perspective.yaml` | User perspectives (`P-*`) |
| `claim.yaml` | Verifiable claims (`CL-*`) |
| `edge.yaml` | Relationship edges (`E-*`) |
| `field-index.yaml` | Field/discipline index entries (`F-*`) |
| `concept-card-template.md` | Ready-to-fill Markdown template for concept cards |
