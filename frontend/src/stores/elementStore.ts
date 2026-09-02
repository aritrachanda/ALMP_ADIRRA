import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { ElementDetail, TableEntry, LifecycleState, DatasetOverview, ReferenceData, SourceInfo, DataStory } from 'src/api/element';
import { getDataStory, draftDataStory, saveDataStory as apiSaveDataStory, bulkDraftDataStories as apiBulkDataStories } from 'src/api/element';
import type { InsightsResult } from 'src/api/insights';
import * as api from 'src/api/element';
import { getInsights } from 'src/api/insights';
import { updateBusinessName as apiBusiness, draftBusinessName as apiDraftBusiness, bulkDraftDescriptions as apiBulkDesc, bulkDraftBusinessNames as apiBulkBiz } from 'src/api/element';
import { refreshTableProfile } from 'src/api/discovery';
import { govDisplayBucket } from 'src/utils/statusDisplay';
import type { AiError } from 'src/composables/useAiError';

// Dynamic in-page breadcrumb trail (e.g. source → dataset → column inside the
// Asset Workspace) — populated by the page that owns the drill-down state,
// read by TopMenu.vue so the header bar always reflects exactly where the
// user is, with every segment individually clickable.
export interface WorkspaceBreadcrumbSegment { label: string; onClick: () => void }

// Fired only when a SINGLE, currently-open element's own DQ score changes as a direct
// result of the CURRENT user's own action on that one element (refreshElementDq() is never
// called from a bulk/multi-column loop) — deliberately not raised for bulk rebuild/re-score
// operations, which can touch hundreds of columns at once.
export interface DqScoreChangeEvent {
  column: string;
  oldScore: number;
  newScore: number;
  direction: 'up' | 'down';
  nonce: number;
  /** Plain-English label for the governance/data action that triggered this re-score
   * (e.g. "Draft saved", "Semantic Type accepted") — undefined for a plain manual refresh
   * with no specific triggering action. */
  reason?: string;
}

export const useElementStore = defineStore('element', () => {
  const sources = ref<string[]>([]);
  const tables = ref<TableEntry[]>([]);
  const element = ref<ElementDetail | null>(null);
  const datasetOverview = ref<DatasetOverview | null>(null);
  const referenceData = ref<ReferenceData | null>(null);
  const sourceInfo = ref<SourceInfo | null>(null);
  const loading = ref(false);
  const loadingElement = ref(false);
  const loadingOverview = ref(false);
  const loadingRefData = ref(false);
  const loadingSourceInfo = ref(false);
  // Real (non-fabricated) staged-loading progress for the 3 SSE-backed loaders below —
  // `completed` = number of real backend stages finished so far; `detail` = live
  // sub-progress text for the stage currently in flight (e.g. "(23/80 columns)").
  const sourceInfoProgress = ref({ completed: 0, detail: '', fraction: 0 });
  const overviewProgress = ref({ completed: 0, detail: '', fraction: 0, total: 0 });
  const elementProgress = ref({ completed: 0, detail: '', fraction: 0 });
  const dqScoreChange = ref<DqScoreChangeEvent | null>(null);
  let _sourceInfoAbort: AbortController | null = null;
  let _overviewAbort: AbortController | null = null;
  let _elementAbort: AbortController | null = null;
  const error = ref<string | null>(null);

  const dataStory = ref<DataStory | null>(null);
  const loadingDataStory = ref(false);

  const insights = ref<InsightsResult | null>(null);
  const insightsLoading = ref(false);
  const insightsError = ref<string | null>(null);

  const breadcrumbTrail = ref<WorkspaceBreadcrumbSegment[]>([]);
  function setBreadcrumbTrail(segments: WorkspaceBreadcrumbSegment[]) { breadcrumbTrail.value = segments; }
  function clearBreadcrumbTrail() { breadcrumbTrail.value = []; }

  let lastLoadedOverviewKey = '';  // Track loaded overview to prevent unnecessary reloads
  const elementCache = new Map<string, ElementDetail>(); // Multi-column in-session cache

  async function loadSources() {
    loading.value = true;
    error.value = null;
    try {
      const res = await fetch('/api/catalogs/sources');
      const data = await res.json();
      sources.value = (data.catalogs as { name: string }[]).map((c) => c.name);
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to load sources';
    } finally {
      loading.value = false;
    }
  }

  async function loadTables(source: string) {
    loading.value = true;
    error.value = null;
    tables.value = [];
    try {
      tables.value = await api.getSourceTables(source);
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to load tables';
    } finally {
      loading.value = false;
    }
  }

  async function loadElement(source: string, table: string, column: string, schema?: string, force = false) {
    const elementKey = `${source}|${schema || ''}|${table}|${column}`;

    // Instant return from multi-column in-session cache (skip if forced)
    const cached = elementCache.get(elementKey);
    if (cached && !force) {
      element.value = cached;
      return;
    }

    if (_elementAbort) _elementAbort.abort();
    _elementAbort = new AbortController();
    loadingElement.value = true;
    elementProgress.value = { completed: 0, detail: '', fraction: 0 };
    error.value = null;
    try {
      const data = await api.streamElement(
        source, table, column, schema,
        (completed) => { elementProgress.value = { ...elementProgress.value, completed, fraction: 0 }; },
        (detail, fraction) => { elementProgress.value = { ...elementProgress.value, detail, fraction: fraction ?? 0 }; },
        _elementAbort.signal,
      );
      element.value = data;
      elementCache.set(elementKey, data);
    } catch (e: unknown) {
      if (!(e instanceof DOMException && e.name === 'AbortError')) {
        error.value = e instanceof Error ? e.message : 'Failed to load element';
      }
    } finally {
      loadingElement.value = false;
    }
  }

  async function loadDatasetOverview(source: string, table: string, schema?: string, force = false) {
    const overviewKey = `${source}|${schema || ''}|${table}`;

    // Skip reload if already loaded (prevents refresh on navigation), unless forced
    if (!force && lastLoadedOverviewKey === overviewKey && datasetOverview.value) {
      return;
    }

    // Different dataset than what's currently shown — drop the stale data immediately so the
    // left rail's loading state shows instead of the PREVIOUS dataset's fields during the switch.
    if (lastLoadedOverviewKey !== overviewKey) {
      datasetOverview.value = null;
    }

    if (_overviewAbort) _overviewAbort.abort();
    _overviewAbort = new AbortController();
    loadingOverview.value = true;
    overviewProgress.value = { completed: 0, detail: '', fraction: 0, total: 0 };
    error.value = null;
    try {
      datasetOverview.value = await api.streamTableOverview(
        source, table, schema,
        (completed) => { overviewProgress.value = { ...overviewProgress.value, completed, fraction: 0 }; },
        (detail, fraction, total) => { overviewProgress.value = { ...overviewProgress.value, detail, fraction: fraction ?? 0, total: total ?? overviewProgress.value.total }; },
        _overviewAbort.signal,
      );
      lastLoadedOverviewKey = overviewKey;
    } catch (e: unknown) {
      if (!(e instanceof DOMException && e.name === 'AbortError')) {
        error.value = e instanceof Error ? e.message : 'Failed to load dataset overview';
      }
    } finally {
      loadingOverview.value = false;
    }
  }

  function patchOverviewState(column: string, newState: LifecycleState) {
    if (!datasetOverview.value) return;
    const oldState = datasetOverview.value.columns_summary.find(c => c.name === column)?.lifecycle_state;
    const updatedSummary = datasetOverview.value.columns_summary.map(c =>
      c.name === column ? { ...c, lifecycle_state: newState } : c
    );
    const counts: import('src/api/element').GovStateCounts = { empty: 0, draft: 0, in_review: 0, approved: 0, bounced: 0 };
    for (const c of updatedSummary) {
      const bucket = govDisplayBucket(c.lifecycle_state);
      counts[bucket] = (counts[bucket] ?? 0) + 1;
    }
    datasetOverview.value = {
      ...datasetOverview.value,
      columns_summary: updatedSummary,
      governance_state: counts,
    };
    // Keep sourceInfo governance counts in sync if it's loaded. Uses the
    // column's actual previous state (captured above, before the summary was
    // rewritten) rather than guessing — decrementing an arbitrary non-empty
    // bucket previously caused the source-level rollup to drift out of sync
    // with the real per-column states whenever columns from other lifecycle
    // states were also present.
    if (sourceInfo.value && oldState && oldState !== newState) {
      const oldBucket = govDisplayBucket(oldState);
      const newBucket = govDisplayBucket(newState);
      if (oldBucket !== newBucket) {
        const gov = { ...sourceInfo.value.governance_state };
        gov[oldBucket] = Math.max(0, (gov[oldBucket] ?? 0) - 1);
        gov[newBucket] = (gov[newBucket] ?? 0) + 1;
        sourceInfo.value = { ...sourceInfo.value, governance_state: gov };
      }
    }
  }

  async function setColumnsScope(
    columns: string[],
    scope: 'in_scope' | 'out_of_scope',
    scopeReason?: string,
    scopedBy?: string,
  ) {
    const overview = datasetOverview.value;
    if (!overview || columns.length === 0) return;
    const { source, table_name: table, schema } = overview;
    try {
      const result = await api.setAssessmentScope(source, table, columns, scope, {
        scopeReason, scopedBy, schema,
      });
      // The backend re-scores synchronously on a scope change (governance event),
      // so a forced overview reload refreshes every affected DQ badge correctly:
      // descoped columns become "Excluded from assessment", re-scoped ones show
      // their recomputed score.
      await loadDatasetOverview(source, table, schema, true);
      return result;
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to update assessment scope';
    }
  }

  async function setLifecycleState(state: LifecycleState) {
    if (!element.value) return;
    const { source, table, column, schema } = element.value;
    try {
      const result = await api.updateLifecycleState(source, table, column, state, schema);
      element.value = { ...element.value, lifecycle_state: result.lifecycle_state };
      elementCache.set(`${source}|${schema || ''}|${table}|${column}`, element.value);
      patchOverviewState(column, result.lifecycle_state);
      // Lifecycle affects the DQ score — re-score so the badge reflects it live.
      await refreshElementDq();
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to update state';
    }
  }

  // ── Phase 5b.1 canonical interpretation-set actions ─────────────────────
  // Each applies the returned canonical status + submission overlay, keeps the
  // dataset/source rollups in sync, and re-scores the DQ badge.
  async function _applyLifecycleResult(result: api.LifecycleActionResult, opts: { skipDqRefresh?: boolean; dqReason?: string } = {}) {
    if (!element.value) return;
    const { source, table, column, schema } = element.value;
    const newState = result.lifecycle_state as LifecycleState;
    element.value = {
      ...element.value, lifecycle_state: newState, submission: result.submission,
      ...(result.last_status ? { last_status: result.last_status } : {}),
    };
    elementCache.set(`${source}|${schema || ''}|${table}|${column}`, element.value);
    patchOverviewState(column, newState);
    if (!opts.skipDqRefresh) await refreshElementDq(opts.dqReason);
  }

  /** Holistic Save of the interpretation set (Definition + Business Name text → Saved). */
  async function saveInterpretation(opts: {
    description?: string | null; descriptionIsAi?: boolean;
    businessName?: string | null; businessNameIsAi?: boolean;
    actor?: string; actorRole?: string;
  } = {}) {
    if (!element.value) return;
    const { source, table, column, schema } = element.value;
    try {
      const result = await api.saveInterpretation(source, table, column, { ...opts, schema: schema ?? undefined });
      // Reflect any text written by the holistic save on the element + summary.
      if (element.value) {
        if (opts.description != null) element.value.column_description = opts.description;
        if (opts.businessName != null) element.value.business_name = opts.businessName;
      }
      await _applyLifecycleResult(result, { dqReason: 'Draft saved' });
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to save interpretation';
    }
  }

  /** Submit the interpretation set for steward review → In-Review. */
  async function submitInterpretation(actor?: string, actorRole?: string, skipDqRefresh = false) {
    if (!element.value) return;
    const { source, table, column, schema } = element.value;
    try {
      const result = await api.submitDefinitionForReview(source, table, column, actor, schema ?? undefined, actorRole);
      await _applyLifecycleResult({ lifecycle_state: 'in_review', submission: result.submission, last_status: result.last_status }, { skipDqRefresh, dqReason: 'Submitted for review' });
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to submit for review';
    }
  }

  /** Analyst pulls an In-Review submission back → Saved (spontaneous). */
  async function withdrawInterpretation(actor?: string, actorRole?: string) {
    if (!element.value) return;
    const { source, table, column, schema } = element.value;
    try {
      const result = await api.withdrawInterpretation(source, table, column, { actor, actorRole, schema: schema ?? undefined });
      await _applyLifecycleResult(result, { dqReason: 'Submission withdrawn' });
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to withdraw';
    }
  }

  /** Analyst pulls a prior approval back → Draft (re-open for editing). */
  async function revokeInterpretation(actor?: string, actorRole?: string) {
    if (!element.value) return;
    const { source, table, column, schema } = element.value;
    try {
      const result = await api.revokeInterpretation(source, table, column, { actor, actorRole, schema: schema ?? undefined });
      await _applyLifecycleResult(result, { dqReason: 'Approval revoked' });
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to revoke';
    }
  }

  /** Steward approves the interpretation set → Approved (frozen). */
  async function approveInterpretation(decidedBy?: string, decidedByRole?: string) {
    if (!element.value) return;
    const { source, table, column, schema } = element.value;
    try {
      const result = await api.approveDefinitionViaReview(source, table, column, decidedBy, schema ?? undefined);
      void decidedByRole;
      await _applyLifecycleResult(result as api.LifecycleActionResult, { dqReason: 'Approved' });
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to approve';
    }
  }

  /** Steward returns the set for rework → Returned. */
  async function returnInterpretation(reason?: string, decidedBy?: string, decidedByRole?: string) {
    if (!element.value) return;
    const { source, table, column, schema } = element.value;
    try {
      const result = await api.returnInterpretation(source, table, column, { reason, decidedBy, decidedByRole, schema: schema ?? undefined });
      await _applyLifecycleResult(result, { dqReason: 'Returned for rework' });
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to return';
    }
  }

  /** Steward outright-rejects the set → Rejected. */
  async function declineInterpretation(reason?: string, decidedBy?: string, decidedByRole?: string) {
    if (!element.value) return;
    const { source, table, column, schema } = element.value;
    try {
      const result = await api.declineInterpretation(source, table, column, { reason, decidedBy, decidedByRole, schema: schema ?? undefined });
      await _applyLifecycleResult(result, { dqReason: 'Rejected' });
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to reject';
    }
  }

  /** Force a fresh DQ score for the current element (Polish Batch Task 6).
   * `dqReason` is a plain-English label for whatever governance/data action just happened
   * (e.g. "Draft saved") — surfaced on the score-change toast; omit for a plain manual
   * refresh with no specific triggering action. */
  async function refreshElementDq(dqReason?: string) {
    if (!element.value) return;
    const { source, table, column, schema } = element.value;
    const key = `${source}|${schema || ''}|${table}|${column}`;
    const stillCurrent = () =>
      !!element.value &&
      `${element.value.source}|${element.value.schema || ''}|${element.value.table}|${element.value.column}` === key;
    const previousScore = element.value.dq?.dq_score ?? null;
    const badge = await api.refreshElementDq(source, table, column, schema);
    // Bail if the user navigated to a different column while this was in flight
    // (this now runs in the background after a save, so the window is wider).
    if (!stillCurrent()) return;
    element.value = { ...element.value!, dq: badge };
    elementCache.set(key, element.value);
    if (previousScore != null && badge?.dq_score != null && badge.dq_score !== previousScore) {
      dqScoreChange.value = {
        column,
        oldScore: previousScore,
        newScore: badge.dq_score,
        direction: badge.dq_score > previousScore ? 'up' : 'down',
        nonce: Date.now(),
        reason: dqReason,
      };
    }
    if (datasetOverview.value) {
      const updated = datasetOverview.value.columns_summary.map((c) =>
        c.name === column ? { ...c, dq: badge } : c,
      );
      datasetOverview.value = { ...datasetOverview.value, columns_summary: updated };
      // The dataset-level roll-up (score + "columns dragging the score down")
      // is rolled up backend-side whenever a member column re-scores (the
      // manual refresh endpoint now re-rolls it too), but the store still
      // needs a fresh fetch to pick that up — force-reload the overview so
      // `dataset_dq` reflects the new column score immediately.
      // The dataset overview + source-info both read the backend roll-up (updated by
      // dq/refresh above) and are independent — reload them in parallel.
      await Promise.all([
        loadDatasetOverview(source, table, schema, true),
        sourceInfo.value ? loadSourceInfo(source) : Promise.resolve(),
      ]);
    }
    return badge;
  }

  async function loadInsights(source: string, table: string, schema?: string, includeAi = false) {
    insightsLoading.value = true;
    insightsError.value = null;
    try {
      insights.value = await getInsights(source, table, schema, includeAi);
    } catch (e: unknown) {
      insightsError.value = e instanceof Error ? e.message : 'Failed to load insights';
    } finally {
      insightsLoading.value = false;
    }
  }

  async function updateDescription(description: string, isAiGenerated: boolean = false) {
    if (!element.value) return;
    const { source, table, column, schema } = element.value;
    try {
      const result = await api.updateDescription(source, table, column, description, schema, isAiGenerated);
      const newState = result.lifecycle_state || element.value.lifecycle_state;
      const updated: ElementDetail = {
        ...element.value,
        column_description: result.column_description,
        lifecycle_state: newState,
        metadata: {
          created_by: element.value.metadata?.created_by ?? null,
          created_at: element.value.metadata?.created_at ?? null,
          updated_at: new Date().toISOString(),
          is_ai_generated: isAiGenerated,
          business_name_is_ai: element.value.metadata?.business_name_is_ai ?? false,
          mapping_instructions: element.value.metadata?.mapping_instructions ?? null,
        },
      };
      element.value = updated;
      elementCache.set(`${source}|${schema || ''}|${table}|${column}`, updated);
      patchOverviewState(column, newState);
      // Also patch the description field on the columns_summary entry
      if (datasetOverview.value) {
        datasetOverview.value = {
          ...datasetOverview.value,
          columns_summary: datasetOverview.value.columns_summary.map(c =>
            c.name === column ? { ...c, description, description_is_ai: isAiGenerated } : c
          ),
        };
      }
      // Description feeds the DQ Definition line-item, but re-scoring is deferred to the
      // tab-level 'Save as Draft' (saveInterpretation) — this per-field save only persists text.
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to update description';
    }
  }

  async function draftDescription(): Promise<{ draft: string; error?: AiError }> {
    if (!element.value) return { draft: '' };
    const { source, table, column, schema } = element.value;
    try {
      return await api.draftDescription(source, table, column, schema);
    } catch (e: unknown) {
      return { draft: '', error: { summary: 'The AI request failed.', detail: e instanceof Error ? e.message : String(e) } };
    }
  }

  async function updateBusinessName(name: string, isAiGenerated: boolean = false): Promise<void> {
    if (!element.value) return;
    const { source, table, column, schema } = element.value;
    try {
      const result = await apiBusiness(source, table, column, name, schema, isAiGenerated);
      element.value = {
        ...element.value,
        business_name: result.business_name,
        metadata: {
          ...element.value.metadata,
          business_name_is_ai: result.business_name_is_ai,
        } as typeof element.value.metadata,
      };
      elementCache.set(`${source}|${schema || ''}|${table}|${column}`, element.value);
      // Patch business_name on the datasetOverview columns_summary entry
      if (datasetOverview.value) {
        datasetOverview.value = {
          ...datasetOverview.value,
          columns_summary: datasetOverview.value.columns_summary.map(c =>
            c.name === column
              ? { ...c, business_name: result.business_name, business_name_is_ai: result.business_name_is_ai }
              : c
          ),
        };
      }
      // Business name feeds the DQ Business-Name line-item, but re-scoring is deferred to the
      // tab-level 'Save as Draft' (saveInterpretation) — this per-field save only persists text.
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to update business name';
    }
  }

  async function draftBusinessName(): Promise<{ draft: string; error?: AiError }> {
    if (!element.value) return { draft: '' };
    const { source, table, column, schema } = element.value;
    try {
      return await apiDraftBusiness(source, table, column, schema);
    } catch (e: unknown) {
      return { draft: '', error: { summary: 'The AI request failed.', detail: e instanceof Error ? e.message : String(e) } };
    }
  }

  async function loadReferenceData(source: string, table: string, column: string, schema?: string) {
    loadingRefData.value = true;
    error.value = null;
    try {
      referenceData.value = await api.getReferenceData(source, table, column, schema);
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to load reference data';
    } finally {
      loadingRefData.value = false;
    }
  }

  // Phase 5b.2 — per-code Reference Data (Postgres backend, unbound fields).
  async function saveReferenceCodes(
    source: string, table: string, column: string,
    codes: api.ReferenceCodeEdit[], schema?: string,
  ) {
    const res = await api.saveReferenceCodes(source, table, column, codes, schema);
    if (referenceData.value) {
      referenceData.value = { ...referenceData.value, codes: res.codes, set_badge: res.set_badge };
    }
    return res;
  }

  async function submitReferenceCodes(
    source: string, table: string, column: string,
    codes: string[] | null, schema?: string,
  ) {
    const res = await api.submitReferenceCodes(source, table, column, codes, schema);
    if (referenceData.value) {
      referenceData.value = { ...referenceData.value, codes: res.codes, set_badge: res.set_badge };
    }
    return res;
  }

  // Phase 5b.3.1 — analyst bulk pull-backs / delete.
  async function withdrawReferenceCodes(
    source: string, table: string, column: string,
    codes: string[], schema?: string,
  ) {
    const res = await api.withdrawReferenceCodes(source, table, column, codes, schema);
    if (referenceData.value) {
      referenceData.value = { ...referenceData.value, codes: res.codes, set_badge: res.set_badge };
    }
    return res;
  }

  async function revokeReferenceCodes(
    source: string, table: string, column: string,
    codes: string[], schema?: string,
  ) {
    const res = await api.revokeReferenceCodes(source, table, column, codes, schema);
    if (referenceData.value) {
      referenceData.value = { ...referenceData.value, codes: res.codes, set_badge: res.set_badge };
    }
    return res;
  }

  async function removeReferenceCodes(
    source: string, table: string, column: string,
    codes: string[], schema?: string,
  ) {
    const res = await api.removeReferenceCodes(source, table, column, codes, schema);
    if (referenceData.value) {
      referenceData.value = { ...referenceData.value, codes: res.codes, set_badge: res.set_badge };
    }
    return res;
  }

  async function loadSourceInfo(source: string) {
    if (_sourceInfoAbort) _sourceInfoAbort.abort();
    _sourceInfoAbort = new AbortController();
    loadingSourceInfo.value = true;
    sourceInfoProgress.value = { completed: 0, detail: '', fraction: 0 };
    error.value = null;
    try {
      sourceInfo.value = await api.streamSourceInfo(
        source,
        (completed) => { sourceInfoProgress.value = { ...sourceInfoProgress.value, completed, fraction: 0 }; },
        (detail, fraction) => { sourceInfoProgress.value = { ...sourceInfoProgress.value, detail, fraction: fraction ?? 0 }; },
        _sourceInfoAbort.signal,
      );
    } catch (e: unknown) {
      if (!(e instanceof DOMException && e.name === 'AbortError')) {
        error.value = e instanceof Error ? e.message : 'Failed to load source info';
      }
    } finally {
      loadingSourceInfo.value = false;
    }
  }

  function clearElementCache() {
    elementCache.clear();
    lastLoadedOverviewKey = '';
  }

  async function bulkGenerateDescriptions(source: string, table: string, schema?: string) {
    const result = await apiBulkDesc(source, table, schema);
    elementCache.clear();
    return result;
  }

  async function bulkGenerateBusinessNames(source: string, table: string, schema?: string) {
    const result = await apiBulkBiz(source, table, schema);
    elementCache.clear();
    return result;
  }

  async function loadDataStory(source: string, table: string, schema?: string) {
    console.log('[loadDataStory] called with:', { source, table, schema });
    dataStory.value = null; // reset so stale previous-table story never bleeds through
    loadingDataStory.value = true;
    try {
      const result = await getDataStory(source, table, schema);
      console.log('[loadDataStory] API returned:', result);
      dataStory.value = result;
      console.log('[loadDataStory] dataStory.value set to:', dataStory.value);
    } catch (e) {
      console.error('[elementStore] loadDataStory failed:', e);
      // keep null
    } finally {
      loadingDataStory.value = false;
    }
  }

  async function generateDataStory(source: string, table: string, schema?: string) {
    loadingDataStory.value = true;
    try {
      const result = await draftDataStory(source, table, schema);
      // Only update if AI returned real content; don't null-out an existing story
      if (result.narrative || result.tagline) {
        dataStory.value = result;
      }
    } catch {
      // leave existing story intact on AI failure
    } finally {
      loadingDataStory.value = false;
    }
  }

  async function saveDataStory(source: string, table: string, tagline: string, narrative: string, schema?: string) {
    console.log('[saveDataStory] called with:', { source, table, tagline: tagline?.slice(0, 30), narrative: narrative?.slice(0, 30), schema });
    loadingDataStory.value = true;
    try {
      const result = await apiSaveDataStory(source, table, tagline, narrative, schema);
      console.log('[saveDataStory] API returned:', result);
      dataStory.value = result;
    } catch (e) {
      console.error('[saveDataStory] FAILED:', e);
      loadingDataStory.value = false;
      throw e; // propagate so the caller can show an error banner
    } finally {
      loadingDataStory.value = false;
    }
  }

  async function bulkGenerateDataStories(source: string) {
    const result = await apiBulkDataStories(source);
    return result;
  }

  /**
   * Refresh the current table profile by querying the live database.
   * Patches primary_key, inferred_primary_key, row_count, completeness, and
   * duplicate_rows on the overview, then force-reloads the active element
   * so column stats are also fresh.
   * Returns 'ok' | 'error'.
   */
  async function refreshProfileFromLive(
    source: string,
    table: string,
    schema: string | null | undefined,
    activeColumn: string | null | undefined,
  ): Promise<'ok' | 'error'> {
    try {
      // Schema-qualify the table name the way the discovery endpoint expects it
      const tableParam = schema ? `${schema}.${table}` : table;
      const profile = await refreshTableProfile(source, tableParam);

      // Patch the overview in-place with live stats
      if (datasetOverview.value) {
        datasetOverview.value = {
          ...datasetOverview.value,
          primary_key: profile.primary_key ?? datasetOverview.value.primary_key,
          inferred_primary_key: profile.inferred_primary_key ?? [],
          row_count: profile.row_count ?? datasetOverview.value.row_count,
          completeness: profile.completeness_summary ?? datasetOverview.value.completeness,
          duplicate_rows: profile.duplicate_count ?? datasetOverview.value.duplicate_rows,
          generated_at: new Date().toISOString(),
        };
      }

      // Invalidate cache for every column in this table so next selection loads fresh
      const prefix = `${source}|${schema || ''}|${table}|`;
      for (const key of [...elementCache.keys()]) {
        if (key.startsWith(prefix)) elementCache.delete(key);
      }
      lastLoadedOverviewKey = ''; // force full overview reload on next navigation

      // Reload active column element if one is selected
      if (activeColumn) {
        await loadElement(source, table, activeColumn, schema ?? undefined, true);
      }

      return 'ok';
    } catch {
      return 'error';
    }
  }

  return {
    sources, tables, element, datasetOverview, referenceData, sourceInfo,
    loading, loadingElement, loadingOverview, loadingRefData, loadingSourceInfo, error,
    sourceInfoProgress, overviewProgress, elementProgress, dqScoreChange,
    insights, insightsLoading, insightsError,
    loadSources, loadTables, loadElement, loadDatasetOverview, loadReferenceData, loadSourceInfo,
    saveReferenceCodes, submitReferenceCodes,
    withdrawReferenceCodes, revokeReferenceCodes, removeReferenceCodes,
    setLifecycleState, patchOverviewState, loadInsights, updateDescription, draftDescription,
    updateBusinessName, draftBusinessName, clearElementCache,
    saveInterpretation, submitInterpretation, withdrawInterpretation,
    revokeInterpretation,
    approveInterpretation, returnInterpretation, declineInterpretation,
    setColumnsScope,
    bulkGenerateDescriptions, bulkGenerateBusinessNames,
    dataStory, loadingDataStory, loadDataStory, generateDataStory, saveDataStory, bulkGenerateDataStories,
    refreshProfileFromLive,
    refreshElementDq,
    breadcrumbTrail, setBreadcrumbTrail, clearBreadcrumbTrail,
  };
});
