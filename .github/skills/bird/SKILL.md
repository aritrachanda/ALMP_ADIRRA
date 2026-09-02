---
name: bird
description: BIRD domain reference for development tasks. Use when work involves ECB BIRD concepts, layers, mappings, metadata exports, or transformation rules.
---

Provide a practical reference for working with the ECB Banks' Integrated Reporting Dictionary (BIRD).

## What BIRD Is

The Banks' Integrated Reporting Dictionary (BIRD) is a collaborative initiative led by the ECB, national central banks, and industry participants to reduce regulatory reporting burden and improve reported data quality.

At a high level, BIRD provides:
- A redundancy-free common input dictionary.
- Integrated metadata linking input concepts to reporting frameworks.
- Transformation rules that explain how to derive/enrich data and generate reporting outputs.

Key boundaries (important for implementation discussions):
- BIRD is not an IT product.
- BIRD is not a regulatory act.
- Adoption by banks is voluntary.
- BIRD does not remove reporting agents' responsibility for compliance.

## Why It Matters In This Repository

This repository maps source banking schemas to target models such as BIRD. In practical terms, BIRD gives the target semantics and vocabulary that mapping logic should align with.

For this project, treat BIRD as:
- A target metadata standard.
- A semantic bridge between heterogeneous source systems and regulatory outputs.
- A reference dictionary where concept meaning matters more than literal column name similarity.

## Core BIRD Components (Development View)

BIRD methodology distinguishes layers and connecting components.

Input-side layers:
- LDM (Logical Data Model): detailed logical model of business requirements and relationships.
- ELDM (Enriched LDM): LDM plus derived attributes.
- IL (Input Layer): forward-engineered physical blueprint from LDM.
- EIL (Enriched IL): IL plus derived attributes.

Output-side layers:
- ROL (Reference Output Layer): output requirements in BIRD reference codification.
- NROL (Non-Reference Output Layer): output requirements in original codification systems.

Connecting/quality components:
- Derivation Transformation Rules: derive/enrich attributes.
- Generation Transformation Rules: produce report outputs.
- Mappings: map non-reference dictionaries into BIRD reference dictionary.
- Forward engineering lineage: links logical to physical layers.
- Validation rules: structural and business checks.

## Vocabulary You Should Use During Development

Use BIRD-consistent terms when describing tasks or outputs:
- Entity (Cube in SMCube terms): roughly table-level concept.
- Attribute (Variable / cube item): roughly column-level concept.
- Restriction/Subdomain/Domain: allowed-value or constraint context.
- Allowed Value (Member): controlled vocabulary value.
- Framework: regulatory collection context (e.g., FINREP, AnaCredit, Asset Encumbrance, SHS).
- Reference vs Non-reference: BIRD codification vs original framework codification.

## Practical Guidance For Mapping Work

When implementing mapping features, prefer this sequence:
1. Understand whether target content is reference or non-reference codification.
2. Align source attributes to BIRD concepts semantically (not only by string similarity).
3. Preserve lineage context (which source field and rationale support each mapped target).
4. Distinguish derivation logic from direct mapping logic.
5. Keep room for framework-specific constraints (FINREP, AnaCredit, AE, SHS).

When presenting mapping confidence, incorporate:
- Concept definition match.
- Domain/allowed-value compatibility.
- Role compatibility (identifier vs observation vs complementary attribute).
- Known transformation requirement (direct vs derived).

## BIRD Access Points To Use

Use the BIRD website components intentionally:
- About BIRD: official definitions, methodology, components, legal notice, release documents.
- Navigator: interactive exploration of input/output models, entities, relationships, mappings.
- Metadata & Exports: technical exports and object-level extracts.
- API: programmatic access, including simplified endpoints and logical lineage endpoints.

High-value links:
- Home: https://bird.ecb.europa.eu/
- About BIRD: https://bird.ecb.europa.eu/projectDefinition
- Navigator: https://bird.ecb.europa.eu/nav
- Metadata & Exports: https://bird.ecb.europa.eu/cm
- API docs: https://bird.ecb.europa.eu/documentation/api/v2/bird.html
- Navigator user guide: https://bird.ecb.europa.eu/userguide/index.html

## Coverage Snapshot (As Published On Website)

According to the About BIRD content currently published:
- AnaCredit: all 10 collection tables.
- Asset Encumbrance: all 23 templates.
- FINREP: 77 of 122 in-scope templates.

Always verify current scope on the website before implementing hard assumptions.

## Governance And Legal Notes

- BIRD is collaboratively governed (Steering Group and Experts Group with industry/authority participation).
- BIRD content is published as open source under Apache 2.0 (per legal notice on the website).
- The website explicitly states BIRD content is non-binding and does not replace formal regulatory requirements.

## How To Use This Skill In Conversations

Use this skill when requests involve:
- "What is BIRD?"
- Interpreting BIRD layers/components for engineering tasks.
- Designing source-to-BIRD mapping logic.
- Understanding reference/non-reference codification and mapping implications.
- Identifying what metadata/export/API source to consult for implementation.

Expected behavior when this skill is active:
- Explain BIRD with correct boundaries (not a regulation, not an IT tool).
- Tie concepts directly to implementation decisions in this repository.
- Prefer semantic and lineage-aware mapping guidance.
- Cite official BIRD pages for disputed or version-sensitive details.

