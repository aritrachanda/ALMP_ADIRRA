/**
 * Pure display helpers for the Semantic Type card (Card 1) in AssetWorkspace.
 *
 * Extracted so the presentation logic is unit-testable without mounting the
 * full page. Behaviour is identical to the inline logic it replaces.
 */

export interface SemEvidenceItem {
  kind?: string | null;
  signal?: string | null;
  weight?: string | null;
}

export interface SemNearestCandidate {
  type_id?: string | null;
  blocked_by?: string | null;
  evidence?: SemEvidenceItem[];
}

export interface SemTypeRecordLike {
  type_id?: string | null;
  resolution_reason?: string | null;
  nearest_candidates?: SemNearestCandidate[] | null;
  /** When this column's semantic type was accepted; null/absent = not yet accepted. */
  accepted_at?: string | null;
  tier?: number | null;
  source?: string | null;
  type_value_conflict?: boolean | null;
  evidence?: SemEvidenceItem[] | null;
  confidence?: number | null;
  candidates?: Array<{ type_id?: string | null; score?: number | null }> | null;
  domain_role?: string | null;
  scope?: string | null;
  pii?: boolean | null;
  pii_category?: string | null;
  [key: string]: unknown;
}

/**
 * Find a column's semantic-type record inside the table-level payload.
 *
 * Matches on the record's `column`, falling back to the last segment of the
 * pipe-delimited `key` when `column` is missing OR an empty string. The fallback
 * MUST use `||` (not `??`): some records come back with `column === ''`, which
 * `??` would not treat as absent — the bug this helper fixes.
 */
export function findSemTypeRecordForColumn(
  columns: Array<Record<string, unknown>>,
  column: string,
): SemTypeRecordLike | null {
  const rec = (columns ?? []).find((c) => {
    const keyCol = typeof c.key === 'string' ? c.key.split('|').pop() : undefined;
    const col = typeof c.column === 'string' && c.column ? c.column : keyCol;
    return col === column;
  });
  return (rec as SemTypeRecordLike) ?? null;
}

/**
 * Evidence kinds that describe what the *data* shows (rendered in the
 * "What the data shows" column). U1b adds `shape` — value-shape signals from
 * the widened resolver belong beside validator/distribution, not in the
 * meaning column.
 */
export const DATA_EV_KINDS = new Set([
  'validator',
  'distribution',
  'shape',
  'pattern',
  'storage',
  'schema',
]);

export function isDataEvidenceKind(kind: string | null | undefined): boolean {
  return DATA_EV_KINDS.has(kind || '');
}

// ── Display normalisation (user decision: show RAW ids everywhere) ───────────
// No plain-label layer. The only mappings applied are:
//  1. a legacy alias, so a pre-rename stored id surfaces as its CURRENT raw id
//     (e.g. legacy 'identifier' → 'surrogate_systemid', not the stale word); and
//  2. the key tag, which renders as 'Primary Key' (the single key role detected
//     today = primary-key membership).
// Unknown ids pass through unchanged. The raw id keeps the natural_/surrogate_
// structure visible, which is the point.

const LEGACY_TYPE_ALIAS: Record<string, string> = {
  identifier: 'surrogate_systemid',
  surrogate_identifier: 'surrogate_systemid',
  natural_identifier: 'natural_key',
  iban: 'natural_iban',
  bic: 'natural_bic',
  lei: 'natural_lei',
  isin: 'natural_isin',
  henkilotunnus: 'natural_henkilotunnus',
  y_tunnus: 'natural_yritystunnus',
  // 2026-08-20 rename: old ids kept so already-persisted records normalise forward.
  natural_htun: 'natural_henkilotunnus',
  natural_ytun: 'natural_yritystunnus',
};

const LEGACY_DOMAIN_ALIAS: Record<string, string> = {
  identifier: 'surrogate_id',
};

/** type_id → current raw id (legacy ids normalised to their current id). */
export function semanticTypeLabel(typeId: string | null | undefined): string {
  if (!typeId || typeId === 'unresolved') return 'unresolved';
  return LEGACY_TYPE_ALIAS[typeId] ?? typeId;
}

// Short/legacy search forms for the two Finnish national-ID types, mirrored from
// their own governed name_tokens in governance/semantic_types.yaml — lets a user
// search "htun", "h-tunnus", "ytunnus" etc. and still find natural_henkilotunnus/
// natural_yritystunnus columns after the 2026-08-20 id rename. Keep in sync with
// that vocabulary file's detectors.name_tokens if either is ever revised.
const TYPE_SEARCH_ALIASES: Record<string, string[]> = {
  natural_henkilotunnus: ['htun', 'htunnus', 'hetu', 'henkilotunnus', 'personal_id', 'person_id', 'ssn_fi', 'pid_fi'],
  natural_yritystunnus: ['ytun', 'ytunnus', 'y_tunnus', 'business_id', 'yritystunnus', 'company_id_fi'],
};

function normaliseSearchToken(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]/g, '');
}

/**
 * Does a free-text search query match this semantic type_id — including its
 * short/legacy forms (e.g. "htun", "y-tunnus")? Used by column search boxes so
 * renaming a governed type_id doesn't break a user's muscle-memory search term.
 */
export function semanticTypeMatchesQuery(typeId: string | null | undefined, query: string): boolean {
  if (!typeId || !query) return false;
  const q = normaliseSearchToken(query);
  if (!q) return false;
  if (normaliseSearchToken(typeId).includes(q)) return true;
  return (TYPE_SEARCH_ALIASES[typeId] ?? []).some((alias) => normaliseSearchToken(alias).includes(q));
}

/** domain_role → raw id; 'key' renders as 'Primary Key'; legacy id normalised. */
export function semanticDomainLabel(role: string | null | undefined): string {
  if (!role || role === 'unresolved') return 'unresolved';
  if (role === 'key') return 'Primary Key';
  return LEGACY_DOMAIN_ALIAS[role] ?? role;
}

/** scope → raw scope value ('' when no scope set). */
export function semanticScopeLabel(scope: string | null | undefined): string {
  return scope || '';
}

/** Evidence kind → steward-readable label. */
export function semanticEvidenceKindLabel(kind: string | null | undefined): string {
  switch (kind) {
    case 'validator': return 'Values checked';
    case 'distribution': return 'Value spread';
    case 'shape': return 'Value shape';
    case 'pattern': return 'Format';
    case 'storage': return 'Storage';
    case 'schema': return 'Data type';
    case 'name': return 'Field name';
    case 'glossary': return 'Glossary';
    case 'prior': return 'Similar field';
    case 'entity': return 'Entity';
    case 'structural': return 'Key / FK';
    case 'ai': return 'AI scan';
    default: return kind ? kind.replace(/_/g, ' ') : 'Signal';
  }
}

export interface StructuredUnresolvedInfo {
  unresolved: boolean;
  reason: string | undefined;
  /** Display label for the (unresolved) identity axis. */
  label: string;
  /** True when signals were present but no channel could initiate a candidate. */
  needsDecision: boolean;
  candidate: SemNearestCandidate | undefined;
  candidateEvidence: SemEvidenceItem[];
}

/**
 * U1b structured-unresolved split. The widened resolver tags an unresolved
 * record with a `resolution_reason` and (for near-misses) `nearest_candidates`.
 *
 * - `no_signal` → "No signal" (genuinely nothing to go on).
 * - `corroboration_without_initiation` / `below_floor` →
 *   "Signals present — needs a decision", with the top near-miss candidate's
 *   evidence surfaced.
 * - `conflict` (or unset) → falls back to the original single "Unresolved"
 *   label; existing conflict rendering is left untouched.
 */
export function structuredUnresolvedInfo(
  record: SemTypeRecordLike | null | undefined,
): StructuredUnresolvedInfo {
  const unresolved = !record || !record.type_id || record.type_id === 'unresolved';
  const reason = record?.resolution_reason ?? undefined;
  const near = (record?.nearest_candidates || []) as SemNearestCandidate[];
  const top = near[0];

  let label = 'Unresolved';
  let needsDecision = false;
  if (unresolved) {
    if (reason === 'no_signal') {
      label = 'No signal';
    } else if (reason === 'corroboration_without_initiation' || reason === 'below_floor') {
      label = 'Signals present — needs a decision';
      needsDecision = true;
    }
  }

  return {
    unresolved,
    reason: reason ?? undefined,
    label,
    needsDecision,
    candidate: top,
    candidateEvidence: needsDecision && top ? (top.evidence || []) : [],
  };
}

/**
 * SD-R3b — Semantic Type as a subdued analyst annotation (Definition tab).
 *
 * Confidence tag (no number). Reuses the existing routing thresholds — High is
 * the same 0.85 boundary the review queue used, Medium the 0.60 proposed floor,
 * Low the 0.45 suggested floor. Below 0.45 there is no recommendation, so the
 * card falls to the `unresolved` presentation (tag = null). `unresolved` never
 * carries a tag. No scoring change — this only reads `confidence`.
 */
export function semanticConfidenceTag(
  record: SemTypeRecordLike | null | undefined,
): 'High' | 'Medium' | 'Low' | null {
  const r = record;
  if (!r || !r.type_id || r.type_id === 'unresolved') return null;
  const c = Number(r.confidence ?? 0);
  if (c >= 0.85) return 'High';
  if (c >= 0.60) return 'Medium';
  if (c >= 0.45) return 'Low';
  return null;
}

export interface SemTypeButtons {
  accept: boolean;
  replace: boolean;
  resolve: boolean;
}

/**
 * Disposition → buttons (SD-R3b). Accept + Replace when a recommendation exists and is
 * not yet accepted; Replace only once accepted (never a second Accept); Resolve
 * for `unresolved`. A `type_value_conflict` is still an unaccepted record, so it
 * keeps Accept + Replace (the card adds a warning). No more `rejected` disposition
 * (2026-08-20, tech-debt #13/#36/#45) — this only chooses which verbs to show.
 */
export function semanticTypeButtons(
  record: SemTypeRecordLike | null | undefined,
): SemTypeButtons {
  const r = record;
  const unresolvedLike = !r || !r.type_id || r.type_id === 'unresolved';
  if (unresolvedLike) return { accept: false, replace: false, resolve: true };
  if (r!.accepted_at) return { accept: false, replace: true, resolve: false };
  return { accept: true, replace: true, resolve: false };
}

export interface ReasoningPlate {
  unresolved: boolean;
  /** For the unresolved case: why nothing was found, plain language. */
  whyNotFound?: string;
  /** Near-miss candidates (unresolved) — what almost resolved and why not. */
  nearMisses: Array<{ type_id: string; reason: string }>;
  /** Primary plain reasons the type was picked (values, name, key, data type). */
  whyThis: string[];
  /** Governance corroboration (glossary / definition / similar field). */
  alsoBacking: string[];
  /** Refuting evidence / conflict, plainly — why it may only be low confidence. */
  caveat?: string;
  /** Actionable advice paired with the caveat (what to check / do). */
  caveatAdvice?: string;
  /** Other candidate types considered — labelled in the view (no scores). */
  alsoConsidered: string[];
}

function plainBlocked(blockedBy: string | null | undefined): string {
  const s = String(blockedBy || '').trim();
  return s || 'ruled out';
}

// Evidence kinds that go in the "Why this" block, in priority order (strongest,
// value-based first). Governance kinds (glossary/definition/prior) go to
// "Also backing this up"; anything else is dropped from the plate.
const WHY_ORDER = ['validator', 'pattern', 'distribution', 'shape', 'structural', 'name', 'entity', 'storage'];
const BACKING_KINDS = new Set(['glossary', 'definition', 'prior']);

function whyRank(kind: string | null | undefined): number {
  const i = WHY_ORDER.indexOf(kind || '');
  return i === -1 ? WHY_ORDER.length : i;
}

/**
 * A plain one-line "what this type is" interpretation, added to "Why this" so the
 * rationale reads like an explanation, not just a list of signals (D1b). Only for
 * the types where the plain-English meaning adds something the evidence doesn't.
 */
function typeInterpretation(r: SemTypeRecordLike): string | undefined {
  const tid = String(r.type_id || '');
  if (/^surrogate_/.test(tid)) return 'No real-world format (like IBAN or LEI) — so it reads as a system-generated id.';
  if (tid === 'natural_key') return 'A real-world / business key — it carries meaning outside the system.';
  if (tid === 'reference_code') return 'A value drawn from a small, fixed code list.';
  return undefined;
}

/**
 * Plain-English meaning of a resolver validator. A positive shape/pattern match
 * only proves the values *look* right; the validator is the deeper check that
 * certifies a *real* value. Naming that check (check digits / official list /
 * format rules) is what stops "looks like it" and "fails the check" reading as a
 * contradiction. `noun` = what to call the check; `confirm` = how a genuine
 * value is certified.
 */
function validatorPlain(name: string): { noun: string; confirm: string } {
  switch (name) {
    case 'mod97':
    case 'lei_checksum':
    case 'isin_checksum':
    case 'hetu_checksum':
    case 'y_tunnus_checksum':
      return { noun: 'check-digit test', confirm: 'a genuine value is confirmed by its built-in check digits, and these don’t add up' };
    case 'iso4217':
      return { noun: 'official-code check', confirm: 'a genuine value must be a currency code on the official ISO 4217 list' };
    case 'iso3166':
      return { noun: 'official-code check', confirm: 'a genuine value must be a country code on the official ISO 3166 list' };
    case 'bic_structure':
      return { noun: 'structure check', confirm: 'a genuine BIC must follow the strict bank / country / location structure' };
    case 'email_format':
      return { noun: 'format check', confirm: 'a genuine value must follow the full email format rules' };
    case 'phone_format':
      return { noun: 'format check', confirm: 'a genuine value must follow the full phone-number format rules' };
    case 'uuid_format':
      return { noun: 'format check', confirm: 'a genuine value must follow the UUID format exactly' };
    case 'date_range':
    case 'timestamp_parse':
      return { noun: 'date check', confirm: 'a genuine value must be a real, parseable date' };
    default:
      return { noun: 'validity check', confirm: 'a genuine value must pass its built-in validity check' };
  }
}

/**
 * A component-level breakdown of the format a validator checks, so the reviewer
 * sees exactly which format was validated and what its parts are (e.g. a BIC).
 * Returned as a clause that reads naturally after "It checks …". Empty string
 * for validators without a fixed multi-part structure.
 */
function validatorFormatSpec(name: string): string {
  switch (name) {
    case 'bic_structure':
      return 'the BIC/SWIFT structure (ISO 9362): 8 or 11 characters — a 4-letter bank code, a 2-letter country code (ISO 3166), a 2-character location code, and an optional 3-character branch code (or XXX for the main office)';
    case 'iso4217':
      return 'the value against the official ISO 4217 currency list (a 3-letter code such as EUR or USD)';
    case 'iso3166':
      return 'the value against the official ISO 3166 country list (a 2-letter code such as FI or US)';
    case 'mod97':
      return 'the IBAN structure and its ISO 7064 mod-97 check digits: a 2-letter country code (ISO 3166), 2 check digits, then the country-specific account number (BBAN)';
    case 'lei_checksum':
      return 'the LEI structure (ISO 17442): 20 alphanumeric characters — 18 identifier characters plus 2 ISO 7064 check digits';
    case 'isin_checksum':
      return 'the ISIN structure (ISO 6166): 12 characters — a 2-letter country prefix, a 9-character national number, and a final Luhn check digit';
    case 'hetu_checksum':
      return 'the Finnish personal identity code (HETU): a date of birth, a century marker, a 3-digit individual number, and a check character';
    case 'y_tunnus_checksum':
      return 'the Finnish Business ID (Y-tunnus): 7 digits followed by a check digit (NNNNNNN-K)';
    case 'uuid_format':
      return 'the UUID structure: 32 hexadecimal digits in 8-4-4-4-12 groups';
    case 'email_format':
      return 'the email structure: a local part, an @ symbol, and a domain ending in a valid top-level domain';
    case 'phone_format':
      return 'the phone-number structure: an optional country prefix followed by a valid run of digits';
    case 'date_range':
    case 'timestamp_parse':
      return 'that each value is a real, parseable date';
    default:
      return '';
  }
}

/** A friendly bare name for a type id (drops natural_/surrogate_, uppercases known acronyms). */
function bareTypeName(typeId: string | null | undefined): string {
  const raw = String(typeId || '').replace(/^(natural_|surrogate_|reference_)/, '');
  const ACR: Record<string, string> = {
    iban: 'IBAN', bic: 'BIC', lei: 'LEI', isin: 'ISIN', uuid: 'UUID',
    htun: 'national ID', ytun: 'business ID', ssn: 'SSN',
  };
  return ACR[raw] || raw.replace(/_/g, ' ') || 'value of this type';
}

/**
 * Turn one evidence item into a plain, reviewer-friendly sentence — plain
 * language but keeping the telling figures (D1b, user-approved). Falls back to
 * the raw signal for any shape we don't specifically reword.
 */
export function plainEvidence(ev: SemEvidenceItem): string {
  const kind = ev.kind || '';
  const sig = String(ev.signal || '');
  if (ev.weight === 'refutes') {
    const m = sig.match(/passed on only ([\d.]+)%/);
    if (m) return `The built-in validity check fails — it passes on only ${m[1]}% of values.`;
    const rm = sig.match(/regex matched only ([\d.]+)%/);
    if (rm) return `The values only partly match the expected shape (${rm[1]}%).`;
    return sig;
  }
  switch (kind) {
    case 'validator': {
      const vName = sig.match(/^(\w+)\s+passed/)?.[1] ?? '';
      const spec = validatorFormatSpec(vName);
      const m = sig.match(/passed on ([\d.]+)%/);
      const base = m
        ? `The values pass this type's built-in validity check (${m[1]}%).`
        : "The values pass this type's built-in validity check.";
      return spec ? `${base} It checks ${spec}.` : base;
    }
    case 'pattern': {
      const m = sig.match(/matched ([\d.]+)%/);
      return m ? `The values match the expected shape (${m[1]}%).` : 'The values match the expected shape.';
    }
    case 'distribution': {
      const dm = sig.match(/(\d+)\s+distinct/);
      if (dm && /(code|enumeration|cardinality)/i.test(sig)) return `Only ${dm[1]} distinct values — looks like a code list.`;
      const um = sig.match(/([\d.]+)%/);
      if (/(uniqueness|unique)/i.test(sig) && /(pk|primary key)/i.test(sig)) {
        return `Every value is unique${um ? ` (${um[1]}%)` : ''} and it's the table's primary key.`;
      }
      if (/(uniqueness|unique)/i.test(sig)) return `The values are highly unique${um ? ` (${um[1]}%)` : ''}.`;
      return sig;
    }
    case 'shape':
      if (/consistent length and character pattern/i.test(sig)) {
        const cm = sig.match(/\(([\d.]+)% share one shape\)/i);
        return cm
          ? `The values are all a consistent length and character pattern (${cm[1]}% share one shape).`
          : 'The values are all a consistent length and character pattern.';
      }
      if (/fixed value length/i.test(sig)) {
        const lm = sig.match(/~(\d+) characters/i);
        return lm
          ? `The values are all the same length (~${lm[1]} characters) — a fixed-width value, typical of an id.`
          : 'The values are all the same length — a fixed-width value, typical of an id.';
      }
      return sig
        .replace(/system-generated identifier shape/i, 'looks like a system-generated id')
        .replace(/mask coverage/i, 'consistent structure');
    case 'name': {
      const m = sig.match(/token '([^']+)' matched/);
      return m ? `The field name matches ("${m[1]}").` : 'The field name points to this type.';
    }
    case 'schema':
      return 'The data type fits this type.';
    case 'structural':
      if (/primary key/i.test(sig)) return "It's part of the table's primary key.";
      if (/(relation|foreign)/i.test(sig)) return "It's used in a table relationship (foreign key).";
      return sig;
    case 'glossary': {
      const m = sig.match(/glossary link:\s*(.+)$/i);
      return m ? `Backed by a confirmed glossary link: "${m[1].trim()}".` : 'Backed by a confirmed glossary link.';
    }
    case 'definition': {
      const m = sig.match(/approved definition:\s*(.+)$/i);
      return m ? `Backed by an approved definition ("${m[1].trim()}").` : 'Backed by an approved definition.';
    }
    case 'prior':
      return 'A similar, already-confirmed field supports this.';
    case 'entity':
      return sig.replace(/entity context supports this type/i, 'the entity context fits this type');
    default:
      return sig;
  }
}

/**
 * Build the "Worth checking" caveat from refuting evidence. When a validator
 * refutes (e.g. IBAN mod97 checksum), reconcile it with the shape match so the
 * card never reads as a contradiction: the values LOOK right (shape/pattern),
 * but the deeper validity check that certifies a *real* one fails. Names the
 * actual check so the reviewer learns why a shape-match isn't proof.
 */
function buildRefuteCaveat(
  refutingEv: SemEvidenceItem[],
  typeId: string | null | undefined,
): { caveat: string; advice: string } {
  const vEv = refutingEv.find((e) => (e.kind || '') === 'validator');
  const sig = String(vEv?.signal || '');
  const rate = sig.match(/only ([\d.]+)%/);
  const vName = sig.match(/^(\w+)\s+passed/);
  if (vEv && rate && vName) {
    const vp = validatorPlain(vName[1]);
    const spec = validatorFormatSpec(vName[1]);
    const name = bareTypeName(typeId);
    const art = /^[aeiou]/i.test(name) ? 'an' : 'a';
    const specClause = spec ? ` It checks ${spec}.` : '';
    return {
      caveat: `The shape matches, but the ${vp.noun} that confirms a real ${name} passes on only ${rate[1]}% of values — ${vp.confirm}.${specClause}`,
      advice: `That usually means placeholder or test data, or that it isn't really ${art} ${name}. Worth a look before you accept.`,
    };
  }
  return {
    caveat: refutingEv.map(plainEvidence).filter(Boolean).join(' '),
    advice: 'Likely placeholder or test data — or not really this type. Worth a look before you accept.',
  };
}

/**
 * The reasoning plate — answers "why this?" in plain, grouped language (D1b):
 * a leading "Why this" (value/name/key evidence), "Also backing this up"
 * (governance), and a "caveat" that surfaces refuting evidence honestly. Built
 * only from data already on the record. No tier codes, no formulas.
 */
export function semanticReasoningPlate(
  record: SemTypeRecordLike | null | undefined,
): ReasoningPlate {
  const r = record;
  if (!r) {
    return { unresolved: true, whyNotFound: 'No signal.', nearMisses: [], whyThis: [], alsoBacking: [], alsoConsidered: [] };
  }

  const ev = (r.evidence || []) as SemEvidenceItem[];
  const near = (r.nearest_candidates || []) as SemNearestCandidate[];
  const nearMisses = near
    .filter((c) => c && c.type_id)
    .map((c) => ({ type_id: String(c.type_id), reason: plainBlocked(c.blocked_by) }));

  const unresolvedLike = !r.type_id || r.type_id === 'unresolved';
  if (unresolvedLike) {
    const reason = r.resolution_reason;
    let whyNotFound = 'No type could be identified from the name, the data type, or the values.';
    if (reason === 'no_signal') whyNotFound = 'Nothing in the name, the data type, or the values pointed to a known type.';
    else if (reason === 'below_floor') whyNotFound = 'The closest match was too weak to recommend — the evidence didn’t support it.';
    else if (reason === 'corroboration_without_initiation') whyNotFound = 'Some signals were present, but none strong enough to start a recommendation.';
    return { unresolved: true, whyNotFound, nearMisses, whyThis: [], alsoBacking: [], alsoConsidered: [] };
  }

  const whyThis = ev
    .filter((e) => e.weight !== 'refutes' && whyRank(e.kind) < WHY_ORDER.length)
    .slice()
    .sort((a, b) => whyRank(a.kind) - whyRank(b.kind))
    .map(plainEvidence)
    .filter(Boolean);
  const interp = typeInterpretation(r);
  if (interp) whyThis.push(interp);

  const alsoBacking = ev
    .filter((e) => BACKING_KINDS.has(e.kind || '') && e.weight !== 'refutes')
    .map(plainEvidence)
    .filter(Boolean);

  const refutingEv = ev.filter((e) => e.weight === 'refutes');
  let caveat: string | undefined;
  let caveatAdvice: string | undefined;
  if (refutingEv.length) {
    const built = buildRefuteCaveat(refutingEv, r.type_id);
    caveat = built.caveat;
    caveatAdvice = built.advice;
  } else if (r.type_value_conflict) {
    caveat = 'The values don’t fully match this type.';
    caveatAdvice = 'Worth checking before you accept.';
  }

  const alsoConsidered = ((r.candidates || []) as Array<{ type_id?: string | null }>)
    .map((c) => (c && c.type_id) || '')
    .filter((t): t is string => !!t && t !== 'unresolved')
    // Compare/dedupe by the DISPLAY-normalised id so a legacy alias of the chosen
    // type (e.g. stored candidate 'identifier' → 'surrogate_systemid') is not shown
    // as a distinct "also considered" — it would read as the accepted type twice.
    .filter((t) => semanticTypeLabel(t) !== semanticTypeLabel(r.type_id))
    .filter((t, i, arr) => arr.findIndex((u) => semanticTypeLabel(u) === semanticTypeLabel(t)) === i);

  return { unresolved: false, nearMisses, whyThis, alsoBacking, caveat, caveatAdvice, alsoConsidered };
}
