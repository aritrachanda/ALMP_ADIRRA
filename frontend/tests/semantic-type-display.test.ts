/**
 * U1b — Semantic Type card display helpers (Card 1).
 *
 * Covers the widened-resolver presentation logic:
 *  - shape evidence is classified as a data-side signal and labelled "Value shape"
 *  - the two structured-unresolved labels ("No signal" / "Signals present …")
 *  - near-miss candidate evidence is surfaced only for the needs-decision case
 *  - the fallback single "Unresolved" label for records without the new fields
 */

import { describe, it, expect } from 'vitest';
import {
  DATA_EV_KINDS,
  isDataEvidenceKind,
  semanticEvidenceKindLabel,
  structuredUnresolvedInfo,
  semanticConfidenceTag,
  semanticTypeButtons,
  semanticReasoningPlate,
  semanticTypeLabel,
  semanticDomainLabel,
  semanticScopeLabel,
  semanticTypeMatchesQuery,
  findSemTypeRecordForColumn,
} from '../src/pages/semanticTypeDisplay';

// ── Shape evidence chip rendering ────────────────────────────────────────────

describe('shape evidence classification', () => {
  it('classifies shape as a data-side (What the data shows) signal', () => {
    expect(DATA_EV_KINDS.has('shape')).toBe(true);
    expect(isDataEvidenceKind('shape')).toBe(true);
  });

  it('labels shape evidence "Value shape"', () => {
    expect(semanticEvidenceKindLabel('shape')).toBe('Value shape');
  });

  it('keeps existing data kinds classified as data-side', () => {
    for (const kind of ['validator', 'distribution', 'pattern', 'storage', 'schema']) {
      expect(isDataEvidenceKind(kind)).toBe(true);
    }
  });

  it('keeps meaning-side kinds out of the data column', () => {
    for (const kind of ['name', 'glossary', 'prior', 'entity', 'ai']) {
      expect(isDataEvidenceKind(kind)).toBe(false);
    }
  });
});

// ── Structured-unresolved: two labels ────────────────────────────────────────

describe('structuredUnresolvedInfo — two-label split', () => {
  it('labels a no_signal record "No signal" with no decision prompt', () => {
    const info = structuredUnresolvedInfo({ type_id: 'unresolved', resolution_reason: 'no_signal' });
    expect(info.unresolved).toBe(true);
    expect(info.label).toBe('No signal');
    expect(info.needsDecision).toBe(false);
    expect(info.candidateEvidence).toEqual([]);
  });

  it('labels a corroboration_without_initiation record "Signals present — needs a decision"', () => {
    const info = structuredUnresolvedInfo({
      type_id: 'unresolved',
      resolution_reason: 'corroboration_without_initiation',
      nearest_candidates: [
        {
          type_id: 'monetary_amount',
          blocked_by: 'no initiating channel fired',
          evidence: [{ kind: 'shape', signal: 'consistent 2-decimal scale across 98% of samples', weight: 'moderate' }],
        },
      ],
    });
    expect(info.label).toBe('Signals present — needs a decision');
    expect(info.needsDecision).toBe(true);
    expect(info.candidate?.type_id).toBe('monetary_amount');
    expect(info.candidateEvidence).toHaveLength(1);
    expect(info.candidateEvidence[0].kind).toBe('shape');
  });

  it('treats below_floor the same as corroboration_without_initiation (needs a decision)', () => {
    const info = structuredUnresolvedInfo({
      type_id: 'unresolved',
      resolution_reason: 'below_floor',
      nearest_candidates: [{ type_id: 'rate', evidence: [{ kind: 'shape', signal: 'bounded [0,1]', weight: 'weak' }] }],
    });
    expect(info.label).toBe('Signals present — needs a decision');
    expect(info.needsDecision).toBe(true);
    expect(info.candidateEvidence).toHaveLength(1);
  });

  it('surfaces no candidate evidence when needsDecision but no nearest_candidates', () => {
    const info = structuredUnresolvedInfo({ type_id: 'unresolved', resolution_reason: 'below_floor' });
    expect(info.needsDecision).toBe(true);
    expect(info.candidate).toBeUndefined();
    expect(info.candidateEvidence).toEqual([]);
  });
});

// ── Fallback single-label path ───────────────────────────────────────────────

describe('structuredUnresolvedInfo — fallback', () => {
  it('falls back to "Unresolved" for an unresolved record without resolution_reason', () => {
    const info = structuredUnresolvedInfo({ type_id: 'unresolved' });
    expect(info.unresolved).toBe(true);
    expect(info.label).toBe('Unresolved');
    expect(info.needsDecision).toBe(false);
  });

  it('leaves conflict rendering untouched (keeps the "Unresolved" fallback label)', () => {
    const info = structuredUnresolvedInfo({ type_id: 'unresolved', resolution_reason: 'conflict' });
    expect(info.label).toBe('Unresolved');
    expect(info.needsDecision).toBe(false);
  });

  it('reports a resolved record as not unresolved', () => {
    const info = structuredUnresolvedInfo({ type_id: 'monetary_amount', resolution_reason: null });
    expect(info.unresolved).toBe(false);
    expect(info.needsDecision).toBe(false);
  });

  it('handles a null record safely (treated as unresolved fallback)', () => {
    const info = structuredUnresolvedInfo(null);
    expect(info.unresolved).toBe(true);
    expect(info.label).toBe('Unresolved');
  });
});

// ── SD-R3b: tag / state→buttons / reasoning plate ────────────────────────────

describe('display normalisation helpers (raw ids + legacy alias)', () => {
  it('passes current type ids through unchanged (raw)', () => {
    expect(semanticTypeLabel('surrogate_systemid')).toBe('surrogate_systemid');
    expect(semanticTypeLabel('natural_lei')).toBe('natural_lei');
    expect(semanticTypeLabel('surrogate_uuid')).toBe('surrogate_uuid');
    expect(semanticTypeLabel('reference_code')).toBe('reference_code');
  });

  it('normalises legacy ids to their current raw id', () => {
    expect(semanticTypeLabel('identifier')).toBe('surrogate_systemid');
    expect(semanticTypeLabel('iban')).toBe('natural_iban');
    expect(semanticTypeLabel('henkilotunnus')).toBe('natural_henkilotunnus');
    expect(semanticTypeLabel('natural_htun')).toBe('natural_henkilotunnus');
    expect(semanticTypeLabel('y_tunnus')).toBe('natural_yritystunnus');
    expect(semanticTypeLabel('natural_ytun')).toBe('natural_yritystunnus');
  });

  it('unknown / unresolved type ids', () => {
    expect(semanticTypeLabel('some_new_id')).toBe('some_new_id');
    expect(semanticTypeLabel('unresolved')).toBe('unresolved');
    expect(semanticTypeLabel(null)).toBe('unresolved');
  });

  it('domain roles pass through raw; key renders as Primary Key; legacy normalised', () => {
    expect(semanticDomainLabel('natural_id')).toBe('natural_id');
    expect(semanticDomainLabel('surrogate_id')).toBe('surrogate_id');
    expect(semanticDomainLabel('key')).toBe('Primary Key');
    expect(semanticDomainLabel('identifier')).toBe('surrogate_id');
  });

  it('scopes pass through raw', () => {
    expect(semanticScopeLabel('global')).toBe('global');
    expect(semanticScopeLabel('internal')).toBe('internal');
    expect(semanticScopeLabel(null)).toBe('');
  });
});

describe('semanticTypeMatchesQuery — short/legacy form search after the id rename', () => {
  it('matches the current id directly', () => {
    expect(semanticTypeMatchesQuery('natural_henkilotunnus', 'henkilotunnus')).toBe(true);
    expect(semanticTypeMatchesQuery('natural_yritystunnus', 'yritystunnus')).toBe(true);
  });

  it('matches short/legacy forms not present in the current id string', () => {
    expect(semanticTypeMatchesQuery('natural_henkilotunnus', 'htun')).toBe(true);
    expect(semanticTypeMatchesQuery('natural_henkilotunnus', 'hetu')).toBe(true);
    expect(semanticTypeMatchesQuery('natural_yritystunnus', 'ytun')).toBe(true);
    expect(semanticTypeMatchesQuery('natural_yritystunnus', 'ytunnus')).toBe(true);
  });

  it('ignores hyphens/underscores/case when matching', () => {
    expect(semanticTypeMatchesQuery('natural_henkilotunnus', 'h-tunnus')).toBe(true);
    expect(semanticTypeMatchesQuery('natural_yritystunnus', 'Y-Tunnus')).toBe(true);
    expect(semanticTypeMatchesQuery('natural_yritystunnus', 'y_tunnus')).toBe(true);
  });

  it('does not cross-match the other type or unrelated queries', () => {
    expect(semanticTypeMatchesQuery('natural_henkilotunnus', 'ytunnus')).toBe(false);
    expect(semanticTypeMatchesQuery('natural_yritystunnus', 'htun')).toBe(false);
    expect(semanticTypeMatchesQuery('monetary_amount', 'htun')).toBe(false);
  });

  it('handles empty/null input safely', () => {
    expect(semanticTypeMatchesQuery(null, 'htun')).toBe(false);
    expect(semanticTypeMatchesQuery('natural_henkilotunnus', '')).toBe(false);
  });
});

describe('semanticConfidenceTag — bands + no-recommendation', () => {
  it('High ≥ 0.85', () => {
    expect(semanticConfidenceTag({ type_id: 'iban', confidence: 0.9 })).toBe('High');
  });
  it('Medium 0.60–0.84', () => {
    expect(semanticConfidenceTag({ type_id: 'reference_code', confidence: 0.72 })).toBe('Medium');
  });
  it('Low 0.45–0.59', () => {
    expect(semanticConfidenceTag({ type_id: 'name', confidence: 0.5 })).toBe('Low');
  });
  it('no recommendation → null (unresolved / no type / null)', () => {
    expect(semanticConfidenceTag({ type_id: 'unresolved', confidence: 0 })).toBeNull();
    expect(semanticConfidenceTag(null)).toBeNull();
  });
});

describe('semanticTypeButtons — disposition → verbs', () => {
  it('unaccepted, real type → Accept + Replace', () => {
    expect(semanticTypeButtons({ type_id: 'reference_code' })).toEqual({ accept: true, replace: true, resolve: false });
  });
  it('unaccepted, low confidence → still Accept + Replace', () => {
    expect(semanticTypeButtons({ type_id: 'name', confidence: 0.5 })).toEqual({ accept: true, replace: true, resolve: false });
  });
  it('accepted → Replace only (never re-Accept)', () => {
    expect(semanticTypeButtons({ type_id: 'iban', accepted_at: '2026-08-20T00:00:00Z' })).toEqual({ accept: false, replace: true, resolve: false });
  });
  it('conflict (unaccepted + type_value_conflict) → Accept + Replace', () => {
    expect(semanticTypeButtons({ type_id: 'iban', type_value_conflict: true })).toEqual({ accept: true, replace: true, resolve: false });
  });
  it('unresolved → Resolve only', () => {
    expect(semanticTypeButtons({ type_id: 'unresolved' })).toEqual({ accept: false, replace: false, resolve: true });
  });
});

describe('semanticReasoningPlate', () => {
  it('recommendation: why-this + also-considered (plain, grouped)', () => {
    const p = semanticReasoningPlate({
      type_id: 'reference_code', confidence: 0.93,
      evidence: [{ kind: 'distribution', signal: '5 distinct value(s) — low-cardinality code/enumeration', weight: 'decisive' }],
      candidates: [{ type_id: 'reference_code', score: 0.93 }, { type_id: 'free_text', score: 0.4 }],
    });
    expect(p.unresolved).toBe(false);
    expect(p.whyThis).toContain('Only 5 distinct values — looks like a code list.');
    expect(p.alsoConsidered).toEqual(['free_text']);
  });

  it('does not list a legacy alias of the chosen type under "also considered"', () => {
    // An accepted record can carry a legacy candidate id ('identifier') that the
    // display layer aliases to the SAME label as the accepted type
    // ('surrogate_systemid') — it must not appear as a distinct "also considered".
    const p = semanticReasoningPlate({
      type_id: 'surrogate_systemid', accepted_at: '2026-08-20T00:00:00Z', confidence: 0.77,
      evidence: [{ kind: 'distribution', signal: 'high uniqueness (100.0%) + PK membership confirms identifier', weight: 'strong' }],
      candidates: [{ type_id: 'identifier', score: 0.77 }, { type_id: 'surrogate_hash', score: 0.47 }],
    });
    expect(p.alsoConsidered).toEqual(['surrogate_hash']);
  });

  it('governance evidence goes to "also backing this up"', () => {
    const p = semanticReasoningPlate({
      type_id: 'iban', confidence: 0.9,
      evidence: [{ kind: 'validator', signal: 'passed', weight: 'decisive' }, { kind: 'glossary', signal: 'linked', weight: 'moderate' }],
    });
    expect(p.whyThis.length).toBe(1);
    expect(p.alsoBacking.some((s) => /glossary link/i.test(s))).toBe(true);
  });

  it('a refuting validator surfaces honestly as a caveat', () => {
    const p = semanticReasoningPlate({
      type_id: 'natural_iban', confidence: 0.3,
      evidence: [
        { kind: 'name', signal: "token 'iban' matched", weight: 'strong' },
        { kind: 'validator', signal: 'mod97 passed on only 1.4% of 1000 DB values. Values refute this type.', weight: 'refutes' },
      ],
    });
    expect(p.whyThis.some((s) => /field name matches/i.test(s))).toBe(true);
    expect(p.caveat).toMatch(/check-digit test/i);
    expect(p.caveat).toMatch(/real IBAN/i);
    expect(p.caveat).toMatch(/1\.4%/);
    expect(p.caveat).not.toMatch(/format check fails/i);
    expect(p.caveatAdvice).toMatch(/placeholder/i);
  });

  it('reconciles a shape match with a failing checksum (no contradiction)', () => {
    const p = semanticReasoningPlate({
      type_id: 'natural_iban', confidence: 0.3,
      evidence: [
        { kind: 'pattern', signal: 'regex matched 100.0% of samples', weight: 'strong' },
        { kind: 'name', signal: "token 'iban' matched", weight: 'strong' },
        { kind: 'validator', signal: 'mod97 passed on only 1.4% of 1000 DB values. Values refute this type.', weight: 'refutes' },
      ],
    });
    // positive shape signal reads as appearance, not a "format check"
    expect(p.whyThis.some((s) => /shape/i.test(s) && /100\.0%/.test(s))).toBe(true);
    // caveat names the real check and does not contradict the shape line
    expect(p.caveat).toMatch(/check-digit test/i);
    expect(p.caveat).toMatch(/1\.4%/);
    expect(p.caveat).not.toMatch(/format check fails/i);
  });

  it('adds a plain "what it is" interpretation and drops the weak data-type line', () => {
    const p = semanticReasoningPlate({
      type_id: 'surrogate_systemid', domain_role: 'key', confidence: 0.77,
      evidence: [
        { kind: 'distribution', signal: 'high uniqueness (100.0%) + PK membership confirms identifier', weight: 'strong' },
        { kind: 'schema', signal: 'data type string is allowed for this type', weight: 'weak' },
        { kind: 'glossary', signal: 'confirmed glossary link: Account Identifier', weight: 'moderate' },
      ],
    });
    expect(p.whyThis.some((s) => /system-generated id/i.test(s))).toBe(true);
    expect(p.whyThis.some((s) => /primary key/i.test(s))).toBe(true);
    expect(p.whyThis.some((s) => /data type/i.test(s))).toBe(false);
    expect(p.alsoBacking.some((s) => /Account Identifier/.test(s))).toBe(true);
  });

  it('renders the shape length/character consistency signal in plain words', () => {
    const p = semanticReasoningPlate({
      type_id: 'surrogate_systemid', domain_role: 'key', confidence: 0.77,
      evidence: [
        { kind: 'distribution', signal: 'high uniqueness (100.0%) + PK membership confirms identifier', weight: 'strong' },
        { kind: 'shape', signal: 'consistent length and character pattern (100% share one shape)', weight: 'weak' },
      ],
    });
    expect(p.whyThis.some((s) => /consistent length and character pattern \(100% share one shape\)\./.test(s))).toBe(true);
  });

  it('renders the fixed-length (hex hash) shape signal in plain words', () => {
    const p = semanticReasoningPlate({
      type_id: 'surrogate_systemid', domain_role: 'key', confidence: 0.77,
      evidence: [
        { kind: 'distribution', signal: 'high uniqueness (100.0%) + PK membership confirms identifier', weight: 'strong' },
        { kind: 'shape', signal: 'fixed value length (~16 characters across all values)', weight: 'weak' },
      ],
    });
    expect(p.whyThis.some((s) => /same length \(~16 characters\)/.test(s))).toBe(true);
    // Must not overclaim a shared character pattern for a varying-mask hash id.
    expect(p.whyThis.some((s) => /character pattern/i.test(s))).toBe(false);
  });

  it('conflict flag surfaces as a caveat', () => {
    const p = semanticReasoningPlate({ type_id: 'iban', confidence: 0.8, type_value_conflict: true, evidence: [] });
    expect(p.caveat).toMatch(/match this type/i);
  });

  it('unresolved no_signal', () => {
    const p = semanticReasoningPlate({ type_id: 'unresolved', resolution_reason: 'no_signal' });
    expect(p.unresolved).toBe(true);
    expect(p.whyNotFound).toMatch(/Nothing in the name/i);
  });

  it('unresolved below_floor', () => {
    const p = semanticReasoningPlate({ type_id: 'unresolved', resolution_reason: 'below_floor' });
    expect(p.whyNotFound).toMatch(/too weak to recommend/i);
  });

  it('unresolved corroboration_without_initiation names the near-misses', () => {
    const p = semanticReasoningPlate({
      type_id: 'unresolved', resolution_reason: 'corroboration_without_initiation',
      nearest_candidates: [{ type_id: 'monetary_amount', blocked_by: "the values aren't numeric", evidence: [] }],
    });
    expect(p.whyNotFound).toMatch(/none strong enough/i);
    expect(p.nearMisses).toEqual([{ type_id: 'monetary_amount', reason: "the values aren't numeric" }]);
  });
});

describe('SD-R3b copy — no tier vocabulary, no decimal-fraction confidences', () => {
  const record = {
    type_id: 'unresolved', resolution_reason: 'below_floor',
    nearest_candidates: [{ type_id: 'monetary_amount', blocked_by: 'the values are not numeric', evidence: [] }],
  };
  const plate = semanticReasoningPlate(record);
  const strings: string[] = [
    ...Object.values(plate).flatMap((v) =>
      typeof v === 'string'
        ? [v]
        : Array.isArray(v)
          ? v.map((x) => (typeof x === 'string' ? x : `${x.type_id} ${x.reason}`))
          : []),
    'High confidence', 'Medium confidence', 'Low confidence',
  ];
  it('no tier codes / Validated / Structural / "nudge"', () => {
    for (const s of strings) {
      expect(s).not.toMatch(/\bT[0-3]\b/);
      expect(s).not.toMatch(/Validated|Structural/);
      expect(s).not.toMatch(/nudge/i);
    }
  });
  it('no decimal-fraction confidences (e.g. .90 / +.02)', () => {
    for (const s of strings) expect(s).not.toMatch(/(^|\D)\.\d/);
  });
});

// ── findSemTypeRecordForColumn — column matching with empty-string fallback ──

describe('findSemTypeRecordForColumn', () => {
  it('matches on the record column when present', () => {
    const cols = [
      { key: 'ALM Bank|raw_almp|sourcesystem|name', column: 'name', type_id: 'name' },
      { key: 'ALM Bank|raw_almp|sourcesystem|id', column: 'id', type_id: 'surrogate_systemid', accepted_at: '2026-08-20T00:00:00Z' },
    ];
    const rec = findSemTypeRecordForColumn(cols, 'id');
    expect(rec?.type_id).toBe('surrogate_systemid');
    expect(rec?.accepted_at).toBe('2026-08-20T00:00:00Z');
  });

  it('falls back to the key when column is an EMPTY string (the bug this fixes)', () => {
    const cols = [
      { key: 'ALM Bank|raw_almp|sourcesystem|id', column: '', type_id: 'surrogate_systemid', accepted_at: '2026-08-20T00:00:00Z' },
    ];
    const rec = findSemTypeRecordForColumn(cols, 'id');
    // `??` would have returned '' here and failed the match — `||` recovers via the key.
    expect(rec?.type_id).toBe('surrogate_systemid');
    expect(rec?.accepted_at).toBe('2026-08-20T00:00:00Z');
  });

  it('falls back to the key when column is missing entirely', () => {
    const cols = [{ key: 'ALM Bank|raw_almp|sourcesystem|id', type_id: 'surrogate_systemid', accepted_at: '2026-08-20T00:00:00Z' }];
    expect(findSemTypeRecordForColumn(cols, 'id')?.accepted_at).toBe('2026-08-20T00:00:00Z');
  });

  it('returns null when no column matches', () => {
    const cols = [{ key: 'ALM Bank|raw_almp|sourcesystem|other', column: 'other', type_id: 'name' }];
    expect(findSemTypeRecordForColumn(cols, 'id')).toBeNull();
  });

  it('returns null for an empty column list', () => {
    expect(findSemTypeRecordForColumn([], 'id')).toBeNull();
  });
});

