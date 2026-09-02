<template>
  <q-page class="wp">
    <div class="wp-layout">

      <!-- ── LEFT RAIL ─────────────────────────────────────────────────── -->
      <aside class="rail">
        <div class="rail-header">
          <div class="rail-field-row">
            <div class="rail-field rail-field--source">
              <div class="rail-section-label">Source</div>
              <q-select
                v-model="selectedSource"
                :options="store.sources"
                dense outlined
                placeholder="Select source…"
                :loading="store.loading"
                @update:model-value="onSourceChange"
                class="rail-select"
              >
                <template #prepend><q-icon name="dns" size="15px" /></template>
              </q-select>
            </div>
            <div class="rail-field rail-field--schema">
              <div class="rail-section-label">Schema</div>
              <q-select
                v-model="selectedSchemaFilter"
                :options="availableSchemas"
                dense outlined clearable
                placeholder="All"
                class="rail-select"
              >
                <template #prepend><q-icon name="schema" size="15px" /></template>
              </q-select>
            </div>
          </div>
        </div>

        <template v-if="selectedSource">
          <div class="rail-sub-header">
            <span class="rail-section-label">Dataset</span>
          </div>
          <div class="rail-header rail-header--dataset">
            <q-select
              :model-value="selectedTable === '*' ? allDatasetsOption : (store.tables.find(t => t.table_name === selectedTable) ?? null)"
              :options="[allDatasetsOption, ...filteredTablesForDataset]"
              :option-label="(t: any) => t._all ? 'All datasets' : t.table_name"
              dense outlined
              :placeholder="store.loading && selectedSource ? 'Loading datasets…' : 'Select dataset…'"
              :loading="store.loading"
              clearable
              @update:model-value="(tbl: any) => {
                if (!tbl) { selectedTable = null; selectedColumn = null; viewMode = 'source'; refreshSourceInfo(); }
                else if (tbl._all) { selectedTable = '*'; selectedColumn = null; viewMode = 'source'; refreshSourceInfo(); }
                else selectTable(tbl);
              }"
              class="rail-select"
            >
              <template #prepend><q-icon name="table_chart" size="15px" /></template>
            </q-select>
          </div>

          <div class="rail-sub-header">
            <span class="rail-section-label">Columns</span>
          </div>

          <div class="rail-search-wrap">
            <q-input v-model="colSearch" dense outlined placeholder="Search columns, semantic type, PII…" clearable class="rail-search" @clear="colSearch = ''">
              <template #prepend><q-icon name="search" size="13px" /></template>
            </q-input>
          </div>

          <!-- Filter chips -->
          <div class="rail-chips">
            <button
              v-for="chip in filterChips" :key="chip.value"
              class="rail-chip" :class="{ 'rail-chip--active': activeFilter === chip.value }"
              @click="activeFilter = chip.value"
            ><span v-if="chip.pip" class="chip-pip" :style="{ background: chip.pip }" />{{ chip.label }}</button>
          </div>

          <!-- Flat column list: specific dataset selected -->
          <div v-if="selectedTable && selectedTable !== '*' && store.datasetOverview" class="rail-col-list">
            <button
              v-for="col in filteredOverviewColumns"
              :key="col.name"
              class="rail-col-btn"
              :class="{ 'rail-col-btn--active': selectedColumn === col.name }"
              @click="selectColumnFromOverview(col)"
            >
              <div class="rail-col-l1">
                <div class="rail-col-l1-left">
                  <span class="rail-col-name">{{ col.name }}</span>
                  <span v-if="store.datasetOverview.primary_key?.includes(col.name)" class="rail-key-badge" title="Primary key">🔑</span>
                  <span v-else-if="store.datasetOverview.inferred_primary_key?.includes(col.name)" class="rail-key-badge rail-key-badge--candidate" title="Candidate key (inferred — no PK constraint declared)">🔑</span>
                  <span v-if="col.foreign_key" class="rail-fk-badge" title="Foreign key">🔗</span>
                </div>
                <div class="rail-col-l1-right">
                  <span v-if="railDqBadge(col.dq).scored" class="rail-dq" :class="[railDqBadge(col.dq).bandClass, selectedColumn === col.name ? scorePulseClass : '']">{{ railDqBadge(col.dq).score }}</span>
                  <span v-else-if="railDqBadge(col.dq).excluded" class="rail-dq rail-dq--excluded" title="Excluded from assessment">
                    <q-icon name="block" size="10px" />
                  </span>
                  <span class="rail-state-badge" :class="`rail-state--${col.lifecycle_state}`">{{ col.lifecycle_state }}</span>
                </div>
              </div>
              <div class="rail-col-l2">
                <span class="rail-col-dtype mono">{{ col.data_type }}</span>
                <span class="rail-col-type">{{ semTypeLabel(col.semantic_type) }}</span>
                <span v-if="col.pii" class="rail-pii-badge" title="Contains PII">PII</span>
              </div>
            </button>
            <div v-if="filteredOverviewColumns.length === 0" class="rail-empty-filter">No columns match.</div>
          </div>

          <!-- Expansion list: All datasets selected -->
          <div v-else-if="selectedTable === '*'" class="rail-table-list">
            <q-expansion-item
              v-for="tbl in store.tables"
              :key="`${tbl.schema}.${tbl.table_name}`"
              :label="tbl.table_name"
              :caption="tbl.schema"
              dense
              header-class="rail-table-header"
              expand-icon-class="text-grey-5"
            >
              <button
                v-for="col in filteredColumns(tbl)"
                :key="col.name"
                class="rail-col-btn"
                :class="{ 'rail-col-btn--active': selectedTable === tbl.table_name && selectedColumn === col.name }"
                @click="selectColumn(tbl, col)"
              >
                <div class="rail-col-l1">
                  <span class="rail-col-name">{{ col.name }}</span>
                  <span v-if="railDqBadge(col.dq).scored" class="rail-dq" :class="[railDqBadge(col.dq).bandClass, (selectedTable === tbl.table_name && selectedColumn === col.name) ? scorePulseClass : '']">{{ railDqBadge(col.dq).score }}</span>
                  <span v-else-if="railDqBadge(col.dq).excluded" class="rail-dq rail-dq--excluded" title="Excluded from assessment">
                    <q-icon name="block" size="10px" />
                  </span>
                  <span
                    v-if="getColumnState(tbl.schema, tbl.table_name, col) !== 'draft'"
                    class="rail-state-badge"
                    :class="`rail-state--${getColumnState(tbl.schema, tbl.table_name, col)}`"
                  >{{ getColumnState(tbl.schema, tbl.table_name, col) }}</span>
                </div>
                <div class="rail-col-l2">
                  <span class="rail-col-type">{{ col.data_type }}</span>
                  <span v-if="col.pii" class="rail-pii-badge" title="Contains PII">PII</span>
                </div>
              </button>
            </q-expansion-item>
          </div>

          <!-- A dataset is selected but its fields are still loading -->
          <div v-else-if="selectedTable && selectedTable !== '*' && !store.datasetOverview" class="rail-empty-filter" style="padding: 20px 16px; display: flex; align-items: center; gap: 8px;">
            <q-spinner-dots size="18px" />
            <span>Loading fields for <strong>{{ selectedTable }}</strong>…</span>
          </div>
          <!-- No dataset selected yet -->
          <div v-else class="rail-empty-filter" style="padding: 20px 16px;">Select a dataset above to browse its fields.</div>

        </template>

        <div v-else class="rail-empty">Select a source to browse its columns.</div>
      </aside>

      <!-- ── DETAIL PANEL ──────────────────────────────────────────────── -->
      <section class="detail">

        <AiErrorBanner :error="aiError" @dismiss="clearAiError" />

        <!-- Empty / loading states -->
        <div v-if="viewMode === 'none' && !store.loading && !store.loadingSourceInfo" class="detail-empty">
          <q-icon name="data_object" size="48px" class="q-mb-md" style="color:#c9c3ba" />
          <div style="color:#86827a;font-size:13px">Select a column to explore its full profile.</div>
        </div>
        <div v-else-if="viewMode === 'none' && store.loading" class="detail-loading">
          <StagedLoader :stages="sourcesLoadStages" :completed="store.loading ? 0 : 1" />
        </div>
        <div v-else-if="viewMode === 'source' && store.loadingSourceInfo" class="detail-loading">
          <StagedLoader :stages="sourceLoadStages" :completed="store.sourceInfoProgress.completed" :active-detail="store.sourceInfoProgress.detail" :active-fraction="store.sourceInfoProgress.fraction" />
        </div>
        <div v-else-if="viewMode === 'table' && store.loadingOverview" class="detail-loading">
          <StagedLoader :stages="datasetLoadStages" :completed="store.overviewProgress.completed" :active-detail="(semanticStageSummary && store.overviewProgress.completed === 2) ? '' : store.overviewProgress.detail" :active-fraction="store.overviewProgress.fraction" />
        </div>
        <div v-else-if="viewMode === 'column' && store.loadingElement" class="detail-loading">
          <StagedLoader :stages="elementLoadStages" :completed="store.elementProgress.completed" :active-detail="store.elementProgress.detail" :active-fraction="store.elementProgress.fraction" />
        </div>

        <!-- Source info (source-level) -->
        <template v-else-if="viewMode === 'source' && store.sourceInfo">
          <div class="src-header">
            <div class="src-title-row">
              <q-icon name="storage" size="20px" style="color:var(--accent)" class="q-mr-sm" />
              <span class="src-name">{{ store.sourceInfo.source }}</span>
              <span v-if="srcAllUnprofiled" class="unprofiled-badge unprofiled-badge--src" aria-label="Never profiled">
                R
                <q-tooltip>No dataset in this source has been profiled yet — every table is in its pre-profiling baseline. Run "Rebuild all profiles" or refresh a dataset individually to start.</q-tooltip>
              </span>
              <span class="src-count-badge">
                {{ store.sourceInfo.table_count }} datasets &nbsp;·&nbsp;
                {{ store.sourceInfo.column_count }} columns &nbsp;·&nbsp;
                {{ store.sourceInfo.total_row_count?.toLocaleString() }} rows
              </span>
            </div>
            <div class="src-generated" v-if="store.sourceInfo.generated_at">
              <span v-if="store.sourceInfo.last_profiled_at">Profiled {{ fmtDate(store.sourceInfo.last_profiled_at) }}</span>
              <button class="src-rebuild-btn" @click="promptRebuildProfiles" :disabled="rebuildState.running">
                <q-icon name="sync" size="12px" class="q-mr-xs" :class="{ 'spin': rebuildState.running }" />
                {{ rebuildState.running ? 'Rebuilding…' : 'Rebuild all profiles' }}
              </button>
              <button class="src-reset-btn" @click="promptResetSource" :disabled="resetSourceState.running">
                <q-icon name="restart_alt" size="12px" class="q-mr-xs" />
                Reset all profiles
              </button>
            </div>
            <div class="src-sub">Source-level overview of connection metadata, dataset inventory, and governance state. Select a dataset from the list below to explore its structure and fields.</div>
            <div class="src-ai-actions">
              <!-- moved to Bulk AI Draft tab -->
            </div>

            <!-- Rebuild warning dialog -->
            <transition name="bulk-banner">
              <div v-if="rebuildState.showWarning" class="rebuild-warn-dialog">
                <div class="rebuild-warn-icon"><q-icon name="warning_amber" size="22px" color="orange" /></div>
                <div class="rebuild-warn-body">
                  <div class="rebuild-warn-title">Rebuild all profiles — this will take a while</div>
                  <div class="rebuild-warn-msg">
                    This re-profiles all <strong>{{ store.sourceInfo.table_count }} tables</strong> in
                    <strong>{{ store.sourceInfo.source }}</strong> directly from the database.
                    Expect roughly <strong>{{ Math.ceil((store.sourceInfo.table_count ?? 0) * 2 / 60) }}–{{ Math.ceil((store.sourceInfo.table_count ?? 0) * 5 / 60) }} minutes</strong> depending on table sizes.
                    The page remains fully usable while this runs. Stats, inferred keys, and quality findings
                    are saved permanently after each table completes — so even if you navigate away, progress is kept.
                    Descriptions, business names, and governance state are never touched.
                  </div>
                  <div class="rebuild-warn-checks">
                    <q-checkbox v-model="rebuildState.includeSemantic" dense label="Also re-derive semantic types" />
                    <q-checkbox v-model="rebuildState.includeDq" dense label="Also re-score data quality" />
                  </div>
                  <div class="rebuild-warn-note">
                    Including these takes longer per table, but keeps semantic types and quality scores from
                    lagging behind the refreshed stats. Opening any individual dataset always re-derives both
                    regardless of these choices — this only affects the bulk pass.
                  </div>
                  <div class="rebuild-warn-actions">
                    <button class="rebuild-confirm-btn" @click="startRebuildProfiles">Start rebuild</button>
                    <button class="rebuild-cancel-btn" @click="rebuildState.showWarning = false">Cancel</button>
                  </div>
                </div>
              </div>
            </transition>

            <!-- Rebuild progress panel -->
            <transition name="bulk-banner">
              <div v-if="rebuildState.running || rebuildState.done" class="rebuild-progress-panel">
                <div class="rebuild-prog-header">
                  <q-icon :name="rebuildState.done ? (rebuildState.failed > 0 ? 'warning' : 'check_circle') : 'sync'"
                    size="15px" class="q-mr-xs"
                    :style="{ color: rebuildState.done ? (rebuildState.failed > 0 ? '#a87232' : 'var(--approved-col)') : 'var(--accent)', animation: rebuildState.running ? 'spin 1.5s linear infinite' : 'none' }" />
                  <span class="rebuild-prog-title">
                    {{ rebuildState.done ? `Rebuild complete — ${rebuildStepsLabel}` : `Rebuilding ${rebuildStepsLabel} — ${rebuildState.currentTable}` }}
                  </span>
                  <button v-if="rebuildState.running" class="rebuild-abort-btn" @click="abortRebuild" title="Abort rebuild">
                    <q-icon name="stop" size="12px" />
                  </button>
                  <button v-if="rebuildState.done" class="rebuild-abort-btn" @click="rebuildState.done = false" title="Dismiss">
                    <q-icon name="close" size="12px" />
                  </button>
                </div>

                <!-- Progress bar -->
                <div class="rebuild-prog-bar-wrap">
                  <div class="rebuild-prog-bar"
                    :style="{ width: rebuildState.total > 0 ? (rebuildState.index / rebuildState.total * 100).toFixed(1) + '%' : '0%' }"
                    :class="{ 'rebuild-prog-bar--done': rebuildState.done, 'rebuild-prog-bar--error': rebuildState.done && rebuildState.failed > 0 }"
                  />
                </div>

                <!-- Stats row -->
                <div class="rebuild-prog-stats">
                  <span class="rebuild-stat">
                    <strong>{{ rebuildState.index }}</strong> / {{ rebuildState.total }} tables
                  </span>
                  <span class="rebuild-stat rebuild-stat--ok">
                    <q-icon name="check" size="11px" class="q-mr-xs" />{{ rebuildState.completed }} done
                  </span>
                  <span v-if="rebuildState.failed > 0" class="rebuild-stat rebuild-stat--err">
                    <q-icon name="error_outline" size="11px" class="q-mr-xs" />{{ rebuildState.failed }} failed
                  </span>
                  <span class="rebuild-stat rebuild-stat--time">
                    <q-icon name="schedule" size="11px" class="q-mr-xs" />
                    {{ fmtSeconds(rebuildState.elapsed) }} elapsed
                    <template v-if="!rebuildState.done && rebuildState.estimatedRemaining > 0">
                      &nbsp;·&nbsp; ~{{ fmtSeconds(rebuildState.estimatedRemaining) }} left
                    </template>
                  </span>
                </div>
              </div>
            </transition>

            <!-- Reset warning dialog -->
            <transition name="bulk-banner">
              <div v-if="resetSourceState.showWarning" class="rebuild-warn-dialog">
                <div class="rebuild-warn-icon"><q-icon name="warning_amber" size="22px" color="orange" /></div>
                <div class="rebuild-warn-body">
                  <div class="rebuild-warn-title">Reset Profile — this cannot be undone</div>
                  <div class="rebuild-warn-msg">
                    This clears ALL profiling and governance state for every
                    <strong>{{ store.sourceInfo.table_count }} table{{ store.sourceInfo.table_count === 1 ? '' : 's' }}</strong> in
                    <strong>{{ store.sourceInfo.source }}</strong> — profile stats, semantic types, DQ scores,
                    Interpretation (descriptions, business names, review status), Reference Data, reference-set
                    bindings, and annotations. Every table returns to the same blank state it had right after
                    onboarding, before it was ever profiled. Schema, column names/types, and declared keys are
                    kept. This runs as one all-or-nothing operation — if anything fails, nothing changes.
                  </div>
                  <div class="rebuild-warn-actions">
                    <button class="rebuild-confirm-btn rebuild-confirm-btn--danger" @click="startResetSource">Reset {{ store.sourceInfo.table_count }} table{{ store.sourceInfo.table_count === 1 ? '' : 's' }}</button>
                    <button class="rebuild-cancel-btn" @click="resetSourceState.showWarning = false">Cancel</button>
                  </div>
                </div>
              </div>
            </transition>

            <!-- Reset progress panel -->
            <transition name="bulk-banner">
              <div v-if="resetSourceState.running || resetSourceState.done" class="rebuild-progress-panel">
                <div class="rebuild-prog-header">
                  <q-icon :name="resetSourceState.done ? (resetSourceState.failed ? 'warning' : 'check_circle') : 'sync'"
                    size="15px" class="q-mr-xs"
                    :style="{ color: resetSourceState.done ? (resetSourceState.failed ? '#a87232' : 'var(--approved-col)') : 'var(--accent)', animation: resetSourceState.running ? 'spin 1.5s linear infinite' : 'none' }" />
                  <span class="rebuild-prog-title">
                    {{ resetSourceState.done
                      ? (resetSourceState.failed ? 'Reset failed — rolled back, nothing changed' : 'Reset complete')
                      : `Resetting — ${resetStepLabel(resetSourceState.currentStep)}` }}
                  </span>
                  <button v-if="resetSourceState.running" class="rebuild-abort-btn" @click="abortResetSource" title="Abort (the reset itself still completes or rolls back atomically — this only stops watching)">
                    <q-icon name="stop" size="12px" />
                  </button>
                  <button v-if="resetSourceState.done" class="rebuild-abort-btn" @click="resetSourceState.done = false" title="Dismiss">
                    <q-icon name="close" size="12px" />
                  </button>
                </div>
                <div class="rebuild-prog-bar-wrap">
                  <div class="rebuild-prog-bar"
                    :style="{ width: resetSourceState.stepsTotal > 0 ? Math.min(100, resetSourceState.stepsCompleted / resetSourceState.stepsTotal * 100).toFixed(1) + '%' : '0%' }"
                    :class="{ 'rebuild-prog-bar--done': resetSourceState.done, 'rebuild-prog-bar--error': resetSourceState.done && resetSourceState.failed }"
                  />
                </div>
                <div v-if="resetSourceState.failed" class="rebuild-warn-msg" style="margin-top:6px">{{ resetSourceState.errorMessage }}</div>
              </div>
            </transition>

            <!-- Source-level tab bar -->
            <div class="tab-bar src-tab-bar">
              <button class="tab-btn" :class="{ 'tab-btn--active': srcActiveTab === 'overview' }" @click="srcActiveTab = 'overview'">Overview</button>
              <button class="tab-btn" :class="{ 'tab-btn--active': srcActiveTab === 'data-model' }" @click="srcActiveTab = 'data-model'">
                <q-icon name="account_tree" size="13px" class="q-mr-xs" />Data Model
              </button>
              <button class="tab-btn" :class="{ 'tab-btn--active': srcActiveTab === 'bulk-ai' }" @click="srcActiveTab = 'bulk-ai'">
                <q-icon name="auto_awesome" size="13px" class="q-mr-xs" />Bulk AI Assistance
                <span v-if="srcMissingStoriesCount > 0" class="tab-badge tab-badge--warn">{{ srcMissingStoriesCount }}</span>
              </button>
              <button class="tab-btn" :class="{ 'tab-btn--active': srcActiveTab === 'documents' }" @click="srcActiveTab = 'documents'">
                <q-icon name="description" size="13px" class="q-mr-xs" />Documents
                <span v-if="docList.length > 0" class="tab-badge">{{ docList.length }}</span>
              </button>
            </div>

            <!-- Bulk generation banner (source level) -->
            <transition name="bulk-banner">
              <div v-if="bulkBanner" class="bulk-banner" :class="`bulk-banner--${bulkBanner.type}`">
                <q-icon :name="bulkBanner.type === 'success' ? 'check_circle' : bulkBanner.type === 'error' ? 'error' : 'info'" size="14px" class="q-mr-xs" />
                {{ bulkBanner.msg }}
                <button class="bulk-banner-close" @click="bulkBanner = null">
                  <q-icon name="close" size="12px" />
                </button>
              </div>
            </transition>
          </div>

          <div class="src-body">

            <!-- ══ OVERVIEW TAB ══════════════════════════════════════════════ -->
            <div v-show="srcActiveTab === 'overview'">
            <!-- Connection & Feed Metadata (screenshot1 layout) -->
            <div class="panel-card q-mb-md">
              <div class="src-conn-header">
                <span class="panel-card-title">Source information</span>
                <span class="src-conn-caption">CONNECTION &amp; FEED METADATA</span>
              </div>
              <div class="src-conn-divider" />
              <div class="src-conn-grid">
                <div class="src-conn-item">
                  <span class="src-conn-lbl">Source system</span>
                  <span class="src-conn-val">{{ store.sourceInfo.connection.source_system ?? '—' }}</span>
                </div>
                <div class="src-conn-item">
                  <span class="src-conn-lbl">System type</span>
                  <span class="src-conn-val">{{ store.sourceInfo.connection.system_type ?? '—' }}</span>
                </div>
                <div class="src-conn-item">
                  <span class="src-conn-lbl">Database</span>
                  <span class="src-conn-val mono">{{ store.sourceInfo.connection.database ?? '—' }}</span>
                </div>
                <div class="src-conn-item">
                  <span class="src-conn-lbl">Schema(s)</span>
                  <span class="src-conn-val mono">{{ store.sourceInfo.connection.schema ?? '—' }}</span>
                </div>
                <div class="src-conn-item">
                  <span class="src-conn-lbl">Access mode</span>
                  <span class="src-conn-val">{{ store.sourceInfo.connection.access_mode ?? '—' }}</span>
                </div>
                <div class="src-conn-item">
                  <span class="src-conn-lbl">Schema hash</span>
                  <span class="src-conn-val mono" :title="store.sourceInfo.schema_hash ?? ''">{{ store.sourceInfo.schema_hash ? store.sourceInfo.schema_hash.slice(0, 12) + '…' : '—' }}</span>
                </div>
                <div class="src-conn-item">
                  <span class="src-conn-lbl">Last profiled</span>
                  <span class="src-conn-val">{{ store.sourceInfo.last_profiled_at ? fmtDate(store.sourceInfo.last_profiled_at) : '—' }}</span>
                </div>
              </div>
            </div>

            <!-- Summary Stats -->
            <KpiStripCard :kpis="srcKpis" class="q-mb-md" />

            <!-- Composition collapses to ONE compact row (the source level's
                 job is comparing its datasets, not re-showing dataset-level
                 composition). Semantic × Governance moved to the Dashboard as
                 a heatmap — it was a superset of these two and made them
                 redundant. -->
            <div class="ds-charts-row q-mb-md">
              <ProportionalBarCard
                title="Governance Pipeline"
                :caption="`${store.sourceInfo.column_count} ELEMENTS`"
                :segments="srcGovernanceSegments"
                :hints="GOV_LEGEND_HINTS"
              />
              <ProportionalBarCard
                title="Semantic-type mix"
                :caption="`${store.sourceInfo.column_count} ELEMENTS · AI-INFERRED`"
                :segments="srcSemanticSegments"
              />
            </div>

            <!-- The hero card: which datasets are big AND low quality. -->
            <QualityMapCard
              title="Dataset Quality Map"
              :caption="`${store.sourceInfo.table_count} DATASETS`"
              :points="srcQualityPoints"
              class="q-mb-md"
              @select="openQualityPoint"
            />


            <!-- Datasets Table -->
            <div v-if="store.sourceInfo.datasets?.length" class="panel-card q-pa-md q-mb-md">
              <div class="ds-panel-title-row q-mb-sm">
                <span class="panel-card-title">Datasets</span>
                <span class="ds-panel-caption">{{ store.sourceInfo.table_count }} ONBOARDED</span>
              </div>
              <table class="src-datasets-table">
                <thead>
                  <tr>
                    <th class="src-ds-num-th">#</th>
                    <th>Dataset</th>
                    <th class="num">Rows</th>
                    <th class="num">Fields</th>
                    <th class="num">DQ Grade</th>
                    <th class="num">Approved</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(ds, idx) in store.sourceInfo.datasets"
                    :key="`${ds.schema}.${ds.table_name}`"
                    class="src-ds-row"
                    @click="selectTableByName(ds.table_name, ds.schema)"
                  >
                    <td class="src-ds-num-cell">{{ idx + 1 }}</td>
                    <td class="src-ds-name-cell">
                      <div class="src-ds-name-inner">
                        <span class="src-ds-name mono">{{ ds.table_name }}</span>
                        <span v-if="!ds.is_profiled" class="unprofiled-badge" aria-label="Never profiled">
                          R
                          <q-tooltip>Never profiled — freshly onboarded, or reset back to its pre-profiling baseline. Click "Refresh Profile" on this dataset to run the first profiling pass.</q-tooltip>
                        </span>
                      </div>
                    </td>
                    <td class="num">{{ ds.row_count?.toLocaleString() ?? '—' }}</td>
                    <td class="num">{{ ds.column_count }}</td>
                    <td class="num">
                      <span v-if="isScored(ds.dataset_dq)" class="el-dq-chip src-ds-dq-chip" :class="dqBandClass(ds.dataset_dq)">
                        <span class="el-dq-chip-band">{{ ds.dataset_dq?.grade_label }}</span>
                      </span>
                      <span v-else class="ds-dq-not-scored">—</span>
                    </td>
                    <td class="num">
                      <span class="ds-released-count">{{ ds.governance?.approved ?? 0 }}</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            </div><!-- end overview tab -->

            <!-- ══ DATA MODEL TAB (source) ═══════════════════════════════════ -->
            <!-- Conceptual Data Model — entity boxes + 1:N lines built from
                 declared/inferred PK-FK relationships across this source's
                 datasets (no manual configuration required). Its own tab so
                 it isn't buried at the bottom of Overview, and has room to
                 grow with more data-model views later. -->
            <div v-show="srcActiveTab === 'data-model'" class="data-model-tab">
            <div class="panel-card q-pa-md ldm-panel" ref="ldmPanelEl" :class="{ 'ldm-panel--fullscreen': ldmFullscreen }">
              <div class="ldm-title-actions">
                <button v-if="ldmNodes.length" class="ldm-action-btn" @click="regenerateLdm" title="Reset layout and re-check PK/FK relationships">
                  <q-icon name="refresh" size="13px" class="q-mr-xs" />Regenerate Model
                </button>
                <button class="ldm-action-btn ldm-action-btn--icon" @click="toggleLdmFullscreen" :title="ldmFullscreen ? 'Exit full screen' : 'Full screen'">
                  <q-icon :name="ldmFullscreen ? 'fullscreen_exit' : 'fullscreen'" size="15px" />
                </button>
              </div>
              <div class="panel-card-title q-mb-sm">
                <q-icon name="account_tree" size="14px" class="q-mr-xs" />Conceptual Data Model
              </div>
              <div v-if="ldmNodes.length" class="ldm-diagram-wrap">
                <svg
                  ref="ldmSvgEl" class="ldm-svg" :class="{ 'ldm-svg--fullscreen': ldmFullscreen }"
                  :viewBox="`0 0 ${ldmCanvas.w} ${ldmCanvas.h}`" preserveAspectRatio="xMidYMid meet"
                >
                  <defs>
                    <linearGradient id="ldmNodeGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stop-color="#4f8fd6" />
                      <stop offset="100%" stop-color="#1c4f8a" />
                    </linearGradient>
                  </defs>
                  <!-- Crow's Foot notation: a double perpendicular tick marks
                       "exactly one" at the parent end; the forked prongs mark
                       "many" at the child end (the main line is the middle
                       prong of the fork). -->
                  <g v-for="edge in ldmEdges" :key="edge.key">
                    <line
                      :x1="edge.x1" :y1="edge.y1" :x2="edge.x2" :y2="edge.y2"
                      class="ldm-edge" :class="edge.declared ? 'ldm-edge--declared' : 'ldm-edge--inferred'"
                    ><title>{{ edge.title }}</title></line>
                    <line
                      v-for="(foot, fi) in edge.crowFeet" :key="`${edge.key}-foot-${fi}`"
                      :x1="foot.x1" :y1="foot.y1" :x2="foot.x2" :y2="foot.y2"
                      class="ldm-edge ldm-edge-mark" :class="edge.declared ? 'ldm-edge--declared' : 'ldm-edge--inferred'"
                    />
                    <line
                      v-for="(tick, ti) in edge.oneTicks" :key="`${edge.key}-tick-${ti}`"
                      :x1="tick.x1" :y1="tick.y1" :x2="tick.x2" :y2="tick.y2"
                      class="ldm-edge ldm-edge-mark" :class="edge.declared ? 'ldm-edge--declared' : 'ldm-edge--inferred'"
                    />
                    <text
                      :x="edge.labelX" :y="edge.labelY" text-anchor="middle"
                      class="ldm-verb-label" :transform="`rotate(${edge.angleDeg}, ${edge.labelX}, ${edge.labelY})`"
                    >{{ edge.verb }}</text>
                  </g>
                  <g
                    v-for="node in ldmNodes" :key="`${node.schema}.${node.table}`"
                    class="ldm-node"
                    @pointerdown="ldmNodePointerDown(node, $event)"
                    @pointermove="ldmNodePointerMove"
                    @pointerup="ldmNodePointerUp"
                    @pointercancel="ldmNodePointerUp"
                    @click="ldmNodeClick(node)"
                  >
                    <rect :x="node.x - node.halfW" :y="node.y - 15" :width="node.halfW * 2" height="30" rx="7" class="ldm-node-box" />
                    <text :x="node.x" :y="node.y + 4" text-anchor="middle" class="ldm-node-label mono">{{ node.table }}</text>
                    <title>{{ node.table }} — drag to reposition, click to open</title>
                  </g>
                </svg>
              </div>
              <div v-else class="ldm-placeholder">
                <q-icon name="schema" size="32px" style="color:#c9c3ba" class="q-mb-sm" />
                <div>Dataset relationship diagram will appear here once configured.</div>
                <div class="ldm-hint q-mt-xs">Select a dataset from the left to explore its fields.</div>
              </div>
              <div v-if="ldmEdges.length" class="ldm-legend">
                <span class="ldm-legend-item"><span class="ldm-legend-swatch ldm-legend-swatch--declared" />Declared FK · 1:N</span>
                <span v-if="ldmHasInferred" class="ldm-legend-item"><span class="ldm-legend-swatch ldm-legend-swatch--inferred" />Inferred FK · 1:N</span>
              </div>
            </div>
            </div><!-- end data model tab -->

            <!-- ══ BULK AI DRAFT TAB (source) ════════════════════════════════ -->
            <div v-show="srcActiveTab === 'bulk-ai'" class="bulk-ai-tab">

              <!-- Stats row -->
              <div class="bulk-stats-row">
                <div class="bulk-stat-card">
                  <div class="bulk-stat-icon" style="background:var(--accent-light);color:var(--accent)">
                    <q-icon name="auto_stories" size="18px" />
                  </div>
                  <div class="bulk-stat-body">
                    <div class="bulk-stat-val">{{ srcMissingStoriesCount }}</div>
                    <div class="bulk-stat-lbl">Missing Data Stories</div>
                    <div class="bulk-stat-sub">{{ srcTotalDatasets }} datasets total</div>
                  </div>
                </div>
                <div class="bulk-stat-card bulk-stat-card--ok" v-if="srcMissingStoriesCount === 0">
                  <q-icon name="check_circle_outline" size="18px" style="color:var(--approved-col)" class="q-mr-sm" />
                  <span style="font-size:13px;color:var(--approved-col);font-weight:600">All data stories are present.</span>
                </div>
              </div>

              <!-- AI Assistance chart (source level) -->
              <div v-if="srcTotalDatasets > 0" class="ai-accept-card">
                <div class="ai-accept-header">
                  <q-icon name="auto_awesome" size="13px" class="q-mr-xs" style="color:var(--ai-col)" />
                  <span class="ai-accept-title">AI Assistance</span>
                  <span class="ai-accept-scope">SOURCE LEVEL</span>
                </div>
                <div class="ai-accept-rows">
                  <!-- Data Stories row -->
                  <div class="ai-accept-row">
                    <div class="ai-accept-label">Data Stories</div>
                    <div class="ai-accept-track">
                      <div class="ai-accept-seg ai-accept-seg--ai"
                        :style="{ width: (srcAiStoryCount / srcTotalDatasets * 100).toFixed(1) + '%' }"
                        :title="srcAiStoryCount + ' AI-generated'"
                      />
                      <div class="ai-accept-seg ai-accept-seg--manual"
                        :style="{ width: ((srcHasStoryCount - srcAiStoryCount) / srcTotalDatasets * 100).toFixed(1) + '%' }"
                        :title="(srcHasStoryCount - srcAiStoryCount) + ' manually written'"
                      />
                    </div>
                    <div class="ai-accept-pct">
                      <span class="ai-accept-pct--ai">{{ srcTotalDatasets > 0 ? (srcAiStoryCount / srcTotalDatasets * 100).toFixed(0) : 0 }}%</span>
                      <span class="ai-accept-pct-lbl"> AI &nbsp;&middot;&nbsp; </span>
                      <span class="ai-accept-pct--manual">{{ srcTotalDatasets > 0 ? ((srcHasStoryCount - srcAiStoryCount) / srcTotalDatasets * 100).toFixed(0) : 0 }}%</span>
                      <span class="ai-accept-pct-lbl"> Manual &nbsp;&middot;&nbsp; </span>
                      <span class="ai-accept-pct--absent">{{ srcTotalDatasets > 0 ? (srcMissingStoriesCount / srcTotalDatasets * 100).toFixed(0) : 0 }}%</span>
                      <span class="ai-accept-pct-lbl"> Missing</span>
                    </div>
                  </div>
                </div>
                <div class="ai-accept-legend">
                  <span class="ai-accept-leg-item"><span class="ai-accept-leg-pip ai-accept-leg-pip--ai"/>AI-generated</span>
                  <span class="ai-accept-leg-item"><span class="ai-accept-leg-pip ai-accept-leg-pip--manual"/>Manually written</span>
                  <span class="ai-accept-leg-item"><span class="ai-accept-leg-pip ai-accept-leg-pip--missing"/>Missing</span>
                </div>
              </div>

              <!-- Section: Data Stories -->
              <div class="bulk-section" :class="{ 'bulk-section--open': bulkSrcStoriesOpen }">
                <div class="bulk-section-header">
                  <div class="bulk-section-title bulk-section-title--toggle" @click="bulkSrcStoriesOpen = !bulkSrcStoriesOpen">
                    <q-icon :name="bulkSrcStoriesOpen ? 'expand_less' : 'expand_more'" size="14px" class="q-mr-xs bulk-toggle-chevron" />
                    <q-icon name="auto_stories" size="14px" class="q-mr-xs" />Data Stories
                    <span class="bulk-section-scope">SOURCE LEVEL · {{ selectedSource }}</span>
                    <span v-if="getLastBulkRun('source', 'data_stories', selectedSource ?? '')" class="bulk-last-run">
                      <q-icon name="history" size="10px" class="q-mr-xs" />{{ fmtDate(getLastBulkRun('source', 'data_stories', selectedSource ?? '') ?? '') }}
                    </span>
                  </div>
                  <div class="bulk-section-actions">
                    <button class="bulk-run-btn" :disabled="bulkStoryLoading || srcMissingStoriesCount === 0" @click="runBulkDataStories">
                      <q-spinner-dots v-if="bulkStoryLoading" size="11px" class="q-mr-xs" />
                      <q-icon v-else name="auto_awesome" size="12px" class="q-mr-xs" />
                      <span v-if="bulkStoryLoading">Generating…</span>
                      <span v-else-if="srcMissingStoriesCount === 0">All generated</span>
                      <span v-else>Generate all {{ srcMissingStoriesCount }} missing</span>
                    </button>
                  </div>
                </div>
                <div v-show="bulkSrcStoriesOpen">
                  <div v-if="srcMissingStoriesCount === 0" class="bulk-empty-ok">
                    <q-icon name="check_circle_outline" size="14px" class="q-mr-xs" />Every dataset has a data story.
                  </div>
                  <div v-else class="bulk-item-list">
                    <div v-for="ds in srcMissingStories" :key="ds.table_name" class="bulk-item">
                      <div class="bulk-item-icon">
                        <q-icon name="table_chart" size="13px" />
                      </div>
                      <div class="bulk-item-body">
                        <span class="bulk-item-name mono">{{ ds.table_name }}</span>
                        <span class="bulk-item-meta">{{ ds.row_count?.toLocaleString() ?? '—' }} rows · {{ ds.column_count }} columns</span>
                      </div>
                      <span class="bulk-item-missing-badge">Missing story</span>
                      <button class="bulk-item-link" @click="selectTableByName(ds.table_name, ds.schema ?? '')">View dataset</button>
                    </div>
                  </div>
                </div>
              </div>

              <!-- History -->
              <div class="bulk-section" :class="{ 'bulk-section--open': bulkSrcHistoryOpen }" v-if="bulkDraftHistory.filter(r => r.scope === 'source' && r.target === selectedSource).length">
                <div class="bulk-section-header">
                  <div class="bulk-section-title bulk-section-title--toggle" @click="bulkSrcHistoryOpen = !bulkSrcHistoryOpen">
                    <q-icon :name="bulkSrcHistoryOpen ? 'expand_less' : 'expand_more'" size="14px" class="q-mr-xs bulk-toggle-chevron" />
                    <q-icon name="history" size="14px" class="q-mr-xs" />Generation History
                    <span class="bulk-section-scope">THIS SOURCE</span>
                  </div>
                </div>
                <div v-show="bulkSrcHistoryOpen" class="bulk-history-list">
                  <div v-for="run in bulkDraftHistory.filter(r => r.scope === 'source' && r.target === selectedSource)" :key="run.id" class="bulk-history-item">
                    <q-icon name="auto_awesome" size="12px" class="bulk-history-icon" />
                    <div class="bulk-history-body">
                      <div class="bulk-history-title">{{ run.type === 'data_stories' ? 'Data stories' : run.type }} generated</div>
                      <div class="bulk-history-meta">{{ run.generated }} generated · {{ run.failed }} failed · {{ run.total }} total</div>
                    </div>
                    <div class="bulk-history-ts">{{ fmtDate(run.ts) }}</div>
                  </div>
                </div>
              </div>
              <div v-else class="bulk-history-empty">
                <q-icon name="history" size="16px" class="q-mr-xs" />No bulk generation runs yet for this source.
              </div>

              <!-- Banner -->
              <transition name="bulk-banner">
                <div v-if="bulkBanner && srcActiveTab === 'bulk-ai'" class="bulk-banner" :class="`bulk-banner--${bulkBanner.type}`">
                  <q-icon :name="bulkBanner.type === 'success' ? 'check_circle' : bulkBanner.type === 'error' ? 'error' : 'info'" size="14px" class="q-mr-xs" />
                  {{ bulkBanner.msg }}
                  <button class="bulk-banner-close" @click="bulkBanner = null"><q-icon name="close" size="12px" /></button>
                </div>
              </transition>
            </div>

            <!-- ══ DOCUMENTS TAB ══════════════════════════════════════════════ -->
            <div v-show="srcActiveTab === 'documents'" class="docs-tab">

              <!-- Header row -->
              <div class="docs-header-row">
                <div>
                  <div class="docs-title">Source Documents</div>
                  <div class="docs-subtitle">Upload data dictionaries, mapping specs, and system documentation. {{ assistantName }} uses these to ground definitions, suggest BIRD mappings, and infer quality rules — with your explicit permission for each use.</div>
                </div>
                <button class="docs-upload-btn" @click="showUploadModal = true">
                  <q-icon name="upload" size="14px" class="q-mr-xs" />Upload document
                </button>
              </div>

              <!-- Compliance notice -->
              <div class="docs-compliance">
                <q-icon name="shield" size="14px" class="docs-compliance-icon" />
                <span><strong>Compliance notice:</strong> Documents are stored encrypted at rest (AES-256) and in transit (TLS 1.3). AI processing runs only on fields you explicitly enable — no content is used for model training. All access and processing events are logged with user identity and timestamp in the immutable audit trail. Documents containing personal data must be anonymised before upload per GDPR Article 25 (data minimisation).</span>
              </div>

              <!-- Toolbar -->
              <div class="docs-toolbar">
                <div class="docs-search-wrap">
                  <q-icon name="search" size="13px" class="docs-search-icon" />
                  <input v-model="docSearch" placeholder="Search documents…" class="docs-search-input" />
                </div>
                <div class="docs-filter-chips">
                  <button class="docs-fchip" :class="{ 'docs-fchip--on': docFilter === 'all' }" @click="docFilter = 'all'">All</button>
                  <button class="docs-fchip" :class="{ 'docs-fchip--on': docFilter === 'Data Dictionary' }" @click="docFilter = 'Data Dictionary'">Data Dictionary</button>
                  <button class="docs-fchip" :class="{ 'docs-fchip--on': docFilter === 'Mapping Spec' }" @click="docFilter = 'Mapping Spec'">Mapping Spec</button>
                  <button class="docs-fchip" :class="{ 'docs-fchip--on': docFilter === 'System Spec' }" @click="docFilter = 'System Spec'">System Spec</button>
                  <button class="docs-fchip" :class="{ 'docs-fchip--on': docFilter === 'Quality Rules' }" @click="docFilter = 'Quality Rules'">Quality Rules</button>
                </div>
              </div>

              <!-- Document list -->
              <div v-if="filteredDocs.length === 0" class="docs-empty">
                <q-icon name="description" size="32px" class="q-mb-sm" style="color:#c9c3ba" />
                <div style="font-size:13px;color:#86827a">No documents uploaded yet.</div>
                <div style="font-size:12px;color:#a8a49a;margin-top:4px">Upload a data dictionary or mapping spec to help {{ assistantName }} understand this source.</div>
              </div>

              <div v-else class="docs-list">
                <div v-for="doc in filteredDocs" :key="doc.id" class="docs-card" :class="{ 'docs-card--open': selectedDocId === doc.id }">
                  <div class="docs-card-row" @click="openDoc(doc.id)">
                    <div class="docs-card-icon">
                      <q-icon name="description" size="16px" />
                    </div>
                    <div class="docs-card-body">
                      <div class="docs-card-name">{{ doc.name }}</div>
                      <div class="docs-card-meta">
                        <span class="docs-type-badge">{{ doc.type }}</span>
                        <span>{{ doc.scope }}</span>
                        <span>{{ doc.owner }}</span>
                        <span>{{ fmtDate(doc.uploadedAt) }}</span>
                      </div>
                    </div>
                    <span class="docs-status-badge" :class="`docs-status--${doc.status}`">
                      <q-spinner-dots v-if="doc.status === 'processing'" size="10px" class="q-mr-xs" />
                      {{ doc.status }}
                    </span>
                    <div class="docs-ai-perms">
                      <span v-if="doc.aiPermissions.definitions" class="docs-perm-chip">Definitions</span>
                      <span v-if="doc.aiPermissions.mapping" class="docs-perm-chip">Mapping</span>
                      <span v-if="doc.aiPermissions.quality" class="docs-perm-chip">Quality rules</span>
                    </div>
                    <q-icon :name="selectedDocId === doc.id ? 'expand_less' : 'expand_more'" size="16px" style="color:#86827a;flex:0 0 auto" />
                  </div>

                  <!-- Expanded: AI Knowledge Preview -->
                  <transition name="bulk-banner">
                    <div v-if="selectedDocId === doc.id" class="docs-ai-preview">
                      <div class="docs-ai-preview-header">
                        <q-icon name="auto_awesome" size="14px" class="q-mr-xs" style="color:var(--accent)" />
                        <span class="docs-ai-preview-title">{{ assistantName }}'s Understanding</span>
                        <span class="docs-ai-preview-badge">
                          <span v-if="doc.status === 'processing'">Processing…</span>
                          <span v-else-if="doc.aiKnowledge">AI-extracted</span>
                          <span v-else>No extraction yet</span>
                        </span>
                      </div>
                      <div v-if="doc.status === 'processing'" class="docs-ai-preview-body docs-ai-preview-body--loading">
                        <q-spinner-dots size="14px" class="q-mr-sm" />{{ assistantName }} is reading this document…
                      </div>
                      <div v-else-if="doc.aiKnowledge" class="docs-ai-preview-body">
                        <p>{{ doc.aiKnowledge }}</p>
                        <div class="docs-ai-preview-actions">
                          <button class="docs-ai-action-btn">
                            <q-icon name="edit" size="12px" class="q-mr-xs" />Edit extraction
                          </button>
                          <button class="docs-ai-action-btn">
                            <q-icon name="refresh" size="12px" class="q-mr-xs" />Re-process
                          </button>
                          <button class="docs-ai-action-btn docs-ai-action-btn--accept">
                            <q-icon name="check" size="12px" class="q-mr-xs" />Accept &amp; apply
                          </button>
                        </div>
                      </div>
                      <div v-else class="docs-ai-preview-body docs-ai-preview-body--empty">
                        <q-icon name="info_outline" size="14px" class="q-mr-xs" />No AI knowledge extracted for this document. Enable AI permissions and re-upload to generate an extraction.
                      </div>
                    </div>
                  </transition>
                </div>
              </div>
            </div>

          </div><!-- end src-body -->
        </template>

        <template v-else-if="viewMode === 'table' && store.datasetOverview">
          <div class="ds-header">
            <div class="ds-title-row">
              <span class="ds-name">{{ store.datasetOverview.table_name }}</span>
              <span v-if="!store.datasetOverview.is_profiled" class="unprofiled-badge" aria-label="Never profiled">
                R
                <q-tooltip>Never profiled — freshly onboarded, or reset back to its pre-profiling baseline. Click "Refresh Profile" to run the first profiling pass.</q-tooltip>
              </span>
              <span class="ds-col-count">{{ store.datasetOverview.column_count }} columns</span>
            </div>
            <!-- Primary Key + "Referenced by" cluster on one row: this table's
                 own PK, then who else points AT it (was the separate, confusingly
                 labelled "Parent FK" row — that label/row is gone). Exactly one
                 referencer shows inline; the count itself is the expand/collapse
                 control once there's more than one (no separate "See" link). -->
            <div v-if="store.datasetOverview.primary_key?.length" class="ds-pk-row">
              <span class="rail-key-badge q-mr-xs" aria-hidden="true">🔑</span>
              <span class="ds-pk-label">Primary Key:</span>
              <span v-for="k in store.datasetOverview.primary_key" :key="k" class="ds-pk-chip mono">{{ k }}</span>
              <q-icon name="fiber_manual_record" size="6px" class="ds-rel-dot" />
              <template v-if="(store.datasetOverview.referenced_by?.length ?? 0) > 1">
                <span class="ds-rel-summary">
                  Referenced by
                  <button type="button" class="ds-rel-count-pill" @click="referencedByExpanded = !referencedByExpanded">{{ store.datasetOverview.referenced_by!.length }}</button>
                  child entities
                </span>
              </template>
              <template v-else-if="store.datasetOverview.referenced_by?.length === 1">
                <span class="ds-rel-summary">
                  Referenced by 1 child entity:
                  <span
                    v-for="rb in store.datasetOverview.referenced_by"
                    :key="'rb-' + rb.table + rb.columns.join(',')"
                    class="ds-pk-chip ds-rb-chip mono"
                    :class="{ 'ds-rb-chip--inferred': !rb.declared }"
                    @click="navigateToDataset(store.datasetOverview!.source, rb.table, rb.schema)"
                  >
                    <q-icon name="arrow_back" size="10px" class="q-mr-xs" />{{ rb.table }}.{{ rb.columns.join(', ') }}
                    <q-icon v-if="!rb.declared" name="rule" size="9px" class="q-ml-xs" />
                    <q-tooltip>
                      <template v-if="rb.declared">Referenced by {{ rb.table }} (declared constraint) — jump there</template>
                      <template v-else>Inferred — deterministic name/type match ({{ fkBasisLabel(rb.basis) }}, {{ rb.confidence }} confidence), not AI. Referenced by {{ rb.table }} — jump there</template>
                    </q-tooltip>
                  </span>
                </span>
              </template>
              <span v-else class="ds-rel-summary ds-rel-none">Referenced by 0 child entities</span>
            </div>
            <div v-else-if="store.datasetOverview.inferred_primary_key?.length" class="ds-pk-row ds-pk-row--inferred">
              <span class="rail-key-badge rail-key-badge--candidate q-mr-xs" aria-hidden="true">🔑</span>
              <span class="ds-pk-label">Candidate key:</span>
              <span v-for="k in store.datasetOverview.inferred_primary_key" :key="k" class="ds-pk-chip ds-pk-chip--inferred mono">{{ k }}</span>
              <q-icon name="info" size="11px" class="q-ml-xs" style="color:#7c8fa6">
                <q-tooltip>No PRIMARY KEY constraint is declared. These columns satisfy uniqueness + no-null criteria and are used as candidate keys for quality checks.</q-tooltip>
              </q-icon>
            </div>
            <div
              v-if="(store.datasetOverview.referenced_by?.length ?? 0) > 1 && referencedByExpanded"
              class="ds-pk-row ds-rel-chip-row"
            >
              <span
                v-for="rb in store.datasetOverview.referenced_by"
                :key="'rb-' + rb.table + rb.columns.join(',')"
                class="ds-pk-chip ds-rb-chip mono"
                :class="{ 'ds-rb-chip--inferred': !rb.declared }"
                @click="navigateToDataset(store.datasetOverview!.source, rb.table, rb.schema)"
              >
                <q-icon name="arrow_back" size="10px" class="q-mr-xs" />{{ rb.table }}.{{ rb.columns.join(', ') }}
                <q-icon v-if="!rb.declared" name="rule" size="9px" class="q-ml-xs" />
                <q-tooltip>
                  <template v-if="rb.declared">Referenced by {{ rb.table }} (declared constraint) — jump there</template>
                  <template v-else>Inferred — deterministic name/type match ({{ fkBasisLabel(rb.basis) }}, {{ rb.confidence }} confidence), not AI. Referenced by {{ rb.table }} — jump there</template>
                </q-tooltip>
              </span>
            </div>

            <!-- Foreign Key — this dataset is the child (has its own FK pointing
                 at another table). This is exactly the DQ scoring's fk_applies
                 signal, so "0" here lines up with a "Dataset integrity N/A"
                 explanation below. (Was "Child FK" — relabelled for clarity;
                 mirrors the Primary Key row's inline/count-pill behaviour.) -->
            <div class="ds-pk-row ds-rel-row">
              <span class="rail-fk-badge q-mr-xs" :class="{ 'rail-fk-badge--orphan': totalOrphanFkCount > 0 }" aria-hidden="true">🔗</span>
              <template v-if="(store.datasetOverview.foreign_keys?.length ?? 0) > 1">
                <span class="ds-pk-label" style="color:#2f5d8a">
                  Foreign Key:
                  <button type="button" class="ds-rel-count-pill ds-rel-count-pill--fk" @click="foreignKeysExpanded = !foreignKeysExpanded">{{ store.datasetOverview.foreign_keys!.length }}</button>
                </span>
                <span v-if="totalOrphanFkCount > 0" class="ds-orphan-pill">⚠ {{ totalOrphanFkCount }} orphan key{{ totalOrphanFkCount === 1 ? '' : 's' }}</span>
              </template>
              <template v-else-if="store.datasetOverview.foreign_keys?.length === 1">
                <span class="ds-pk-label" style="color:#2f5d8a">Foreign Key: 1</span>
                <span
                  v-for="fk in store.datasetOverview.foreign_keys"
                  :key="'fk-' + fk.column"
                  class="ds-pk-chip ds-fk-chip mono"
                  :class="{ 'ds-fk-chip--inferred': !fk.declared, 'ds-fk-chip--orphan': (fk.orphan_count ?? 0) > 0 }"
                  @click="navigateToDataset(store.datasetOverview!.source, fk.references_table, store.datasetOverview!.schema)"
                >
                  <q-icon name="arrow_forward" size="10px" class="q-mr-xs" />{{ fk.column }} → {{ fk.references_table }}.{{ fk.references_column }}
                  <q-icon v-if="!fk.declared" name="rule" size="9px" class="q-ml-xs" />
                  <q-tooltip>
                    <template v-if="fk.declared">Foreign key (declared constraint) — jump to {{ fk.references_table }}</template>
                    <template v-else>Inferred foreign key — deterministic name/type match ({{ fkBasisLabel(fk.basis) }}, {{ fk.confidence }} confidence), not AI, no DB constraint declared. Jump to {{ fk.references_table }}</template>
                  </q-tooltip>
                </span>
                <span v-if="totalOrphanFkCount > 0" class="ds-orphan-pill">⚠ {{ totalOrphanFkCount }} orphan key{{ totalOrphanFkCount === 1 ? '' : 's' }}</span>
              </template>
              <span v-else class="ds-pk-label" style="color:#2f5d8a">Foreign Key: 0</span>
            </div>
            <div
              v-if="(store.datasetOverview.foreign_keys?.length ?? 0) > 1 && foreignKeysExpanded"
              class="ds-pk-row ds-rel-chip-row"
            >
              <span
                v-for="fk in store.datasetOverview.foreign_keys"
                :key="'fk-' + fk.column"
                class="ds-pk-chip ds-fk-chip mono"
                :class="{ 'ds-fk-chip--inferred': !fk.declared, 'ds-fk-chip--orphan': (fk.orphan_count ?? 0) > 0 }"
                @click="navigateToDataset(store.datasetOverview!.source, fk.references_table, store.datasetOverview!.schema)"
              >
                <q-icon name="arrow_forward" size="10px" class="q-mr-xs" />{{ fk.column }} → {{ fk.references_table }}.{{ fk.references_column }}
                <q-icon v-if="!fk.declared" name="rule" size="9px" class="q-ml-xs" />
                <q-tooltip>
                  <template v-if="fk.declared">Foreign key (declared constraint) — jump to {{ fk.references_table }}</template>
                  <template v-else>Inferred foreign key — deterministic name/type match ({{ fkBasisLabel(fk.basis) }}, {{ fk.confidence }} confidence), not AI, no DB constraint declared. Jump to {{ fk.references_table }}</template>
                </q-tooltip>
              </span>
            </div>
            <div class="ds-sub">Statistics are captured automatically at each ingest run and describe this table as a whole. Click any field below to explore its detail.</div>
            <div v-if="store.datasetOverview.description" class="ds-desc">{{ store.datasetOverview.description }}</div>

            <!-- Bulk generation banner -->
            <transition name="bulk-banner">
              <div v-if="bulkBanner" class="bulk-banner" :class="`bulk-banner--${bulkBanner.type}`">
                <q-icon :name="bulkBanner.type === 'success' ? 'check_circle' : bulkBanner.type === 'error' ? 'error' : 'info'" size="14px" class="q-mr-xs" />
                {{ bulkBanner.msg }}
                <button class="bulk-banner-close" @click="bulkBanner = null">
                  <q-icon name="close" size="12px" />
                </button>
              </div>
            </transition>

            <!-- Legend footer -->
            <div class="ds-legend-row">
              <div class="ds-legend-group dq-grade-legend dq-grade-legend--inline">
                <span class="ds-legend-label">DQ Grade</span>
                <template v-for="(b, i) in DQ_GRADE_BANDS" :key="b.label">
                  <span class="dq-grade-legend-item">
                    <span class="ds-legend-pip" :class="`dq-band-fill--${b.colorIntent}`" />
                    <b class="dq-grade-legend-label" :class="`dq-band--${b.colorIntent}`">{{ b.label }}</b>
                    <q-tooltip>{{ b.max != null ? `${b.min}–${b.max}` : `${b.min}+` }}</q-tooltip>
                  </span>
                  <span v-if="i < DQ_GRADE_BANDS.length - 1" class="dq-grade-legend-sep">·</span>
                </template>
              </div>
              <div class="ds-legend-group">
                <span class="ds-legend-label">Governance State</span>
                <span class="ds-legend-item">
                  <span class="ds-legend-pip" style="background:var(--empty-col)" />Empty
                  <q-tooltip>Not started yet</q-tooltip>
                </span>
                <span class="ds-legend-item">
                  <span class="ds-legend-pip" style="background:var(--draft-col)" />Draft
                  <q-tooltip>Not submitted yet</q-tooltip>
                </span>
                <span class="ds-legend-item">
                  <span class="ds-legend-pip" style="background:var(--in-review-col)" />In-Review
                  <q-tooltip>Submitted for review</q-tooltip>
                </span>
                <span class="ds-legend-item">
                  <span class="ds-legend-pip" style="background:var(--approved-col)" />Approved
                  <q-tooltip>Reviewed and approved by a steward</q-tooltip>
                </span>
                <span class="ds-legend-item">
                  <span class="ds-legend-pip" style="background:var(--bounced-col)" />Bounced
                  <q-tooltip>Reviewed but not approved</q-tooltip>
                </span>
              </div>
            </div>

            <!-- Tab bar -->
            <div class="tab-bar">
              <button class="tab-btn" :class="{ 'tab-btn--active': dsActiveTab === 'overview' }" @click="dsActiveTab = 'overview'">Overview</button>
              <button v-if="store.datasetOverview" class="tab-btn" :class="{ 'tab-btn--active': dsActiveTab === 'insights' }" @click="dsActiveTab = 'insights'">DQ Insights</button>
              <button class="tab-btn" :class="{ 'tab-btn--active': dsActiveTab === 'bulk-ai' }" @click="dsActiveTab = 'bulk-ai'">
                <q-icon name="auto_awesome" size="13px" class="q-mr-xs" />Bulk AI Assistance
                <span v-if="dsMissingDescriptions.length + dsMissingBusinessNames.length > 0" class="tab-badge tab-badge--warn">{{ dsMissingDescriptions.length + dsMissingBusinessNames.length }}</span>
              </button>
              <button class="tab-btn" :class="{ 'tab-btn--active': dsActiveTab === 'scoping' }" @click="dsActiveTab = 'scoping'">
                <q-icon name="rule" size="13px" class="q-mr-xs" />Scoping
                <span v-if="scopeSuggestedColumns.length > 0" class="tab-badge tab-badge--warn">{{ scopeSuggestedColumns.length }}</span>
              </button>
              <div class="tab-bar-spacer" />
              <div class="tab-bar-meta">
                <span v-if="store.datasetOverview.profiled_at" class="tab-bar-profiled">
                  <q-icon name="schedule" size="11px" class="q-mr-xs" />Last profiled at {{ fmtDate(store.datasetOverview.profiled_at) }}
                </span>
                <q-btn flat dense no-caps color="primary" icon="refresh" label="Refresh Profile" size="sm" :loading="refreshingProfile" @click="refreshProfile">
                  <q-tooltip>Re-profile this table from the live database and save the updated stats permanently</q-tooltip>
                </q-btn>
                <q-btn v-if="store.datasetOverview.generated_at" flat dense no-caps color="negative" icon="restart_alt" label="Reset Profile" size="sm" :disabled="resetTableState.running" @click="promptResetTable">
                  <q-tooltip>Clear all profiling and governance state for this table back to its pre-profiling baseline</q-tooltip>
                </q-btn>
              </div>
            </div>

            <!-- Table-level reset warning dialog -->
            <transition name="bulk-banner">
              <div v-if="resetTableState.showWarning" class="rebuild-warn-dialog">
                <div class="rebuild-warn-icon"><q-icon name="warning_amber" size="22px" color="orange" /></div>
                <div class="rebuild-warn-body">
                  <div class="rebuild-warn-title">Reset Profile — this cannot be undone</div>
                  <div class="rebuild-warn-msg">
                    This clears ALL profiling and governance state for <strong>{{ selectedTable }}</strong> —
                    profile stats, semantic types, DQ score, Interpretation (descriptions, business name,
                    review status), Reference Data, reference-set binding, and annotations. The table returns
                    to the same blank state it had right after onboarding, before it was ever profiled. Schema,
                    column names/types, and declared keys are kept. This runs as one all-or-nothing operation —
                    if anything fails, nothing changes.
                  </div>
                  <div class="rebuild-warn-actions">
                    <button class="rebuild-confirm-btn rebuild-confirm-btn--danger" @click="startResetTable">Reset this table</button>
                    <button class="rebuild-cancel-btn" @click="resetTableState.showWarning = false">Cancel</button>
                  </div>
                </div>
              </div>
            </transition>

            <!-- Table-level reset progress panel -->
            <transition name="bulk-banner">
              <div v-if="resetTableState.running || resetTableState.done" class="rebuild-progress-panel">
                <div class="rebuild-prog-header">
                  <q-icon :name="resetTableState.done ? (resetTableState.failed ? 'warning' : 'check_circle') : 'sync'"
                    size="15px" class="q-mr-xs"
                    :style="{ color: resetTableState.done ? (resetTableState.failed ? '#a87232' : 'var(--approved-col)') : 'var(--accent)', animation: resetTableState.running ? 'spin 1.5s linear infinite' : 'none' }" />
                  <span class="rebuild-prog-title">
                    {{ resetTableState.done
                      ? (resetTableState.failed ? 'Reset failed — rolled back, nothing changed' : 'Reset complete')
                      : `Resetting — ${resetStepLabel(resetTableState.currentStep)}` }}
                  </span>
                  <button v-if="resetTableState.done" class="rebuild-abort-btn" @click="resetTableState.done = false" title="Dismiss">
                    <q-icon name="close" size="12px" />
                  </button>
                </div>
                <div class="rebuild-prog-bar-wrap">
                  <div class="rebuild-prog-bar"
                    :style="{ width: resetTableState.stepsTotal > 0 ? Math.min(100, resetTableState.stepsCompleted / resetTableState.stepsTotal * 100).toFixed(1) + '%' : '0%' }"
                    :class="{ 'rebuild-prog-bar--done': resetTableState.done, 'rebuild-prog-bar--error': resetTableState.done && resetTableState.failed }"
                  />
                </div>
                <div v-if="resetTableState.failed" class="rebuild-warn-msg" style="margin-top:6px">{{ resetTableState.errorMessage }}</div>
              </div>
            </transition>
          </div>

          <div class="ds-body">
            <!-- OVERVIEW TAB -->
            <div v-show="dsActiveTab === 'overview'">

            <!-- Data Story narrative -->
            <div class="panel-card q-pa-md q-mb-md ds-narrative-card">
              <div class="desc-view" style="align-items: flex-start">
                <div class="desc-content" style="flex: 1; min-width: 0">
                  <div class="panel-card-title q-mb-sm">
                    Data Story
                    <span v-if="store.dataStory?.is_ai_generated && !storyEditMode" class="ds-panel-caption q-ml-sm">
                      <q-icon name="auto_awesome" size="10px" class="q-mr-xs" />AI-GENERATED
                    </span>
                  </div>

                  <!-- No story yet — view mode -->
                  <template v-if="!store.dataStory?.narrative && !storyEditMode">
                    <div v-if="store.loadingDataStory" class="ds-narrative-empty">
                      <q-spinner-dots size="11px" class="q-mr-xs" />Generating…
                    </div>
                    <div v-else class="desc-empty">Write a data story for this dataset…</div>
                  </template>

                  <!-- Story exists — view mode -->
                  <template v-else-if="store.dataStory?.narrative && !storyEditMode">
                    <div class="ds-narrative-body">
                      {{ store.dataStory.narrative }}
                      <div v-if="store.dataStory.tagline" class="ds-narrative-tagline"><b>Data Grain: </b>{{ store.dataStory.tagline }}</div>
                    </div>
                  </template>

                  <!-- Edit mode -->
                  <template v-else-if="storyEditMode">
                    <textarea v-model="storyNarrativeEdit" class="ds-story-textarea" rows="5" placeholder="Data story narrative…" />
                    <input v-model="storyTaglineEdit" class="ds-story-tagline-input" placeholder="One-sentence tagline…" />
                    <div class="ds-story-edit-actions">
                      <button class="ds-story-save-btn" :disabled="storySaving" @click="saveStory">
                        <q-spinner-dots v-if="storySaving" size="11px" class="q-mr-xs" />
                        <q-icon v-else name="save" size="13px" class="q-mr-xs" />
                        Save
                      </button>
                      <button class="ds-story-ai-btn" :disabled="store.loadingDataStory" @click="runGenerateDataStory">
                        <q-spinner-dots v-if="store.loadingDataStory" size="11px" class="q-mr-xs" />
                        <q-icon v-else name="auto_awesome" size="13px" class="q-mr-xs" />
                        <span v-if="store.loadingDataStory">Generating…</span>
                        <span v-else>Draft with AI</span>
                      </button>
                      <button class="ds-story-cancel-btn" @click="cancelEditStory">
                        <q-icon name="close" size="13px" class="q-mr-xs" />Cancel
                      </button>
                    </div>
                  </template>

                  <!-- Save confirmation banner -->
                  <div v-if="storySavedBanner" class="ds-story-saved-banner">
                    <q-icon name="check_circle" size="13px" class="q-mr-xs" />Data story saved.
                  </div>
                  <div v-if="storySaveError" class="ds-story-save-error">
                    <q-icon name="error_outline" size="13px" class="q-mr-xs" />Save failed — check the server connection.
                  </div>
                </div>

                <!-- Edit icon always visible in top-right; copy only when story exists -->
                <div v-if="!storyEditMode" class="desc-icons">
                  <button class="icon-btn" title="Edit data story" @click="startEditStory">
                    <q-icon name="edit" size="16px" />
                  </button>
                  <button v-if="store.dataStory?.narrative" class="icon-btn" title="Copy to clipboard" @click="copyStory">
                    <q-icon name="content_copy" size="16px" />
                  </button>
                </div>
              </div>
            </div>

            <KpiStripCard :kpis="dsKpis" class="q-mb-md" />

            <!-- Semantic Type Mix + Governance State + DQ Grade Distribution:
                 one row, three shared proportional-bar cards. Semantic types
                 keep their categorical identity colours; governance reads the
                 sequential journey ramp; DQ grades read the diverging ramp. -->
            <div class="ds-charts-row-3 q-mb-md">
              <ProportionalBarCard
                title="Semantic Type Mix"
                :caption="`${store.datasetOverview.column_count} COLS`"
                :segments="dsSemanticSegments"
              />
              <ProportionalBarCard
                title="Governance State"
                :caption="`${store.datasetOverview.column_count} ELEMENTS`"
                :segments="dsGovernanceSegments"
                :hints="GOV_LEGEND_HINTS"
              />
              <ProportionalBarCard
                title="DQ Grade Distribution"
                :caption="`${store.datasetOverview.column_count} COLS`"
                :segments="dsDqGradeSegments"
              />
            </div>

            <div class="ds-charts-row q-mb-md">
              <ProportionalBarCard
                title="Semantic Resolution"
                caption="BLOCKS SUBMISSION UNTIL ACCEPTED"
                :segments="dsSemanticStateSegments"
                :hints="SEM_STATE_HINTS"
              />
              <SplitBarCard
                title="AI Assistance"
                caption="WHO AUTHORED IT"
                :rows="dsAiAssistRows"
              />
            </div>

            <!-- Columns Table -->
            <div class="panel-card q-pa-md q-mb-md">
              <div class="panel-card-title q-mb-sm">Columns</div>
              <table class="col-table">
                <thead>
                  <tr>
                    <th class="col-num-th">#</th>
                    <th>Column</th>
                    <th>Type</th>
                    <th>Semantic</th>
                    <th>Completeness</th>
                    <th>DQ</th>
                    <th>Actions</th>
                    <th>State</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(c, idx) in store.datasetOverview.columns_summary"
                    :key="c.name"
                    class="col-row"
                    @click="selectColumnFromOverview(c)"
                  >
                    <td class="col-num-cell">{{ idx + 1 }}</td>
                    <td class="mono col-name-cell">
                      {{ c.name }}
                      <span v-if="store.datasetOverview.primary_key?.includes(c.name)" class="col-key-badge" aria-label="Primary key">
                        🔑
                        <q-tooltip>Primary key</q-tooltip>
                      </span>
                      <span v-else-if="store.datasetOverview.inferred_primary_key?.includes(c.name)" class="col-key-badge col-key-badge--candidate" aria-label="Candidate key">
                        🔑
                        <q-tooltip>Candidate key (inferred — no PK constraint declared)</q-tooltip>
                      </span>
                      <span
                        v-if="c.foreign_key"
                        class="col-fk-badge"
                        :class="{ 'col-fk-badge--inferred': !c.foreign_key.declared }"
                        aria-label="Foreign key"
                      >
                        🔗
                        <q-tooltip>
                          <template v-if="c.foreign_key.declared">Foreign key → {{ c.foreign_key.references_table }}.{{ c.foreign_key.references_column }}</template>
                          <template v-else>Inferred FK — deterministic name/type match ({{ fkBasisLabel(c.foreign_key.basis) }}, {{ c.foreign_key.confidence }} confidence), not AI → {{ c.foreign_key.references_table }}.{{ c.foreign_key.references_column }} — no DB constraint declared</template>
                        </q-tooltip>
                      </span>
                    </td>
                    <td class="col-type-cell">{{ c.data_type }}</td>
                    <td class="col-sem-cell">{{ semTypeLabel(c.semantic_type) }}</td>
                    <td>
                      <template v-if="c.completeness != null">
                        <div class="col-comp-bar">
                          <div class="col-comp-fill" :style="{ width: fmtPct(c.completeness) + '%' }" />
                        </div>
                        <span class="col-comp-pct">{{ fmtPct(c.completeness) }}%</span>
                      </template>
                      <span v-else class="col-comp-pct">—</span>
                    </td>
                    <td>
                      <span v-if="railDqBadge(c.dq).scored" class="rail-dq" :class="railDqBadge(c.dq).bandClass">{{ c.dq?.grade_label }}</span>
                      <span v-else-if="railDqBadge(c.dq).excluded" class="rail-dq rail-dq--excluded" title="Excluded from assessment">
                        <q-icon name="block" size="10px" />
                      </span>
                      <span v-else class="scoping-dq-none">—</span>
                    </td>
                    <td>
                      <button
                        v-if="(c.dq?.action_count ?? 0) > 0"
                        type="button"
                        class="col-actions-badge col-actions-link"
                        title="Open this column's DQ Insights → Actions to improve"
                        @click.stop="openColumnActions(c)"
                      >
                        <q-icon name="build" size="10px" />{{ c.dq?.action_count }}
                      </button>
                      <span v-else class="scoping-dq-none">—</span>
                    </td>
                    <td><span class="rail-state-badge" :class="`rail-state--${c.lifecycle_state}`">{{ c.lifecycle_state }}</span></td>
                  </tr>
                </tbody>
              </table>
            </div>

            <!-- Footnotes removed — legend is in the dataset header -->
            </div>

            <!-- INSIGHTS TAB -->
            <div v-show="dsActiveTab === 'insights'" class="tab-panel q-ma-md">
              <!-- Dataset Quality roll-up (U4a · DQ §15) — this table's columns
                   roll up into one dataset DQ badge; separate from the per-column
                   (element) DQ card. Sits above the observations/findings below
                   since the score is the headline of DQ Insights. -->
              <div class="dq-card panel-card q-mb-md ds-dq-card">
                <div class="ds-dq-title-row">
                  <span class="panel-card-title">Dataset Quality</span>
                  <span v-if="datasetDq?.scored_at" class="ds-panel-caption">
                    Last evaluated {{ fmtDate(datasetDq.scored_at) }}
                  </span>
                </div>
                <template v-if="isDatasetScored(datasetDq)">
                  <div class="dq-card-main">
                    <div class="dq-donut-wrap">
                      <svg class="dq-donut" viewBox="0 0 120 120">
                        <g transform="rotate(-90 60 60)">
                          <circle
                            v-for="arc in datasetDqDonut.arcs" :key="`dt-${arc.name}`"
                            class="dq-arc-track" :class="`dq-arc--${arc.colorKey}`"
                            cx="60" cy="60" :r="datasetDqDonut.radius" fill="none"
                            :stroke-dasharray="arc.trackDash" :stroke-dashoffset="arc.dashOffset"
                          />
                          <circle
                            v-for="arc in datasetDqDonut.arcs" :key="`df-${arc.name}`"
                            class="dq-arc-fill" :class="`dq-arc--${arc.colorKey}`"
                            cx="60" cy="60" :r="datasetDqDonut.radius" fill="none"
                            :stroke-dasharray="arc.fillDash" :stroke-dashoffset="arc.dashOffset"
                          />
                        </g>
                        <text x="60" y="68" class="dq-donut-score" text-anchor="middle">{{ datasetScorePreciseText(datasetDq) }}</text>
                      </svg>
                    </div>
                    <div class="dq-legend">
                      <div class="dq-legend-head dq-legend-head--actions">
                        <!-- Trend delta (§14) lives inside the score pill itself
                             — e.g. "79 · Good (+2 ⬆)" — no separate sentence. -->
                        <span class="dq-band-pill" :class="datasetBandClass(datasetDq)">
                          {{ datasetBadgeText(datasetDq) }}<span v-if="datasetDqTrendDelta" class="ds-dq-trend-delta"> · {{ datasetDqTrendDelta }}</span>
                        </span>
                      </div>
                      <div v-for="c in datasetDqLegend" :key="c.name" class="dq-legend-row">
                        <span class="dq-dot" :class="`dq-arc--${c.colorKey}`" />
                        <span class="dq-legend-label">{{ c.label }}</span>
                        <span class="dq-legend-val mono">{{ c.earned }}/{{ c.max }}</span>
                        <span v-if="c.gradeLabel" class="dq-legend-band" :class="`dq-band--${c.gradeColorIntent || 'neutral'}`">{{ c.gradeLabel }}</span>
                      </div>
                      <!-- Explicit N/A row (§7 follow-up) — otherwise "Dataset
                           integrity" just silently never appears, which reads
                           as a bug rather than a deliberate rule. -->
                      <div v-if="datasetIntegrityNotApplicable" class="dq-legend-row dq-legend-row--na">
                        <span class="dq-dot dq-dot--na" />
                        <span class="dq-legend-label">Dataset integrity</span>
                        <span class="dq-legend-val mono">N/A *</span>
                      </div>
                    </div>
                  </div>

                  <!-- Plain-English score derivation — how the 0–100 composite is
                       built, for anyone unfamiliar with the model. -->
                  <div class="ds-dq-explainer">
                    <template v-if="datasetIntegrityNotApplicable">
                      * Dataset integrity is not applicable since this table has neither a
                      composite primary key nor any foreign key. The Average DQ Score is
                      evaluated on 100 instead of 85.
                    </template>
                    <template v-else>
                      How it's calculated: the average DQ score across this table's columns
                      (worth {{ datasetDqLegend[0]?.max ?? 85 }} of 100 points) plus dataset-level
                      integrity checks like duplicate keys and orphan foreign keys
                      (worth {{ datasetDqLegend[1]?.max ?? 15 }} of 100 points).
                    </template>
                  </div>

                  <!-- Which columns dragged the roll-up down (lowest first) + integrity. -->
                  <div class="dq-breakdown">
                    <div class="dq-comp-block">
                      <div class="dq-comp-head">
                        <span class="dq-dot dq-arc--rollup" />
                        <span class="dq-comp-title">Columns dragging the score down</span>
                      </div>
                      <div v-if="!dqDraggerRows.length" class="ds-dq-contrib-empty">
                        All columns are in Good or Excellent DQ grade, so nothing to show below.
                      </div>
                      <div v-for="ct in dqDraggerRows" :key="ct.key" class="ds-dq-contrib">
                        <button
                          type="button" class="ds-dq-contrib-name ds-dq-contrib-link mono"
                          @click="ct.column ? selectColumnFromOverview(ct.column, 'observations') : undefined"
                        >
                          {{ ct.key }}
                          <q-icon name="open_in_new" size="10px" class="q-ml-xs" />
                        </button>
                        <span class="ds-dq-contrib-grade mono" :class="`dq-band--${ct.grade_color_intent || 'neutral'}`">{{ ct.dq_score }} · {{ ct.grade_label || 'Not scored' }}</span>
                        <span class="ds-dq-contrib-actions" :class="{ 'ds-dq-contrib-actions--none': !ct.action_count }">
                          <q-icon name="build" size="11px" class="q-mr-xs" />{{ ct.action_count || 0 }} action{{ ct.action_count === 1 ? '' : 's' }}
                        </span>
                      </div>
                    </div>
                    <div v-if="datasetDqIntegrity.length" class="dq-comp-block">
                      <div class="dq-comp-head">
                        <span class="dq-dot dq-arc--integrity" />
                        <span class="dq-comp-title">Dataset integrity</span>
                      </div>
                      <div v-for="li in datasetDqIntegrity" :key="li.label" class="dq-li">
                        <div class="dq-li-top">
                          <span class="dq-li-label">{{ li.label }}</span>
                          <span class="dq-li-val mono">{{ li.earned }}/{{ li.max }}</span>
                        </div>
                        <div v-if="li.evidence_note" class="dq-li-note">{{ li.evidence_note }}</div>
                      </div>
                    </div>
                  </div>
                </template>
                <div v-else-if="isFullyDescoped(datasetDq)" class="dq-card-empty dq-card-empty--excluded">
                  <q-icon name="block" size="18px" class="q-mr-xs" />
                  Fully descoped — every column in this table is out of scope, so the dataset is not scored.
                </div>
                <div v-else class="dq-card-empty">
                  <q-icon name="donut_large" size="18px" class="q-mr-xs" />
                  {{ datasetBandLabel(datasetDq) }} — no dataset quality score yet.
                </div>
              </div>
            </div>

            <!-- BULK AI DRAFT TAB (dataset level) -->
            <div v-show="dsActiveTab === 'bulk-ai'" class="bulk-ai-tab tab-panel q-ma-md">

              <!-- Stats -->
              <div class="bulk-stats-row">
                <div class="bulk-stat-card">
                  <div class="bulk-stat-icon" style="background:#fff3e8;color:var(--draft-col)">
                    <q-icon name="text_fields" size="18px" />
                  </div>
                  <div class="bulk-stat-body">
                    <div class="bulk-stat-val">{{ dsMissingDescriptions.length }}</div>
                    <div class="bulk-stat-lbl">Missing Definitions</div>
                    <div class="bulk-stat-sub">{{ dsTotalCols }} columns total</div>
                  </div>
                </div>
                <div class="bulk-stat-card">
                  <div class="bulk-stat-icon" style="background:#e8f3ff;color:var(--in-review-col)">
                    <q-icon name="badge" size="18px" />
                  </div>
                  <div class="bulk-stat-body">
                    <div class="bulk-stat-val">{{ dsMissingBusinessNames.length }}</div>
                    <div class="bulk-stat-lbl">Missing Business Names</div>
                    <div class="bulk-stat-sub">{{ dsTotalCols }} columns total</div>
                  </div>
                </div>
              </div>

              <!-- AI Assistance chart (dataset level) -->
              <div v-if="dsTotalCols > 0" class="ai-accept-card">
                <div class="ai-accept-header">
                  <q-icon name="auto_awesome" size="13px" class="q-mr-xs" style="color:var(--ai-col)" />
                  <span class="ai-accept-title">AI Assistance</span>
                  <span class="ai-accept-scope">DATASET LEVEL</span>
                </div>
                <div class="ai-accept-rows">
                  <!-- Field Definitions row -->
                  <div class="ai-accept-row">
                    <div class="ai-accept-label">Field Definitions</div>
                    <div class="ai-accept-track">
                      <div class="ai-accept-seg ai-accept-seg--ai"
                        :style="{ width: (dsAiDescCount / dsTotalCols * 100).toFixed(1) + '%' }"
                        :title="dsAiDescCount + ' AI-generated'"
                      />
                      <div class="ai-accept-seg ai-accept-seg--manual"
                        :style="{ width: ((dsTotalCols - dsMissingDescriptions.length - dsAiDescCount) / dsTotalCols * 100).toFixed(1) + '%' }"
                        :title="(dsTotalCols - dsMissingDescriptions.length - dsAiDescCount) + ' manually written'"
                      />
                    </div>
                    <div class="ai-accept-pct">
                      <span class="ai-accept-pct--ai">{{ dsTotalCols > 0 ? (dsAiDescCount / dsTotalCols * 100).toFixed(0) : 0 }}%</span>
                      <span class="ai-accept-pct-lbl"> AI &nbsp;&middot;&nbsp; </span>
                      <span class="ai-accept-pct--manual">{{ dsTotalCols > 0 ? ((dsTotalCols - dsMissingDescriptions.length - dsAiDescCount) / dsTotalCols * 100).toFixed(0) : 0 }}%</span>
                      <span class="ai-accept-pct-lbl"> Manual &nbsp;&middot;&nbsp; </span>
                      <span class="ai-accept-pct--absent">{{ dsTotalCols > 0 ? (dsMissingDescriptions.length / dsTotalCols * 100).toFixed(0) : 0 }}%</span>
                      <span class="ai-accept-pct-lbl"> Missing</span>
                    </div>
                  </div>
                  <!-- Business Names row -->
                  <div class="ai-accept-row">
                    <div class="ai-accept-label">Business Names</div>
                    <div class="ai-accept-track">
                      <div class="ai-accept-seg ai-accept-seg--ai"
                        :style="{ width: (dsAiBizNameCount / dsTotalCols * 100).toFixed(1) + '%' }"
                        :title="dsAiBizNameCount + ' AI-generated'"
                      />
                      <div class="ai-accept-seg ai-accept-seg--manual"
                        :style="{ width: ((dsTotalCols - dsMissingBusinessNames.length - dsAiBizNameCount) / dsTotalCols * 100).toFixed(1) + '%' }"
                        :title="(dsTotalCols - dsMissingBusinessNames.length - dsAiBizNameCount) + ' manually written'"
                      />
                    </div>
                    <div class="ai-accept-pct">
                      <span class="ai-accept-pct--ai">{{ dsTotalCols > 0 ? (dsAiBizNameCount / dsTotalCols * 100).toFixed(0) : 0 }}%</span>
                      <span class="ai-accept-pct-lbl"> AI &nbsp;&middot;&nbsp; </span>
                      <span class="ai-accept-pct--manual">{{ dsTotalCols > 0 ? ((dsTotalCols - dsMissingBusinessNames.length - dsAiBizNameCount) / dsTotalCols * 100).toFixed(0) : 0 }}%</span>
                      <span class="ai-accept-pct-lbl"> Manual &nbsp;&middot;&nbsp; </span>
                      <span class="ai-accept-pct--absent">{{ dsTotalCols > 0 ? (dsMissingBusinessNames.length / dsTotalCols * 100).toFixed(0) : 0 }}%</span>
                      <span class="ai-accept-pct-lbl"> Missing</span>
                    </div>
                  </div>
                </div>
                <div class="ai-accept-legend">
                  <span class="ai-accept-leg-item"><span class="ai-accept-leg-pip ai-accept-leg-pip--ai"/>AI-generated</span>
                  <span class="ai-accept-leg-item"><span class="ai-accept-leg-pip ai-accept-leg-pip--manual"/>Manually written</span>
                  <span class="ai-accept-leg-item"><span class="ai-accept-leg-pip ai-accept-leg-pip--missing"/>Missing</span>
                </div>
              </div>

              <!-- Section: Definitions -->
              <div class="bulk-section" :class="{ 'bulk-section--open': bulkDsDescOpen }">
                <div class="bulk-section-header">
                  <div class="bulk-section-title bulk-section-title--toggle" @click="bulkDsDescOpen = !bulkDsDescOpen">
                    <q-icon :name="bulkDsDescOpen ? 'expand_less' : 'expand_more'" size="14px" class="q-mr-xs bulk-toggle-chevron" />
                    <q-icon name="description" size="14px" class="q-mr-xs" />Field Definitions
                    <span class="bulk-section-scope">DATASET LEVEL · {{ store.datasetOverview?.table_name }}</span>
                    <span v-if="getLastBulkRun('dataset', 'descriptions', selectedTable ?? '')" class="bulk-last-run">
                      <q-icon name="history" size="10px" class="q-mr-xs" />{{ fmtDate(getLastBulkRun('dataset', 'descriptions', selectedTable ?? '') ?? '') }}
                    </span>
                  </div>
                  <div class="bulk-section-actions">
                    <button class="bulk-run-btn" :disabled="bulkDescLoading || dsMissingDescriptions.length === 0" @click="runBulkDescriptions">
                      <q-spinner-dots v-if="bulkDescLoading" size="11px" class="q-mr-xs" />
                      <q-icon v-else name="auto_awesome" size="12px" class="q-mr-xs" />
                      <span v-if="bulkDescLoading">Generating…</span>
                      <span v-else-if="dsMissingDescriptions.length === 0">All generated</span>
                      <span v-else>Generate all {{ dsMissingDescriptions.length }} missing</span>
                    </button>
                  </div>
                </div>
                <div v-show="bulkDsDescOpen">
                  <div v-if="dsMissingDescriptions.length === 0" class="bulk-empty-ok">
                    <q-icon name="check_circle_outline" size="14px" class="q-mr-xs" />Every column has a definition.
                  </div>
                  <div v-else class="bulk-item-list">
                    <div v-for="col in dsMissingDescriptions" :key="col.name" class="bulk-item">
                      <div class="bulk-item-icon"><q-icon name="view_column" size="13px" /></div>
                      <div class="bulk-item-body">
                        <span class="bulk-item-name mono">{{ col.name }}</span>
                        <span class="bulk-item-meta">{{ col.data_type }} · {{ semTypeLabel(col.semantic_type) }}</span>
                      </div>
                      <span class="bulk-item-missing-badge">No description</span>
                      <button class="bulk-item-link" @click="selectColumnFromOverview(col)">View element</button>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Section: Business Names -->
              <div class="bulk-section" :class="{ 'bulk-section--open': bulkDsBizOpen }">
                <div class="bulk-section-header">
                  <div class="bulk-section-title bulk-section-title--toggle" @click="bulkDsBizOpen = !bulkDsBizOpen">
                    <q-icon :name="bulkDsBizOpen ? 'expand_less' : 'expand_more'" size="14px" class="q-mr-xs bulk-toggle-chevron" />
                    <q-icon name="badge" size="14px" class="q-mr-xs" />Business Names
                    <span class="bulk-section-scope">DATASET LEVEL · {{ store.datasetOverview?.table_name }}</span>
                    <span v-if="getLastBulkRun('dataset', 'business_names', selectedTable ?? '')" class="bulk-last-run">
                      <q-icon name="history" size="10px" class="q-mr-xs" />{{ fmtDate(getLastBulkRun('dataset', 'business_names', selectedTable ?? '') ?? '') }}
                    </span>
                  </div>
                  <div class="bulk-section-actions">
                    <button class="bulk-run-btn" :disabled="bulkBizLoading || dsMissingBusinessNames.length === 0" @click="runBulkBusinessNames">
                      <q-spinner-dots v-if="bulkBizLoading" size="11px" class="q-mr-xs" />
                      <q-icon v-else name="auto_awesome" size="12px" class="q-mr-xs" />
                      <span v-if="bulkBizLoading">Generating…</span>
                      <span v-else-if="dsMissingBusinessNames.length === 0">All generated</span>
                      <span v-else>Generate all {{ dsMissingBusinessNames.length }} missing</span>
                    </button>
                  </div>
                </div>
                <div v-show="bulkDsBizOpen">
                  <div v-if="dsMissingBusinessNames.length === 0" class="bulk-empty-ok">
                    <q-icon name="check_circle_outline" size="14px" class="q-mr-xs" />Every column has a business name.
                  </div>
                  <div v-else class="bulk-item-list">
                    <div v-for="col in dsMissingBusinessNames" :key="col.name" class="bulk-item">
                      <div class="bulk-item-icon"><q-icon name="view_column" size="13px" /></div>
                      <div class="bulk-item-body">
                        <span class="bulk-item-name mono">{{ col.name }}</span>
                        <span class="bulk-item-meta">{{ col.data_type }} · {{ semTypeLabel(col.semantic_type) }}</span>
                      </div>
                      <span class="bulk-item-missing-badge">No business name</span>
                      <button class="bulk-item-link" @click="selectColumnFromOverview(col)">View element</button>
                    </div>
                  </div>
                </div>
              </div>

              <!-- History for this dataset -->
              <div class="bulk-section" :class="{ 'bulk-section--open': bulkDsHistoryOpen }" v-if="bulkDraftHistory.filter(r => r.scope === 'dataset' && r.target === selectedTable).length">
                <div class="bulk-section-header">
                  <div class="bulk-section-title bulk-section-title--toggle" @click="bulkDsHistoryOpen = !bulkDsHistoryOpen">
                    <q-icon :name="bulkDsHistoryOpen ? 'expand_less' : 'expand_more'" size="14px" class="q-mr-xs bulk-toggle-chevron" />
                    <q-icon name="history" size="14px" class="q-mr-xs" />Generation History
                    <span class="bulk-section-scope">THIS DATASET</span>
                  </div>
                </div>
                <div v-show="bulkDsHistoryOpen" class="bulk-history-list">
                  <div v-for="run in bulkDraftHistory.filter(r => r.scope === 'dataset' && r.target === selectedTable)" :key="run.id" class="bulk-history-item">
                    <q-icon name="auto_awesome" size="12px" class="bulk-history-icon" />
                    <div class="bulk-history-body">
                      <div class="bulk-history-title">{{ run.type === 'descriptions' ? 'Field definitions' : run.type === 'business_names' ? 'Business names' : run.type }} generated</div>
                      <div class="bulk-history-meta">{{ run.generated }} generated · {{ run.failed }} failed · {{ run.total }} total</div>
                    </div>
                    <div class="bulk-history-ts">{{ fmtDate(run.ts) }}</div>
                  </div>
                </div>
              </div>
              <div v-else class="bulk-history-empty">
                <q-icon name="history" size="16px" class="q-mr-xs" />No bulk generation runs yet for this dataset.
              </div>

              <!-- Banner -->
              <transition name="bulk-banner">
                <div v-if="bulkBanner && dsActiveTab === 'bulk-ai'" class="bulk-banner" :class="`bulk-banner--${bulkBanner.type}`">
                  <q-icon :name="bulkBanner.type === 'success' ? 'check_circle' : bulkBanner.type === 'error' ? 'error' : 'info'" size="14px" class="q-mr-xs" />
                  {{ bulkBanner.msg }}
                  <button class="bulk-banner-close" @click="bulkBanner = null"><q-icon name="close" size="12px" /></button>
                </div>
              </transition>
            </div>

            <!-- SCOPING TAB (U2c · decision D1) -->
            <div v-show="dsActiveTab === 'scoping'" class="scoping-tab tab-panel q-ma-md">
              <div class="scoping-intro">
                <q-icon name="rule" size="15px" class="q-mr-xs" style="color: var(--accent)" />
                Mark platform-technical columns (load timestamps, batch IDs, surrogate keys) as
                <b>out of scope</b>. Out-of-scope columns are excluded from data-quality scoring and stop
                demanding governance. Descoping is always your decision — suggestions never apply themselves.
              </div>

              <!-- Suggestions banner -->
              <div v-if="scopeSuggestedColumns.length > 0" class="scoping-suggest-banner">
                <q-icon name="lightbulb" size="14px" class="q-mr-xs" />
                {{ scopeSuggestedColumns.length }} column{{ scopeSuggestedColumns.length === 1 ? '' : 's' }}
                detected as technical / platform fields and suggested for descoping.
                <button class="scoping-suggest-select" @click="selectSuggestedForDescope">Select suggested</button>
              </div>

              <!-- Bulk action bar -->
              <div class="scoping-bulk-bar">
                <div class="scoping-bulk-left">
                  <span class="scoping-sel-count">{{ scopeSelection.size }} selected</span>
                  <button v-if="scopeSelection.size > 0" class="scoping-clear-btn" @click="clearScopeSelection">Clear</button>
                </div>
                <input
                  v-model="scopeReason"
                  class="scoping-reason-input"
                  placeholder="Optional reason (e.g. platform-generated load metadata)…"
                />
                <div class="scoping-bulk-actions">
                  <button
                    class="scoping-btn scoping-btn--out"
                    :disabled="scopeSelection.size === 0 || scopeSaving"
                    @click="applyBulkScope('out_of_scope')"
                  >
                    <q-spinner-dots v-if="scopeSaving" size="12px" class="q-mr-xs" />
                    <q-icon v-else name="block" size="13px" class="q-mr-xs" />Mark out of scope
                  </button>
                  <button
                    class="scoping-btn scoping-btn--in"
                    :disabled="scopeSelection.size === 0 || scopeSaving"
                    @click="applyBulkScope('in_scope')"
                  >
                    <q-icon name="check_circle" size="13px" class="q-mr-xs" />Mark in scope
                  </button>
                </div>
              </div>

              <!-- Banner -->
              <transition name="bulk-banner">
                <div v-if="scopeBanner" class="bulk-banner" :class="`bulk-banner--${scopeBanner.type}`">
                  <q-icon :name="scopeBanner.type === 'success' ? 'check_circle' : 'error'" size="14px" class="q-mr-xs" />
                  {{ scopeBanner.msg }}
                  <button class="bulk-banner-close" @click="scopeBanner = null"><q-icon name="close" size="12px" /></button>
                </div>
              </transition>

              <!-- Column list -->
              <table class="scoping-table">
                <thead>
                  <tr>
                    <th class="scoping-check-th"></th>
                    <th>Column</th>
                    <th>Type</th>
                    <th>Semantic</th>
                    <th>DQ</th>
                    <th>Scope</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="c in scopeColumns"
                    :key="c.name"
                    class="scoping-row"
                    :class="{ 'scoping-row--out': isColOutOfScope(c) }"
                  >
                    <td class="scoping-check-cell">
                      <input
                        type="checkbox"
                        :checked="scopeSelection.has(c.name)"
                        @change="toggleScopeSelection(c.name)"
                      />
                    </td>
                    <td class="mono scoping-name-cell">{{ c.name }}</td>
                    <td class="scoping-type-cell">{{ c.data_type }}</td>
                    <td class="scoping-sem-cell">
                      {{ semTypeLabel(c.semantic_type) }}
                      <span v-if="colDescopeSuggestion(c)" class="scoping-sugg-chip" :class="`scoping-sugg-chip--${colDescopeSuggestion(c)!.strength}`">
                        <q-icon name="lightbulb" size="10px" class="q-mr-xs" />technical
                        <q-tooltip>{{ colDescopeSuggestion(c)!.reason }}</q-tooltip>
                      </span>
                    </td>
                    <td class="scoping-dq-cell">
                      <span v-if="isColOutOfScope(c)" class="scoping-excluded">Excluded</span>
                      <span v-else-if="isScored(c.dq)" class="rail-dq" :class="dqBandClass(c.dq)">{{ c.dq?.dq_score }}</span>
                      <span v-else class="scoping-dq-none">—</span>
                    </td>
                    <td>
                      <span class="scoping-scope-badge" :class="isColOutOfScope(c) ? 'scoping-scope-badge--out' : 'scoping-scope-badge--in'">
                        {{ colScopeLabel(c) }}
                      </span>
                    </td>
                    <td class="scoping-action-cell">
                      <button
                        v-if="!isColOutOfScope(c) && colDescopeSuggestion(c)"
                        class="scoping-row-btn scoping-row-btn--suggest"
                        :disabled="scopeSaving"
                        @click="applyColumnScope(c.name, 'out_of_scope')"
                      >
                        <q-icon name="block" size="11px" class="q-mr-xs" />Suggest: mark out of scope
                      </button>
                      <button
                        v-else-if="!isColOutOfScope(c)"
                        class="scoping-row-btn"
                        :disabled="scopeSaving"
                        @click="applyColumnScope(c.name, 'out_of_scope')"
                      >
                        Mark out of scope
                      </button>
                      <button
                        v-else
                        class="scoping-row-btn scoping-row-btn--restore"
                        :disabled="scopeSaving"
                        @click="applyColumnScope(c.name, 'in_scope')"
                      >
                        <q-icon name="undo" size="11px" class="q-mr-xs" />Restore to scope
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

          </div>
        </template>
        <template v-else-if="viewMode === 'column' && store.element">

          <!-- Header -->
          <div class="el-header">
            <!-- Row 1: technical name + badges (left) · lifecycle state + actions (right) -->
            <div class="el-title-row">
              <span class="el-name mono">{{ store.element.column }}</span>
              <span v-if="isScored(store.element.dq)" class="el-dq-chip" :class="dqBandClass(store.element.dq)" :title="`Data Quality: ${dqBadgeText(store.element.dq)}`">
                <span class="el-dq-chip-score">{{ store.element.dq?.dq_score }}</span>
                <span class="el-dq-chip-band">{{ store.element.dq?.grade_label }}</span>
              </span>
              <span v-else-if="isExcluded(store.element.dq)" class="el-dq-chip el-dq-chip--excluded" title="Excluded from assessment">
                <q-icon name="block" size="11px" class="q-mr-xs" />{{ DQ_EXCLUDED_LABEL }}
              </span>
              <span v-if="store.element.pii" class="el-pii-badge" :title="store.element.pii_category ? `Personal / sensitive data — ${String(store.element.pii_category).replace(/_/g,' ')}` : 'Personal / sensitive data'">
                <q-icon name="shield" size="11px" class="q-mr-xs" />PII
              </span>
              <!-- Right-aligned header group: the tab-contextual actions. The lifecycle
                   state badge now sits on the biz row (below) beside the meta titles. -->
              <div class="el-header-right">
                <div class="el-lifecycle-cluster">
                  <template v-if="activeTab === 'interpretation'">
                    <div v-if="isLcEditable" class="el-lc-row">
                      <button class="action-btn action-btn--primary" :disabled="lcActionLoading" @click="onSaveDraft">
                        <q-spinner-dots v-if="lcActionLoading" size="13px" class="q-mr-xs" /><q-icon v-else name="save" size="14px" class="q-mr-xs" />Save draft
                      </button>
                      <button class="action-btn action-btn--confirm" :disabled="lcActionLoading || !submitGateMet" :title="submitGateMet ? '' : 'Add a definition, a business name, and accept a semantic type to enable Submit'" @click="onSubmitClick">
                        <q-icon name="rate_review" size="14px" class="q-mr-xs" />Submit for review
                      </button>
                    </div>
                    <div v-if="isLcInReview || isLcApproved" class="el-lc-row">
                      <button v-if="isLcInReview" class="action-btn action-btn--secondary" :disabled="lcActionLoading" @click="onWithdraw">
                        <q-icon name="undo" size="14px" class="q-mr-xs" />Withdraw submission
                      </button>
                      <button v-else-if="isLcApproved" class="action-btn action-btn--secondary" :disabled="lcActionLoading" @click="onRevoke">
                        <q-icon name="undo" size="14px" class="q-mr-xs" />Revoke approval
                      </button>
                    </div>
                  </template>
                  <span v-else-if="activeTab === 'refdata' && rdPgMode && !rdNotApplicable" class="el-codeset-status">
                    {{ rdCodesetSummaryLabel }}
                  </span>
                </div>
              </div>
            </div>

            <!-- Row 2: business name + glossary + semantic type (all display-only;
                 each has its own decision block below) -->
            <div class="el-biz-row">
              <span class="el-meta-item">
                <span class="el-meta-label">Business Name</span>
                <span v-if="bnameValue" class="el-meta-value el-meta-value--linked">{{ bnameValue }}</span>
                <span v-else class="el-meta-value el-meta-value--empty">Not set</span>
              </span>
              <span class="el-meta-sep" />
              <span class="el-meta-item">
                <span class="el-meta-label">Glossary</span>
                <span v-if="store.element.glossary_term" class="el-meta-value el-meta-value--linked">{{ store.element.glossary_term.title }}</span>
                <span v-else class="el-meta-value el-meta-value--empty">Not Linked</span>
              </span>
              <span class="el-meta-sep" />
              <span class="el-meta-item">
                <span class="el-meta-label">Semantic Type</span>
                <span v-if="semTypeLoading && !semTypeRecord" class="el-meta-value el-meta-value--empty">…</span>
                <span v-else-if="semTypeRecord?.accepted_at && semTypeRecord.type_id !== 'unresolved'" class="el-meta-value el-meta-value--linked">{{ semTypeIdLabel(semTypeRecord.type_id) }}</span>
                <span v-else class="el-meta-value el-meta-value--empty">Pending review</span>
              </span>
              <span class="el-state-badge el-state-badge--lg el-biz-status" :style="{ color: lifecycleTone.textColor, background: lifecycleTone.bgColor, border: `1px solid ${lifecycleTone.borderColor}` }">{{ lifecycleTone.label }}</span>
            </div>

            <!-- Custom tab bar -->
            <div class="tab-bar">
              <button
                v-for="t in tabs" :key="t.key"
                class="tab-btn"
                :class="{ 'tab-btn--active': activeTab === t.key, 'tab-btn--disabled': t.disabled, 'tab-btn--component': !!t.colorKey }"
                :disabled="t.disabled"
                @click="!t.disabled && (activeTab = t.key)"
              >
                {{ t.label }}
                <span v-if="t.badge" class="tab-badge" :class="t.badgeClass">{{ t.badge }}</span>
              </button>
              <span v-if="lastStatusLabel" class="tab-bar-status">{{ lastStatusLabel }}</span>
            </div>
          </div>

          <!-- Tab panels -->
          <div class="el-body">

            <!-- PROFILE -->
            <div v-show="activeTab === 'profile'" class="tab-panel q-ma-md">

              <!-- Stat cards: Completeness / Uniqueness / Duplicate / Placeholder -->
              <div class="stat-cards q-mb-md">
                <div class="stat-card">
                  <div class="stat-card-val" :class="completenessTextColor">
                    {{ store.element.stats.null_pct != null ? fmtPct(1 - store.element.stats.null_pct) + '%' : '—' }}
                  </div>
                  <div class="stat-card-lbl">Completeness</div>
                  <div v-if="store.element.stats.null_pct != null" class="stat-meter">
                    <div class="stat-meter-fill" :class="completenessMeterColor" :style="{ width: fmtPct(1 - store.element.stats.null_pct) + '%' }" />
                  </div>
                </div>
                <div class="stat-card">
                  <div class="stat-card-val" :class="uniquenessPC != null && uniquenessPC >= 99 ? 'text-positive' : ''">
                    {{ uniquenessPC != null ? uniquenessPC.toFixed(1) + '%' : '—' }}
                  </div>
                  <div class="stat-card-lbl">Uniqueness</div>
                  <div v-if="uniquenessPC != null" class="stat-meter">
                    <div class="stat-meter-fill stat-meter-fill--neutral" :style="{ width: uniquenessPC.toFixed(1) + '%' }" />
                  </div>
                </div>
                <div class="stat-card">
                  <div class="stat-card-val" :class="duplicatePC != null && duplicatePC > 0 ? 'text-warning' : ''">
                    {{ duplicatePC != null ? duplicatePC.toFixed(1) + '%' : '—' }}
                  </div>
                  <div class="stat-card-lbl">Duplicate</div>
                  <div v-if="duplicatePC != null" class="stat-meter">
                    <div class="stat-meter-fill" :class="duplicatePC > 0 ? 'stat-meter-fill--warn' : 'stat-meter-fill--neutral'" :style="{ width: Math.min(duplicatePC, 100).toFixed(1) + '%' }" />
                  </div>
                </div>
                <div class="stat-card">
                  <div class="stat-card-val" :class="placeholderPC != null && placeholderPC > 0 ? 'text-warning' : ''">
                    {{ placeholderPC != null ? placeholderPC.toFixed(1) + '%' : '—' }}
                  </div>
                  <div class="stat-card-lbl">Placeholder</div>
                  <div v-if="placeholderPC != null" class="stat-meter">
                    <div class="stat-meter-fill" :class="placeholderPC > 0 ? 'stat-meter-fill--warn' : 'stat-meter-fill--neutral'" :style="{ width: Math.min(placeholderPC, 100).toFixed(1) + '%' }" />
                  </div>
                </div>
              </div>

              <!-- Semantic type & Distribution grid -->
              <div class="sem-dist-grid q-mb-md">
                <!-- Data quality at a glance (evidence, not a type verdict) -->
                <div class="panel-card block-card">
                  <div class="block-bar">
                    <span class="block-bar-left">
                      <span class="block-bar-title">Data quality at a glance</span>
                      <span class="ds-panel-caption">OBSERVED · PROFILING</span>
                    </span>
                  </div>
                  <div class="block-body q-pa-md">
                  <div class="dq-facts">
                    <div v-for="(f, i) in profileDqFacts" :key="i" class="dq-fact" :class="`dq-fact--${f.tone}`">
                      <q-icon :name="f.icon" size="15px" class="dq-fact-ic" />
                      <span class="dq-fact-text">{{ f.text }}</span>
                    </div>
                    <div v-if="!profileDqFacts.length" class="dq-fact dq-fact--neutral">
                      <q-icon name="info" size="15px" class="dq-fact-ic" />
                      <span class="dq-fact-text">No profiling statistics available yet.</span>
                    </div>
                  </div>
                  <div class="dq-sem-status" :class="profileSemStatus.cls">
                    <q-icon :name="profileSemStatus.icon" size="14px" class="q-mr-xs" />
                    <span>{{ profileSemStatus.text }}</span>
                    <button v-if="!profileSemStatus.accepted" class="dq-sem-link" @click="activeTab = 'interpretation'">Review →</button>
                  </div>
                  </div>
                </div>

                <!-- Cardinality (identifier) OR Value distribution -->
                <div v-if="store.element.semantic_type === 'identifier'" class="panel-card block-card">
                  <div class="block-bar"><span class="block-bar-title">Cardinality</span></div>
                  <div class="block-body q-pa-md">
                  <div class="sem-panel">
                    <q-icon name="fingerprint" size="24px" style="color:#0d7a5f;flex-shrink:0" />
                    <div>
                      <div class="sem-name">{{ store.element.stats.distinct_count?.toLocaleString() ?? '—' }} distinct values</div>
                      <div class="sem-desc">High-cardinality identifier — a value-frequency histogram is not meaningful. Uniqueness and pattern integrity are the relevant quality signals.</div>
                    </div>
                  </div>
                  </div>
                </div>
                <div v-else class="panel-card block-card">
                  <div class="block-bar">
                    <span class="block-bar-left"><span class="block-bar-title">Value distribution</span></span>
                    <div v-if="distBins.length" class="dist-mode-btns">
                      <button class="dist-mode-btn" :class="{ 'dist-mode-btn--active': distMode === 'freq' }" @click="distMode = 'freq'">By freq</button>
                      <button class="dist-mode-btn" :class="{ 'dist-mode-btn--active': distMode === 'alpha' }" @click="distMode = 'alpha'">A→Z</button>
                      <button class="dist-mode-btn" :class="{ 'dist-mode-btn--active': distLogScale }" @click="distLogScale = !distLogScale">Log</button>
                    </div>
                  </div>
                  <div class="block-body q-pa-md">
                  <template v-if="distBinsDisplayed.length">
                    <div class="dist-histogram">
                      <div v-for="bin in distBinsDisplayed" :key="String(bin.label)" class="dist-bar-wrap">
                        <div class="dist-bar-track">
                          <div class="dist-bar-fill" :style="{ height: bin.pct + '%' }" />
                        </div>
                        <div class="dist-bar-label">{{ String(bin.label).slice(0, 8) }}</div>
                      </div>
                    </div>
                  </template>
                  <div v-else class="panel-empty">No distribution data available.</div>
                  </div>
                </div>
              </div>

              <!-- Characteristics + Sample values side-by-side -->
              <div class="char-samp-grid q-mb-md">
                <div class="panel-card block-card">
                  <div class="block-bar"><span class="block-bar-title">Characteristics</span></div>
                  <div class="block-body q-pa-md">
                  <div class="char-kv">
                    <span class="char-k">Row count</span><span class="char-v mono">{{ store.element.stats.row_count?.toLocaleString() ?? '—' }}</span>
                    <span class="char-k">Distinct values</span><span class="char-v mono">{{ store.element.stats.distinct_count?.toLocaleString() ?? '—' }}</span>
                    <span class="char-k">Completeness</span><span class="char-v mono">{{ store.element.stats.null_pct != null ? fmtPct(1 - store.element.stats.null_pct) + '%' : '—' }}</span>
                    <span class="char-k">Null %</span><span class="char-v mono">{{ store.element.stats.null_pct != null ? fmtPct(store.element.stats.null_pct) + '%' : '—' }}</span>
                    <span class="char-k">Uniqueness</span><span class="char-v mono">{{ uniquenessPC != null ? uniquenessPC.toFixed(1) + '%' : '—' }}</span>
                    <span class="char-k">Min</span><span class="char-v mono">{{ store.element.stats.min_value ?? '—' }}</span>
                    <span class="char-k">Max</span><span class="char-v mono">{{ store.element.stats.max_value ?? '—' }}</span>
                    <span class="char-k">Data type</span><span class="char-v mono">{{ store.element.data_type }}</span>
                    <template v-if="store.element.foreign_key">
                      <span class="char-k">{{ store.element.foreign_key.declared ? 'Foreign key' : 'Inferred FK' }}</span>
                      <span class="char-v mono">
                        <button
                          class="char-fk-link"
                          :class="{ 'char-fk-link--inferred': !store.element.foreign_key.declared, 'char-fk-link--orphan': (store.element.foreign_key.orphan_count ?? 0) > 0 }"
                          @click="navigateToDataset(store.element!.source, store.element!.foreign_key!.references_table, store.element!.schema)"
                        >
                          <q-icon name="account_tree" size="12px" class="q-mr-xs" :style="{ color: (store.element.foreign_key.orphan_count ?? 0) > 0 ? 'var(--danger-col)' : (store.element.foreign_key.declared ? '#2f5d8a' : '#8b6bb1') }" />{{ store.element.foreign_key.references_table }}.{{ store.element.foreign_key.references_column }}
                        </button>
                        <q-icon v-if="!store.element.foreign_key.declared" name="info" size="11px" class="q-ml-xs" style="color:#8b6bb1">
                          <q-tooltip>Inferred by deterministic {{ fkBasisLabel(store.element.foreign_key.basis) }} ({{ store.element.foreign_key.confidence }} confidence) — not AI, no DB constraint declared</q-tooltip>
                        </q-icon>
                        <span v-if="(store.element.foreign_key.orphan_count ?? 0) > 0" class="ds-orphan-pill">⚠ {{ store.element.foreign_key.orphan_count }} orphan key{{ store.element.foreign_key.orphan_count === 1 ? '' : 's' }}</span>
                      </span>
                    </template>
                    <template v-if="isStringDataType && charProfileAW">
                      <span class="char-k">Character type</span>
                      <span class="char-v"><span class="char-profile-badge">{{ charProfileAW }}</span></span>
                    </template>
                    <template v-if="isStringDataType">
                      <span class="char-k">Min length</span><span class="char-v mono">{{ store.element.stats.length_min ?? '—' }}</span>
                      <span class="char-k">Max length</span><span class="char-v mono">{{ store.element.stats.length_max ?? '—' }}</span>
                      <span class="char-k">Avg length</span><span class="char-v mono">{{ store.element.stats.length_avg != null ? (store.element.stats.length_avg as number).toFixed(1) : '—' }}</span>
                    </template>
                  </div>
                  </div>
                </div>
                <div class="panel-card block-card">
                  <div class="block-bar"><span class="block-bar-title">Sample values</span></div>
                  <div class="block-body q-pa-md">
                  <table v-if="store.element.stats.sample_values?.length" class="samp-table">
                    <tr v-for="(v, i) in store.element.stats.sample_values.slice(0, 8)" :key="i">
                      <td class="samp-n">{{ i + 1 }}</td>
                      <td class="samp-v mono">{{ v }}</td>
                    </tr>
                  </table>
                  <div v-else class="panel-empty">No sample values available.</div>
                  </div>
                </div>
              </div>

              <p class="profile-note">Profiling runs automatically on ingest — read-only. These statistics describe the element as observed and are not editable here.</p>
            </div>

            <!-- OBSERVATIONS -->
            <div v-show="activeTab === 'observations'" class="tab-panel q-ma-md">

              <!-- Data Quality card (U2d · DQ §14): the composite score spans
                   multiple dimensions, so its home is the dedicated Data Quality
                   tab. Compact score·band chip stays in the element header. -->
              <div class="dq-card panel-card q-mb-md">
                <template v-if="isScored(dqBadge)">
                  <div class="dq-card-main">
                    <div class="dq-donut-wrap">
                      <svg class="dq-donut" viewBox="0 0 120 120">
                        <g transform="rotate(-90 60 60)">
                          <circle
                            v-for="arc in dqDonut.arcs" :key="`t-${arc.name}`"
                            class="dq-arc-track" :class="`dq-arc--${arc.colorKey}`"
                            cx="60" cy="60" :r="dqDonut.radius" fill="none"
                            :stroke-dasharray="arc.trackDash" :stroke-dashoffset="arc.dashOffset"
                          />
                          <circle
                            v-for="arc in dqDonut.arcs" :key="`f-${arc.name}`"
                            class="dq-arc-fill" :class="`dq-arc--${arc.colorKey}`"
                            cx="60" cy="60" :r="dqDonut.radius" fill="none"
                            :stroke-dasharray="arc.fillDash" :stroke-dashoffset="arc.dashOffset"
                          />
                        </g>
                        <text x="60" y="58" class="dq-donut-score" text-anchor="middle">{{ dqScoreText(dqBadge) }}</text>
                        <rect x="25" y="66" width="70" height="19" rx="9.5" class="dq-donut-grade-pill" :class="dqBandClass(dqBadge)" />
                        <text x="60" y="79.5" class="dq-donut-band" text-anchor="middle">{{ dqBandLabel(dqBadge) }}</text>
                      </svg>
                    </div>
                    <div class="dq-legend">
                      <div class="dq-legend-head">
                        <div class="dq-grade-legend dq-grade-legend--inline">
                          <template v-for="(b, i) in DQ_GRADE_BANDS" :key="b.label">
                            <span class="dq-grade-legend-item">
                              <span class="dq-grade-legend-range mono">{{ b.max != null ? `${b.min}–${b.max}` : `${b.min}+` }}</span>
                              <b class="dq-grade-legend-label" :class="`dq-band--${b.colorIntent}`">{{ b.label }}</b>
                            </span>
                            <span v-if="i < DQ_GRADE_BANDS.length - 1" class="dq-grade-legend-sep">·</span>
                          </template>
                        </div>
                        <button
                          class="dq-refresh-btn"
                          :disabled="refreshingDq"
                          title="Force a fresh DQ score for this column (bypasses the cached score)"
                          @click="refreshElementDq"
                        >
                          <q-icon name="refresh" size="13px" :class="{ 'dq-refresh-spin': refreshingDq }" />
                          Refresh DQ Score
                        </button>
                      </div>
                      <div v-if="dqBadge?.scored_at" class="dq-scored-at">
                        <q-icon name="schedule" size="12px" class="q-mr-xs" />
                        Last evaluated {{ fmtDate(dqBadge.scored_at) }}
                      </div>
                      <div v-if="dqReallocation" class="dq-realloc">{{ dqReallocation }}</div>
                      <div v-for="c in dqComponents" :key="c.name" class="dq-legend-row">
                        <span class="dq-dot" :class="`dq-arc--${c.colorKey}`" />
                        <span class="dq-legend-label">{{ c.label }}</span>
                        <span class="dq-legend-val mono">{{ c.earned }}/{{ c.max }}</span>
                        <span v-if="c.gradeLabel" class="dq-legend-band" :class="`dq-band--${c.gradeColorIntent || 'neutral'}`">{{ c.gradeLabel }}</span>
                      </div>
                      <div class="dq-actual-score-row">
                        <span class="dq-actual-score-label">Actual score</span>
                        <span class="dq-actual-score-rule" />
                        <span class="dq-band-pill" :class="dqBandClass(dqBadge)" title="Sum of the applicable component scores">{{ dqScorePreciseText(dqBadge) }}</span>
                      </div>
                    </div>
                  </div>

                  <!-- Per-dimension breakdown — one scale (composite 0–100): every
                       line-item, block and the headline reconcile (U4b-fix Task 1).
                       Grouped into the Data·Governance pillars plus Actions to
                       improve — each its own collapsible, glass-panelled group
                       header, visible by default (defaults collapsed, no
                       separate show/hide toggle needed). -->
                  <div v-if="dqComponentGroups.length" class="dq-breakdown">
                    <div v-for="group in dqComponentGroups" :key="group.key" class="dq-group">
                      <button
                        class="dq-group-head" :class="`dq-group-head--${group.key}`"
                        type="button" @click="toggleDqGroup(group.key)"
                      >
                        <q-icon :name="dqGroupExpanded[group.key] ? 'expand_less' : 'expand_more'" size="16px" />
                        <span class="dq-group-title">{{ group.label }}</span>
                        <span v-if="group.pct != null" class="dq-pillar" :class="`dq-pillar--${group.key}`">{{ group.pct }}%</span>
                        <span class="dq-group-points mono">{{ group.earned }}/{{ group.max }}</span>
                      </button>
                      <div v-if="dqGroupExpanded[group.key]" class="dq-group-body">
                        <div v-for="comp in group.components" :key="comp.name" class="dq-comp-block">
                          <div class="dq-comp-head">
                            <span class="dq-dot" :class="`dq-arc--${componentColorKey(comp.name)}`" />
                            <span class="dq-comp-title">{{ componentLabel(comp.name) }}</span>
                            <span class="dq-comp-score mono">{{ comp.earned }}/{{ comp.max }}</span>
                          </div>
                          <div v-for="li in comp.line_items" :key="li.label" class="dq-li">
                            <div class="dq-li-top">
                              <span class="dq-li-label">{{ li.label }}</span>
                              <span class="dq-li-val mono">{{ li.earned }}/{{ li.max }}</span>
                            </div>
                            <div v-if="li.formula" class="dq-li-formula mono">{{ li.formula }}</div>
                            <div v-if="li.evidence_note" class="dq-li-note">{{ li.evidence_note }}</div>
                          </div>
                        </div>
                      </div>
                    </div>

                    <!-- U4b — Actions to improve (§17): derived from the line-item
                         gaps above, sorted by impact, with the shortest path to the
                         next grade band headlined. Each action shows where it lands
                         you (U4b-fix Task 2) and its supporting observation (Task 5).
                         Styled as its own group header, matching Data/Governance:
                         the pill carries the action count, the bold value the total
                         recoverable points across every action. -->
                    <div v-if="dqActionsList.length || dqPath" class="dq-group">
                      <button
                        class="dq-group-head dq-group-head--actions"
                        type="button" @click="toggleDqGroup('actions')"
                      >
                        <q-icon :name="dqGroupExpanded.actions ? 'expand_less' : 'expand_more'" size="16px" />
                        <span class="dq-group-title">Actions to improve</span>
                        <span v-if="dqActionsList.length" class="dq-pillar dq-pillar--actions">{{ dqActionsList.length }}</span>
                        <span v-if="dqActionsTotalPoints" class="dq-group-points mono">+{{ dqActionsTotalPoints }}</span>
                      </button>
                      <div v-if="dqGroupExpanded.actions" class="dq-group-body">
                        <div v-if="dqPath && dqPath.at_top_band" class="dq-path dq-path--top">
                          <q-icon name="verified" size="15px" class="q-mr-xs" />
                          At {{ dqPath.current_grade }} — no actions needed.
                        </div>
                        <div v-else-if="dqPath && dqPath.any_one_suffices" class="dq-path">
                          <q-icon name="trending_up" size="15px" class="q-mr-xs" />
                          <span>
                            <b>Any one</b> of these {{ dqPath.actions.length }} actions (+{{ dqPath.actions[0].points }} points)
                            moves this column from {{ dqPath.current_grade }} {{ dqPath.current_score }}
                            → {{ dqPath.landing_grade ?? dqPath.next_grade }} {{ dqPath.landing_score ?? dqPath.next_grade_min }}.
                          </span>
                        </div>
                        <div v-else-if="dqPath" class="dq-path">
                          <q-icon name="trending_up" size="15px" class="q-mr-xs" />
                          <span>
                            <b>{{ dqPath.actions.length }}</b>
                            action{{ dqPath.actions.length === 1 ? '' : 's' }}
                            {{ dqPath.actions.length === 1 ? 'moves' : 'move' }} this column from {{ dqPath.current_grade }} {{ dqPath.current_score }}
                            → {{ dqPath.landing_grade ?? dqPath.next_grade }} {{ dqPath.landing_score ?? dqPath.next_grade_min }}
                            (+{{ pathPoints }} points).
                          </span>
                        </div>
                        <ul v-if="dqActionsList.length" class="dq-action-list">
                          <li
                            v-for="(a, i) in dqActionsList" :key="i" class="dq-action"
                            :class="{ 'dq-action--in-path': pathLineItems.has(`${a.component}|${a.line_item}`) }"
                          >
                            <span class="dq-action-points mono">+{{ a.points }}</span>
                            <span class="dq-action-body">
                              <span class="dq-action-caption">{{ actionCaption(a) }}</span>
                              <span class="dq-action-step">{{ a.step }}</span>
                              <span v-if="a.resulting_score != null" class="dq-action-dest">
                                <q-icon name="arrow_forward" size="12px" />
                                raises this column to <b>{{ a.resulting_score }}</b>
                                <span v-if="a.resulting_grade"> · {{ a.resulting_grade }}</span>
                              </span>
                              <span
                                v-for="(o, oi) in actionObservations(a)" :key="oi"
                                class="dq-action-why"
                              >
                                <q-icon name="info_outline" size="12px" class="q-mr-xs" />{{ o.rationale || o.title }}
                              </span>
                              <span class="dq-action-meta">
                                <span class="dq-action-type" :class="`dq-action-type--${a.action_type}`">{{ a.action_type }}</span>
                                · {{ componentLabel(a.component) }}
                              </span>
                            </span>
                            <DqActionShareMenu
                              v-if="store.element"
                              :action="a"
                              :observations="actionObservations(a)"
                              :source="store.element.source"
                              :schema="store.element.schema"
                              :table="store.element.table"
                              :column="store.element.column"
                            />
                          </li>
                        </ul>
                      </div>
                    </div>
                  </div>
                </template>
                <div v-else-if="isExcluded(dqBadge)" class="dq-card-empty dq-card-empty--excluded">
                  <q-icon name="block" size="18px" class="q-mr-xs" />
                  {{ DQ_EXCLUDED_LABEL }} — this column is marked out of scope and is not scored.
                </div>
                <div v-else class="dq-card-empty">
                  <q-icon name="donut_large" size="18px" class="q-mr-xs" />
                  {{ dqBandLabel(dqBadge) }} — no data quality score for this column yet.
                  <button class="dq-refresh-btn dq-refresh-btn--inline" :disabled="refreshingDq" @click="refreshElementDq">
                    <q-icon name="refresh" size="13px" :class="{ 'dq-refresh-spin': refreshingDq }" />
                    Score now
                  </button>
                </div>
              </div>

              <!-- U4b-fix (Task 5): observations that map to an action appear as its
                   "why" above. Only observations with no matching action remain as
                   standalone, humanised cards — plain sentence, no raw JSON. -->
              <template v-if="dqUnmatchedObservations.length">
                <div
                  v-for="(f, i) in dqUnmatchedObservations" :key="i"
                  class="finding-card q-mb-sm"
                  :class="`finding-card--${f.severity}`"
                >
                  <div class="finding-header">
                    <span class="finding-sev-badge" :class="`fsev--${f.severity}`">{{ f.severity }}</span>
                    <span v-if="f.category" class="finding-dim-badge" :class="`fdim--${f.category}`">{{ dqDimensionLabel(f.category) }}</span>
                    <span class="finding-prov-badge" :class="f.source === 'ai' ? 'fprov--ai' : 'fprov--rule'">
                      <q-icon :name="f.source === 'ai' ? 'auto_awesome' : 'shield'" size="10px" class="q-mr-xs" />
                      {{ f.source === 'ai' ? 'AI-detected' : 'Rule-based' }}
                    </span>
                    <span class="finding-title">{{ f.title }}</span>
                  </div>
                  <div v-if="f.rationale" class="finding-rationale">{{ f.rationale }}</div>
                  <div v-if="f.regulatory_note" class="finding-regnote">
                    <q-icon name="gavel" size="11px" class="q-mr-xs" />{{ f.regulatory_note }}
                  </div>
                </div>
              </template>
            </div>

            <!-- INTERPRETATION -->
            <div v-show="activeTab === 'interpretation'" class="tab-panel q-ma-md">
              <!-- Steward decision feedback (5b.3.2b #1): relocated from the retired Status
                   block; a returned/rejected set keeps its reason on show until re-submit. -->
              <div v-if="stewardFeedback" class="steward-feedback" :class="stewardFeedback.cls">
                <q-icon :name="stewardFeedback.icon" size="15px" class="q-mr-xs" />
                <span>{{ stewardFeedback.text }}</span>
              </div>
              <!-- Definition -->
              <div class="panel-card block-card q-mb-md">
                <div class="block-bar">
                  <span class="block-bar-left">
                    <span class="block-bar-title">Definition</span>
                    <span v-if="store.element?.metadata?.is_ai_generated && descValue" class="block-bar-badge">
                      <q-icon name="auto_awesome" size="10px" />AI Generated
                    </span>
                  </span>
                  <span v-if="!isDescEditMode" class="block-bar-actions">
                    <button
                      v-if="isLcEditable"
                      class="icon-btn"
                      title="Edit description"
                      @click="isDescEditMode = true"
                    >
                      <q-icon name="edit" size="16px" />
                    </button>
                    <button
                      v-if="descValue"
                      class="icon-btn"
                      title="Copy to clipboard"
                      @click="copyToClipboard"
                    >
                      <q-icon name="content_copy" size="16px" />
                    </button>
                  </span>
                </div>
                <div class="block-body q-pa-md">
                  <!-- Read-only view -->
                  <div v-if="!isDescEditMode" class="desc-view">
                    <div class="desc-content">
                      <div v-if="descValue" class="desc-text">{{ descValue }}</div>
                      <div v-else class="desc-empty">Write a business-friendly description…</div>
                    </div>
                  </div>

                  <!-- Edit mode -->
                  <template v-else>
                    <q-input
                      v-model="descValue"
                      type="textarea"
                      outlined dense autogrow
                      placeholder="Write a business-friendly description…"
                      :rows="3"
                      class="desc-input"
                      @input="isUserEdit = true"
                    />
                    <div class="desc-actions q-mt-sm">
                      <button class="action-btn action-btn--primary" :disabled="!descDirty || saveDescLoading" @click="saveDescription">
                        <q-spinner-dots v-if="saveDescLoading" size="13px" class="q-mr-xs" />
                        <q-icon v-else name="save" size="14px" class="q-mr-xs" />
                        <template v-if="saveDescLoading">Saving…</template>
                        <template v-else>Save</template>
                      </button>
                      <button class="action-btn action-btn--ai" :disabled="draftLoading" @click="draftWithAi">
                        <q-icon name="auto_awesome" size="14px" class="q-mr-xs" />
                        <template v-if="draftLoading">Drafting…</template>
                        <template v-else>Draft with AI</template>
                      </button>
                      <button class="action-btn action-btn--secondary" @click="cancelEdit">
                        <q-icon name="close" size="14px" class="q-mr-xs" />
                        Cancel
                      </button>
                    </div>
                  </template>
                </div>
              </div>

              <!-- Business Name — its own decision block (analyst names the field,
                   then Saves a draft or Submits for Architect review) -->
              <div class="panel-card block-card q-mb-md">
                <div class="block-bar">
                  <span class="block-bar-left">
                    <span class="block-bar-title">Business Name</span>
                    <span v-if="store.element.metadata?.business_name_is_ai && bnameValue" class="block-bar-badge">
                      <q-icon name="auto_awesome" size="10px" />AI Generated
                    </span>
                  </span>
                  <span class="block-bar-actions">
                    <button v-if="!bnameEditMode && isLcEditable" class="icon-btn" title="Edit business name" @click="bnameEditMode = true">
                      <q-icon name="edit" size="16px" />
                    </button>
                  </span>
                </div>
                <div class="block-body q-pa-md">
                  <!-- Read-only view -->
                  <div v-if="!bnameEditMode" class="desc-view">
                    <div class="desc-content">
                      <div v-if="bnameValue" class="desc-text">{{ bnameValue }}</div>
                      <div v-else class="desc-empty">Add a business-friendly name for this field…</div>
                    </div>
                  </div>

                  <!-- Edit mode -->
                  <template v-else>
                    <q-input
                      v-model="bnameValue"
                      outlined dense
                      placeholder="Enter a business-friendly name…"
                      class="desc-input"
                      @keydown.enter="saveBusinessName"
                      @keydown.escape="cancelBname"
                      @update:model-value="bnameIsAi = false"
                    />
                    <div class="desc-actions q-mt-sm">
                      <button class="action-btn action-btn--primary" :disabled="!bnameValue.trim() || bnameSaving" @click="saveBusinessName">
                        <q-spinner-dots v-if="bnameSaving" size="13px" class="q-mr-xs" />
                        <q-icon v-else name="save" size="14px" class="q-mr-xs" />
                        <template v-if="bnameSaving">Saving…</template>
                        <template v-else>Save</template>
                      </button>
                      <button class="action-btn action-btn--ai" :disabled="bnameDraftLoading" @click="draftBusinessNameHandler">
                        <q-spinner-dots v-if="bnameDraftLoading" size="13px" class="q-mr-xs" />
                        <q-icon v-else name="auto_awesome" size="14px" class="q-mr-xs" />
                        <template v-if="bnameDraftLoading">Drafting…</template>
                        <template v-else>Draft with AI</template>
                      </button>
                      <button class="action-btn action-btn--secondary" @click="cancelBname">
                        <q-icon name="close" size="14px" class="q-mr-xs" />
                        Cancel
                      </button>
                    </div>
                  </template>
                </div>
              </div>

              <!-- Glossary term -->
              <BusinessContextPanel
                :term-ref="store.element.glossary_term"
                :source="store.element.source"
                :schema="store.element.schema"
                :table="store.element.table"
                :column="store.element.column"
                @linkage-changed="reloadElement"
              />

              <!-- ── Semantic Type — analyst annotation (SD-R3b) ─────────── -->
              <div v-if="semTypeRecord" class="panel-card block-card q-mt-md sem-annot">
                <div class="block-bar">
                  <span class="block-bar-left">
                    <span class="block-bar-title">Semantic Type <span class="sem-annot-hint">what kind of field is this?</span></span>
                    <template v-if="!semTypeIsUnresolved">
                      <span v-if="semTypeAccepted" class="sem-annot-tag sem-annot-tag--accepted">Accepted</span>
                      <span v-else-if="semTypeTag" class="sem-annot-tag" :class="`sem-annot-tag--${semTypeTag.toLowerCase()}`">{{ semTypeTag }} confidence</span>
                    </template>
                  </span>
                  <span class="block-bar-actions">
                    <button v-if="semTypeBtns.replace && isLcEditable" class="st-btn" @click="openSemTypePicker()">
                      <q-icon name="edit" size="13px" class="q-mr-xs" />Replace
                    </button>
                    <button v-if="semTypeBtns.resolve && isLcEditable" class="st-btn" @click="openSemTypePicker()">
                      <q-icon name="search" size="13px" class="q-mr-xs" />Resolve
                    </button>
                  </span>
                </div>
                <div class="block-body q-pa-md">

                <div class="sem-annot-line">
                  <template v-if="semTypeIsUnresolved">
                    <span class="sem-annot-type sem-annot-type--none">Unresolved</span>
                  </template>
                  <template v-else>
                    <span class="sem-annot-type">{{ semTypeIdLabel(semTypeRecord.type_id) }}</span>
                    <span v-if="semTypePii" class="sem-annot-pii" :title="semTypePiiTitle">PII</span>
                    <span v-if="semTypeConflict" class="sem-annot-warn"><q-icon name="warning" size="13px" class="q-mr-xs" />Values disagree — check before accepting</span>
                  </template>

                  <span class="sem-annot-actions">
                    <button v-if="semTypeBtns.accept && isLcEditable" class="st-btn st-btn--confirm" :disabled="semTypeConfirming" @click="acceptSemType()">
                      <q-spinner-dots v-if="semTypeConfirming && !semTypeOverrideOpen" size="13px" class="q-mr-xs" />
                      <q-icon v-else name="check" size="13px" class="q-mr-xs" />Accept
                    </button>
                  </span>
                </div>

                <!-- Domain · Scope context line (Domain → Type → Scope; Type is the headline above) -->
                <div v-if="semTypeRecord && !semTypeIsUnresolved" class="sem-annot-taxo">
                  <span class="sem-annot-taxo-item">{{ semDomainLabel(semTypeRecord.domain_role) }}</span>
                  <template v-if="semScopeLabel(semTypeRecord.scope)">
                    <span class="sem-annot-taxo-sep">·</span>
                    <span class="sem-annot-taxo-item">{{ semScopeLabel(semTypeRecord.scope) }} scope</span>
                  </template>
                </div>

                <!-- Governed vocabulary picker (Replace / Resolve) — no N/A entry -->
                <div v-if="semTypeOverrideOpen" class="sem-annot-picker st-override-cascade">
                  <div class="st-ov-row">
                    <label>Role</label>
                    <q-select v-model="semOverrideRole" :options="vocabRoles" option-label="label" option-value="id" emit-value map-options dense outlined options-dense label="Role" style="min-width:140px" @update:model-value="semOverrideTypeId = null" />
                  </div>
                  <span class="st-ov-arr">›</span>
                  <div class="st-ov-row">
                    <label>Type</label>
                    <q-select v-model="semOverrideTypeId" :options="vocabTypesForRole" option-label="label" option-value="id" emit-value map-options dense outlined options-dense label="Type" :disable="!semOverrideRole" style="min-width:170px" />
                  </div>
                  <span class="st-ov-arr">›</span>
                  <div class="st-ov-row">
                    <label>Scope</label>
                    <q-select v-model="semOverrideScope" :options="[{label:'Global',id:'global'},{label:'Regional',id:'regional'},{label:'Internal',id:'internal'}]" option-label="label" option-value="id" emit-value map-options dense outlined options-dense label="Scope" style="min-width:110px" />
                  </div>
                  <button class="st-btn st-btn--confirm" :disabled="!semOverrideTypeId || semTypeConfirming" @click="applySemTypeOverride">
                    <q-spinner-dots v-if="semTypeConfirming" size="13px" class="q-mr-xs" />
                    <q-icon v-else name="check" size="13px" class="q-mr-xs" />Apply
                  </button>
                  <button class="st-btn st-btn--ghost" @click="semTypeOverrideOpen = false">Cancel</button>
                </div>

                <div class="sem-annot-sep" />

                <!-- Reasoning plate (collapsed by default, plain terms) -->
                <button class="sem-plate-toggle" @click="semPlateOpen = !semPlateOpen">
                  <q-icon :name="semPlateOpen ? 'expand_less' : 'expand_more'" size="15px" />
                  <span>Why this?</span>
                </button>
                <div v-if="semPlateOpen" class="sem-plate-body">
                  <template v-if="semPlate.unresolved">
                    <p class="sem-plate-why">{{ semPlate.whyNotFound }}</p>
                    <div v-if="semPlate.nearMisses.length" class="sem-plate-block">
                      <div class="sem-plate-h">Closest matches, and why not</div>
                      <div v-for="(m, i) in semPlate.nearMisses" :key="i" class="sem-plate-row">
                        <span>{{ semTypeIdLabel(m.type_id) }}</span> — {{ m.reason }}
                      </div>
                    </div>
                    <button class="sem-plate-ai" :disabled="semTypeAiRunning" @click="resolveSemTypeWithAi">
                      <q-spinner-dots v-if="semTypeAiRunning" size="13px" class="q-mr-xs" />
                      <q-icon v-else name="auto_awesome" size="13px" class="q-mr-xs" />
                      {{ semTypeAiRunning ? 'Scanning…' : 'Ask AI to help' }}
                    </button>
                  </template>
                  <template v-else>
                    <div v-if="semPlate.whyThis.length" class="sem-plate-block">
                      <div class="sem-plate-h">Why this</div>
                      <div v-for="(f, i) in semPlate.whyThis" :key="i" class="sem-plate-row">{{ f }}</div>
                    </div>
                    <div v-if="semPlate.alsoBacking.length" class="sem-plate-block">
                      <div class="sem-plate-h">Also backing this up</div>
                      <div v-for="(f, i) in semPlate.alsoBacking" :key="i" class="sem-plate-row">{{ f }}</div>
                    </div>
                    <div v-if="semPlate.caveat" class="sem-plate-block">
                      <div class="sem-plate-h sem-plate-h--warn">Worth checking</div>
                      <div class="sem-plate-row sem-plate-caveat">{{ semPlate.caveat }}</div>
                      <div v-if="semPlate.caveatAdvice" class="sem-plate-row sem-plate-caveat">{{ semPlate.caveatAdvice }}</div>
                    </div>
                    <div v-if="semPlate.alsoConsidered.length" class="sem-plate-block">
                      <div class="sem-plate-h">Also considered</div>
                      <div class="sem-plate-row">{{ semPlate.alsoConsidered.map(semTypeIdLabel).join(', ') }}</div>
                    </div>
                  </template>
                </div>
                </div>
              </div>
              <div v-else class="panel-card block-card q-mt-md sem-annot sem-annot--empty">
                <div class="block-bar">
                  <span class="block-bar-title">Semantic Type</span>
                  <span class="block-bar-actions">
                    <button class="st-btn" :disabled="semTypeResolving" @click="resolveSemType">
                      <q-spinner-dots v-if="semTypeResolving" size="13px" class="q-mr-xs" />
                      <q-icon v-else name="search" size="13px" class="q-mr-xs" />Resolve now
                    </button>
                  </span>
                </div>
                <div class="block-body q-pa-md">
                  <span class="desc-empty">No semantic type resolved yet.</span>
                </div>
              </div>

              <!-- Interpretation lifecycle footer retired (5b.3.2b #1): the analyst actions
                   live in the tab-contextual header, and the steward decision feedback is
                   relocated to a slim banner at the top of this tab. -->

              <!-- Submit-for-review confirmation panel (Phase 5b.1 — restyled 5b.3.2 #10) -->
              <q-dialog v-model="submitPanelOpen">
                <q-card class="submit-panel-card" style="min-width:460px;max-width:560px">
                  <q-card-section class="submit-panel-head">
                    <div class="submit-panel-head-row">
                      <span class="submit-panel-head-icon"><q-icon name="rate_review" size="18px" /></span>
                      <div>
                        <div class="submit-panel-title">Submit interpretation for review</div>
                        <div class="submit-panel-sub mono">{{ store.element?.column }}</div>
                      </div>
                    </div>
                  </q-card-section>
                  <q-card-section class="submit-panel-body">
                    <div class="submit-panel-label">Included in this submission</div>
                    <div class="sp-item">
                      <q-icon name="check_circle" size="15px" class="sp-item-check" />
                      <div class="sp-item-main">
                        <div class="sp-item-key">Definition</div>
                        <div class="sp-item-val">{{ descValue || '—' }}</div>
                      </div>
                    </div>
                    <div class="sp-item">
                      <q-icon name="check_circle" size="15px" class="sp-item-check" />
                      <div class="sp-item-main">
                        <div class="sp-item-key">Business name</div>
                        <div class="sp-item-val">{{ bnameValue || '—' }}</div>
                      </div>
                    </div>
                    <div class="sp-item">
                      <q-icon name="check_circle" size="15px" class="sp-item-check" />
                      <div class="sp-item-main">
                        <div class="sp-item-key">Semantic type</div>
                        <div class="sp-item-val">{{ semTypeRecord && !semTypeIsUnresolved ? semTypeIdLabel(semTypeRecord.type_id) : '—' }}</div>
                      </div>
                    </div>
                    <div v-if="store.element?.glossary_term" class="sp-item">
                      <q-icon name="check_circle" size="15px" class="sp-item-check" />
                      <div class="sp-item-main">
                        <div class="sp-item-key">Glossary term</div>
                        <div class="sp-item-val">{{ store.element.glossary_term.title }}</div>
                      </div>
                    </div>

                    <!-- Linked Reference Codeset cascade (5b.3.1) — submission-only, opt-in. -->
                    <label v-if="submitCascadeEligible" class="submit-panel-cascade">
                      <input type="checkbox" v-model="submitCascadeRefCodes" />
                      <span><strong>Linked Reference Codeset</strong> — also submit {{ rdSubmittableCount }} filled code{{ rdSubmittableCount === 1 ? '' : 's' }} for review</span>
                    </label>
                  </q-card-section>
                  <q-card-actions align="right" class="submit-panel-actions">
                    <button class="action-btn action-btn--secondary" @click="submitPanelOpen = false">Cancel</button>
                    <button class="action-btn action-btn--confirm" :disabled="lcActionLoading" @click="onConfirmSubmit">
                      <q-spinner-dots v-if="lcActionLoading" size="13px" class="q-mr-xs" />
                      <q-icon v-else name="rate_review" size="14px" class="q-mr-xs" />Confirm submit
                    </button>
                  </q-card-actions>
                </q-card>
              </q-dialog>

            </div>

            <!-- REFERENCE DATA -->
            <div v-show="activeTab === 'refdata'" class="tab-panel q-ma-md">
              <div v-if="store.loadingRefData" class="panel-card q-pa-md">
                <q-spinner-dots size="24px" color="primary" />
                <span class="q-ml-sm">Loading reference data…</span>
              </div>
              <template v-else-if="store.referenceData?.is_coded">
                <div class="panel-card q-pa-md q-mb-md">
                  <div class="row items-center q-mb-sm">
                    <span class="panel-card-title">Reference Data</span>
                    <span v-if="!rdNotApplicable" class="refdata-status-badge q-ml-sm" :class="rdBadgeClass">{{ rdStatusLabel }}</span>
                  </div>

                  <!-- Non-coded semantic type: Reference Data insert mode is only for coded
                       semantic types (reference_code, currency_code, country_code). -->
                  <div v-if="rdNotApplicable" class="refdata-domain refdata-domain--none">
                    <q-icon name="info" size="14px" class="q-mr-xs" />
                    Reference Data applies only to coded fields — this column's semantic type
                    (<b>{{ semTypeRecord?.type_id ?? 'not set' }}</b>) is not a coded type
                    (reference_code, currency_code, or country_code), so there are no codes to review here.
                  </div>

                  <template v-else>
                  <!-- Reference-set binding (Phase 3; own submit/approve lifecycle since 2026-08-16) -->
                  <div class="rd-binding q-mb-md">
                    <template v-if="rdBoundSetId">
                      <div class="rd-binding-bound">
                        <q-icon name="link" size="15px" class="q-mr-xs" />
                        Bound to <b>{{ rdBoundSet?.name ?? rdBoundSetId }}</b>
                        <span v-if="rdBoundSet" class="rd-binding-kind">{{ rdBoundSet.kind === 'standard' ? 'Standard' : 'Local' }}</span>
                        <span class="rd-binding-status" :class="`rd-binding-status--${rdBindingStatus}`">{{ rdBindingStatusLabel }}</span>
                        <button class="action-btn action-btn--secondary q-ml-sm" :disabled="rdBindingSaving" @click="rdUnbind">
                          <q-spinner-dots v-if="rdBindingSaving" size="13px" class="q-mr-xs" />
                          <q-icon v-else name="link_off" size="14px" class="q-mr-xs" />Unbind
                        </button>
                      </div>
                      <div class="rd-binding-note">{{ rdBindingNote }}</div>
                    </template>
                    <template v-else>
                      <div class="rd-binding-row">
                        <q-select
                          v-model="rdSelectedSetId"
                          :options="rdSetOptions"
                          emit-value
                          map-options
                          dense
                          outlined
                          clearable
                          label="Bind to reference set"
                          class="rd-binding-select"
                          @focus="rdLoadSets"
                        />
                        <button class="action-btn action-btn--primary" :disabled="!rdSelectedSetId || rdBindingSaving" @click="rdBind(rdSelectedSetId)">
                          <q-spinner-dots v-if="rdBindingSaving" size="13px" class="q-mr-xs" />
                          <q-icon v-else name="link" size="14px" class="q-mr-xs" />Bind
                        </button>
                      </div>
                      <div v-if="rdSuggestedSet" class="rd-binding-suggest">
                        <q-icon name="lightbulb" size="14px" class="q-mr-xs" />
                        Suggested: <b>{{ rdSuggestedSet.name }}</b>
                        <button class="rd-suggest-link" :disabled="rdBindingSaving" @click="rdBind(rdSuggestedSetId)">Bind suggested</button>
                      </div>
                    </template>
                  </div>

                  <!-- ═══ Per-code reviewable Reference Data (5b.2, Postgres, unbound) ═══ -->
                  <template v-if="rdPgMode">
                    <div v-if="!rdSemanticAccepted" class="rd-gate-banner q-mb-sm">
                      <q-icon name="lock" size="14px" class="q-mr-xs" />
                      Reference Data unlocks once the semantic type is Accepted. Accept the coded type on the Interpretation tab to draft and submit codes here.
                    </div>
                    <template v-else>

                    <!-- Bulk-action toolbar (5b.3.1) — drives the analyst pull-backs on the
                         checkbox selection; each button acts on its matching status subset. -->
                    <div class="rd-bulk-bar q-mb-sm">
                      <span class="rd-bulk-count">{{ rdSelectedCount }} selected</span>
                      <button
                        class="action-btn action-btn--secondary"
                        :disabled="rdBulkLoading || rdWithdrawableSelected.length === 0"
                        title="Return selected In-Review codes to editable Draft"
                        @click="rdWithdrawSelected"
                      >
                        <q-spinner-dots v-if="rdBulkLoading" size="13px" class="q-mr-xs" />
                        <q-icon v-else name="undo" size="14px" class="q-mr-xs" />Withdraw{{ rdWithdrawableSelected.length ? ` ${rdWithdrawableSelected.length}` : '' }}
                      </button>
                      <button
                        class="action-btn action-btn--secondary"
                        :disabled="rdBulkLoading || rdRevocableSelected.length === 0"
                        title="Return selected Approved codes to editable Draft"
                        @click="rdRevokeSelected"
                      >
                        <q-icon name="lock_open" size="14px" class="q-mr-xs" />Revoke{{ rdRevocableSelected.length ? ` ${rdRevocableSelected.length}` : '' }}
                      </button>
                      <button
                        class="action-btn action-btn--secondary"
                        :disabled="rdBulkLoading || rdRemovableSelected.length === 0"
                        title="Delete selected Empty/Draft codes"
                        @click="rdRemoveSelected"
                      >
                        <q-icon name="delete_outline" size="14px" class="q-mr-xs" />Remove{{ rdRemovableSelected.length ? ` ${rdRemovableSelected.length}` : '' }}
                      </button>
                    </div>

                    <table class="code-table rd-code-table">
                      <thead>
                        <tr>
                          <th style="width:36px"><input type="checkbox" :checked="rdAllSelected" @change="rdAllSelected = ($event.target as HTMLInputElement).checked" /></th>
                          <th>Code</th>
                          <th>Value</th>
                          <th>Meaning</th>
                          <th style="width:120px">Origin</th>
                          <th style="width:110px">Status</th>
                          <th v-if="!rdBoundSetId">Share</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="c in rdDisplayCodes" :key="c.code" :class="{ 'rd-row-locked': !rdRowEditable(c), 'rd-row-selected': rdSelected.has(c.code), 'rd-row-governed': c.governed }">
                          <td>
                            <q-icon v-if="c.governed" name="lock" size="14px" title="Governed by the bound reference set" />
                            <input v-else type="checkbox" :checked="rdSelected.has(c.code)" @change="rdToggleCode(c.code, ($event.target as HTMLInputElement).checked)" />
                          </td>
                          <td class="mono">
                            {{ c.code }}
                            <q-icon v-if="c.in_source === false" name="add_circle_outline" size="12px" class="q-ml-xs rd-declared-mark" title="Declared code (not observed in source)" />
                          </td>
                          <td>
                            <input
                              v-if="rdRowEditable(c)"
                              class="rd-meaning-input"
                              :value="rdValueEdits[c.code] ?? c.value ?? ''"
                              placeholder="Enter value…"
                              @input="rdValueEdits[c.code] = ($event.target as HTMLInputElement).value"
                            />
                            <template v-else>{{ c.value ?? '—' }}</template>
                          </td>
                          <td>
                            <input
                              v-if="rdRowEditable(c)"
                              class="rd-meaning-input"
                              :value="rdMeaningEdits[c.code] ?? c.meaning ?? ''"
                              placeholder="Enter meaning…"
                              @input="rdMeaningEdits[c.code] = ($event.target as HTMLInputElement).value"
                            />
                            <template v-else>{{ c.meaning ?? '—' }}</template>
                          </td>
                          <td>
                            <select
                              v-if="rdRowEditable(c)"
                              class="rd-origin-select"
                              :value="rdOriginEdits[c.code] ?? c.origin ?? 'profiled'"
                              @change="rdOriginEdits[c.code] = ($event.target as HTMLSelectElement).value"
                            >
                              <option value="profiled">Profiled</option>
                              <option value="declared">Declared</option>
                            </select>
                            <span v-else-if="c.governed" class="rd-origin-static">Master list</span>
                            <span v-else class="rd-origin-static">{{ c.origin === 'declared' ? 'Declared' : 'Profiled' }}</span>
                          </td>
                          <td>
                            <span class="rd-code-status" :class="`rdcode--${c.status ?? 'empty'}`">
                              <q-icon v-if="c.status === 'approved' || c.governed" name="lock" size="11px" class="q-mr-xs" />
                              {{ rdCodeStatusLabel(c.status) }}
                            </span>
                          </td>
                          <td v-if="!rdBoundSetId">{{ c.share_pct != null ? c.share_pct + '%' : '—' }}</td>
                        </tr>
                      </tbody>
                    </table>

                    <!-- Add code + footer actions -->
                    <div class="rd-code-actions q-mt-sm">
                      <div v-if="rdShowAddCode" class="rd-add-row">
                        <input
                          v-model="rdNewCodeName"
                          class="rd-meaning-input rd-add-input"
                          placeholder="New code…"
                          @keyup.enter="rdAddCode"
                        />
                        <button class="action-btn action-btn--primary" :disabled="!rdNewCodeName.trim()" @click="rdAddCode">
                          <q-icon name="add" size="14px" class="q-mr-xs" />Add
                        </button>
                        <button class="action-btn action-btn--secondary" @click="rdShowAddCode = false; rdNewCodeName = ''">Cancel</button>
                      </div>
                      <button v-else class="action-btn action-btn--secondary" @click="rdShowAddCode = true">
                        <q-icon name="add" size="14px" class="q-mr-xs" />Add code
                      </button>
                    </div>

                    <div class="rd-code-footer q-mt-md">
                      <button class="action-btn action-btn--primary" :disabled="rdSavingCodes || !rdCanSaveDraft" @click="rdSaveDraft">
                        <q-spinner-dots v-if="rdSavingCodes" size="13px" class="q-mr-xs" />
                        <q-icon v-else name="save" size="14px" class="q-mr-xs" />Save draft
                      </button>
                      <button
                        class="action-btn action-btn--primary"
                        :disabled="rdSubmitting || !rdCanSubmit || !rdSemanticAccepted"
                        :title="!rdSemanticAccepted ? 'Accept the semantic type to submit' : (!rdCanSubmit ? 'Tick at least one filled draft code, or bind this field, to submit' : '')"
                        @click="rdSubmitCodes"
                      >
                        <q-spinner-dots v-if="rdSubmitting" size="13px" class="q-mr-xs" />
                        <q-icon v-else name="rate_review" size="14px" class="q-mr-xs" />{{ rdSubmitLabel }}
                      </button>
                      <span class="rd-code-footer-hint">Tick the filled draft codes to submit. Approved and in-review codes are frozen.</span>
                    </div>
                    </template>
                  </template>

                  <!-- ═══ Legacy whole-field Reference Data (yaml backend / bound sets) ═══ -->
                  <template v-else>
                  <table class="code-table">
                    <thead>
                      <tr>
                        <th>Code</th>
                        <th>Value</th>
                        <th>Meaning</th>
                        <th>Share</th>
                        <th style="width:80px"></th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="c in rdCodes" :key="c.code">
                        <td class="mono">{{ c.code }}</td>
                        <td>
                          <template v-if="rdEditMode">
                            <input
                              class="rd-meaning-input"
                              :value="rdValueEdits[c.code] ?? c.value ?? ''"
                              :placeholder="c.value ?? 'Enter value…'"
                              @input="rdValueEdits[c.code] = ($event.target as HTMLInputElement).value"
                            />
                          </template>
                          <template v-else>
                            {{ c.value ?? '—' }}
                          </template>
                        </td>
                        <td>
                          <template v-if="rdEditMode">
                            <input
                              class="rd-meaning-input"
                              :value="rdMeaningEdits[c.code] ?? c.meaning ?? ''"
                              :placeholder="c.meaning ?? 'Enter meaning…'"
                              @input="rdMeaningEdits[c.code] = ($event.target as HTMLInputElement).value"
                            />
                          </template>
                          <template v-else>
                            {{ c.meaning ?? '—' }}
                          </template>
                        </td>
                        <td>{{ c.share_pct }}%</td>
                        <td>
                          <div class="code-bar">
                            <div class="code-bar-fill" :style="{ width: c.share_pct + '%' }" />
                          </div>
                        </td>
                      </tr>
                    </tbody>
                  </table>

                  <!-- Meaning edit actions -->
                  <div class="rd-edit-row q-mt-sm">
                    <template v-if="rdBoundSetId">
                      <span class="rd-bound-hint"><q-icon name="lock" size="13px" class="q-mr-xs" />Meanings managed by the bound set.</span>
                    </template>
                    <template v-else-if="!rdEditMode">
                      <button class="action-btn action-btn--secondary" @click="rdStartEdit">
                        <q-icon name="edit" size="14px" class="q-mr-xs" />Edit meanings
                      </button>
                    </template>
                    <template v-else>
                      <button class="action-btn action-btn--primary" :disabled="rdSaving" @click="rdSaveMeanings">
                        <q-spinner-dots v-if="rdSaving" size="13px" class="q-mr-xs" />
                        <q-icon v-else name="save" size="14px" class="q-mr-xs" />Save
                      </button>
                      <button class="action-btn action-btn--secondary" @click="rdCancelEdit">
                        <q-icon name="close" size="14px" class="q-mr-xs" />Cancel
                      </button>
                    </template>
                  </div>

                  <!-- Reference Data workflow -->
                  <div class="def-workflow q-mt-md">
                    <div class="def-wf-header">
                      <span class="def-wf-title">Reference Data Status</span>
                      <span class="def-wf-state" :class="`def-wf-state--${rdStatus === 'approved' ? 'approved' : rdStatus === 'under_review' ? 'defined' : 'draft'}`">{{ rdStatusLabel }}</span>
                    </div>
                    <div class="def-wf-steps">
                      <span class="def-wf-step" :class="{ active: true }">1. Candidate</span>
                      <span class="def-wf-arr">›</span>
                      <span class="def-wf-step" :class="{ active: rdStatus === 'under_review' || rdStatus === 'approved' }">2. Under Review</span>
                      <span class="def-wf-arr">›</span>
                      <span class="def-wf-step" :class="{ active: rdStatus === 'approved' }">3. Approved</span>
                    </div>
                    <div class="def-wf-actions">
                      <button
                        v-if="rdStatus === 'candidate'"
                        class="action-btn action-btn--secondary"
                        :disabled="rdStatusSaving"
                        @click="rdSetStatus('under_review')"
                      >
                        <q-spinner-dots v-if="rdStatusSaving" size="13px" class="q-mr-xs" />
                        <q-icon v-else name="rate_review" size="14px" class="q-mr-xs" />Submit for Review
                      </button>
                      <button
                        v-else-if="rdStatus === 'under_review'"
                        class="action-btn action-btn--primary"
                        :disabled="rdStatusSaving"
                        @click="rdSetStatus('approved')"
                      >
                        <q-spinner-dots v-if="rdStatusSaving" size="13px" class="q-mr-xs" />
                        <q-icon v-else name="verified" size="14px" class="q-mr-xs" />Approve
                      </button>
                      <button
                        v-if="rdStatus !== 'candidate'"
                        class="action-btn action-btn--secondary"
                        :disabled="rdStatusSaving"
                        @click="rdSetStatus('candidate')"
                      >
                        <q-icon name="restart_alt" size="14px" class="q-mr-xs" />Revert to Candidate
                      </button>
                    </div>
                  </div>
                  </template>
                  </template>
                </div>
              </template>
              <div v-else class="panel-card q-pa-md panel-empty">
                <q-icon name="info" class="q-mr-xs" />This column is not a coded column (has more than 50 distinct values).
              </div>
            </div>

            <!-- MAPPING -->
            <div v-show="activeTab === 'mapping'" class="tab-panel q-ma-md">
              <div v-if="store.element.mapping_candidates.length">
                <q-card v-for="(mc, i) in store.element.mapping_candidates" :key="i" flat bordered class="q-mb-sm" style="border-radius:8px">
                  <q-card-section class="q-pa-sm">
                    <div class="row items-center q-gutter-sm">
                      <q-chip dense class="mono bg-blue-1 text-blue-9">{{ mc.target }}</q-chip>
                      <q-icon name="arrow_forward" color="grey-5" />
                      <span class="mono text-body2">{{ mc.target_schema }}.{{ mc.target_table }}.{{ mc.target_column }}</span>
                      <q-space />
                      <q-badge :color="confidenceColor(mc.confidence)" :label="`${mc.confidence != null ? Math.round(mc.confidence * 100) : '?'}%`" />
                      <q-badge :color="candidateStatusColor(mc.status)" :label="mc.status || 'pending'" class="text-capitalize" />
                    </div>
                    <div v-if="mc.rationale" class="text-caption text-grey-6 q-mt-xs">{{ mc.rationale }}</div>
                    <div v-if="mc.transformation_type" class="text-caption text-grey-5 q-mt-xs">Transform: <span class="mono">{{ mc.transformation_type }}</span></div>
                  </q-card-section>
                </q-card>
              </div>
              <div v-else class="panel-card q-pa-md panel-empty">
                <q-icon name="alt_route" class="q-mr-xs" />No mapping candidates yet.
                <q-btn flat dense size="sm" label="Go to Mapping" color="primary" :to="`/workspace/mapping`" class="q-ml-sm" />
              </div>
            </div>

            <!-- HISTORY -->
            <div v-show="activeTab === 'history'" class="tab-panel q-ma-md">
              <div class="panel-card q-pa-md">
                <div v-if="store.element.audit_history.length">
                  <q-list dense separator>
                    <q-item v-for="(evt, i) in store.element.audit_history" :key="i" dense>
                      <q-item-section avatar>
                        <q-icon :name="(evt as any).event_class === 'ai' ? 'smart_toy' : 'history'" size="15px" color="grey-5" />
                      </q-item-section>
                      <q-item-section>
                        <div class="row items-center justify-between gap-md">
                          <span class="text-body2">{{ formatAuditEvent(evt) }}</span>
                          <span class="text-caption text-grey-7">{{ fmtDate((evt as any).occurred_at) }}</span>
                        </div>
                      </q-item-section>
                    </q-item>
                  </q-list>
                </div>
                <div v-else class="panel-empty">No audit history for this element.</div>
              </div>
            </div>

          </div>
        </template>

        <!-- ── UPLOAD MODAL ──────────────────────────────────────────────── -->
        <q-dialog v-model="showUploadModal" persistent>
          <q-card style="width:600px;max-width:95vw;border-radius:16px">
            <q-card-section class="row items-center q-pb-sm">
              <div class="docs-modal-icon"><q-icon name="upload" size="19px" /></div>
              <div class="q-ml-sm">
                <div style="font-size:15px;font-weight:700">Upload source document</div>
                <div style="font-size:11.5px;color:#86827a">PDF, DOCX, XLSX, TXT, CSV · max 50 MB · must not contain personal data (GDPR Art. 25)</div>
              </div>
              <q-space /><q-btn flat round dense icon="close" @click="showUploadModal = false" />
            </q-card-section>
            <q-card-section class="q-pt-xs" style="display:flex;flex-direction:column;gap:14px">
              <!-- Dropzone placeholder -->
              <div
                class="docs-dropzone"
                :class="{ 'docs-dropzone--drag': dropzoneActive }"
                @click="fileInputRef?.click()"
                @dragover.prevent="dropzoneActive = true"
                @dragleave.prevent="dropzoneActive = false"
                @drop.prevent="onFileDrop"
              >
                <input
                  ref="fileInputRef"
                  type="file"
                  accept=".pdf,.docx,.xlsx,.txt,.csv"
                  style="display:none"
                  @change="onFileChange"
                />
                <q-icon name="upload_file" size="32px" style="color:#c9c3ba;margin-bottom:8px" />
                <div style="font-weight:600;font-size:13px">
                  <span v-if="uploadForm.file">{{ uploadForm.file.name }}</span>
                  <span v-else>Drop file here or click to browse</span>
                </div>
                <div style="font-size:11.5px;color:#86827a;margin-top:3px">
                  <span v-if="uploadForm.file">{{ (uploadForm.file.size / 1024 / 1024).toFixed(2) }} MB</span>
                  <span v-else>PDF, DOCX, XLSX, TXT, CSV · max 50 MB</span>
                </div>
              </div>
              <!-- Name + Type -->
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <q-input v-model="uploadForm.name" outlined dense label="Document name *" />
                <q-select v-model="uploadForm.type" outlined dense label="Document type *"
                  :options="['Data Dictionary','Mapping Spec','Quality Rules','System Spec','Other']" />
              </div>
              <!-- Description -->
              <q-input v-model="uploadForm.description" outlined dense type="textarea" rows="2" label="Description (recommended)" />
              <!-- Owner + Scope -->
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <q-input v-model="uploadForm.owner" outlined dense label="Document owner *" />
                <q-select v-model="uploadForm.scope" outlined dense label="Scope"
                  :options="['System-level','Dataset-level','Cross-dataset']" />
              </div>
              <!-- AI Permissions -->
              <div class="docs-modal-ai-section">
                <div class="docs-modal-ai-header">
                  <q-icon name="auto_awesome" size="14px" class="q-mr-xs" style="color:var(--accent)" />
                  <strong>{{ assistantName }} AI processing</strong>
                  <span style="font-size:11.5px;color:#86827a;font-weight:400;margin-left:6px">Choose what {{ assistantName }} may use this document for. Each requires explicit consent and is audited.</span>
                </div>
                <div class="docs-modal-ai-perms">
                  <label class="docs-perm-row">
                    <q-checkbox v-model="uploadForm.aiDef" dense color="primary" />
                    <div>
                      <div style="font-size:13px;font-weight:600">Definition grounding</div>
                      <div style="font-size:11.5px;color:#86827a">{{ assistantName }} reads definitions from this document to enrich element descriptions and glossary terms.</div>
                    </div>
                  </label>
                  <label class="docs-perm-row">
                    <q-checkbox v-model="uploadForm.aiMap" dense color="primary" />
                    <div>
                      <div style="font-size:13px;font-weight:600">Mapping suggestions</div>
                      <div style="font-size:11.5px;color:#86827a">{{ assistantName }} uses mapping specs or business descriptions to suggest BIRD/CRDM target alignments.</div>
                    </div>
                  </label>
                  <label class="docs-perm-row">
                    <q-checkbox v-model="uploadForm.aiQuality" dense color="primary" />
                    <div>
                      <div style="font-size:13px;font-weight:600">Quality rule inference</div>
                      <div style="font-size:11.5px;color:#86827a">{{ assistantName }} identifies data quality rules stated in the document and proposes validation rules. Rules are editable and auditable before activation.</div>
                    </div>
                  </label>
                </div>
              </div>
              <!-- GDPR notice -->
              <div style="font-size:10.5px;color:#86827a;line-height:1.5">By uploading you confirm this document contains no personal data and you have authority to share it for data governance purposes. Governed by GDPR Art. 25.</div>
            </q-card-section>
            <q-card-actions align="right" class="q-pa-md q-pt-xs">
              <q-btn flat no-caps label="Cancel" @click="showUploadModal = false" />
              <q-btn no-caps unelevated color="primary" label="Upload & process" :disabled="!uploadForm.name || !uploadForm.type" @click="submitUpload" />
            </q-card-actions>
          </q-card>
        </q-dialog>
      </section>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue';
import { Notify } from 'quasar';
import { useRoute } from 'vue-router';
import { useElementStore, type WorkspaceBreadcrumbSegment } from 'src/stores/elementStore';
import type { TableEntry, LifecycleState, ColumnSummary, ReferenceSetSummary, CodeEntry } from 'src/api/element';
import { updateReferenceData as apiUpdateReferenceData, listReferenceSets as apiListReferenceSets, REFERENCE_SET_SUGGESTIONS } from 'src/api/element';
import { listDocuments, uploadDocument } from 'src/api/documents';
import { rebuildSourceProfiles, resetSourceProfile, resetTableProfile } from 'src/api/discovery';
import BusinessContextPanel from 'src/components/BusinessContextPanel.vue';
import StagedLoader from 'src/components/StagedLoader.vue';
import AiErrorBanner from 'src/components/AiErrorBanner.vue';
import DqActionShareMenu from 'src/components/DqActionShareMenu.vue';
import KpiStripCard from 'src/components/viz/KpiStripCard.vue';
import ProportionalBarCard from 'src/components/viz/ProportionalBarCard.vue';
import SplitBarCard from 'src/components/viz/SplitBarCard.vue';
import QualityMapCard from 'src/components/viz/QualityMapCard.vue';
import {
  govSegments,
  dqIntentColor,
  GOV_SEGMENT_HINT,
  GOV_SEGMENT_LABEL,
  type VizSegment,
  type VizKpi,
  type VizQualityPoint,
} from 'src/components/viz/vizTypes';
import { useAiError } from 'src/composables/useAiError';
import { usePersonaStore } from 'src/stores/personaStore';
import { useRoleStore } from 'src/stores/roleStore';import { ASSISTANT_NAME } from 'src/config/assistant';
import { getStatusTone, govDisplayBucket } from 'src/utils/statusDisplay';
import { parseDeepLinkQuery, resolveTableColumn, shouldApplyDeepLink, type DeepLinkQuery } from './assetWorkspaceDeepLink';
import { semanticConfidenceTag, semanticTypeButtons, semanticReasoningPlate, semanticTypeLabel, semanticDomainLabel, semanticScopeLabel, semanticTypeMatchesQuery, findSemTypeRecordForColumn, type SemTypeRecordLike } from './semanticTypeDisplay';
import {
  isScored,
  isExcluded,
  DQ_EXCLUDED_LABEL,
  dqBandClass,
  dqBadgeText,
  dqBandLabel,
  dqScoreText,
  dqScorePreciseText,
  DQ_GRADE_BANDS,
  componentDisplays,
  componentColorKey,
  componentLabel,
  componentTabColorKey,
  donutSegments,
  dqActions,
  dqPathToNextGrade,
  reallocationExplanation,
  actionCaption,
  railDqBadge,
  groupedComponents,
  observationsForAction,
  unmatchedObservations,
  dqGradeDistribution,
} from './dqBadgeDisplay';
import type { DQAction, DQObservation } from './dqBadgeDisplay';
import {
  descopeSuggestion,
  isOutOfScope,
  scopeLabel,
} from './assessmentScopeDisplay';
import {
  isDatasetScored,
  isFullyDescoped,
  datasetScorePreciseText,
  datasetBandLabel,
  datasetBadgeText,
  datasetBandClass,
  datasetDonutSegments,
  datasetComponentDisplays,
  datasetContributions,
  DATASET_DRAG_THRESHOLD,
  datasetIntegrityItems,
} from './datasetDqDisplay';

const store = useElementStore();

const route = useRoute();

const roleStore = useRoleStore();

// Shared "AI action failed" banner for the non-chat LLM features on this page
// (AI draft description/business name, bulk drafts, AI semantic resolve).
const { aiError, setAiError, clearAiError, aiErrorFrom } = useAiError();

const _personaStore = usePersonaStore();
onMounted(() => _personaStore.loadPersona());
const assistantName = computed(() => _personaStore.name || ASSISTANT_NAME);

// ── Data Quality badge / card (U2b, DQ §14) ──────────────────────────────────
const dqBadge = computed(() => store.element?.dq ?? null);
const dqComponents = computed(() => componentDisplays(dqBadge.value));

// Polish Batch Task 8(b) — PROPOSAL, not yet decided: rename the "Data Quality"
// tab to "DQ Insights". Kept as a single, trivially-revertible label constant
// (flip back to 'Data Quality' to undo) — no route/key/store renamed.
const DQ_TAB_LABEL = 'DQ Insights';

// U4b — remediation slab + legibility.
const dqActionsList = computed(() => dqActions(dqBadge.value));
const dqPath = computed(() => dqPathToNextGrade(dqBadge.value));
const dqReallocation = computed(() => reallocationExplanation(dqBadge.value));
// U4b-fix — one-scale breakdown (Task 1) + observations folded into actions (Task 5).
// Data·Governance group headers, plus Actions to improve as a third group:
// Profile grouped as Data, everything else as Governance. No separate
// show/hide toggle — each group header is independently collapsible and
// defaults to collapsed.
const dqComponentGroups = computed(() => groupedComponents(dqBadge.value));
const dqGroupExpanded = ref<Record<string, boolean>>({ data: false, governance: false, actions: false });
const toggleDqGroup = (key: string) => {
  dqGroupExpanded.value[key] = !dqGroupExpanded.value[key];
};
const dqFindings = computed<DQObservation[]>(
  () => (store.element?.findings as DQObservation[] | undefined) ?? [],
);
const actionObservations = (a: DQAction) => observationsForAction(a, dqFindings.value);
const dqUnmatchedObservations = computed(
  () => unmatchedObservations(dqActionsList.value, dqFindings.value),
);
const pathLineItems = computed(
  () => new Set((dqPath.value?.actions ?? []).map((a) => `${a.component}|${a.line_item}`)),
);
const pathPoints = computed(() => {
  const acts = dqPath.value?.actions ?? [];
  return Math.round(acts.reduce((sum, a) => sum + a.points, 0) * 10) / 10;
});
// Total recoverable points across every action (not just the shortest path to
// the next grade) — shown in bold on the Actions group header, alongside the
// action count pill.
const dqActionsTotalPoints = computed(() => {
  const total = dqActionsList.value.reduce((sum, a) => sum + a.points, 0);
  return Math.round(total * 10) / 10;
});

// Polish Batch Task 9 — DQ grade distribution for the dataset overview, read
// straight off the already-persisted per-column badges (no scoring here).
const datasetDqGradeDist = computed(
  () => dqGradeDistribution(store.datasetOverview?.columns_summary ?? []),
);
// Polish Batch Task 11 (PROPOSAL) — dataset-level Observation Summary panel
// was removed (redundant with the DQ Insights findings list, and its AI
// column was always 0 since the backend built it with include_ai=False).

const DQ_DONUT_RADIUS = 52;
const DQ_DONUT_GAP = 8; // px gap between component arcs

const dqDonut = computed(() => {
  const circumference = 2 * Math.PI * DQ_DONUT_RADIUS;
  const segments = donutSegments(dqBadge.value);
  let cursor = 0;
  const arcs = segments.map((seg) => {
    const sweepLen = Math.max(0, seg.sweepFraction * circumference - DQ_DONUT_GAP);
    const fillLen = seg.fillFraction * sweepLen;
    const offset = cursor;
    cursor += seg.sweepFraction * circumference;
    return {
      name: seg.name,
      colorKey: seg.colorKey,
      trackDash: `${sweepLen} ${circumference - sweepLen}`,
      fillDash: `${fillLen} ${circumference - fillLen}`,
      dashOffset: -offset,
    };
  });
  return { circumference, radius: DQ_DONUT_RADIUS, arcs };
});

// ── Dataset DQ badge / card (U4a, DQ §15) ────────────────────────────────────
const datasetDq = computed(() => store.datasetOverview?.dataset_dq ?? null);
const datasetDqLegend = computed(() => datasetComponentDisplays(datasetDq.value));
const datasetDqIntegrity = computed(() => datasetIntegrityItems(datasetDq.value));
// True when a scored dataset has no "dataset_integrity" component at all
// (no PK/FK to check, or its only key is a single already-unique-checked
// column) — surfaced as an explicit "N/A" row + explanation so a steward
// never has to wonder why that line is just missing (§7 follow-up).
const datasetIntegrityNotApplicable = computed(() =>
  isDatasetScored(datasetDq.value) &&
  !(datasetDq.value?.applicable_components ?? []).includes('dataset_integrity'),
);
// "Columns dragging the score down" rows — filtered and sorted on each
// column's own live element badge (columns_summary), NOT the dataset
// roll-up's snapshot dq_score. The roll-up's line-item can lag a column's
// latest re-evaluation by one refresh cycle; filtering on that stale value
// while displaying the live one caused a column already re-scored to
// Good/Excellent to keep showing up in the list. Filter + display now read
// the same source, so a column drops out the moment it clears the threshold.
const dqDraggerRows = computed(() => {
  const summaries = store.datasetOverview?.columns_summary ?? [];
  const merged = datasetContributions(datasetDq.value).map((ct) => {
    const column = summaries.find((c) => c.name === ct.key) ?? null;
    const badge = column?.dq ?? null;
    return {
      key: ct.key,
      column,
      dq_score: badge?.dq_score ?? ct.dq_score,
      grade_label: badge?.grade_label ?? ct.grade_label,
      grade_color_intent: badge?.grade_color_intent ?? ct.grade_color_intent,
      action_count: badge?.action_count ?? ct.action_count ?? 0,
    };
  });
  return merged
    .filter((row) => row.dq_score < DATASET_DRAG_THRESHOLD)
    .sort((a, b) => a.dq_score - b.dq_score);
});
// Compact trend delta (§14) appended inside the score pill itself — e.g.
// "79 · Good (+2 ⬆)" — no separate sentence/column-count clutter next to it.
// Compares the CURRENT run to the PREVIOUS one (last two trend points), not
// the oldest kept point — so it stays in sync with the most recent
// re-evaluation (up/down/unchanged) rather than a stale multi-run window.
const datasetDqTrendEndpoints = computed(() => {
  const trend = (datasetDq.value?.trend ?? []).filter(
    (t): t is { dq_score: number; scored_at?: string | null; state?: string | null } =>
      t.dq_score != null,
  );
  if (trend.length < 2) return null;
  return { first: trend[trend.length - 2]!.dq_score, last: trend[trend.length - 1]!.dq_score };
});
const datasetDqTrendDelta = computed(() => {
  const ep = datasetDqTrendEndpoints.value;
  if (!ep) return '';
  const delta = ep.last - ep.first;
  const sign = delta > 0 ? '+' : '';
  const arrow = delta < 0 ? '⬇' : '⬆'; // unchanged (0) reads as "0 ⬆" per spec
  return `${sign}${delta} ${arrow}`;
});

const datasetDqDonut = computed(() => {
  const circumference = 2 * Math.PI * DQ_DONUT_RADIUS;
  const segments = datasetDonutSegments(datasetDq.value);
  let cursor = 0;
  const arcs = segments.map((seg) => {
    const sweepLen = Math.max(0, seg.sweepFraction * circumference - DQ_DONUT_GAP);
    const fillLen = seg.fillFraction * sweepLen;
    const offset = cursor;
    cursor += seg.sweepFraction * circumference;
    return {
      name: seg.name,
      colorKey: seg.colorKey,
      trackDash: `${sweepLen} ${circumference - sweepLen}`,
      fillDash: `${fillLen} ${circumference - fillLen}`,
      dashOffset: -offset,
    };
  });
  return { circumference, radius: DQ_DONUT_RADIUS, arcs };
});
const selectedSource = ref<string | null>(null);
const selectedTable = ref<string | null>(null);
const selectedTableSchema = ref<string | null>(null);
const selectedColumn = ref<string | null>(null);
const selectedSchemaFilter = ref<string | null>(null);
const viewMode = ref<'none' | 'source' | 'table' | 'column'>('none');
const activeTab = ref('profile');
const dsActiveTab = ref('overview');
const srcActiveTab = ref('overview');

// Plain-language, staged progress lines for the detail-panel loaders (StagedLoader
// narrates the stages of backend work; the panel swaps to real content on arrival).
// Every line below corresponds to a real, honest checkpoint the backend reports over
// SSE (see api/routes/element.py's _build_source_info/_build_table_overview/_build_element)
// — none of this is timed or fabricated; a stage only ticks once its real work is done.
const sourcesLoadStages = computed(() => [
  'Fetching your data sources…',
]);
const sourceLoadStages = computed(() => [
  `Opening ${selectedSource.value ?? 'the source'}'s catalog…`,
  'Checking data quality…',
  'Reviewing governance status and field types…',
  'Finalizing the workspace view…',
]);
const datasetLoadStages = computed(() => [
  `Opening ${selectedTable.value ?? 'the dataset'}…`,
  'Reading the column layout…',
  semanticStageSummary.value,
  'Gathering observations and findings…',
  'Checking data quality for every field…',
  'Putting the profile together…',
]);
// Stage index 2 (semantic-type resolution) has no static label -- once the LAST column's
// real tick arrives (fraction hits 1), swap the whole line to a one-time summary sentence
// instead of leaving the checklist row blank once this stage completes. Sticky: reset only
// when a fresh dataset load restarts the stage counter from 0.
const semanticStageSummary = ref('');
watch(() => store.overviewProgress.completed, (val) => {
  if (val === 0) semanticStageSummary.value = '';
});
watch(
  () => [store.overviewProgress.completed, store.overviewProgress.fraction, store.overviewProgress.total] as const,
  ([completed, fraction, total]) => {
    if (completed === 2 && fraction >= 1 && total > 0) {
      semanticStageSummary.value = `All ${total} fields are re-computed`;
    }
  },
);
const elementLoadStages = computed(() => [
  `Opening ${selectedColumn.value ?? 'the field'}…`,
  'Looking for glossary links and mappings…',
  'Working out its meaning and quality score…',
  'Finishing up…',
]);

// ── Assessment scoping panel (U2c, decision D1) ──────────────────────────────
const scopeSelection = ref<Set<string>>(new Set());
const scopeReason = ref('');
const scopeSaving = ref(false);
const scopeBanner = ref<{ type: 'success' | 'error'; msg: string } | null>(null);
const allDatasetsOption = { _all: true, table_name: '*', schema: '', description: null, row_count: null, columns: [] };
const colSearch = ref('');
const activeFilter = ref<'all' | 'empty' | 'draft' | 'in_review' | 'approved' | 'bounced' | 'observations' | 'coded' | 'pii' | 'unresolved'>('all');

// Definition tab state
const descValue = ref('');
const descDirty = ref(false);
const isDescEditMode = ref(false);
const draftLoading = ref(false);
const saveDescLoading = ref(false);
const isAiDraft = ref(false);  // Track if current draft is AI-generated
const isUserEdit = ref(false);  // Track manual user edits vs. programmatic updates

// Reference Data tab state
const rdEditMode = ref(false);
const rdMeaningEdits = ref<Record<string, string>>({});
const rdValueEdits = ref<Record<string, string>>({});
const rdSaving = ref(false);
const rdStatusSaving = ref(false);
const rdLocalStatus = ref<string | null>(null);

// Per-code Reference Data (5b.2, Postgres backend) state
const rdOriginEdits = ref<Record<string, string>>({});
const rdAddedCodes = ref<CodeEntry[]>([]);
const rdShowAddCode = ref(false);
const rdNewCodeName = ref('');
const rdSavingCodes = ref(false);
const rdSubmitting = ref(false);
// Multi-select + analyst bulk pull-backs (5b.3.1)
const rdSelected = ref<Set<string>>(new Set());
const rdBulkLoading = ref(false);
// Cascade tick in the interpretation submit panel (5b.3.1) — opt-in per submit.
const submitCascadeRefCodes = ref(false);

// Reference-set binding (Phase 3)
const rdSets = ref<ReferenceSetSummary[]>([]);
const rdBindingSaving = ref(false);
const rdSelectedSetId = ref<string | null>(null);

// Profile refresh state
const refreshingProfile = ref(false);

// ── Source profile rebuild state ──────────────────────────────────────────
function _rebuildStateDefault() {
  return {
    showWarning: false,
    running: false,
    done: false,
    index: 0,
    total: 0,
    completed: 0,
    failed: 0,
    currentTable: '',
    elapsed: 0,
    estimatedRemaining: 0,
    // SD-R5 (2026-08-12): bulk rebuild's opt-out checkboxes — default checked,
    // mirroring individual Refresh Profile's now-unconditional semantic+DQ pairing.
    includeSemantic: true,
    includeDq: true,
  };
}
const rebuildState = ref(_rebuildStateDefault());
let _rebuildAbort: AbortController | null = null;

// Bulk AI generation state
const bulkDescLoading = ref(false);
const bulkBizLoading = ref(false);
// Bulk section collapse state (all collapsed by default)
const bulkSrcStoriesOpen = ref(false);
const bulkSrcHistoryOpen = ref(false);
const bulkDsDescOpen = ref(false);
const bulkDsBizOpen = ref(false);
const bulkDsHistoryOpen = ref(false);
const bulkBanner = ref<{ msg: string; type: 'success' | 'info' | 'error' } | null>(null);
let bulkBannerTimer: ReturnType<typeof setTimeout> | null = null;

// Dataset header's "Referenced by" / "References to" chip lists — collapsed
// by default when there's more than one (a single entry is shown inline).
const referencedByExpanded = ref(false);
const foreignKeysExpanded = ref(false);

function showBulkBanner(msg: string, type: 'success' | 'info' | 'error' = 'success') {
  bulkBanner.value = { msg, type };
  if (bulkBannerTimer) clearTimeout(bulkBannerTimer);
  bulkBannerTimer = setTimeout(() => { bulkBanner.value = null; }, 5000);
}

// ── Bulk AI Draft history ─────────────────────────────────────────────────
interface BulkDraftRun {
  id: number;
  ts: string;
  scope: string; // 'source' | 'dataset'
  target: string; // source name or dataset name
  type: 'data_stories' | 'descriptions' | 'business_names' | 'all';
  generated: number;
  failed: number;
  total: number;
}
const bulkDraftHistory = ref<BulkDraftRun[]>([]);
let bulkRunCounter = 0;

const _BULK_LS_KEY = 'adirra-bulk-last-run';

function _loadBulkLastRun(): Record<string, string> {
  try { return JSON.parse(localStorage.getItem(_BULK_LS_KEY) ?? '{}'); } catch { return {}; }
}
function _saveBulkLastRun(rec: Record<string, string>) {
  try { localStorage.setItem(_BULK_LS_KEY, JSON.stringify(rec)); } catch { /* quota */ }
}
function _bulkLsKey(scope: string, type: string, target: string) {
  return `${scope}|${type}|${target}`;
}

// Reactive last-run map (scope|type|target → ISO timestamp)
const bulkLastRunMap = ref<Record<string, string>>(_loadBulkLastRun());

function getLastBulkRun(scope: string, type: string, target: string): string | null {
  return bulkLastRunMap.value[_bulkLsKey(scope, type, target)] ?? null;
}

function recordBulkRun(run: Omit<BulkDraftRun, 'id' | 'ts'>) {
  const ts = new Date().toISOString();
  bulkDraftHistory.value.unshift({ id: ++bulkRunCounter, ts, ...run });
  const rec = _loadBulkLastRun();
  rec[_bulkLsKey(run.scope, run.type, run.target)] = ts;
  _saveBulkLastRun(rec);
  bulkLastRunMap.value = { ...rec };
}

// ── Documents tab state ───────────────────────────────────────────────────
interface SourceDoc {
  id: number;
  name: string;
  type: 'Data Dictionary' | 'Mapping Spec' | 'System Spec' | 'Quality Rules' | 'Other';
  description: string;
  owner: string;
  scope: string;
  uploadedAt: string;
  status: 'processing' | 'ready' | 'failed';
  size: string;
  aiPermissions: { definitions: boolean; mapping: boolean; quality: boolean };
  aiKnowledge?: string; // what AI extracted
  _docId?: string; // backend document id (distinct from local numeric id)
}

const docList = ref<SourceDoc[]>([]);
const showUploadModal = ref(false);
const fileInputRef = ref<HTMLInputElement | null>(null);
const dropzoneActive = ref(false);
const docFilter = ref<'all' | 'Data Dictionary' | 'Mapping Spec' | 'System Spec' | 'Quality Rules'>('all');
const docSearch = ref('');
const uploadForm = ref<{ name: string; type: string; description: string; owner: string; scope: string; aiDef: boolean; aiMap: boolean; aiQuality: boolean; file: File | null }>({ name: '', type: '', description: '', owner: '', scope: 'System-level', aiDef: true, aiMap: true, aiQuality: false, file: null });
const selectedDocId = ref<number | null>(null);

const filteredDocs = computed(() => {
  let docs = docList.value;
  if (docFilter.value !== 'all') docs = docs.filter(d => d.type === docFilter.value);
  if (docSearch.value.trim()) {
    const q = docSearch.value.toLowerCase();
    docs = docs.filter(d => d.name.toLowerCase().includes(q) || d.description.toLowerCase().includes(q));
  }
  return docs;
});

function openDoc(id: number) { selectedDocId.value = selectedDocId.value === id ? null : id; }

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  if (file) {
    uploadForm.value.file = file;
    if (!uploadForm.value.name) uploadForm.value.name = file.name.replace(/\.[^.]+$/, '');
  }
  // reset so the same file can be re-selected
  input.value = '';
}

function onFileDrop(e: DragEvent) {
  dropzoneActive.value = false;
  const file = e.dataTransfer?.files?.[0];
  if (file) {
    uploadForm.value.file = file;
    if (!uploadForm.value.name) uploadForm.value.name = file.name.replace(/\.[^.]+$/, '');
  }
}

async function submitUpload() {
  if (!uploadForm.value.name || !uploadForm.value.type || !selectedSource.value) return;
  const localId = Date.now();
  const placeholder: SourceDoc = {
    id: localId,
    name: uploadForm.value.name,
    type: uploadForm.value.type as SourceDoc['type'],
    description: uploadForm.value.description,
    owner: uploadForm.value.owner || 'Unknown',
    scope: uploadForm.value.scope,
    uploadedAt: new Date().toISOString(),
    status: 'processing',
    size: '—',
    aiPermissions: { definitions: uploadForm.value.aiDef, mapping: uploadForm.value.aiMap, quality: uploadForm.value.aiQuality },
  };
  docList.value.unshift(placeholder);
  showUploadModal.value = false;
  const formSnapshot = { ...uploadForm.value };
  uploadForm.value = { name: '', type: '', description: '', owner: '', scope: 'System-level', aiDef: true, aiMap: true, aiQuality: false, file: null };
  dropzoneActive.value = false;
  try {
    const saved = await uploadDocument(selectedSource.value, {
      name: formSnapshot.name,
      doc_type: formSnapshot.type,
      description: formSnapshot.description,
      owner: formSnapshot.owner,
      scope: formSnapshot.scope,
      ai_def: formSnapshot.aiDef,
      ai_map: formSnapshot.aiMap,
      ai_quality: formSnapshot.aiQuality,
    }, formSnapshot.file ?? undefined);
    const idx = docList.value.findIndex(d => d.id === localId);
    if (idx !== -1) {
      docList.value[idx]._docId = saved.id;
      docList.value[idx].status = 'ready';
      docList.value[idx].size = saved.file_size_kb != null ? `${saved.file_size_kb} KB` : '—';
      docList.value[idx].aiKnowledge = saved.synopsis ?? undefined;
    }
  } catch {
    docList.value = docList.value.filter(d => d.id !== localId);
  }
}

// Distribution chart mode
const distMode = ref<'freq' | 'alpha'>('freq');
const distLogScale = ref(false);

// Business Name state
const bnameValue = ref('');
const bnameEditMode = ref(false);
const bnameSaving = ref(false);
const bnameDraftLoading = ref(false);
const bnameIsAi = ref(false);

// Business name is folded into the interpretation set (5b.3.2b) — it rides the element
// lifecycle and has no separate review state of its own.

// ── Mapping Type tab state ─────────────────────────────────────────────────
const semTypeRecord = ref<SemTypeRecordLike | null>(null);
const semTypeLoading = ref(false);
const semTypeResolving = ref(false);
const semTypeConfirming = ref(false);
const semTypeAiRunning = ref(false);
// Override: cascading Role → Type → Scope pickers
const semTypeOverrideOpen = ref(false);
const semOverrideRole = ref<string | null>(null);
const semOverrideTypeId = ref<string | null>(null);
const semOverrideScope = ref<string | null>(null);
// Vocabulary loaded from API once per session
interface VocabData {
  roles?: Array<{ id: string; label: string }>;
  types_by_role?: Record<string, Array<{ id: string; label: string }>>;
  [key: string]: unknown;
}
const vocabData = ref<VocabData | null>(null);

// SD-R3b: Semantic Type as a subdued analyst annotation in the Definition tab.
const semPlateOpen = ref(false);
const semTypeTag = computed(() => semanticConfidenceTag(semTypeRecord.value));
const semTypeBtns = computed(() => semanticTypeButtons(semTypeRecord.value));
const semPlate = computed(() => semanticReasoningPlate(semTypeRecord.value));
const semTypeIsUnresolved = computed(() => {
  const r = semTypeRecord.value;
  return !r || !r.type_id || r.type_id === 'unresolved';
});
const semTypeAccepted = computed(() => !!semTypeRecord.value?.accepted_at);
const semTypeConflict = computed(() => !!semTypeRecord.value?.type_value_conflict);
const semTypePii = computed(() => !!semTypeRecord.value?.pii);
const semTypePiiTitle = computed(() => {
  const cat = semTypeRecord.value?.pii_category;
  const pretty = cat ? String(cat).replace(/_/g, ' ') : '';
  return pretty ? `Personal / sensitive data — ${pretty}` : 'Personal / sensitive data';
});
// Accept confirms the current recommendation; Replace/Resolve open the governed
// vocabulary picker (the existing override → accept path). No `rejected` concept.
function acceptSemType() { void confirmSemType(); }
function openSemTypePicker() {
  const r = semTypeRecord.value;
  semTypeOverrideOpen.value = true;
  semOverrideRole.value = r?.domain_role ?? null;
  semOverrideTypeId.value = r && r.type_id !== 'unresolved' ? (r.type_id ?? null) : null;
  semOverrideScope.value = r?.scope ?? null;
}

// ── Phase 5b.1 canonical interpretation-set lifecycle (UI) ─────────────────
const CODED_SEM_TYPES = ['reference_code', 'currency_code', 'country_code'];
const isCodedSemType = computed(() => {
  const t = semTypeRecord.value?.type_id;
  return !!t && CODED_SEM_TYPES.includes(t);
});
const lifecycleTone = computed(() => getStatusTone(store.element?.lifecycle_state ?? 'empty'));
const isLcApproved = computed(() => store.element?.lifecycle_state === 'approved');
const isLcInReview = computed(() => store.element?.lifecycle_state === 'in_review');
const isLcFrozen = computed(() => isLcApproved.value || isLcInReview.value);
const isLcEditable = computed(() => !isLcFrozen.value);
const submitGateMet = computed(() =>
  !!descValue.value.trim() && !!bnameValue.value.trim() && semTypeAccepted.value);
// Last lifecycle status update (5b.3.2 #12) — action verb + when. Shown once, at the
// tab-bar row (not per-card — a single consolidated "what happened last, and when" beats
// two separate, individually-meaningless per-card timestamps).
const lastStatusLabel = computed(() => {
  const ls = store.element?.last_status;
  if (!ls || !ls.at) return null;
  const verb = ({ draft: 'Drafted', in_review: 'Submitted', approved: 'Approved', returned: 'Returned', rejected: 'Rejected', withdrawn: 'Withdrawn', revoked: 'Revoked' } as Record<string, string>)[ls.action ?? ''] ?? 'Updated';
  return `${verb} on ${fmtDate(ls.at)}`;
});

// Steward decision feedback (5b.3.2b #1): a returned/rejected set surfaces the reason as a
// slim banner under the header until the analyst re-submits (a fresh submit clears the overlay).
const stewardFeedback = computed(() => {
  const sub = store.element?.submission;
  if (!sub || isLcInReview.value) return null;
  if (sub.decision === 'returned') {
    return { cls: 'sf--returned', icon: 'reply', text: `Returned for rework — ${sub.reject_reason || 'see steward comments'}` };
  }
  if (sub.decision === 'rejected') {
    return { cls: 'sf--rejected', icon: 'block', text: `Rejected — ${sub.reject_reason || 'no reason given'}` };
  }
  return null;
});

const submitPanelOpen = ref(false);
const lcActionLoading = ref(false);

async function onSaveDraft() {
  lcActionLoading.value = true;
  try {
    await store.saveInterpretation({
      description: descValue.value,
      descriptionIsAi: isAiDraft.value,
      businessName: bnameValue.value || null,
      businessNameIsAi: bnameIsAi.value,
      actorRole: roleStore.currentRole,
    });
    descDirty.value = false;
    isDescEditMode.value = false;
    bnameEditMode.value = false;
  } finally {
    lcActionLoading.value = false;
  }
}
function onSubmitClick() {
  submitCascadeRefCodes.value = false;
  submitPanelOpen.value = true;
  // Load reference codes so the "Linked Reference Codeset" cascade section can reflect
  // filled drafts even when submitting from the Interpretation tab (refdata may be unloaded
  // or stale for a previously-viewed column).
  const el = store.element;
  const rd = store.referenceData;
  if (isCodedSemType.value && el
      && (!rd || rd.source !== el.source || rd.table !== el.table || rd.column !== el.column)) {
    void store.loadReferenceData(el.source, el.table, el.column, el.schema);
  }
}
async function onConfirmSubmit() {
  lcActionLoading.value = true;
  try {
    const cascading = submitCascadeRefCodes.value && submitCascadeEligible.value && !!store.element;
    // When cascading, skip the interpretation submit's DQ refresh and run a single
    // refresh after the codes submit (one refresh tail instead of two).
    await store.submitInterpretation(undefined, roleStore.currentRole, cascading);
    if (cascading && store.element) {
      const el = store.element;
      await store.submitReferenceCodes(el.source, el.table, el.column, null, el.schema);
      await store.refreshElementDq('Submitted for review');
    }
    submitPanelOpen.value = false;
  } finally {
    lcActionLoading.value = false;
  }
}
async function onWithdraw() {
  lcActionLoading.value = true;
  try { await store.withdrawInterpretation(undefined, roleStore.currentRole); }
  finally { lcActionLoading.value = false; }
}
async function onRevoke() {
  lcActionLoading.value = true;
  try { await store.revokeInterpretation(undefined, roleStore.currentRole); }
  finally { lcActionLoading.value = false; }
}


// Fire ONLY when the viewed column changes — not when the same element's own fields
// update (e.g. a Save/Submit reassigns store.element). Watching the identity key keeps
// per-column edit buffers + the semantic-type record intact across lifecycle actions, so
// an accepted type no longer flickers to "Resolve now" and Submit doesn't drop out.
watch(
  () => store.element
    ? `${store.element.source}|${store.element.schema ?? ''}|${store.element.table}|${store.element.column}`
    : null,
  () => {
    const el = store.element;
    descValue.value = el?.column_description ?? '';
    descDirty.value = false;
    isDescEditMode.value = false;
    isUserEdit.value = false;
    isAiDraft.value = false;
    distMode.value = 'freq';
    distLogScale.value = false;
    bnameValue.value = el?.business_name ?? '';
    bnameEditMode.value = false;
    bnameIsAi.value = false;
    // Refresh the mapping-type record when the element changes while the tab is open
    // (the activeTab watch only fires on tab change, not element change).
    semTypeRecord.value = null;
    semTypeOverrideOpen.value = false;
    rdClearSelection();
    rdAddedCodes.value = [];
    if (el) {
      void loadSemTypeRecord();
      // On a page reload the restored active tab does not *change*, so the
      // activeTab watch never fires — load the tab's data here once the element
      // resolves so Reference Data isn't stuck on the "not a coded column" fallback.
      if (activeTab.value === 'refdata') {
        void store.loadReferenceData(el.source, el.table, el.column, el.schema);
        void rdLoadSets();
      }
    }
  },
);

watch(descValue, (v) => {
  descDirty.value = v !== (store.element?.column_description ?? '');
  // Only clear AI flag if user manually edits the text (isUserEdit = true)
  if (descDirty.value && isAiDraft.value && isUserEdit.value) {
    isAiDraft.value = false;
  }
});

// Load reference codes once a field is known to be coded, so the Interpretation-tab
// "Bound code set" strip badge reflects the real per-code status (and the submit-panel
// cascade section can see filled drafts) without needing to open the Reference Data tab.
watch(isCodedSemType, (coded) => {
  const el = store.element;
  const rd = store.referenceData;
  if (coded && el
      && (!rd || rd.source !== el.source || rd.table !== el.table || rd.column !== el.column)) {
    void store.loadReferenceData(el.source, el.table, el.column, el.schema);
  }
});

watch(activeTab, (tab) => {
  if (tab === 'refdata' && store.element && !store.referenceData) {
    void store.loadReferenceData(
      store.element.source,
      store.element.table,
      store.element.column,
      store.element.schema,
    );
  }
  if (tab === 'refdata') {
    void rdLoadSets();
  }
  if (tab === 'interpretation') {
    void loadSemTypeRecord();
  }
});

const filterChips = [
  { label: 'All',        value: 'all',          pip: null },
  { label: 'Empty',     value: 'empty',        pip: 'var(--empty-col)' },
  { label: 'Draft',      value: 'draft',        pip: 'var(--draft-col)' },
  { label: 'In-Review',  value: 'in_review',    pip: 'var(--in-review-col)' },
  { label: 'Approved',   value: 'approved',     pip: 'var(--approved-col)' },
  { label: 'Bounced',    value: 'bounced',      pip: 'var(--bounced-col)' },
  { label: 'Coded',      value: 'coded',        pip: '#6b46c1' },
  { label: 'PII',        value: 'pii',          pip: 'var(--danger-col)' },
  { label: 'Unresolved', value: 'unresolved',   pip: '#9e9e9e' },
] as const;

const railStates = ref<Record<string, LifecycleState>>({});

// localStorage persistence for selections
const STORAGE_KEY = 'workspace_selection';

function saveSelection() {
  const selection = {
    source: selectedSource.value,
    table: selectedTable.value,
    schema: selectedTableSchema.value,
    column: selectedColumn.value,
    viewMode: viewMode.value,
    activeTab: activeTab.value,
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(selection));
}

async function restoreSelection() {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (!saved) return;
  try {
    const { source, table, schema, column, viewMode: mode, activeTab: tab } = JSON.parse(saved);
    if (!source) return;

    // Restore all refs immediately so the UI snaps to the right level/item
    // The loading spinners for that level will show while data fetches
    selectedSource.value = source;
    // SD-R3c: the 'definition' tab was renamed 'interpretation'; heal any
    // persisted selection so an old localStorage value still lands on a panel.
    if (tab) activeTab.value = tab === 'definition' ? 'interpretation' : tab;

    if (column && table && table !== '*') {
      selectedTable.value = table;
      selectedTableSchema.value = schema;
      selectedColumn.value = column;
      viewMode.value = 'column';
      // Load everything needed for column view in parallel
      void store.loadTables(source);
      await Promise.all([
        store.loadElement(source, table, column, schema),
        store.loadDatasetOverview(source, table, schema),
        store.loadInsights(source, table, schema, false),
        store.loadDataStory(source, table, schema),
      ]);
    } else if (table && table !== '*') {
      selectedTable.value = table;
      selectedTableSchema.value = schema;
      viewMode.value = 'table';
      void store.loadTables(source);
      await Promise.all([
        store.loadDatasetOverview(source, table, schema),
        store.loadInsights(source, table, schema, false),
        store.loadDataStory(source, table, schema),
      ]);
    } else {
      // table === '*' (All datasets) or genuinely no table saved — restore the
      // '*' selection so the rail's expansion list re-renders, never pass '*'
      // to any per-table/element endpoint.
      if (table === '*') selectedTable.value = '*';
      viewMode.value = mode === 'source' ? 'source' : 'none';
      void store.loadTables(source);
      await store.loadSourceInfo(source);
    }
  } catch (e) {
    console.error('Failed to restore selection:', e);
  }
}

// Phase 4: drive selection from a deep-link query (?source=&schema=&table=&column=&tab=).
// Validates each level against loaded data and stops at the deepest valid one.
async function applySelectionFromQuery(parsed: DeepLinkQuery): Promise<void> {
  const source = parsed.source;
  if (!source) return;
  selectedSource.value = source;
  if (parsed.tab) activeTab.value = parsed.tab;

  await store.loadTables(source);
  const resolved = resolveTableColumn(store.tables, parsed.table, parsed.schema, parsed.column);

  if (resolved.level === 'source') {
    viewMode.value = 'source';
    await store.loadSourceInfo(source);
    return;
  }

  selectedTable.value = resolved.table;
  selectedTableSchema.value = resolved.schema;

  if (resolved.level === 'table') {
    viewMode.value = 'table';
    await Promise.all([
      store.loadDatasetOverview(source, resolved.table!, resolved.schema ?? undefined),
      store.loadInsights(source, resolved.table!, resolved.schema ?? undefined, false),
      store.loadDataStory(source, resolved.table!, resolved.schema ?? undefined),
    ]);
    return;
  }

  // column level
  selectedColumn.value = resolved.column;
  viewMode.value = 'column';
  if (!parsed.tab) activeTab.value = 'profile';
  await Promise.all([
    store.loadElement(source, resolved.table!, resolved.column!, resolved.schema ?? undefined),
    store.loadDatasetOverview(source, resolved.table!, resolved.schema ?? undefined),
    store.loadInsights(source, resolved.table!, resolved.schema ?? undefined, false),
    store.loadDataStory(source, resolved.table!, resolved.schema ?? undefined),
  ]);
}

onMounted(async () => {
  await store.loadSources();
  // Phase 4: a deep-link query with a valid source wins over the localStorage restore.
  const parsed = parseDeepLinkQuery(route.query as Record<string, unknown>);
  if (shouldApplyDeepLink(parsed, store.sources)) {
    await applySelectionFromQuery(parsed);
  } else {
    await restoreSelection();
  }
});

// Save selection whenever it changes
watch(() => selectedSource.value, saveSelection);
watch(() => selectedTable.value, saveSelection);
watch(() => selectedTableSchema.value, saveSelection);
watch(() => selectedColumn.value, saveSelection);
watch(() => viewMode.value, saveSelection);
watch(() => activeTab.value, saveSelection);

// Tech-debt fix (found 2026-08-06, fixed 2026-08-12): a rebuild progress/complete
// banner from one source must never bleed into a different source's page. Abort
// any still-running rebuild for the source being left (its per-table writes
// already committed so far are unaffected — only the banner and further SSE
// callbacks are stopped) and reset the banner to its default, empty state.
watch(() => selectedSource.value, () => {
  if (rebuildState.value.running) abortRebuild();
  rebuildState.value = _rebuildStateDefault();
});

// Publish the current drill-down position (source → dataset → column) to the
// global store as a clickable breadcrumb trail, so TopMenu.vue can render it
// in the top header bar even though it lives outside this page's component tree.
function updateBreadcrumbTrail() {
  if (viewMode.value === 'none' || !selectedSource.value) {
    store.clearBreadcrumbTrail();
    return;
  }
  const source = selectedSource.value;
  const segments: WorkspaceBreadcrumbSegment[] = [
    { label: source, onClick: () => navigateToSource(source) },
  ];
  const table = selectedTable.value;
  const schema = selectedTableSchema.value ?? '';
  if ((viewMode.value === 'table' || viewMode.value === 'column') && table && table !== '*') {
    segments.push({ label: table, onClick: () => navigateToDataset(source, table, schema) });
  }
  const column = selectedColumn.value;
  if (viewMode.value === 'column' && table && column) {
    segments.push({ label: column, onClick: () => navigateToColumn(source, table, schema, column) });
  }
  store.setBreadcrumbTrail(segments);
}
watch([selectedSource, selectedTable, selectedTableSchema, selectedColumn, viewMode], updateBreadcrumbTrail, { immediate: true });
onBeforeUnmount(() => store.clearBreadcrumbTrail());

function onSourceChange(source: string) {
  selectedTable.value = null;
  selectedTableSchema.value = null;
  selectedColumn.value = null;
  selectedSchemaFilter.value = null;
  viewMode.value = 'source';
  store.element = null;
  store.datasetOverview = null;
  store.referenceData = null;
  store.insights = null;
  railStates.value = {};
  colSearch.value = '';
  activeFilter.value = 'all';
  docList.value = [];
  void store.loadTables(source);
  void store.loadSourceInfo(source);
  void loadDocuments(source);
}

// Schema filter for the rail — always visible, so a single-schema source
// still clearly shows which one schema is onboarded (not just hidden away).
const availableSchemas = computed(() => {
  const set = new Set(store.tables.map(t => t.schema).filter((s): s is string => !!s));
  return Array.from(set).sort();
});
const filteredTablesForDataset = computed(() => {
  if (!selectedSchemaFilter.value) return store.tables;
  return store.tables.filter(t => t.schema === selectedSchemaFilter.value);
});
// When a source has exactly one schema, show it pre-selected rather than a
// blank "All" placeholder — makes the single-schema case visible at a glance.
watch(availableSchemas, (schemas) => {
  selectedSchemaFilter.value = schemas.length === 1 ? schemas[0] : null;
});

function refreshSourceInfo() {
  if (selectedSource.value) {
    void store.loadSourceInfo(selectedSource.value);
  }
}

function navigateToSource(source: string) {
  selectedSource.value = source;
  onSourceChange(source);
}

function navigateToDataset(source: string, table: string, schema: string) {
  selectedSource.value = source;
  selectedTable.value = table;
  selectedTableSchema.value = schema;
  selectedColumn.value = null;
  viewMode.value = 'table';
  store.element = null;
  store.referenceData = null;
  activeTab.value = 'profile';
  referencedByExpanded.value = false;
  foreignKeysExpanded.value = false;
  void store.loadTables(source);
  void store.loadDatasetOverview(source, table, schema);
  void store.loadInsights(source, table, schema, false);
  void store.loadDataStory(source, table, schema);
}

function navigateToColumn(source: string, table: string, schema: string, column: string) {
  selectedSource.value = source;
  selectedTable.value = table;
  selectedTableSchema.value = schema;
  selectedColumn.value = column;
  viewMode.value = 'column';
  void store.loadTables(source);
  void store.loadElement(source, table, column, schema);
  void store.loadDatasetOverview(source, table, schema);
  void store.loadInsights(source, table, schema, false);
  void store.loadDataStory(source, table, schema);
}

function selectTable(tbl: TableEntry) {
  selectedTable.value = tbl.table_name;
  selectedTableSchema.value = tbl.schema;
  selectedColumn.value = null;
  viewMode.value = 'table';
  store.element = null;
  store.referenceData = null;
  referencedByExpanded.value = false;
  foreignKeysExpanded.value = false;
  void store.loadDatasetOverview(selectedSource.value!, tbl.table_name, tbl.schema);
  void store.loadInsights(selectedSource.value!, tbl.table_name, tbl.schema, false);
  void store.loadDataStory(selectedSource.value!, tbl.table_name, tbl.schema);
}

function selectTableByName(tableName: string, schema: string) {
  const tbl = store.tables.find(t => t.table_name === tableName && t.schema === schema);
  if (tbl) selectTable(tbl);
}

function getColumnState(schema: string, table: string, col: { name: string; lifecycle_state?: LifecycleState }): LifecycleState {
  const key = selectedSource.value ? `${selectedSource.value}|${schema}|${table}|${col.name}` : '';
  return railStates.value[key] ?? col.lifecycle_state ?? 'draft';
}

function filteredColumns(tbl: TableEntry) {
  return tbl.columns.filter((col) => {
    const q = colSearch.value.toLowerCase();
    const matchSearch = !q || col.name.toLowerCase().includes(q)
      || (col.pii === true && q.length >= 2 && 'pii'.includes(q));
    if (!matchSearch) return false;
    if (activeFilter.value === 'all') return true;
    if (activeFilter.value === 'coded') return (col.distinct_count ?? 999) <= 50;
    if (activeFilter.value === 'pii') return col.pii === true;
    if (activeFilter.value === 'unresolved') return (col.semantic_state ?? 'unresolved') === 'unresolved';
    const state = getColumnState(tbl.schema, tbl.table_name, col);
    return govDisplayBucket(state) === activeFilter.value;
  });
}

const filteredOverviewColumns = computed(() => {
  const cols = store.datasetOverview?.columns_summary ?? [];
  return cols.filter((col) => {
    const q = colSearch.value.toLowerCase();
    const matchSearch = !q ||
      col.name.toLowerCase().includes(q) ||
      col.semantic_type.toLowerCase().includes(q) ||
      semanticTypeMatchesQuery(col.semantic_type, q) ||
      (col.pii === true && q.length >= 2 && 'pii'.includes(q));
    if (!matchSearch) return false;
    if (activeFilter.value === 'all') return true;
    if (activeFilter.value === 'coded') return (col.distinct_count ?? 999) <= 50;
    if (activeFilter.value === 'pii') return col.pii === true;
    if (activeFilter.value === 'unresolved') return (col.semantic_state ?? 'unresolved') === 'unresolved';
    return govDisplayBucket(col.lifecycle_state) === activeFilter.value;
  });
});

// ── Bulk AI Draft scan computeds ─────────────────────────────────────────
const srcMissingStories = computed(() =>
  (store.sourceInfo?.datasets ?? []).filter(d => !d.has_story)
);
const srcMissingStoriesCount = computed(() => srcMissingStories.value.length);
const srcTotalDatasets = computed(() => store.sourceInfo?.table_count ?? 0);
const srcAiStoryCount = computed(() =>
  (store.sourceInfo?.datasets ?? []).filter(d => d.story_is_ai).length
);
const srcHasStoryCount = computed(() => srcTotalDatasets.value - srcMissingStoriesCount.value);

const dsMissingDescriptions = computed(() =>
  (store.datasetOverview?.columns_summary ?? []).filter(c => !c.description)
);
const dsMissingBusinessNames = computed(() =>
  (store.datasetOverview?.columns_summary ?? []).filter(c => !c.business_name)
);
const dsTotalCols = computed(() => store.datasetOverview?.column_count ?? 0);
const dsAiDescCount = computed(() =>
  (store.datasetOverview?.columns_summary ?? []).filter(c => c.description_is_ai).length
);
const dsAiBizNameCount = computed(() =>
  (store.datasetOverview?.columns_summary ?? []).filter(c => c.business_name_is_ai).length
);

function semTypeLabel(type: string): string {
  return semanticTypeLabel(type);
}

// ── Mapping Type presentation helpers ──────────────────────────────────────
// Human label for a governed type_id (UI counterpart of the semantic type).
function semTypeIdLabel(typeId: string | null | undefined): string {
  return semanticTypeLabel(typeId);
}

function semDomainLabel(role: string | null | undefined): string {
  return semanticDomainLabel(role);
}

function semScopeLabel(scope: string | null | undefined): string {
  return semanticScopeLabel(scope);
}

// Data-quality dimension label for a finding category.
function dqDimensionLabel(cat: string | null | undefined): string {
  switch (cat) {
    case 'completeness': return 'Completeness';
    case 'validity': return 'Validity';
    case 'uniqueness': return 'Uniqueness';
    case 'consistency': return 'Consistency';
    case 'regulatory': return 'Regulatory';
    case 'metadata': return 'Metadata';
    default: return cat ? cat.replace(/_/g, ' ') : 'Quality';
  }
}

// ── Vocabulary from API ──────────────────────────────────────────────────
const vocabRoles = computed(() => (vocabData.value?.roles || []) as Array<{ id: string; label: string }>);
const vocabTypesForRole = computed(() => {
  const role = semOverrideRole.value;
  if (!role || !vocabData.value) return [];
  return (vocabData.value.types_by_role?.[role] || []) as Array<{ id: string; label: string }>;
});

const uniquenessPC = computed(() => {
  const s = store.element?.stats;
  if (!s) return null;
  if (s.uniqueness_pct != null) return s.uniqueness_pct * 100;
  if (s.distinct_count != null && s.row_count) return (s.distinct_count / s.row_count) * 100;
  return null;
});

const duplicatePC = computed(() => {
  const s = store.element?.stats;
  if (!s || s.row_count == null || s.row_count === 0) return null;
  return ((s.duplicate_count ?? 0) / s.row_count) * 100;
});

const placeholderPC = computed(() => {
  const s = store.element?.stats;
  if (!s || s.row_count == null || s.row_count === 0) return null;
  return ((s.placeholder_count ?? 0) / s.row_count) * 100;
});

// ── Profile: is the column a string/text type (for char-length display) ──
const isStringDataType = computed(() => {
  const dt = (store.element?.data_type || '').toUpperCase();
  return dt.includes('VARCHAR') || dt.includes('TEXT') || dt.includes('CHAR') || dt.includes('STRING');
});

const charProfileAW = computed((): string | null => {
  if (!isStringDataType.value || !store.element) return null;
  const s = store.element.stats;
  const samples: string[] = (s.sample_values || []).map((v) => String(v ?? '')).filter(Boolean);
  const src = samples.length ? samples : [(s.inferred_pattern as string) || ''];
  let hasLetters = false, hasDigits = false;
  for (const t of src) {
    if (/[A-Za-z]/.test(t)) hasLetters = true;
    if (/[0-9]/.test(t)) hasDigits = true;
    if (hasLetters && hasDigits) break;
  }
  if (hasLetters && hasDigits) return 'Alphanumeric';
  if (hasLetters) return 'Alphabetic';
  if (hasDigits) return 'Digits';
  return null;
});

// ── Definition tab: status badge driven by lifecycle state ────────────────
const defTabBadge = computed(() => {
  const el = store.element;
  if (!el) return null;
  if (el.lifecycle_state === 'approved') return '✓';
  return null;
});
const defTabBadgeClass = computed(() => {
  const el = store.element;
  if (!el) return '';
  if (el.lifecycle_state === 'approved') return 'tab-badge--ok';
  if (el.lifecycle_state === 'defined') return 'tab-badge--warn';
  return 'tab-badge--no';
});

// ── Reference Data: derived state ─────────────────────────────────────────
const rdCodes = computed(() => store.referenceData?.codes ?? []);
const rdStatus = computed(() => rdLocalStatus.value ?? store.referenceData?.status ?? 'candidate');
const rdStatusLabel = computed(() => {
  // Postgres per-code mode: the header badge reflects the whole-tab set badge.
  if (rdPgMode.value) return rdSetBadgeLabel.value;
  const s = rdStatus.value;
  if (s === 'approved') return 'Approved';
  if (s === 'under_review') return 'Under Review';
  return 'Candidate';
});

// ── Per-code Reference Data (5b.2, Postgres backend) ────────────────────────
// 2026-08-16 redesign: bound fields ALSO use this per-code table now — the set's recognised
// codes render read-only (governed by the master list); any unrecognised code still gets the
// full editable/submittable per-code treatment. Previously bound fields were excluded here and
// fell into the legacy whole-field branch below, which has no per-code review of its own.
const rdPgMode = computed(() => store.referenceData?.backend === 'postgres');
// Insert mode (the per-code reviewable object) is ONLY for coded semantic types
// (reference_code / currency_code / country_code) — never gated on distinct_count.
// A low-cardinality column whose semantic type is not coded shows a not-applicable
// message instead of an editable code table.
const rdNotApplicable = computed(() => rdPgMode.value && !isCodedSemType.value);
// Prefer the live semantic-type record (refreshed on every element change and on
// Accept/Replace) so the Submit gate reflects an acceptance made on the Interpretation
// tab without needing a Reference Data refetch. Fall back to the value baked into the
// reference-data payload when the record has not been loaded yet.
const rdSemanticAccepted = computed(
  () => semTypeAccepted.value || (store.referenceData?.semantic_accepted ?? false),
);
const rdSetBadge = computed(() => store.referenceData?.set_badge ?? 'empty');
const rdSetBadgeLabel = computed(() => ({
  empty: 'Empty',
  draft: 'Draft',
  in_review: 'In-Review',
  partially_approved: 'Partially approved',
  approved: 'Approved',
}[rdSetBadge.value] ?? 'Empty'));
// Colour token for the status badge — per-code set badge in Postgres mode (so the
// Interpretation-tab strip + tab header echo the real per-code state), else legacy status.
const rdBadgeClass = computed(() =>
  rdPgMode.value ? `rdstatus--${rdSetBadge.value}` : `rdstatus--${rdStatus.value}`,
);
// Numeric codeset status for the tab-contextual header (5b.3.2 #5).
const rdCodesetSummaryLabel = computed(() => {
  const codes = rdCodes.value;
  const total = codes.length;
  if (!total) return 'No codes yet';
  const approved = codes.filter((c) => c.status === 'approved').length;
  const submitted = codes.filter((c) => c.status === 'in_review' || c.status === 'approved').length;
  return `${submitted} of ${total} submitted · ${approved} approved`;
});
const rdDisplayCodes = computed<CodeEntry[]>(() => [...rdCodes.value, ...rdAddedCodes.value]);
const rdSubmittableCount = computed(() =>
  rdCodes.value.filter((c) => c.status === 'draft' && (c.meaning ?? '').trim()).length,
);
function rdRowEditable(c: CodeEntry): boolean {
  if (c.governed) return false;
  return rdPgMode.value && (c.status === 'empty' || c.status === 'draft' || c.status === undefined);
}
function rdCodeStatusLabel(status?: string): string {
  return ({ empty: 'Empty', draft: 'Draft', in_review: 'In-Review', approved: 'Approved', returned: 'Returned', rejected: 'Rejected', governed: 'Master list' } as Record<string, string>)[status ?? 'empty'] ?? 'Empty';
}

// ── Multi-select + analyst bulk pull-backs (5b.3.1) ────────────────────────
// Select-all spans every rendered code (frozen rows included, so Withdraw/Revoke
// can target in_review/approved codes). Each bulk action operates only on the
// subset of the selection whose status matches it.
const rdAllSelected = computed<boolean>({
  get: () => {
    const selectable = rdDisplayCodes.value.filter((c) => !c.governed);
    return selectable.length > 0 && selectable.every((c) => rdSelected.value.has(c.code));
  },
  set: (on) => {
    if (on) rdDisplayCodes.value.filter((c) => !c.governed).forEach((c) => rdSelected.value.add(c.code));
    else rdSelected.value.clear();
  },
});
function rdToggleCode(code: string, on: boolean) {
  if (on) rdSelected.value.add(code);
  else rdSelected.value.delete(code);
}
function rdClearSelection() {
  rdSelected.value.clear();
}
const rdSelectedCount = computed(() => rdSelected.value.size);
const rdWithdrawableSelected = computed(() =>
  rdDisplayCodes.value.filter((c) => rdSelected.value.has(c.code) && c.status === 'in_review').map((c) => c.code),
);
const rdRevocableSelected = computed(() =>
  rdDisplayCodes.value.filter((c) => rdSelected.value.has(c.code) && c.status === 'approved').map((c) => c.code),
);
// Remove targets only analyst-owned codes (declared codes + unsaved added rows, both
// in_source === false); profiled codes come from the source and always reappear, so they
// are cleared by editing-blank + Save, not Remove.
const rdRemovableSelected = computed(() =>
  rdDisplayCodes.value
    .filter((c) => rdSelected.value.has(c.code) && rdRowEditable(c) && c.in_source === false)
    .map((c) => c.code),
);
// Submit is tick-driven (5b.3.1 refinement): only the selected FILLED draft codes submit.
const rdSubmittableSelected = computed(() =>
  rdDisplayCodes.value
    .filter((c) => rdSelected.value.has(c.code) && c.status === 'draft' && (c.meaning ?? '').trim())
    .map((c) => c.code),
);
// Save draft is enabled only when there's an actual pending change to persist (a typed
// value/meaning/origin edit or a newly added code) — not when every code is frozen.
const rdCanSaveDraft = computed(() =>
  rdAddedCodes.value.length > 0
  || Object.keys(rdValueEdits.value).length > 0
  || Object.keys(rdMeaningEdits.value).length > 0
  || Object.keys(rdOriginEdits.value).length > 0,
);
// Cascade section shows only for coded fields whose semantic type is Accepted and that have
// >=1 filled draft to carry along (matches the two conditions: coded type AND accepted).
const submitCascadeEligible = computed(
  () => isCodedSemType.value && rdSemanticAccepted.value && rdSubmittableCount.value > 0,
);

// ── Reference-set binding (Phase 3) ───────────────────────────────────────
const rdBoundSetId = computed(() => store.referenceData?.bound_set_id ?? null);
const rdBoundSet = computed(() => rdSets.value.find((s) => s.id === rdBoundSetId.value) ?? null);
// The binding decision's OWN submit/approve status — separate from any leftover unrecognised
// codes' per-code statuses (2026-08-16 redesign).
const rdBindingStatus = computed(() => store.referenceData?.binding_status ?? 'draft');
const rdBindingStatusLabel = computed(() => ({
  draft: 'Draft', in_review: 'In Review', approved: 'Approved',
}[rdBindingStatus.value] ?? 'Draft'));
const rdBindingNote = computed(() => {
  const s = rdBindingStatus.value;
  if (s === 'approved') return 'This binding has been reviewed and approved.';
  if (s === 'in_review') return 'This binding has been submitted and is awaiting steward review.';
  return 'Meanings for recognised codes come from the bound set. Any unrecognised code below can still be filled in and submitted on its own. Unbind to remove this binding.';
});
// Whether Submit has anything to send: filled unrecognised-code drafts, OR (2026-08-16) the
// binding decision itself, still in its own 'draft' (never submitted) state.
const rdBindingPendingSubmit = computed(() => !!rdBoundSetId.value && rdBindingStatus.value === 'draft');
const rdCanSubmit = computed(() => rdSubmittableSelected.value.length > 0 || rdBindingPendingSubmit.value);
const rdSubmitLabel = computed(() => {
  const n = rdSubmittableSelected.value.length;
  if (n > 0 && rdBindingPendingSubmit.value) return `Submit binding + ${n} value${n === 1 ? '' : 's'}`;
  if (n > 0) return `Submit ${n} value${n === 1 ? '' : 's'}`;
  if (rdBindingPendingSubmit.value) return 'Submit binding';
  return 'Submit';
});
const rdSetOptions = computed(() =>
  rdSets.value.map((s) => ({ label: `${s.name} (${s.kind})`, value: s.id })),
);
const rdSuggestedSetId = computed(() => {
  const semType = store.element?.semantic_type;
  return semType ? (REFERENCE_SET_SUGGESTIONS[semType] ?? null) : null;
});
const rdSuggestedSet = computed(() =>
  rdSuggestedSetId.value ? (rdSets.value.find((s) => s.id === rdSuggestedSetId.value) ?? null) : null,
);

// ── Profile: evidence-backed data-quality facts (no type reveal) ─────────
const profileDqFacts = computed(() => {
  const s = store.element?.stats;
  const facts: { icon: string; tone: string; text: string }[] = [];
  if (!s) return facts;
  if (s.null_pct != null) {
    if (s.null_pct <= 0) {
      facts.push({ icon: 'check_circle', tone: 'good', text: 'Complete — every row has a value (0 missing).' });
    } else {
      const bad = s.null_pct >= 0.5;
      facts.push({ icon: bad ? 'error' : 'warning', tone: bad ? 'bad' : 'warn', text: `${fmtPct(s.null_pct)}% of values are missing (NULL).` });
    }
  }
  if (uniquenessPC.value != null) {
    const u = uniquenessPC.value;
    if (u >= 99) facts.push({ icon: 'fingerprint', tone: 'good', text: `Effectively unique — ${u.toFixed(1)}% distinct values.` });
    else facts.push({ icon: 'donut_large', tone: 'neutral', text: `${u.toFixed(1)}% distinct — a repeating / categorical column.` });
  }
  if (placeholderPC.value != null && placeholderPC.value > 0) {
    facts.push({ icon: 'report', tone: 'warn', text: `${placeholderPC.value.toFixed(1)}% placeholder / sentinel values detected.` });
  }
  if (duplicatePC.value != null && duplicatePC.value > 0) {
    facts.push({ icon: 'content_copy', tone: 'warn', text: `${duplicatePC.value.toFixed(1)}% duplicate values.` });
  }
  if (facts.length < 2 && s.distinct_count != null) {
    facts.push({ icon: 'data_usage', tone: 'neutral', text: `${s.distinct_count.toLocaleString()} distinct values observed.` });
  }
  return facts;
});

// ── Profile: lifecycle-gated semantic-deduction status ──────────────────
const profileSemStatus = computed(() => {
  const r = semTypeRecord.value;
  if (r?.accepted_at) {
    const t = r.type_id && r.type_id !== 'unresolved' ? r.type_id : 'typed';
    return { accepted: true, cls: 'dq-ss-ok', icon: 'verified', text: `Semantic Type accepted · ${t}` };
  }
  if (r) {
    return { accepted: false, cls: 'dq-ss-pending', icon: 'pending', text: 'Semantic Deduction in review — type not yet governed.' };
  }
  return { accepted: false, cls: 'dq-ss-pending', icon: 'radio_button_unchecked', text: 'Semantic Deduction not started.' };
});


function selectColumn(tbl: TableEntry, col: { name: string; data_type: string }) {
  selectedTable.value = tbl.table_name;
  selectedTableSchema.value = tbl.schema;
  selectedColumn.value = col.name;
  viewMode.value = 'column';
  activeTab.value = 'profile';
  store.referenceData = null;
  rdLocalStatus.value = null;
  rdEditMode.value = false;
  rdMeaningEdits.value = {};
  rdValueEdits.value = {};

  void store.loadElement(selectedSource.value!, tbl.table_name, col.name, tbl.schema).then(() => {
    if (store.element) {
      const key = `${store.element.source}|${store.element.schema}|${store.element.table}|${store.element.column}`;
      railStates.value[key] = store.element.lifecycle_state;
    }
  });

  void store.loadInsights(selectedSource.value!, tbl.table_name, tbl.schema, false);
}

function selectColumnFromOverview(col: ColumnSummary, tab: string = 'profile') {
  if (!selectedSource.value || !selectedTable.value || !selectedTableSchema.value) return;
  selectedColumn.value = col.name;
  viewMode.value = 'column';
  activeTab.value = tab;
  store.referenceData = null;
  rdLocalStatus.value = null;
  rdEditMode.value = false;
  rdMeaningEdits.value = {};
  rdValueEdits.value = {};

  void store.loadElement(selectedSource.value, selectedTable.value, col.name, selectedTableSchema.value).then(() => {
    if (store.element) {
      const key = `${store.element.source}|${store.element.schema}|${store.element.table}|${store.element.column}`;
      railStates.value[key] = store.element.lifecycle_state;
    }
  });
}

// Columns table's "Actions" count → open straight to this column's DQ Insights
// tab with the "Actions to improve" group already expanded, instead of just
// landing on the tab and requiring an extra click.
function openColumnActions(col: ColumnSummary) {
  selectColumnFromOverview(col, 'observations');
  dqGroupExpanded.value.actions = true;
}

// ── Assessment scoping panel (U2c, decision D1) ──────────────────────────────
const scopeColumns = computed<ColumnSummary[]>(() => store.datasetOverview?.columns_summary ?? []);

/** Columns currently suggested for descoping (SD `technical`) that are still in scope. */
const scopeSuggestedColumns = computed(() =>
  scopeColumns.value.filter((c) => descopeSuggestion(c) !== null),
);

function colDescopeSuggestion(c: ColumnSummary) {
  return descopeSuggestion(c);
}

function isColOutOfScope(c: ColumnSummary): boolean {
  return isOutOfScope(c.assessment_scope);
}

function colScopeLabel(c: ColumnSummary): string {
  return scopeLabel(c.assessment_scope);
}

function toggleScopeSelection(name: string) {
  const next = new Set(scopeSelection.value);
  if (next.has(name)) next.delete(name);
  else next.add(name);
  scopeSelection.value = next;
}

function clearScopeSelection() {
  scopeSelection.value = new Set();
}

function selectSuggestedForDescope() {
  scopeSelection.value = new Set(scopeSuggestedColumns.value.map((c) => c.name));
}

/** Apply a scope to a single column (the per-row toggle / one-click suggestion). */
async function applyColumnScope(name: string, scope: 'in_scope' | 'out_of_scope') {
  await applyScope([name], scope);
}

/** Apply a scope to the current multi-select (bulk action). */
async function applyBulkScope(scope: 'in_scope' | 'out_of_scope') {
  const cols = Array.from(scopeSelection.value);
  if (cols.length === 0) return;
  await applyScope(cols, scope);
}

async function applyScope(columns: string[], scope: 'in_scope' | 'out_of_scope') {
  if (columns.length === 0 || scopeSaving.value) return;
  scopeSaving.value = true;
  scopeBanner.value = null;
  try {
    await store.setColumnsScope(columns, scope, scopeReason.value.trim() || undefined);
    if (store.error) {
      scopeBanner.value = { type: 'error', msg: store.error };
    } else {
      const verb = scope === 'out_of_scope' ? 'marked out of scope' : 'marked in scope';
      scopeBanner.value = {
        type: 'success',
        msg: `${columns.length} column${columns.length === 1 ? '' : 's'} ${verb}.`,
      };
      // Drop applied columns from the selection; keep the reason for the next batch.
      const remaining = new Set(scopeSelection.value);
      for (const c of columns) remaining.delete(c);
      scopeSelection.value = remaining;
    }
  } catch (e: unknown) {
    scopeBanner.value = { type: 'error', msg: e instanceof Error ? e.message : 'Scope update failed' };
  } finally {
    scopeSaving.value = false;
  }
}

/** Force-reload the current element from the API (bypasses cache). Used after linkage changes. */
async function reloadElement() {
  if (!store.element) return;
  const { source, table, column, schema } = store.element;
  await store.loadElement(source, table, column, schema ?? undefined, true);
  // A glossary link/unlink changes the DQ Glossary line-item but does not trigger
  // a backend re-score on its own — force one so the badge updates live.
  await store.refreshElementDq('Glossary linkage updated');
}

async function saveDescription() {
  saveDescLoading.value = true;
  try {
    // Save with AI flag if it's a drafted description; clear flag if user edited it manually
    await store.updateDescription(descValue.value, isAiDraft.value);
    isAiDraft.value = false;  // Clear flag after save (any subsequent edits are manual)
    descDirty.value = false;
    isDescEditMode.value = false;  // Exit edit mode to show the read-only view with badge
    // Sync the rail state for the all-datasets expansion view
    if (store.element) {
      const key = `${store.element.source}|${store.element.schema}|${store.element.table}|${store.element.column}`;
      railStates.value[key] = store.element.lifecycle_state;
    }
  } finally {
    saveDescLoading.value = false;
  }
}

async function draftWithAi() {
  draftLoading.value = true;
  clearAiError();
  try {
    const { draft, error } = await store.draftDescription();
    if (error) { setAiError(error); return; }
    if (draft) {
      isUserEdit.value = false;  // Mark as programmatic update, not user edit
      descValue.value = draft;
      isAiDraft.value = true;  // Mark as AI-generated
      descDirty.value = true;  // Enable Save button
      isUserEdit.value = false;  // Ensure it stays false after update
    } else {
      setAiError({ summary: 'The AI didn’t return a suggestion. Please try again.' });
    }
  } finally {
    draftLoading.value = false;
  }
}

async function runBulkDescriptions() {
  if (!selectedSource.value || !selectedTable.value) return;
  const tbl = store.datasetOverview;
  bulkDescLoading.value = true;
  clearAiError();
  try {
    const result = await store.bulkGenerateDescriptions(selectedSource.value, selectedTable.value, tbl?.schema);
    if (result.error) setAiError(result.error);
    if (result.generated > 0) {
      showBulkBanner(`Successfully generated descriptions for ${result.generated} field${result.generated !== 1 ? 's' : ''}.`, 'success');
      recordBulkRun({ scope: 'dataset', target: selectedTable.value, type: 'descriptions', generated: result.generated, failed: 0, total: result.total ?? result.generated });
      // Reload overview so description_is_ai flags reflect the new bulk-generated state
      await store.loadDatasetOverview(selectedSource.value, selectedTable.value, tbl?.schema ?? undefined, true);
    } else if (!result.error) {
      showBulkBanner('All fields already have descriptions — nothing to generate.', 'info');
    }
  } catch (e: unknown) {
    setAiError(aiErrorFrom(e, 'Description generation failed — please try again.'));
  } finally {
    bulkDescLoading.value = false;
  }
}

async function runBulkBusinessNames() {
  if (!selectedSource.value || !selectedTable.value) return;
  const tbl = store.datasetOverview;
  bulkBizLoading.value = true;
  clearAiError();
  try {
    const result = await store.bulkGenerateBusinessNames(selectedSource.value, selectedTable.value, tbl?.schema);
    if (result.error) setAiError(result.error);
    if (result.generated > 0) {
      showBulkBanner(`Successfully saved business names for ${result.generated} field${result.generated !== 1 ? 's' : ''}.`, 'success');
      recordBulkRun({ scope: 'dataset', target: selectedTable.value, type: 'business_names', generated: result.generated, failed: 0, total: result.total ?? result.generated });
      // Reload overview so business_name_is_ai flags reflect the new bulk-generated state
      await store.loadDatasetOverview(selectedSource.value, selectedTable.value, tbl?.schema ?? undefined, true);
    } else if (!result.error) {
      showBulkBanner('All fields already have business names — nothing to generate.', 'info');
    }
  } catch (e: unknown) {
    setAiError(aiErrorFrom(e, 'Business-name generation failed — please try again.'));
  } finally {
    bulkBizLoading.value = false;
  }
}

async function refreshProfile() {
  if (!selectedSource.value || !selectedTable.value) return;
  refreshingProfile.value = true;
  try {
    const result = await store.refreshProfileFromLive(
      selectedSource.value,
      selectedTable.value,
      selectedTableSchema.value,
      selectedColumn.value,
    );
    if (result === 'error') {
      console.error('Live profile refresh failed');
    }
    // SD-R5: semantic types + DQ are now always re-derived server-side as part
    // of the refresh itself (no separate opt-in step needed).
  } finally {
    refreshingProfile.value = false;
  }
}

// U-polish Task 6 — field-level DQ re-evaluate: force a fresh score for the
// current column, bypassing the cached/heal path `GET .../dq` uses.
const refreshingDq = ref(false);
async function refreshElementDq() {
  if (refreshingDq.value) return;
  refreshingDq.value = true;
  try {
    await store.refreshElementDq();
  } catch (e) {
    console.error('DQ re-evaluate failed', e);
  } finally {
    refreshingDq.value = false;
  }
}

// Score-change attention cue (left-rail per-column badge only) + a bottom-right toast —
// fires only for the single, currently-open element's own score change (store.dqScoreChange
// is never raised by bulk actions, see elementStore.ts's DqScoreChangeEvent doc comment).
const scorePulseClass = ref('');
let scorePulseTimer: ReturnType<typeof setTimeout> | null = null;
watch(() => store.dqScoreChange, (evt) => {
  if (!evt) return;
  const up = evt.direction === 'up';
  if (scorePulseTimer) clearTimeout(scorePulseTimer);
  scorePulseClass.value = '';
  requestAnimationFrame(() => {
    scorePulseClass.value = up ? 'dq-score-pulse-up' : 'dq-score-pulse-down';
    scorePulseTimer = setTimeout(() => { scorePulseClass.value = ''; }, 1700);
  });
  Notify.create({
    message: evt.reason
      ? `${evt.reason} — ${evt.column}'s DQ score ${up ? 'improved' : 'dropped'} to ${evt.newScore}.`
      : `${evt.column}'s DQ score ${up ? 'improved' : 'dropped'} to ${evt.newScore}.`,
    icon: up ? 'check_circle' : 'trending_down',
    // Quasar defaults an un-coloured Notify to a `text-white` class (assumes a dark
    // background) — without this it renders white text on our light card background,
    // unreadable. Explicit textColor stops Quasar injecting that default class.
    textColor: 'dark',
    classes: up ? 'dq-toast dq-toast--up' : 'dq-toast dq-toast--down',
    position: 'bottom-right',
    timeout: 4000,
  });
});

function fmtSeconds(secs: number): string {
  if (secs < 60) return `${Math.round(secs)}s`;
  const m = Math.floor(secs / 60);
  const s = Math.round(secs % 60);
  return s > 0 ? `${m}m ${s}s` : `${m}m`;
}

function promptRebuildProfiles() {
  rebuildState.value.showWarning = true;
}

async function startRebuildProfiles() {
  if (!selectedSource.value) return;
  rebuildState.value.showWarning = false;
  rebuildState.value.running = true;
  rebuildState.value.done = false;
  rebuildState.value.index = 0;
  rebuildState.value.total = store.sourceInfo?.table_count ?? 0;
  rebuildState.value.completed = 0;
  rebuildState.value.failed = 0;
  rebuildState.value.currentTable = '';
  rebuildState.value.elapsed = 0;
  rebuildState.value.estimatedRemaining = 0;

  _rebuildAbort = new AbortController();
  const source = selectedSource.value;

  try {
    await rebuildSourceProfiles(
      source,
      (event, data) => {
        if (event === 'progress') {
          rebuildState.value.index = (data.index as number) ?? 0;
          rebuildState.value.total = (data.total as number) ?? rebuildState.value.total;
          rebuildState.value.currentTable = (data.table as string) ?? '';
          rebuildState.value.elapsed = (data.elapsed as number) ?? 0;
          rebuildState.value.estimatedRemaining = (data.estimated_remaining as number) ?? 0;
          rebuildState.value.completed = (data.completed as number) ?? 0;
          rebuildState.value.failed = (data.failed as number) ?? 0;
        } else if (event === 'done') {
          rebuildState.value.index = (data.total as number) ?? rebuildState.value.total;
          rebuildState.value.completed = (data.completed as number) ?? 0;
          rebuildState.value.failed = (data.failed as number) ?? 0;
          rebuildState.value.elapsed = (data.elapsed as number) ?? 0;
          rebuildState.value.estimatedRemaining = 0;
        }
      },
      _rebuildAbort.signal,
      { includeSemantic: rebuildState.value.includeSemantic, includeDq: rebuildState.value.includeDq },
    );
  } catch (e) {
    if (!(e instanceof DOMException && e.name === 'AbortError')) {
      console.error('Rebuild failed:', e);
    }
  } finally {
    rebuildState.value.running = false;
    rebuildState.value.done = true;
    _rebuildAbort = null;
    // Reload source info so the "Profiled" timestamp and dataset list update
    if (selectedSource.value === source) {
      await store.loadSourceInfo(source);
    }
  }
}

function abortRebuild() {
  _rebuildAbort?.abort();
}

// ── Profile reset state (add-profile-reset) — table-level + source-level ───
// Child-before-parent step order, mirroring core/profile_reset.py's STEPS constant.
const PROFILE_RESET_STEP_LABELS: Record<string, string> = {
  dq_score: 'Clearing data quality scores',
  semantic_type: 'Clearing semantic types',
  reference_code: 'Clearing reference data',
  reference_set_binding: 'Clearing reference-set binding',
  reference_binding_review: 'Clearing reference-set review status',
  interpretation_lifecycle: 'Resetting interpretation status',
  interpretation_content: 'Clearing descriptions & business names',
  annotations: 'Clearing annotations',
  catalog: 'Clearing profile statistics',
};
const PROFILE_RESET_STEP_COUNT = Object.keys(PROFILE_RESET_STEP_LABELS).length;

function resetStepLabel(step: string): string {
  return PROFILE_RESET_STEP_LABELS[step] ?? 'Working…';
}

function _resetStateDefault() {
  return {
    showWarning: false,
    running: false,
    done: false,
    failed: false,
    currentStep: '',
    stepsCompleted: 0,
    stepsTotal: PROFILE_RESET_STEP_COUNT,
    errorMessage: '',
  };
}
const resetTableState = ref(_resetStateDefault());
const resetSourceState = ref(_resetStateDefault());
let _resetTableAbort: AbortController | null = null;
let _resetSourceAbort: AbortController | null = null;

function promptResetTable() {
  resetTableState.value = { ..._resetStateDefault(), showWarning: true };
}

async function startResetTable() {
  if (!selectedSource.value || !selectedTable.value) return;
  resetTableState.value = { ..._resetStateDefault(), running: true };
  _resetTableAbort = new AbortController();
  const source = selectedSource.value;
  const table = selectedTable.value;
  const schema = selectedTableSchema.value;
  const tableParam = schema ? `${schema}.${table}` : table;

  try {
    await resetTableProfile(
      source,
      tableParam,
      (event, data) => {
        if (event === 'progress') {
          resetTableState.value.currentStep = String(data.step ?? '');
          resetTableState.value.stepsCompleted += 1;
        } else if (event === 'error') {
          resetTableState.value.failed = true;
          resetTableState.value.errorMessage = String(data.message ?? 'Reset failed — rolled back, nothing changed.');
        }
      },
      _resetTableAbort.signal,
    );
  } catch (e) {
    if (!(e instanceof DOMException && e.name === 'AbortError')) {
      resetTableState.value.failed = true;
      resetTableState.value.errorMessage = 'Reset failed — rolled back, nothing changed.';
    }
  } finally {
    resetTableState.value.running = false;
    resetTableState.value.done = true;
    _resetTableAbort = null;
    // Reload the dataset overview so "Last profiled at", the DQ badge, and the
    // Interpretation tab immediately reflect the pre-profiling state. Data Story and
    // Reference Data live in separate store refs (not part of datasetOverview), so they
    // need their own reload too, or they'd keep showing pre-reset content.
    if (selectedSource.value === source && selectedTable.value === table) {
      const activeColumn = selectedColumn.value;
      await Promise.all([
        store.loadDatasetOverview(source, table, schema ?? undefined, true),
        store.loadDataStory(source, table, schema ?? undefined),
        ...(activeColumn ? [store.loadElement(source, table, activeColumn, schema ?? undefined, true)] : []),
      ]);
      if (activeColumn) {
        await store.loadReferenceData(source, table, activeColumn, schema ?? undefined);
      }
    }
  }
}

function promptResetSource() {
  resetSourceState.value = {
    ..._resetStateDefault(),
    stepsTotal: PROFILE_RESET_STEP_COUNT * (store.sourceInfo?.table_count ?? 1),
    showWarning: true,
  };
}

async function startResetSource() {
  if (!selectedSource.value) return;
  resetSourceState.value = {
    ..._resetStateDefault(),
    stepsTotal: PROFILE_RESET_STEP_COUNT * (store.sourceInfo?.table_count ?? 1),
    running: true,
  };
  _resetSourceAbort = new AbortController();
  const source = selectedSource.value;

  try {
    await resetSourceProfile(
      source,
      (event, data) => {
        if (event === 'progress') {
          const table = typeof data.table === 'string' ? data.table : '';
          resetSourceState.value.currentStep = table
            ? `${table} — ${resetStepLabel(String(data.step ?? ''))}`
            : String(data.step ?? '');
          resetSourceState.value.stepsCompleted += 1;
        } else if (event === 'error') {
          resetSourceState.value.failed = true;
          resetSourceState.value.errorMessage = String(data.message ?? 'Reset failed — rolled back, nothing changed.');
        }
      },
      _resetSourceAbort.signal,
    );
  } catch (e) {
    if (!(e instanceof DOMException && e.name === 'AbortError')) {
      resetSourceState.value.failed = true;
      resetSourceState.value.errorMessage = 'Reset failed — rolled back, nothing changed.';
    }
  } finally {
    resetSourceState.value.running = false;
    resetSourceState.value.done = true;
    _resetSourceAbort = null;
    // Reload source info so the "Profiled" timestamp and dataset list update. If a
    // specific dataset/column is also currently open, refresh those too — Data Story,
    // Reference Data, and the element detail live in separate store refs untouched by
    // loadSourceInfo, and a source-level reset just cleared all of them too.
    if (selectedSource.value === source) {
      await store.loadSourceInfo(source);
      if (selectedTable.value) {
        const table = selectedTable.value;
        const schema = selectedTableSchema.value;
        const activeColumn = selectedColumn.value;
        await Promise.all([
          store.loadDatasetOverview(source, table, schema ?? undefined, true),
          store.loadDataStory(source, table, schema ?? undefined),
          ...(activeColumn ? [store.loadElement(source, table, activeColumn, schema ?? undefined, true)] : []),
        ]);
        if (activeColumn) {
          await store.loadReferenceData(source, table, activeColumn, schema ?? undefined);
        }
      }
    }
  }
}

function abortResetSource() {
  _resetSourceAbort?.abort();
}

// Plain-language list of what a bulk rebuild is actually doing per table, so the
// progress banner doesn't say "profiles" while silently also re-deriving semantic
// types / re-scoring DQ underneath (both opted into via the warning dialog's checkboxes).
const rebuildStepsLabel = computed(() => {
  const extras: string[] = [];
  if (rebuildState.value.includeSemantic) extras.push('semantic types');
  if (rebuildState.value.includeDq) extras.push('quality scores');
  return extras.length ? `profiles, ${extras.join(' & ')}` : 'profiles';
});

function cancelEdit() {
  descValue.value = store.element?.column_description ?? '';
  descDirty.value = false;
  isDescEditMode.value = false;
}

async function saveBusinessName() {
  if (!bnameValue.value.trim()) return;
  bnameSaving.value = true;
  try {
    await store.updateBusinessName(bnameValue.value.trim(), bnameIsAi.value);
    bnameEditMode.value = false;
  } finally {
    bnameSaving.value = false;
  }
}

function cancelBname() {
  bnameValue.value = store.element?.business_name ?? '';
  bnameIsAi.value = false;
  bnameEditMode.value = false;
}

async function draftBusinessNameHandler() {
  bnameDraftLoading.value = true;
  clearAiError();
  try {
    const { draft, error } = await store.draftBusinessName();
    if (error) { setAiError(error); return; }
    if (draft) {
      bnameValue.value = draft;
      bnameIsAi.value = true;
      bnameEditMode.value = true;
    } else {
      setAiError({ summary: 'The AI didn’t return a suggestion. Please try again.' });
    }
  } finally {
    bnameDraftLoading.value = false;
  }
}

// ── Mapping Type functions ─────────────────────────────────────────────────
async function loadVocabData() {
  if (vocabData.value) return;
  try { vocabData.value = await (await fetch('/api/semantic-types/vocabulary')).json(); } catch { /* non-fatal */ }
}

async function loadSemTypeRecord() {
  const el = store.element;
  if (!el) return;
  semTypeLoading.value = true;
  void loadVocabData();
  try {
    const qs = el.schema ? `?schema=${encodeURIComponent(el.schema)}` : '';
    const data = await (await fetch(`/api/semantic-types/${el.source}/${el.table}${qs}`)).json() as { columns?: Array<Record<string, unknown>> };
    semTypeRecord.value = findSemTypeRecordForColumn(data.columns ?? [], el.column);
  } catch {
    semTypeRecord.value = null;
  } finally {
    semTypeLoading.value = false;
  }
}

async function resolveSemType() {
  const el = store.element;
  if (!el) return;
  semTypeResolving.value = true;
  try {
    const qs = el.schema ? `?schema=${encodeURIComponent(el.schema)}` : '';
    await fetch(`/api/semantic-types/${el.source}/${el.table}/resolve${qs}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ include_ai: false }) });
    await loadSemTypeRecord();
  } finally {
    semTypeResolving.value = false;
  }
}

// AI assistance anchor — only for the unresolved / ambiguous tail. Re-runs
// resolution WITH the AI pass enabled; the proposal is still steward-gated.
async function resolveSemTypeWithAi() {
  const el = store.element;
  if (!el) return;
  semTypeAiRunning.value = true;
  clearAiError();
  try {
    const qs = el.schema ? `?schema=${encodeURIComponent(el.schema)}` : '';
    const resp = await fetch(`/api/semantic-types/${el.source}/${el.table}/resolve${qs}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ include_ai: true }) });
    const data = await resp.json().catch(() => null) as { error?: { summary: string; detail?: string | null; status?: number | null } } | null;
    if (data?.error) { setAiError(data.error); return; }
    await loadSemTypeRecord();
  } catch (e: unknown) {
    setAiError(aiErrorFrom(e, 'AI semantic resolution failed.'));
  } finally {
    semTypeAiRunning.value = false;
  }
}

async function confirmSemType(typeId?: string, domainRole?: string) {
  const el = store.element;
  if (!el) return;
  semTypeConfirming.value = true;
  try {
    const qs = el.schema ? `?schema=${encodeURIComponent(el.schema)}` : '';
    const aiAssisted = semTypeRecord.value?.source === 'ai';
    const body: Record<string, unknown> = { ai_assisted: aiAssisted, accepted_by_role: roleStore.currentRole };
    if (typeId) body.type_id = typeId;
    if (domainRole) body.domain_role = domainRole;
    await fetch(`/api/semantic-types/${el.source}/${el.table}/${el.column}/accept${qs}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    semTypeOverrideOpen.value = false;
    semOverrideTypeId.value = null;
    semOverrideRole.value = null;
    await loadSemTypeRecord();
    // Re-score the field — refreshElementDq also force-reloads the dataset overview +
    // source-info (when loaded), which refreshes the "Semantic-type mix" charts too.
    await store.refreshElementDq('Semantic Type accepted');
  } finally {
    semTypeConfirming.value = false;
  }
}

// Steward override — confirm with the cascading-picked type_id + domain role
// (send the domain too, so an overridden type never mismatches its domain).
function applySemTypeOverride() {
  const typeId = semOverrideTypeId.value;
  if (!typeId) return;
  void confirmSemType(typeId, semOverrideRole.value ?? undefined);
}

function copyToClipboard() {
  if (!descValue.value) return;
  navigator.clipboard.writeText(descValue.value).catch(() => {
    // Fallback for older browsers
    const textarea = document.createElement('textarea');
    textarea.value = descValue.value;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
  });
}

// ── Definition workflow — replaced by the canonical footer actions (onSaveDraft/
// onSubmitClick/onConfirmSubmit/onWithdraw/onApprove/onReturn/onReject) above.

// ── Document store wiring ───────────────────────────────────────────────
async function loadDocuments(source: string): Promise<void> {
  try {
    const docs = await listDocuments(source);
    docList.value = docs.map(d => ({
      id: d.id as unknown as number,
      name: d.name,
      type: d.doc_type as typeof docList.value[number]['type'],
      description: d.description,
      owner: d.owner,
      scope: d.scope,
      uploadedAt: d.uploaded_at,
      status: 'ready' as const,
      size: d.file_size_kb != null ? `${d.file_size_kb} KB` : '—',
      aiPermissions: { definitions: d.ai_permissions.definitions, mapping: d.ai_permissions.mapping, quality: d.ai_permissions.quality },
      aiKnowledge: d.synopsis ?? undefined,
      _docId: d.id,
    }));
  } catch {
    docList.value = [];
  }
}

// ── Reference Data workflow functions ─────────────────────────────────────
function rdStartEdit() {
  rdMeaningEdits.value = {};
  rdValueEdits.value = {};
  rdEditMode.value = true;
}

function rdCancelEdit() {
  rdMeaningEdits.value = {};
  rdValueEdits.value = {};
  rdEditMode.value = false;
}

async function rdSaveMeanings() {
  const el = store.element;
  if (!el || !store.referenceData) return;
  rdSaving.value = true;
  try {
    await apiUpdateReferenceData(el.source, el.table, el.column, { meanings: rdMeaningEdits.value, values: rdValueEdits.value }, el.schema);
    // Update local codes so UI reflects changes immediately
    if (store.referenceData) {
      for (const c of store.referenceData.codes) {
        if (rdMeaningEdits.value[c.code] !== undefined) {
          c.meaning = rdMeaningEdits.value[c.code] || null;
        }
        if (rdValueEdits.value[c.code] !== undefined) {
          c.value = rdValueEdits.value[c.code] || null;
        }
      }
    }
    rdEditMode.value = false;
    rdMeaningEdits.value = {};
    rdValueEdits.value = {};
    // Documented codes feed the DQ Reference-Data component — re-score live.
    await store.refreshElementDq('Reference code meanings saved');
  } finally {
    rdSaving.value = false;
  }
}

async function rdSetStatus(status: string) {
  const el = store.element;
  if (!el) return;
  rdStatusSaving.value = true;
  try {
    await apiUpdateReferenceData(el.source, el.table, el.column, { status }, el.schema);
    rdLocalStatus.value = status;
    if (store.referenceData) {
      store.referenceData.status = status;
    }
    // Reference-Data status feeds its DQ line-item — re-score live.
    await store.refreshElementDq(
      status === 'approved' ? 'Reference codes approved'
      : status === 'under_review' ? 'Reference codes submitted for review'
      : 'Reference codes withdrawn',
    );
  } finally {
    rdStatusSaving.value = false;
  }
}

async function rdLoadSets() {
  if (rdSets.value.length) return;
  try {
    rdSets.value = await apiListReferenceSets();
  } catch {
    rdSets.value = [];
  }
}

async function rdReloadReferenceData() {
  const el = store.element;
  if (!el) return;
  rdClearSelection();
  store.referenceData = null;
  await store.loadReferenceData(el.source, el.table, el.column, el.schema);
}

// ── Per-code Reference Data (5b.2, Postgres backend) actions ───────────────
function rdAddCode() {
  const name = rdNewCodeName.value.trim();
  if (!name) return;
  const exists = rdDisplayCodes.value.some((c) => c.code === name);
  if (!exists) {
    rdAddedCodes.value.push({
      code: name, value: null, meaning: null, share_pct: null,
      origin: 'declared', status: 'empty', in_source: false,
    });
  }
  rdNewCodeName.value = '';
  rdShowAddCode.value = false;
}

async function rdSaveDraft() {
  const el = store.element;
  if (!el || !store.referenceData) return;
  const edits = rdDisplayCodes.value
    .filter((c) => rdRowEditable(c))
    .map((c) => ({
      code: c.code,
      value: rdValueEdits.value[c.code] ?? c.value ?? null,
      meaning: rdMeaningEdits.value[c.code] ?? c.meaning ?? null,
      origin: (rdOriginEdits.value[c.code] ?? c.origin ?? 'profiled') as 'profiled' | 'declared',
    }));
  if (!edits.length) return;
  rdSavingCodes.value = true;
  try {
    await store.saveReferenceCodes(el.source, el.table, el.column, edits, el.schema);
    rdAddedCodes.value = [];
    rdMeaningEdits.value = {};
    rdValueEdits.value = {};
    rdOriginEdits.value = {};
    // Documented codes feed the DQ Reference-Data component — re-score live.
    await store.refreshElementDq('Reference codes saved as draft');
  } finally {
    rdSavingCodes.value = false;
  }
}

async function rdSubmitCodes() {
  const el = store.element;
  const codes = rdSubmittableSelected.value;
  // 2026-08-16 redesign — ONE COMBINED ACTION: a bound field with nothing but the binding
  // itself pending (no unrecognised codes filled in) can still Submit; the backend submits
  // the binding decision alone in that case.
  const bindingPending = !!rdBoundSetId.value && rdBindingStatus.value === 'draft';
  if (!el || (!codes.length && !bindingPending)) return;
  rdSubmitting.value = true;
  try {
    await store.submitReferenceCodes(el.source, el.table, el.column, codes, el.schema);
    rdClearSelection();
    // Submission also affects the binding's own status — refetch the full payload rather
    // than merging just the codes/set_badge fields the plain per-code response returns.
    await rdReloadReferenceData();
    // Submitting changes the derived set status — re-score live.
    await store.refreshElementDq('Reference codes submitted for review');
  } finally {
    rdSubmitting.value = false;
  }
}

async function rdWithdrawSelected() {
  const el = store.element;
  const codes = rdWithdrawableSelected.value;
  if (!el || !codes.length) return;
  rdBulkLoading.value = true;
  try {
    await store.withdrawReferenceCodes(el.source, el.table, el.column, codes, el.schema);
    rdClearSelection();
    await store.refreshElementDq('Reference codes withdrawn');
  } finally {
    rdBulkLoading.value = false;
  }
}

async function rdRevokeSelected() {
  const el = store.element;
  const codes = rdRevocableSelected.value;
  if (!el || !codes.length) return;
  rdBulkLoading.value = true;
  try {
    await store.revokeReferenceCodes(el.source, el.table, el.column, codes, el.schema);
    rdClearSelection();
    await store.refreshElementDq('Reference codes revoked');
  } finally {
    rdBulkLoading.value = false;
  }
}

async function rdRemoveSelected() {
  const el = store.element;
  const codes = rdRemovableSelected.value;
  if (!el || !codes.length) return;
  // Client-only added rows are dropped locally; persisted empty/draft rows are deleted server-side.
  const addedNames = new Set(rdAddedCodes.value.map((c) => c.code));
  const persisted = codes.filter((c) => !addedNames.has(c));
  rdBulkLoading.value = true;
  try {
    rdAddedCodes.value = rdAddedCodes.value.filter((c) => !codes.includes(c.code));
    if (persisted.length) {
      await store.removeReferenceCodes(el.source, el.table, el.column, persisted, el.schema);
      await store.refreshElementDq('Reference code removed');
    }
    rdClearSelection();
  } finally {
    rdBulkLoading.value = false;
  }
}

async function rdBind(setId: string | null) {
  const el = store.element;
  if (!el || !setId) return;
  rdBindingSaving.value = true;
  try {
    await apiUpdateReferenceData(el.source, el.table, el.column, { bound_set_id: setId }, el.schema);
    rdSelectedSetId.value = null;
    await rdReloadReferenceData();
    // Binding a reference set changes the DQ Reference-Data component — re-score live.
    await store.refreshElementDq('Reference set bound');
  } finally {
    rdBindingSaving.value = false;
  }
}

async function rdUnbind() {
  const el = store.element;
  if (!el) return;
  rdBindingSaving.value = true;
  try {
    await apiUpdateReferenceData(el.source, el.table, el.column, { unbind: true }, el.schema);
    await rdReloadReferenceData();
    // Unbinding a reference set changes the DQ Reference-Data component — re-score live.
    await store.refreshElementDq('Reference set unbound');
  } finally {
    rdBindingSaving.value = false;
  }
}

// ── computed ──────────────────────────────────────────────────────────────

const tabs = computed(() => {
  const el = store.element;
  if (!el) return [];
  const isCoded = (el.stats?.distinct_count ?? 999) <= 50;
  return [
    { key: 'profile', label: 'Profile', badge: null, badgeClass: '', disabled: false, colorKey: componentTabColorKey('profile'), critical: false },
    { key: 'interpretation', label: 'Interpretation', badge: defTabBadge.value, badgeClass: defTabBadgeClass.value, disabled: false, colorKey: componentTabColorKey('interpretation'), critical: false },
    { key: 'refdata', label: 'Reference Data', badge: isCoded ? (rdStatus.value === 'approved' ? '✓' : null) : '—', badgeClass: rdStatus.value === 'approved' ? 'tab-badge--ok' : '', disabled: !isCoded, colorKey: componentTabColorKey('refdata'), critical: false },
    { key: 'observations', label: DQ_TAB_LABEL, badge: null, badgeClass: '', disabled: false, colorKey: componentTabColorKey('observations'), critical: false },
    { key: 'mapping', label: `Mapping (${el.mapping_candidates.length})`, badge: null, badgeClass: '', disabled: false, colorKey: componentTabColorKey('mapping'), critical: false },
    { key: 'history', label: `History (${el.audit_history.length})`, badge: null, badgeClass: '', disabled: false, colorKey: componentTabColorKey('history'), critical: false },
  ];
});

function formatAuditEvent(evtRaw: unknown): string {
  const evt = evtRaw as { event_type?: string; payload?: { new_state?: string } & Record<string, unknown> };
  const eventType: string = evt.event_type || '';
  const payload = evt.payload || {};

  // Map event types to user-friendly messages
  if (eventType === 'element.state_changed') {
    const newState = payload.new_state || 'Unknown';
    return `State changed to ${capitalize(newState)}`;
  }
  if (eventType === 'element.description_updated') {
    return 'Description saved';
  }
  if (eventType === 'ai.call') {
    return 'AI draft generated';
  }
  if (eventType === 'insights.generated') {
    return 'Insights generated';
  }
  if (eventType === 'mapping.candidate.accepted') {
    return 'Mapping candidate accepted';
  }
  if (eventType === 'mapping.candidate.rejected') {
    return 'Mapping candidate rejected';
  }
  if (eventType === 'glossary.term.created') {
    return 'Linked to glossary term';
  }

  // Fallback: convert snake_case to Title Case
  return eventType.split('_').map(w => capitalize(w)).join(' ');
}

function capitalize(str: string): string {
  return str.charAt(0).toUpperCase() + str.slice(1);
}

const distBins = computed(() => {
  const tv = store.element?.stats?.top_values;
  if (tv && tv.length > 0) {
    const max = tv[0]?.count ?? 1;
    return tv.slice(0, 12).map(({ value, count }) => ({
      label: String(value ?? 'null'), count,
      pct: Math.round((count / max) * 100),
    }));
  }
  const vals = store.element?.stats?.sample_values;
  if (!vals || vals.length === 0) return [];
  const freq: Record<string, number> = {};
  for (const v of vals) {
    const k = String(v ?? 'null');
    freq[k] = (freq[k] ?? 0) + 1;
  }
  const sorted = Object.entries(freq).sort((a, b) => b[1] - a[1]).slice(0, 10);
  const max = sorted[0]?.[1] ?? 1;
  return sorted.map(([label, count]) => ({ label, count, pct: Math.round((count / max) * 100) }));
});

const distBinsDisplayed = computed(() => {
  let bins = [...distBins.value];
  if (distMode.value === 'alpha') {
    bins.sort((a, b) => String(a.label).localeCompare(String(b.label)));
  }
  if (distLogScale.value) {
    const maxCount = Math.max(...bins.map(b => b.count), 1);
    return bins.map(b => ({
      ...b,
      pct: b.count > 0 ? Math.round((Math.log(b.count + 1) / Math.log(maxCount + 1)) * 100) : 0,
    }));
  }
  return bins;
});

const completenessTextColor = computed(() => {
  const np = store.element?.stats?.null_pct ?? 0;
  if (np < 0.05) return 'color-green';
  if (np < 0.2) return 'color-amber';
  return 'color-red';
});

const completenessMeterColor = computed(() => {
  const np = store.element?.stats?.null_pct ?? 0;
  if (np < 0.05) return 'stat-meter-fill--green';
  if (np < 0.2) return 'stat-meter-fill--amber';
  return 'stat-meter-fill--red';
});

// ── helpers ───────────────────────────────────────────────────────────────

function confidenceColor(conf: number | null): string {
  if (conf == null) return 'grey-5';
  if (conf >= 0.85) return 'positive';
  if (conf >= 0.6) return 'warning';
  return 'negative';
}

function candidateStatusColor(status: string): string {
  if (status === 'accepted') return 'positive';
  if (status === 'rejected') return 'negative';
  return 'grey-5';
}

function fmtPct(v: number | null): string {
  if (v == null) return '—';
  return (v * 100).toFixed(1);
}

function fmtDate(ts: string): string {
  if (!ts) return '';
  return new Date(ts).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
}

const FK_BASIS_LABELS: Record<string, string> = {
  exact_name: 'exact name match',
  table_reference: 'column name references table name',
  abbreviation: 'abbreviated name match',
};

function fkBasisLabel(basis: string | null | undefined): string {
  return (basis && FK_BASIS_LABELS[basis]) || 'name/type match';
}

const totalOrphanFkCount = computed<number>(() => {
  return (store.datasetOverview?.foreign_keys ?? []).reduce((sum, fk) => sum + (fk.orphan_count ?? 0), 0);
});

// ── Source-level cards (shared viz components) ────────────────────────────
// The source level's job is RANKING/COMPARING its datasets, not re-showing
// dataset-level composition — so composition collapses to one compact strip
// and the space goes to the Quality Map + datasets table.

const srcSemanticSegments = computed<VizSegment[]>(() => {
  const items = store.sourceInfo?.semantic_type_mix ?? [];
  const total = items.reduce((sum, s) => sum + s.count, 0) || 1;
  return items.map((s) => ({
    label: s.label || capitalize(s.type),
    count: s.count,
    color: s.color,
    pct: (100 * s.count) / total,
  }));
});

const srcGovernanceSegments = computed<VizSegment[]>(
  () => govSegments(store.sourceInfo?.governance_state),
);

/** Share of elements a steward has moved beyond Draft. */
const srcGovernedPct = computed(() => {
  const g = store.sourceInfo?.governance_state;
  if (!g) return 0;
  const total = (g.empty ?? 0) + (g.draft ?? 0) + (g.in_review ?? 0) + (g.approved ?? 0) + (g.bounced ?? 0);
  if (!total) return 0;
  return Math.round((((g.in_review ?? 0) + (g.approved ?? 0) + (g.bounced ?? 0)) / total) * 100);
});

/** Mean DQ score across this source's scored datasets. */
const srcAvgDq = computed<number | null>(() => {
  const scores = (store.sourceInfo?.datasets ?? [])
    .map((d) => d.dataset_dq?.dq_score)
    .filter((s): s is number => typeof s === 'number');
  if (!scores.length) return null;
  return Math.round(scores.reduce((a, b) => a + b, 0) / scores.length);
});

/** True only when every dataset in this source is still in its pre-profiling
 *  baseline (freshly onboarded, or every table individually reset) — drives
 *  the "never profiled" badge next to the source name in the header. */
const srcAllUnprofiled = computed(() => {
  const datasets = store.sourceInfo?.datasets ?? [];
  return datasets.length > 0 && datasets.every((d) => !d.is_profiled);
});

const srcKpis = computed<VizKpi[]>(() => {
  const info = store.sourceInfo;
  if (!info) return [];
  const avg = srcAvgDq.value;
  const dqColor = avg == null ? undefined : avg >= 90 ? 'var(--dq-excellent)' : avg >= 75 ? 'var(--dq-good)' : avg >= 60 ? 'var(--dq-adequate)' : avg >= 40 ? 'var(--dq-weak)' : 'var(--dq-critical)';
  return [
    { label: 'Datasets', value: info.table_count ?? '—' },
    { label: 'Data Elements', value: info.column_count?.toLocaleString() ?? '—' },
    { label: 'Total Rows', value: info.total_row_count?.toLocaleString() ?? '—' },
    {
      label: 'Governance Progress',
      value: `${srcGovernedPct.value}%`,
      meterPct: srcGovernedPct.value,
      color: srcGovernedPct.value >= 60 ? 'var(--dq-excellent)' : srcGovernedPct.value >= 25 ? 'var(--dq-adequate)' : 'var(--dq-critical)',
      hint: 'What % of this source\'s elements have moved past Draft',
    },
    {
      label: 'Avg DQ Score',
      value: avg == null ? '—' : avg,
      meterPct: avg,
      color: dqColor,
      hint: avg == null ? 'No datasets scored yet' : 'Average quality score across the datasets that have been scored',
    },
  ];
});

/** One bubble per dataset for the Quality Map. */
const srcQualityPoints = computed<VizQualityPoint[]>(
  () => (store.sourceInfo?.datasets ?? []).map((d) => {
    const g = d.governance ?? {};
    const govTotal = Object.values(g).reduce((a, b) => a + b, 0);
    const govMoved = (g.in_review ?? 0) + (g.approved ?? 0) + (g.bounced ?? 0);
    return {
      label: d.table_name,
      schema: d.schema,
      governancePct: govTotal ? Math.round((govMoved / govTotal) * 100) : 0,
      score: d.dataset_dq?.dq_score ?? null,
      rows: d.row_count ?? 0,
      columns: d.column_count ?? 0,
      color: dqIntentColor(d.dataset_dq?.grade_color_intent),
    };
  }),
);

function openQualityPoint(point: VizQualityPoint) {
  selectTableByName(point.label, point.schema);
}

// ── Conceptual Data Model (source level) ──────────────────────────────────
// Entity-box + 1:N line diagram built straight from the PK/FK relationships
// already present in each table's catalog entry (`relations` for DB-declared
// constraints, `inferred_relations` for name/type-inferred fallbacks) —
// no extra profiling needed. Cardinality is always 1:N by construction of a
// PK/FK pair: the referenced ("to") table is the "1" side, the table holding
// the FK ("from") is the "N" side. Layout is a simple deterministic circle —
// sufficient for the handful of tables a demo source has, no graph-layout
// library needed. Entities are draggable (position "sticks" where dropped —
// no snap-back) and lines re-anchor to the dragged position automatically;
// "Regenerate Model" clears drag overrides back to the default circle and
// re-fetches the source so PK/FK changes are re-checked.
interface LdmNode {
  table: string;
  schema: string;
  x: number;
  y: number;
  halfW: number;
}

/** User-dragged positions, keyed by "schema.table" — persisted to
 * localStorage per source so the arrangement survives page reloads and
 * navigating away and back, not just kept in memory for the session.
 * "Regenerate Model" (or a full-screen toggle, which changes the canvas
 * size) resets it. Not reactive-bound to the default layout math so a drag
 * never gets pulled back to its circle position. */
const LDM_LAYOUT_STORAGE_PREFIX = 'adirra-ldm-layout:';

function ldmLayoutStorageKey(source: string): string {
  return `${LDM_LAYOUT_STORAGE_PREFIX}${source}`;
}

function loadLdmLayout(source: string | null): Record<string, { x: number; y: number }> {
  if (!source) return {};
  try {
    const raw = localStorage.getItem(ldmLayoutStorageKey(source));
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function saveLdmLayout(source: string | null, overrides: Record<string, { x: number; y: number }>): void {
  if (!source) return;
  try {
    localStorage.setItem(ldmLayoutStorageKey(source), JSON.stringify(overrides));
  } catch {
    // Storage unavailable/full — layout simply won't persist, not fatal.
  }
}

function clearLdmLayout(source: string | null): void {
  if (!source) return;
  try {
    localStorage.removeItem(ldmLayoutStorageKey(source));
  } catch {
    // ignore
  }
}

const ldmOverrides = ref<Record<string, { x: number; y: number }>>(loadLdmLayout(selectedSource.value));

// Re-fetching a new source's diagram should restore that source's own saved
// layout (or a blank slate if it's never been customized) rather than
// carrying over whatever was on screen for the previous source.
watch(selectedSource, (src) => {
  ldmOverrides.value = ldmFullscreen.value ? {} : loadLdmLayout(src);
});

// The diagram's logical coordinate space. Full screen uses a much larger
// canvas — not just a bigger on-screen box around the same cramped layout —
// so entities actually get more room to spread out instead of the same
// small 640×400 arrangement merely being scaled up (zoomed) to fill the
// screen, which left nodes just as close together as before.
const ldmCanvas = computed(() => (ldmFullscreen.value ? { w: 1500, h: 860 } : { w: 640, h: 400 }));

const ldmNodes = computed<LdmNode[]>(() => {
  const datasets = store.sourceInfo?.datasets ?? [];
  const n = datasets.length;
  if (!n) return [];
  const { w, h } = ldmCanvas.value;
  const cx = w / 2;
  const cy = h / 2;
  const r = n <= 1 ? 0 : Math.min(cx, cy) - 90;
  return datasets.map((ds, i) => {
    const key = `${ds.schema}.${ds.table_name}`;
    const override = ldmOverrides.value[key];
    const angle = n === 1 ? 0 : (2 * Math.PI * i) / n - Math.PI / 2;
    return {
      table: ds.table_name,
      schema: ds.schema,
      x: override?.x ?? (cx + r * Math.cos(angle)),
      y: override?.y ?? (cy + r * Math.sin(angle)),
      halfW: Math.max(38, ds.table_name.length * 3.4 + 12),
    };
  });
});

function ldmNodeFor(table: string): LdmNode | undefined {
  return ldmNodes.value.find((n) => n.table === table);
}

// Drag handling — pointer coordinates are converted into the SVG's own user
// space via getScreenCTM() so dragging tracks the cursor 1:1 regardless of
// how the viewBox is scaled (including in full-screen). A short drag-distance
// threshold distinguishes an actual drag from a click so dropping a node
// doesn't also fire the "navigate to dataset" click handler.
const ldmSvgEl = ref<SVGSVGElement | null>(null);
let ldmDragKey: string | null = null;
let ldmDragPointerId: number | null = null;
let ldmDragStart: { x: number; y: number } | null = null;
let ldmDragMoved = false;

function ldmSvgPoint(evt: PointerEvent): { x: number; y: number } | null {
  const svg = ldmSvgEl.value;
  if (!svg) return null;
  const ctm = svg.getScreenCTM();
  if (!ctm) return null;
  const pt = svg.createSVGPoint();
  pt.x = evt.clientX;
  pt.y = evt.clientY;
  const transformed = pt.matrixTransform(ctm.inverse());
  return { x: transformed.x, y: transformed.y };
}

function ldmNodePointerDown(node: LdmNode, evt: PointerEvent) {
  ldmDragKey = `${node.schema}.${node.table}`;
  ldmDragPointerId = evt.pointerId;
  ldmDragMoved = false;
  ldmDragStart = ldmSvgPoint(evt);
  (evt.currentTarget as Element).setPointerCapture(evt.pointerId);
}

function ldmNodePointerMove(evt: PointerEvent) {
  if (!ldmDragKey || evt.pointerId !== ldmDragPointerId) return;
  const p = ldmSvgPoint(evt);
  if (!p) return;
  if (ldmDragStart && Math.hypot(p.x - ldmDragStart.x, p.y - ldmDragStart.y) > 3) {
    ldmDragMoved = true;
  }
  ldmOverrides.value = { ...ldmOverrides.value, [ldmDragKey]: p };
}

function ldmNodePointerUp(evt: PointerEvent) {
  if (evt.pointerId === ldmDragPointerId) {
    // Full-screen positions use a different canvas size, so they aren't
    // saved — only the normal-view layout persists across reloads.
    if (ldmDragMoved && !ldmFullscreen.value) {
      saveLdmLayout(selectedSource.value, ldmOverrides.value);
    }
    ldmDragKey = null;
    ldmDragPointerId = null;
  }
}

/** Click fires after pointerup too — skip navigation when it was actually a drag. */
function ldmNodeClick(node: LdmNode) {
  if (ldmDragMoved) {
    ldmDragMoved = false;
    return;
  }
  selectTableByName(node.table, node.schema);
}

function regenerateLdm() {
  ldmOverrides.value = {};
  clearLdmLayout(selectedSource.value);
  refreshSourceInfo();
}

// Full screen scoped to the diagram card only (not the whole app).
const ldmPanelEl = ref<HTMLElement | null>(null);
const ldmFullscreen = ref(false);

function toggleLdmFullscreen() {
  const el = ldmPanelEl.value;
  if (!el) return;
  if (document.fullscreenElement === el) {
    void document.exitFullscreen();
  } else {
    void el.requestFullscreen?.();
  }
}

function onLdmFullscreenChange() {
  ldmFullscreen.value = document.fullscreenElement === ldmPanelEl.value;
  // The canvas size (and therefore the default circle layout) differs
  // between normal and full-screen — start fresh for full screen since its
  // coordinates don't apply to the other canvas; restore the saved layout
  // when coming back to the normal view instead of losing it.
  ldmOverrides.value = ldmFullscreen.value ? {} : loadLdmLayout(selectedSource.value);
}

onMounted(() => document.addEventListener('fullscreenchange', onLdmFullscreenChange));
onBeforeUnmount(() => document.removeEventListener('fullscreenchange', onLdmFullscreenChange));

const ldmEdges = computed(() => {
  const rels = store.sourceInfo?.relationships ?? [];
  const boxHalfH = 15;
  return rels
    .map((rel) => {
      const from = ldmNodeFor(rel.from_table); // "many" side (FK holder)
      const to = ldmNodeFor(rel.to_table); // "one" side (referenced/parent)
      if (!from || !to || from === to) return null;
      const dx = to.x - from.x;
      const dy = to.y - from.y;
      const dist = Math.hypot(dx, dy) || 1;
      const ux = dx / dist;
      const uy = dy / dist;
      const px = -uy; // perpendicular unit vector, for crow's-foot/tick marks
      const py = ux;
      const x1 = from.x + ux * from.halfW;
      const y1 = from.y + uy * boxHalfH;
      const x2 = to.x - ux * to.halfW;
      const y2 = to.y - uy * boxHalfH;

      // Crow's-foot ("many") at the child end — two splayed prongs off the
      // main line; the line itself forms the middle prong.
      const footBack = 13;
      const footSpread = 7;
      const footBaseX = x1 + ux * footBack;
      const footBaseY = y1 + uy * footBack;
      const crowFeet = [
        { x1, y1, x2: footBaseX + px * footSpread, y2: footBaseY + py * footSpread },
        { x1, y1, x2: footBaseX - px * footSpread, y2: footBaseY - py * footSpread },
      ];

      // Double perpendicular tick ("exactly one") at the parent end.
      const tickSpread = 7;
      const tick1 = { back: 9 }, tick2 = { back: 14 };
      const oneTicks = [tick1, tick2].map(({ back }) => {
        const cx2 = x2 - ux * back;
        const cy2 = y2 - uy * back;
        return { x1: cx2 + px * tickSpread, y1: cy2 + py * tickSpread, x2: cx2 - px * tickSpread, y2: cy2 - py * tickSpread };
      });

      // Verb label — sits just above the line's midpoint, rotated to follow
      // the line's own angle so it reads along the relationship.
      const midX = (x1 + x2) / 2;
      const midY = (y1 + y2) / 2;
      let angleDeg = Math.atan2(dy, dx) * (180 / Math.PI);
      // Keep the text upright (never upside-down) regardless of line direction.
      if (angleDeg > 90 || angleDeg < -90) angleDeg += 180;
      const labelOffset = 9;
      const labelX = midX - px * labelOffset;
      const labelY = midY - py * labelOffset;

      return {
        key: `${rel.from_schema}.${rel.from_table}.${rel.from_columns.join(',')}->${rel.to_table}`,
        x1, y1, x2, y2,
        declared: rel.declared,
        crowFeet,
        oneTicks,
        labelX, labelY, angleDeg,
        verb: 'has',
        title: `${rel.from_table}.${rel.from_columns.join(', ')} → ${rel.to_table}.${rel.to_columns.join(', ')}` +
          (rel.declared ? ' (declared FK)' : ' (inferred FK — name/type match, not AI)'),
      };
    })
    .filter((e): e is NonNullable<typeof e> => e !== null);
});

const ldmHasInferred = computed(() => ldmEdges.value.some((e) => !e.declared));

// Proportional-bar segments (§7 chart redesign) — replaces the old fixed-
// width vertical-bar columns whose labels truncated (e.g. "Identifi...").
// pct is each category's share of the panel's own total, for a stacked bar.
// Semantic types keep their own categorical identity colours (from the API);
// governance reads the shared sequential journey ramp.
const dsSemanticSegments = computed<VizSegment[]>(() => {
  const items = store.datasetOverview?.semantic_type_mix ?? [];
  const total = items.reduce((sum, s) => sum + s.count, 0) || 1;
  return items.map((s) => ({
    label: capitalize(s.type),
    count: s.count,
    color: s.color,
    pct: (100 * s.count) / total,
  }));
});

const dsGovernanceSegments = computed<VizSegment[]>(
  () => govSegments(store.datasetOverview?.governance_state),
);

/** Legend tooltips keyed by the label the bar card renders. */
const GOV_LEGEND_HINTS: Record<string, string> = Object.fromEntries(
  Object.entries(GOV_SEGMENT_HINT).map(([key, hint]) => [GOV_SEGMENT_LABEL[key as keyof typeof GOV_SEGMENT_LABEL], hint]),
);

const dsDqGradeSegments = computed<VizSegment[]>(
  () => datasetDqGradeDist.value.map((g) => ({
    label: g.grade,
    count: g.count,
    pct: g.pct,
    color: dqIntentColor(g.colorIntent),
  })),
);

const SEM_STATE_COLOR: Record<string, string> = {
  accepted: 'var(--gov-approved-vivid)',
  pending: 'var(--gov-draft-vivid)',
  unresolved: 'var(--gov-empty-vivid)',
};

const SEM_STATE_HINTS: Record<string, string> = {
  Accepted: 'An analyst has accepted this column\'s semantic type — submission is unblocked',
  Pending: 'A type was deduced but nobody has accepted it yet — still blocks submission',
  Unresolved: 'No semantic type could be deduced — blocks submission',
};

/**
 * Semantic resolution status. Worth its own card because an element cannot be
 * submitted until its semantic type is accepted — unresolved/pending columns
 * are what's actually blocking the pipeline.
 */
const dsSemanticStateSegments = computed<VizSegment[]>(() => {
  const cols = store.datasetOverview?.columns_summary ?? [];
  if (!cols.length) return [];
  const counts: Record<string, number> = { accepted: 0, pending: 0, unresolved: 0 };
  for (const c of cols) {
    const state = c.semantic_state ?? 'unresolved';
    counts[state] = (counts[state] ?? 0) + 1;
  }
  return (['accepted', 'pending', 'unresolved'] as const)
    .filter((k) => counts[k] > 0)
    .map((k) => ({
      label: k.charAt(0).toUpperCase() + k.slice(1),
      count: counts[k],
      pct: (100 * counts[k]) / cols.length,
      color: SEM_STATE_COLOR[k],
    }));
});

const AI_COL = '#8b5cf6';
const MANUAL_COL = 'var(--gov-in-review-vivid)';
const ABSENT_COL = 'var(--adirra-paper-2)';

/**
 * How often the agent actually did the work — AI-authored vs hand-written vs
 * still missing, per governed content type. Read from the persisted
 * `*_is_ai` provenance flags, so it reflects real accepted AI output.
 */
const dsAiAssistRows = computed(() => {
  const cols = store.datasetOverview?.columns_summary ?? [];
  if (!cols.length) return [];
  const tally = (has: (c: ColumnSummary) => boolean, isAi: (c: ColumnSummary) => boolean) => {
    let ai = 0; let manual = 0; let absent = 0;
    for (const c of cols) {
      if (!has(c)) absent += 1;
      else if (isAi(c)) ai += 1;
      else manual += 1;
    }
    return [
      { label: 'AI-generated', count: ai, color: AI_COL },
      { label: 'Hand-written', count: manual, color: MANUAL_COL },
      { label: 'Not yet written', count: absent, color: ABSENT_COL },
    ];
  };
  return [
    { label: 'Definitions', segments: tally((c) => !!c.description, (c) => c.description_is_ai) },
    { label: 'Business names', segments: tally((c) => !!c.business_name, (c) => c.business_name_is_ai) },
  ];
});
/** Dataset-level KPI strip — counts plus the three health percentages. */const dsKpis = computed<VizKpi[]>(() => {
  const ov = store.datasetOverview;
  if (!ov) return [];
  const meterColor = (p: number) => (p >= 90 ? 'var(--dq-excellent)' : p >= 60 ? 'var(--dq-adequate)' : 'var(--dq-critical)');
  // Never profiled (fresh onboarding or post-reset) — no meaningful percentage to show yet,
  // render a blank "not yet measured" tile instead of a false 100%.
  const hasCompleteness = ov.completeness != null;
  const completeness = hasCompleteness ? Number(fmtPct(ov.completeness)) : null;
  const hasPkIntegrity = pkIntegrityPct.value != null;
  return [
    { label: 'Total Rows', value: ov.row_count?.toLocaleString('en-US') ?? '—' },
    { label: 'Columns', value: ov.column_count ?? '—' },
    {
      label: 'Avg Completeness',
      value: hasCompleteness ? `${fmtPct(ov.completeness)}%` : '—',
      meterPct: completeness,
      color: hasCompleteness ? meterColor(completeness as number) : null,
      hint: hasCompleteness
        ? 'What % of each column is actually filled in, on average'
        : 'Not yet measured — profile this dataset to see completeness',
    },
    {
      label: 'PK Integrity',
      value: hasPkIntegrity ? `${pkIntegrityPct.value}%` : '—',
      meterPct: pkIntegrityPct.value,
      color: hasPkIntegrity ? meterColor(pkIntegrityPct.value as number) : null,
      hint: hasPkIntegrity
        ? 'What % of rows are unique — no duplicate rows detected'
        : 'Not yet measured — profile this dataset to check for duplicate rows',
    },
    {
      label: 'Governance Progress',
      value: `${govCompletionPct.value}%`,
      meterPct: govCompletionPct.value,
      color: meterColor(govCompletionPct.value),
      hint: 'What % of this table\'s elements have moved past Draft',
    },
  ];
});

// ── Data Story ─────────────────────────────────────────────────────────────

const storyEditMode = ref(false);
const storyNarrativeEdit = ref('');
const storyTaglineEdit = ref('');
const storySaving = ref(false);
const storySavedBanner = ref(false);
const storySaveError = ref(false);
const bulkStoryLoading = ref(false);

async function runGenerateDataStory() {
  if (!selectedSource.value || !selectedTable.value) return;
  await store.generateDataStory(selectedSource.value, selectedTable.value, selectedTableSchema.value ?? undefined);
  // If called from edit mode and AI produced content, fill the textarea for review before saving
  if (storyEditMode.value && store.dataStory?.narrative) {
    storyNarrativeEdit.value = store.dataStory.narrative;
    storyTaglineEdit.value = store.dataStory.tagline ?? '';
  }
}

async function runBulkDataStories() {
  if (!selectedSource.value) return;
  bulkStoryLoading.value = true;
  try {
    const result = await store.bulkGenerateDataStories(selectedSource.value);
    if (result.ai_unavailable) {
      showBulkBanner('AI is not configured. Configure AI in project.yaml to generate data stories.', 'error');
    } else if (result.generated === 0 && result.already_existed === result.total) {
      showBulkBanner('All datasets already have data stories.', 'info');
    } else if (result.generated > 0) {
      const msg = `Generated ${result.generated} data ${result.generated === 1 ? 'story' : 'stories'}` +
        (result.already_existed > 0 ? `, ${result.already_existed} already existed` : '') +
        (result.failed > 0 ? `, ${result.failed} failed` : '') + '.';
      showBulkBanner(msg, 'success');
      recordBulkRun({ scope: 'source', target: selectedSource.value, type: 'data_stories', generated: result.generated, failed: result.failed ?? 0, total: result.total });
    } else {
      showBulkBanner('No new data stories were generated.', 'info');
    }
    // Reload source info so the missing-stories list and badge reflect the new state
    await store.loadSourceInfo(selectedSource.value);
  } catch {
    showBulkBanner('Failed to generate data stories.', 'error');
  } finally {
    bulkStoryLoading.value = false;
  }
}

function startEditStory() {
  storyNarrativeEdit.value = store.dataStory?.narrative ?? '';
  storyTaglineEdit.value = store.dataStory?.tagline ?? '';
  storyEditMode.value = true;
}

function cancelEditStory() {
  storyEditMode.value = false;
}

async function saveStory() {
  if (!selectedSource.value || !selectedTable.value) return;
  storySaving.value = true;
  storySavedBanner.value = false;
  storySaveError.value = false;
  try {
    await store.saveDataStory(
      selectedSource.value, selectedTable.value,
      storyTaglineEdit.value, storyNarrativeEdit.value,
      selectedTableSchema.value ?? undefined,
    );
    storyEditMode.value = false;
    storySavedBanner.value = true;
    setTimeout(() => { storySavedBanner.value = false; }, 3500);
  } catch (e) {
    console.error('[saveStory] save failed:', e);
    storySaveError.value = true;
    setTimeout(() => { storySaveError.value = false; }, 4000);
  } finally {
    storySaving.value = false;
  }
}

async function copyStory() {
  const narrative = store.dataStory?.narrative ?? '';
  const tagline = store.dataStory?.tagline ?? '';
  const text = tagline ? `${narrative}\n\n${tagline}` : narrative;
  await navigator.clipboard.writeText(text);
}

// ── PK Integrity & Governance Completion KPIs ─────────────────────────────

const pkIntegrityPct = computed<number | null>(() => {
  const ov = store.datasetOverview;
  // No rows profiled yet (fresh onboarding or post-reset) — there's nothing to check
  // duplicates against, so report "not yet measured" rather than a false 100%.
  if (!ov || !ov.row_count) return null;
  const dups = ov.duplicate_rows ?? 0;
  const pct = Math.round(((ov.row_count - dups) / ov.row_count) * 100);
  return Math.max(0, pct);
});

const govCompletionPct = computed(() => {
  const g = store.datasetOverview?.governance_state;
  if (!g) return 0;
  const total = (g.empty ?? 0) + (g.draft ?? 0) + (g.in_review ?? 0) + (g.approved ?? 0) + (g.bounced ?? 0);
  if (!total) return 0;
  // "governed" = steward has taken a formal action (in_review + approved; bounced was reviewed and returned)
  return Math.round(((g.in_review ?? 0) + (g.approved ?? 0) + (g.bounced ?? 0)) / total * 100);
});
</script>

<style scoped>
/* ── CSS custom props (warm palette) ──────────────────────────────────── */
.wp {
  --accent: #0d5c54;
  --accent-light: #e6f2f0;
  --paper: #f6f4f0;
  --card-bg: rgba(255, 253, 248, 0.62);
  --border: #ddd6c8;
  --text: #1c1b18;
  --text-2: #86827a;
  --draft-col: var(--gov-draft);
  --in-review-col: var(--gov-in-review);
  --approved-col: var(--gov-approved);
  --empty-col: var(--gov-empty);
  --bounced-col: var(--gov-bounced);
  --pending-col: var(--gov-empty);
  --danger-col: #9e3326;
  --warn-col: #a9651b;
  --info-col: #2f5d8a;
  --ai-col: #8b5cf6;
  /* 5 distinct DQ grade colours (one per band) — previously Excellent/Good
     reused near-identical greens (#1e5c2c/--approved-col) and Adequate/Weak
     reused near-identical oranges (--warn-col/#c0561b). Each grade now has
     its own hue across the whole app (dataset + element levels alike),
     since every DQ badge/pill/bar reads off this same var set.
     Values themselves now live in tokens.scss (U2d single-source). */
  height: 100%;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.wp-layout {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* ── Rail ────────────────────────────────────────────────────────────── */
.rail {
  flex: 0 0 300px;
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  background: #e8edf2;
}

.rail-section-label {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .10em;
  text-transform: uppercase;
  color: var(--text-2);
  margin-bottom: 6px;
}

.rail-header {
  padding: 12px 12px 8px;
  border-bottom: 1px solid var(--border);
}

/* Dataset dropdown sits right under its own sub-header (unlike Source, which
   has no preceding label row) — trim the extra top/bottom padding so it
   doesn't read as taller than the other rail rows. */
.rail-header--dataset {
  padding: 2px 12px 8px;
}

/* Source + Schema share one row. Schema needs closer to equal width — "src"
   was clipping at a narrower share, even though schema values are usually
   short, because the field also carries an icon + clear button + arrow. */
.rail-field-row {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}
.rail-field {
  min-width: 0;
}
.rail-field--source { flex: 1 1 0%; }
.rail-field--schema { flex: 1 1 0%; }

/* Modernized dropdown "card" look — lifts the rail selects off the flat
   background so they read as polished controls, matching the rest of the
   app's panel-card / accent-glow treatment instead of the stock Quasar
   outline. */
.rail-select :deep(.q-field__control) {
  font-size: 12.5px;
  background: var(--card-bg);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  border-radius: 10px;
  box-shadow: 0 1px 2px rgba(28, 27, 24, 0.06);
  transition: border-color .15s ease, box-shadow .15s ease, background .15s ease;
}
.rail-select :deep(.q-field__control)::before {
  border-color: var(--border) !important;
  border-radius: 10px;
}
.rail-select:hover :deep(.q-field__control)::before {
  border-color: var(--accent) !important;
}
.rail-select :deep(.q-icon) { color: var(--accent); opacity: .85; }
.rail-select :deep(.q-field__control) { padding-left: 2px; }
.rail-select :deep(.q-field--focused .q-field__control),
.rail-select :deep(.q-field--highlighted .q-field__control) {
  background: var(--accent-light) !important;
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 16%, transparent), 0 2px 6px rgba(13, 92, 84, 0.12);
}
.rail-select :deep(.q-field--focused .q-field__control::after),
.rail-select :deep(.q-field--highlighted .q-field__control::after) {
  border-color: var(--accent) !important;
  border-width: 1.5px !important;
  border-radius: 10px;
  box-shadow: none !important;
}

.rail-sub-header {
  padding: 10px 14px 4px;
}

.rail-search-wrap {
  padding: 0 10px 4px;
}

.rail-search :deep(.q-field__control) {
  height: 30px;
  font-size: 12px;
  background: var(--card-bg);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  border-radius: 10px;
  box-shadow: 0 1px 2px rgba(28, 27, 24, 0.06);
  transition: border-color .15s ease, box-shadow .15s ease, background .15s ease;
}
.rail-search :deep(.q-field__control)::before {
  border-color: var(--border) !important;
  border-radius: 10px;
}
.rail-search:hover :deep(.q-field__control)::before {
  border-color: var(--accent) !important;
}
.rail-search :deep(.q-icon) { color: var(--accent); opacity: .85; }
.rail-search :deep(.q-field--focused .q-field__control),
.rail-search :deep(.q-field--highlighted .q-field__control) {
  background: var(--accent-light) !important;
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 16%, transparent), 0 2px 6px rgba(13, 92, 84, 0.12);
}
.rail-search :deep(.q-field--focused .q-field__control::after),
.rail-search :deep(.q-field--highlighted .q-field__control::after) {
  border-color: var(--accent) !important;
  border-width: 1.5px !important;
  border-radius: 10px;
  box-shadow: none !important;
}

.rail-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  padding: 0 10px 8px;
}

.rail-chip {
  font-size: 10.5px;
  font-weight: 600;
  height: 22px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: 11px;
  background: var(--card-bg);
  color: var(--text-2);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 5px;
  transition: background .12s, color .12s, border-color .12s;
}

.chip-pip {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.rail-chip--active {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}
.rail-chip--active .chip-pip { opacity: .85; }

.rail-table-list { flex: 1; }

:deep(.rail-table-header) {
  font-size: 12.5px;
  font-weight: 600;
  padding: 6px 12px;
  color: var(--text);
}

/* ── 2-line column button — floating card style ─────────────────────── */
.rail-col-list { padding: 4px 8px 40px; }

.rail-col-btn {
  display: flex;
  flex-direction: column;
  width: 100%;
  padding: 10px 12px 10px 14px;
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  cursor: pointer;
  text-align: left;
  transition: background .12s, border-color .12s, box-shadow .12s;
  gap: 4px;
  margin-bottom: 4px;
  position: relative;
}

.rail-col-btn:hover {
  background: color-mix(in srgb, var(--accent) 6%, var(--card-bg));
  border-color: color-mix(in srgb, var(--accent) 30%, var(--border));
}

.rail-col-btn--active {
  background: linear-gradient(160deg, #16887c 0%, var(--accent) 55%, #0a4a43 100%) !important;
  border-color: #0a4a43 !important;
  box-shadow: 0 3px 10px -2px rgba(13, 92, 84, 0.45), inset 0 1px 0 rgba(255, 255, 255, 0.28) !important;
}

.rail-col-btn--active .rail-col-name,
.rail-col-btn--active .rail-col-type,
.rail-col-btn--active .rail-col-dtype {
  color: #fdfffe;
}

.rail-col-btn--active .rail-state-badge {
  background: rgba(255, 255, 255, 0.85) !important;
  border-color: transparent;
}

.rail-col-l1 {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  flex-wrap: nowrap;
  overflow: hidden;
}

/* Left cluster = what the database/source itself provides (name, PK/FK) —
   kept tight together, never stretched apart. Right cluster (DQ/state, see
   .rail-col-l1-right below) = what ADIRRA derives — pushed to the row's end via
   justify-content: space-between on the parent. */
.rail-col-l1-left {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  overflow: hidden;
}

.rail-col-l1-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
}

.rail-col-name {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 0 1 auto;
  min-width: 0;
}

.rail-state-badge {
  flex: 0 0 auto;
  font-size: 9px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: .05em;
  margin-left: auto;
}

.rail-state--draft    { background: color-mix(in srgb, var(--draft-col) 14%, transparent);      color: var(--draft-col); }
.rail-state--defined  { background: color-mix(in srgb, var(--draft-col) 14%, transparent);      color: var(--draft-col); }
.rail-state--empty    { background: color-mix(in srgb, var(--empty-col) 22%, transparent);      color: var(--empty-col); }
.rail-state--in_review { background: color-mix(in srgb, var(--in-review-col) 14%, transparent); color: var(--in-review-col); }
.rail-state--approved { background: color-mix(in srgb, var(--approved-col) 14%, transparent);  color: var(--approved-col); }
.rail-state--returned,
.rail-state--rejected,
.rail-state--withdrawn,
.rail-state--revoked  { background: color-mix(in srgb, var(--bounced-col) 14%, transparent);   color: var(--bounced-col); }

.rail-pii-badge {
  flex: 0 0 auto;
  font-size: 9px;
  font-weight: 800;
  padding: 2px 6px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: .06em;
  margin-left: 6px;
  background: #b3261e;
  color: #fff;
}

.rail-col-l2 {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 1px;
}

.rail-col-dtype {
  font-size: 10.5px;
  color: var(--text-2);
  flex: 0 0 auto;
}

.rail-col-type {
  font-size: 11px;
  color: var(--text-2);
  flex: 1;
  text-align: right;
}

.rail-key-badge {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 15px;
  height: 15px;
  border-radius: 50%;
  background: #0a3f39;
  font-size: 9px;
  line-height: 1;
  box-shadow: 0 1px 2px rgba(0,0,0,.3);
}

.rail-key-badge--candidate {
  background: #7c8fa6;
}

.rail-fk-badge {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 15px;
  height: 15px;
  border-radius: 50%;
  background: #16345c;
  font-size: 9px;
  line-height: 1;
  box-shadow: 0 1px 2px rgba(0,0,0,.3);
}

.rail-fk-badge--orphan {
  background: var(--danger-col);
}

.rail-empty-filter {
  padding: 16px;
  font-size: 12px;
  color: var(--text-2);
  text-align: center;
}

.rail-obs-warn {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 10px;
  font-weight: 600;
  color: var(--warn-col);
}

/* Dataset-level Columns table — Actions-to-improve count, between DQ and
   State (replaces the old Obs column). Same amber identity as the element-
   level "Actions to improve" pillar, and reads live off the column's own DQ
   badge, so it updates the moment that column is re-evaluated. */
.col-actions-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 10px;
  font-weight: 700;
  color: #caa33d;
}

/* Clickable variant — jumps straight to this column's DQ Insights → Actions
   to improve panel, so the count isn't just a static readout. */
.col-actions-link {
  background: none;
  border: none;
  padding: 0;
  font: inherit;
  cursor: pointer;
}

.col-actions-link:hover {
  text-decoration: underline;
}

.rail-empty {
  text-align: center;
  margin-top: 2rem;
  font-size: 12px;
  color: var(--text-2);
  padding: 12px;
}

/* ── xstrip ───────────────────────────────────────────────────────────── */
.xstrip {
  display: flex;
  align-items: center;
  padding: 5px 16px;
  background: var(--accent-light);
  border-bottom: 1px solid #b5d4cf;
  font-size: 12.5px;
  gap: 4px;
  min-height: 34px;
  color: var(--text);
}

.xstrip--blocking { background: #fdf0ee; border-bottom-color: #e8b8b1; }
.xstrip--loading { background: #f8f8f6; border-bottom-color: var(--border); }

.xstrip-label { font-weight: 700; color: var(--accent); }
.xstrip-sep { color: var(--text-2); }
.xstrip-body { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.xstrip-blocking { color: var(--danger-col); }

.xstrip-btn {
  flex: 0 0 auto;
  font-size: 11px;
  padding: 3px 10px;
  border: 1px solid var(--accent);
  border-radius: 6px;
  background: transparent;
  color: var(--accent);
  cursor: pointer;
  font-weight: 600;
}

.xstrip-btn:hover { background: var(--accent); color: #fff; }

/* ── Detail panel ─────────────────────────────────────────────────────── */
.detail {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  min-height: 0;
  background: radial-gradient(ellipse 110% 55% at 50% 0%, #b8d4ec 0%, #d4e6f2 28%, #e8f0f7 50%, #f6f3ec 75%);
}

.detail-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.detail-loading {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
}
.detail-loading-msg {
  font-size: 13.5px;
  color: var(--text-body, #3d3830);
}
.detail-loading-hint {
  font-size: 11.5px;
  color: #a09890;
}

/* ── Element header ───────────────────────────────────────────────────── */
.el-header {
  padding: 14px 20px 0;
  border-bottom: 1px solid var(--border);
  background: var(--card-bg);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  flex: 0 0 auto;
}

.el-title-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.el-header-right {
  margin-left: auto;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}
.el-lifecycle-cluster {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}
.el-lc-row {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 6px;
}
.el-codeset-status {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-2, #6b6862);
  white-space: nowrap;
}

.el-action-row {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 3px;
}

.el-name {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 19px;
  font-weight: 700;
  color: var(--text);
  letter-spacing: -.01em;
}

.el-state-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 5px;
  color: #fff;
  text-transform: capitalize;
  font-weight: 600;
}
/* Larger, right-aligned lifecycle badge (5b.3.2b #4) — pulled off the element name. */
.el-state-badge--lg {
  font-size: 12px;
  padding: 3px 11px;
  border-radius: 6px;
  letter-spacing: .01em;
}
/* Lifecycle badge lives on the biz row, pushed to the far right (5b.3.2 UX). */
.el-biz-status {
  margin-left: auto;
  flex: 0 0 auto;
}

/* Steward decision feedback banner (5b.3.2b #1) — slim, under the header. */
.steward-feedback {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12.5px;
  font-weight: 500;
  padding: 8px 12px;
  border-radius: 6px;
  margin-bottom: 12px;
}
.steward-feedback.sf--returned { background: #fef3c7; color: #92400e; border: 1px solid #fcd9a3; }
.steward-feedback.sf--rejected { background: #fee2e2; color: #991b1b; border: 1px solid #f6c2c2; }

.el-state--draft { background: var(--draft-col); }
.el-state--defined { background: var(--defined-col); }
.el-state--approved { background: var(--approved-col); }

/* Business Name subtitle row */
.el-biz-row {
  display: flex;
  align-items: center;
  gap: 5px;
  margin: 0 0 0;
  padding: 7px 0;
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  min-height: 22px;
}
.el-biz-name {
  font-size: 14.5px;
  font-weight: 700;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 340px;
}
.el-biz-ai-badge {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 9.5px;
  font-weight: 700;
  background: #f0e8ff;
  color: #6b46c1;
  border-radius: 3px;
  padding: 1px 4px;
  flex-shrink: 0;
}
.el-biz-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px 3px;
  border-radius: 3px;
  color: var(--text-2);
  opacity: 0.55;
  transition: opacity .15s, background .15s;
  flex-shrink: 0;
}
.el-biz-icon-btn:hover { opacity: 1; background: var(--border); }
.el-biz-icon-btn:disabled { opacity: 0.3; cursor: default; }
.el-biz-icon-btn--save { color: var(--approved-col); opacity: 0.9; }
.el-biz-icon-btn--ai { color: var(--ai-col); opacity: 0.85; }
.el-biz-icon-btn--ai:hover { opacity: 1; color: var(--ai-col); }
.el-biz-input {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  background: var(--paper);
  border: 1px solid var(--accent);
  border-radius: 4px;
  padding: 2px 8px;
  outline: none;
  min-width: 200px;
  max-width: 320px;
}

.el-grade-chip {
  font-size: 10px;
  font-weight: 800;
  padding: 2px 7px;
  border-radius: 5px;
  color: #fff;
}

.el-grade--a { background: var(--approved-col); }
.el-grade--b { background: var(--warn-col); }
.el-grade--c { background: var(--danger-col); }

/* ── Data Quality badge / card (U2b · DQ §14) ──────────────────────────── */
/* Grade-band colour intents (§7) — shared by chip, pill, band text, dots. */
.dq-band--positive-strong { color: var(--dq-excellent); }
.dq-band--positive { color: var(--dq-good); }
.dq-band--warning { color: var(--dq-adequate); }
.dq-band--warning-strong { color: var(--dq-weak); }
.dq-band--negative { color: var(--dq-critical); }
.dq-band--neutral { color: var(--text-2); }

/* Header chip: score + band. */
.el-dq-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 1px 8px 1px 3px;
  border: 1px solid var(--border);
  border-radius: 11px;
  background: var(--card-bg);
  font-size: 10.5px;
}
.el-pii-badge {
  display: inline-flex;
  align-items: center;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: .05em;
  padding: 2px 9px;
  border-radius: 11px;
  background: #b3261e;
  color: #fff;
  border: 1px solid #b3261e;
}
.el-dq-chip-score {
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  min-width: 20px;
  height: 16px;
  padding: 0 5px;
  border-radius: 8px;  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  background: currentColor;
}
.el-dq-chip-score { color: #fff; }
.el-dq-chip.dq-band--positive-strong .el-dq-chip-score { background: var(--dq-excellent); }
.el-dq-chip.dq-band--positive .el-dq-chip-score { background: var(--dq-good); }
.el-dq-chip.dq-band--warning .el-dq-chip-score { background: var(--dq-adequate); }
.el-dq-chip.dq-band--warning-strong .el-dq-chip-score { background: var(--dq-weak); }
.el-dq-chip.dq-band--negative .el-dq-chip-score { background: var(--dq-critical); }
.el-dq-chip.dq-band--neutral .el-dq-chip-score { background: var(--pending-col); }
.el-dq-chip-band { font-weight: 700; }

/* Score-change attention cue (left-rail badge only, per-column) — pulses twice with a
   bold scale + solid colour flip + glow ring, direction-coded (green = improved, amber =
   dropped), independent of the absolute grade-band colour underneath. */
@keyframes dq-score-pulse {
  0%, 100% { transform: scale(1); box-shadow: 0 0 0 0 transparent; }
  50% { transform: scale(1.55); box-shadow: 0 0 0 9px var(--dq-pulse-color, transparent); background-color: var(--dq-pulse-solid, inherit); }
}
.dq-score-pulse-up { --dq-pulse-color: rgba(35, 160, 85, 0.55); --dq-pulse-solid: #23a055; animation: dq-score-pulse 0.85s ease-in-out 2; position: relative; z-index: 2; }
.dq-score-pulse-down { --dq-pulse-color: rgba(214, 130, 20, 0.55); --dq-pulse-solid: #d68214; animation: dq-score-pulse 0.85s ease-in-out 2; position: relative; z-index: 2; }

/* Excluded-from-assessment states (U2c · decision D1). */
.el-dq-chip--excluded {
  color: var(--text-2);
  font-weight: 700;
  border-style: dashed;
  padding: 1px 9px;
}
.rail-dq--excluded {
  color: var(--text-2);
  background: transparent;
  border: 1px dashed var(--border);
  display: inline-flex;
  align-items: center;
  padding: 1px 4px;
}
.dq-card-empty--excluded { color: var(--text-2); font-style: normal; }

/* ── Assessment scoping panel (U2c · decision D1) ──────────────────────── */
.scoping-intro {
  font-size: 12.5px;
  color: var(--text-2);
  line-height: 1.55;
  margin-bottom: 12px;
}
.scoping-suggest-banner {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  padding: 8px 12px;
  margin-bottom: 12px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--warn-col) 12%, var(--card-bg));
  border: 1px solid color-mix(in srgb, var(--warn-col) 35%, transparent);
  color: var(--text-1);
}
.scoping-suggest-select {
  margin-left: auto;
  font-size: 11.5px;
  font-weight: 700;
  color: var(--accent);
  background: none;
  border: none;
  cursor: pointer;
  text-decoration: underline;
}
.scoping-bulk-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  margin-bottom: 12px;
  border-radius: 8px;
  background: var(--card-bg);
  border: 1px solid var(--border);
  flex-wrap: wrap;
}
.scoping-bulk-left { display: flex; align-items: center; gap: 8px; }
.scoping-sel-count { font-size: 12px; font-weight: 700; color: var(--text-1); }
.scoping-clear-btn {
  font-size: 11px;
  color: var(--text-2);
  background: none;
  border: none;
  cursor: pointer;
  text-decoration: underline;
}
.scoping-reason-input {
  flex: 1 1 240px;
  min-width: 180px;
  font-size: 12px;
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--input-bg, var(--card-bg));
  color: var(--text-1);
}
.scoping-bulk-actions { display: flex; gap: 8px; }
.scoping-btn {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  font-weight: 700;
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid var(--border);
  cursor: pointer;
  background: var(--card-bg);
  color: var(--text-1);
}
.scoping-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.scoping-btn--out { border-color: color-mix(in srgb, var(--danger-col) 45%, transparent); color: #b34527; }
.scoping-btn--in { border-color: color-mix(in srgb, var(--approved-col) 45%, transparent); color: var(--approved-col); }
.scoping-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.scoping-table thead th {
  text-align: left;
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-2);
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
}
.scoping-check-th { width: 28px; }
.scoping-row { border-bottom: 1px solid var(--border-soft, var(--border)); }
.scoping-row td { padding: 7px 8px; vertical-align: middle; }
.scoping-row--out { opacity: 0.55; background: color-mix(in srgb, var(--text-2) 5%, transparent); }
.scoping-name-cell { font-weight: 600; color: var(--text-1); }
.scoping-type-cell, .scoping-sem-cell { color: var(--text-2); }
.scoping-sugg-chip {
  display: inline-flex;
  align-items: center;
  font-size: 9.5px;
  font-weight: 700;
  padding: 1px 6px;
  margin-left: 6px;
  border-radius: 8px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.scoping-sugg-chip--accepted { background: color-mix(in srgb, var(--warn-col) 22%, var(--card-bg)); color: #a15b12; }
.scoping-sugg-chip--hint { background: color-mix(in srgb, var(--text-2) 14%, var(--card-bg)); color: var(--text-2); }
.scoping-excluded { font-size: 10.5px; font-weight: 700; color: var(--text-2); font-style: italic; }
.scoping-dq-none { color: var(--text-3, var(--text-2)); }
.scoping-scope-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 8px;
  border-radius: 8px;
}
.scoping-scope-badge--in { background: color-mix(in srgb, var(--approved-col) 16%, var(--card-bg)); color: var(--approved-col); }
.scoping-scope-badge--out { background: color-mix(in srgb, var(--text-2) 16%, var(--card-bg)); color: var(--text-2); }
.scoping-action-cell { text-align: right; }
.scoping-row-btn {
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--card-bg);
  color: var(--text-1);
  cursor: pointer;
}
.scoping-row-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.scoping-row-btn--suggest { border-color: color-mix(in srgb, var(--warn-col) 45%, transparent); color: #a15b12; }
.scoping-row-btn--restore { border-color: color-mix(in srgb, var(--approved-col) 45%, transparent); color: var(--approved-col); }

/* Rail score badge — grade-coloured pill, white score, consistent with the
   element card's DQ bands (U4b-fix-2 Task 4). The band class sets the pill
   BACKGROUND; the text stays white. (Previously `background: currentColor`
   plus trailing `color:#fff` overrides collapsed to white-on-white — an empty
   square where the retired A/B/C grade badge used to sit.) */
.rail-dq {
  font-size: 10px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  padding: 1px 6px;
  border-radius: 5px;
  color: #fff;
  background: var(--pending-col);
}
.rail-dq.dq-band--positive-strong { background: var(--dq-excellent); }
.rail-dq.dq-band--positive { background: var(--dq-good); }
.rail-dq.dq-band--warning { background: var(--dq-adequate); }
.rail-dq.dq-band--warning-strong { background: var(--dq-weak); }
.rail-dq.dq-band--negative { background: var(--dq-critical); }
.rail-dq.dq-band--neutral { background: var(--pending-col); }

/* Component colour roles (donut arc + legend dot + component-tab accent).
   Read the single-source palette tokens (U2d, tokens.scss) so a token change
   re-colours the donut segment and its tab accent together. */
.dq-arc--profile { color: var(--dq-profile); }
.dq-arc--interpretation { color: var(--dq-interpretation); }
.dq-arc--refdata { color: var(--dq-refdata); }
.dq-arc--other { color: var(--pending-col); }
/* Dataset roll-up arcs (U4a · §15.4) — reuse the profile/interpretation palette
   roles (column roll-up = blue, integrity = brown) so a token re-skin flows
   through to the dataset donut too. */
.dq-arc--rollup { color: var(--dq-profile); }
.dq-arc--integrity { color: var(--dq-interpretation); }

/* Dataset Quality card (U4a) — header row, trend sparkline, contribution rows. */
.ds-dq-card { padding: 14px 16px; }
.ds-dq-title-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}
.ds-dq-trend-delta { font-weight: 800; font-variant-numeric: tabular-nums; }
.ds-dq-contrib {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  padding: 3px 0;
}
.ds-dq-contrib-name { flex: 1 1 auto; color: var(--text); min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.ds-dq-contrib-link {
  display: inline-flex;
  align-items: center;
  border: none;
  background: none;
  padding: 0;
  font: inherit;
  text-align: left;
  cursor: pointer;
  color: var(--accent);
}
.ds-dq-contrib-link:hover,
.ds-dq-contrib-link:focus-visible {
  text-decoration: underline;
}
.ds-dq-contrib-grade {
  font-weight: 700;
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 8px;
  background: var(--accent-light);
  flex-shrink: 0;
}
.ds-dq-contrib-grade.dq-band--positive-strong { background: var(--dq-excellent); color: #fff; }
.ds-dq-contrib-grade.dq-band--positive { background: var(--dq-good); color: #fff; }
.ds-dq-contrib-grade.dq-band--warning { background: var(--dq-adequate); color: #fff; }
.ds-dq-contrib-grade.dq-band--warning-strong { background: var(--dq-weak); color: #fff; }
.ds-dq-contrib-grade.dq-band--negative { background: var(--dq-critical); color: #fff; }
.ds-dq-contrib-grade.dq-band--neutral { background: var(--accent-light); color: var(--text-2); }
.ds-dq-contrib-actions {
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  font-weight: 600;
  color: #caa33d;
  flex-shrink: 0;
  min-width: 62px;
}
.ds-dq-contrib-actions--none { color: var(--text-2); font-weight: 400; }
.ds-dq-contrib-empty { font-size: 12px; color: var(--text-2); padding: 3px 0; }

/* Card layout. */
.dq-card { padding: 14px 16px; }
.dq-card-main { display: flex; gap: 18px; align-items: center; }
.dq-donut-wrap { flex: 0 0 auto; }
.dq-donut { width: 110px; height: 110px; }
.dq-arc-track { stroke: currentColor; stroke-width: 9; opacity: 0.18; stroke-linecap: butt; }
.dq-arc-fill { stroke: currentColor; stroke-width: 9; stroke-linecap: round; }
.dq-donut-score { font-size: 23px; font-weight: 800; fill: var(--text); font-variant-numeric: tabular-nums; }
.dq-donut-grade-pill.dq-band--positive-strong { fill: var(--dq-excellent); }
.dq-donut-grade-pill.dq-band--positive { fill: var(--dq-good); }
.dq-donut-grade-pill.dq-band--warning { fill: var(--dq-adequate); }
.dq-donut-grade-pill.dq-band--warning-strong { fill: var(--dq-weak); }
.dq-donut-grade-pill.dq-band--negative { fill: var(--dq-critical); }
.dq-donut-grade-pill.dq-band--neutral { fill: var(--text-2); }
.dq-donut-band { fill: #fff; font-size: 11.5px; font-weight: 800; text-transform: none; }

.dq-legend { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.dq-legend-head { display: flex; align-items: center; gap: 10px; margin-bottom: 4px; flex-wrap: wrap; }
.dq-legend-head--actions { justify-content: flex-end; }
.dq-legend-head--actions .dq-refresh-btn { margin-left: 0; }
.dq-band-pill {
  font-size: 13px;
  font-weight: 800;
  padding: 2px 10px;
  border-radius: 10px;
  background: var(--accent-light);
  color: currentColor;
}
/* Polish Batch Task 5 — the pill carries the grade-band colour as its
   background (white text for contrast), consistent with the rail/chip badges
   elsewhere on the card. */
.dq-band-pill.dq-band--positive-strong { background: var(--dq-excellent); color: #fff; }
.dq-band-pill.dq-band--positive { background: var(--dq-good); color: #fff; }
.dq-band-pill.dq-band--warning { background: var(--dq-adequate); color: #fff; }
.dq-band-pill.dq-band--warning-strong { background: var(--dq-weak); color: #fff; }
.dq-band-pill.dq-band--negative { background: var(--dq-critical); color: #fff; }
.dq-band-pill.dq-band--neutral { background: var(--accent-light); color: var(--text-2); }
/* Task 6 — field-level re-evaluate affordance, mirrors the "Refresh Profile" button. */
.dq-refresh-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
  background: none;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 3px 8px;
  cursor: pointer;
}
.dq-refresh-btn:disabled { opacity: 0.55; cursor: not-allowed; }
.dq-refresh-btn--inline { margin-left: 10px; }
.dq-refresh-spin { animation: dq-refresh-spin-anim 0.9s linear infinite; }
@keyframes dq-refresh-spin-anim { to { transform: rotate(360deg); } }
/* Task 2 — tighten the label·score pairing: the label no longer flex-grows to
   push the score to the far right; the grade pill (when present) is what
   hugs the right edge instead. */
.dq-legend-row { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.dq-dot { width: 9px; height: 9px; border-radius: 50%; background: currentColor; flex: 0 0 auto; }
.dq-legend-label { color: var(--text); }
.dq-legend-val { color: var(--text-2); font-size: 11px; font-weight: 700; }
.dq-legend-band { font-size: 10px; font-weight: 700; margin-left: auto; }
.dq-actual-score-row { display: flex; align-items: center; gap: 8px; margin-top: 3px; padding-top: 7px; }
.dq-actual-score-label { color: var(--text-2); font-size: 11px; font-weight: 700; }
.dq-actual-score-rule { height: 1px; flex: 1 1 auto; background: var(--border); }
.dq-actual-score-row .dq-band-pill { font-size: 12px; }
/* N/A row (§7 follow-up) — deliberately muted/greyed, distinct from an
   active, coloured component row, so it reads as "not applicable" rather
   than "another scored dimension". */
.dq-legend-row--na { opacity: 0.6; }
.dq-dot--na { background: var(--text-2) !important; }
.dq-legend-row--na .dq-legend-val { font-style: italic; }

.dq-breakdown { margin-top: 12px; border-top: 1px solid var(--border); padding-top: 10px; display: flex; flex-direction: column; gap: 10px; }

/* Plain-English "how it's calculated" line above the always-visible
   contribution breakdown (no expand/collapse toggle anymore). */
.ds-dq-explainer {
  margin-top: 10px;
  font-size: 11px;
  line-height: 1.45;
  color: var(--text-2);
}

/* Data·Governance·Actions group headers (grouped breakdown): glass-panelled,
   a light gradient blending white with each group's own accent colour (one
   shade lighter than a solid fill), each independently collapsible. Profile
   is the sole Data component; Definition / Reference Data / Semantic Type
   roll into Governance — mirrors the backend's data_score/governance_score
   split. Actions to improve is styled the same way as a third group. */
.dq-group { border-radius: 10px; overflow: hidden; border: 1px solid var(--border); }
.dq-group-head {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  font: inherit;
  color: var(--text);
  cursor: pointer;
  border: none;
  border-left: 3px solid transparent;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.6), inset 0 -1px 0 rgba(0, 0, 0, 0.05);
}
.dq-group-head--data {
  border-left-color: var(--dq-profile);
  background: linear-gradient(135deg, #ffffff 0%, color-mix(in srgb, var(--dq-profile) 32%, white) 100%);
}
.dq-group-head--governance {
  border-left-color: var(--dq-interpretation);
  background: linear-gradient(135deg, #ffffff 0%, color-mix(in srgb, var(--dq-interpretation) 32%, white) 100%);
}
.dq-group-head--actions {
  border-left-color: #caa33d;
  background: linear-gradient(135deg, #ffffff 0%, color-mix(in srgb, #caa33d 32%, white) 100%);
}
.dq-group-title { font-weight: 800; font-size: 12.5px; letter-spacing: 0.02em; color: var(--text); }
.dq-group-points { margin-left: auto; font-size: 12px; font-weight: 800; color: var(--text); font-variant-numeric: tabular-nums; }
.dq-group-body { padding: 10px 12px 2px; display: flex; flex-direction: column; gap: 12px; }

.dq-comp-block { display: flex; flex-direction: column; gap: 5px; }
.dq-comp-head { display: flex; align-items: center; gap: 7px; }
.dq-comp-title { font-weight: 700; font-size: 12px; color: var(--text); }
.dq-comp-score { margin-left: auto; font-size: 11px; font-weight: 700; color: var(--text-2); }
.dq-li { padding: 4px 0 4px 16px; border-left: 2px solid var(--border); }
.dq-li-top { display: flex; align-items: baseline; gap: 8px; }
.dq-li-label { font-size: 12px; color: var(--text); }
.dq-li-val { margin-left: auto; font-size: 11px; color: var(--text-2); }
.dq-li-formula { font-size: 10.5px; color: var(--text-2); margin-top: 2px; }
.dq-li-note { font-size: 11px; color: var(--text); margin-top: 3px; line-height: 1.4; }
.dq-card-empty { display: flex; align-items: center; font-size: 12px; color: var(--text-2); }

/* Last-evaluated timestamp — when this column's DQ score was last computed. */
.dq-scored-at {
  display: flex;
  align-items: center;
  font-size: 10.5px;
  color: var(--text-2);
  margin-top: 3px;
}

/* Grade-band legend: plain text ranges with the grade name in its band colour. */
.dq-grade-legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
  font-size: 11px;
}
.dq-grade-legend-item { display: inline-flex; align-items: center; gap: 4px; }
.dq-grade-legend-range { color: var(--text-2); }
.dq-grade-legend-label { font-weight: 700; }
.dq-grade-legend-sep { color: var(--border); }

/* Inline variant for compact header and footer placement. */
.dq-grade-legend--inline {
  margin-top: 0;
  padding-top: 0;
  border-top: none;
  gap: 8px;
}

/* U4b — reallocation explanation (legibility #4). */
.dq-realloc {
  font-size: 11px;
  color: var(--text-2);
  line-height: 1.45;
  margin-bottom: 2px;
}

/* U4b — data·governance pillar % beside a component block header (legibility #1). */
.dq-pillar {
  font-size: 9.5px;
  font-weight: 800;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  padding: 1px 6px;
  border-radius: 8px;
  font-variant-numeric: tabular-nums;
}
.dq-pillar--data { color: #fff; background: var(--dq-profile); }
.dq-pillar--governance { color: #fff; background: var(--dq-interpretation); }
.dq-pillar--actions { color: #fff; background: #caa33d; }

/* U4b — remediation action slab (§17). */
.dq-path {
  display: flex;
  align-items: center;
  font-size: 11.5px;
  color: var(--text);
  background: var(--accent-light);
  border-radius: 8px;
  padding: 6px 10px;
  line-height: 1.4;
}
.dq-path b { font-variant-numeric: tabular-nums; }
.dq-path--top { color: var(--approved-col); }
.dq-action-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.dq-action {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 5px 8px;
  border-radius: 7px;
  border: 1px solid var(--border);
}
.dq-action--in-path { border-color: var(--accent); background: var(--accent-light); }
.dq-action-points {
  flex: 0 0 auto;
  font-weight: 800;
  font-size: 12px;
  color: var(--approved-col);
  font-variant-numeric: tabular-nums;
  min-width: 38px;
}
.dq-action-body { display: flex; flex: 1 1 auto; flex-direction: column; gap: 2px; min-width: 0; }
.dq-action-caption { font-size: 12px; font-weight: 700; color: var(--text); line-height: 1.35; }
.dq-action-step { font-size: 12px; color: var(--text-2); line-height: 1.4; }
.dq-action-dest {
  font-size: 11px;
  color: var(--approved-col);
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 3px;
}
.dq-action-dest b { font-variant-numeric: tabular-nums; }
.dq-action-why {
  font-size: 11px;
  color: var(--text-2);
  line-height: 1.4;
  display: flex;
  align-items: flex-start;
}
.dq-action-meta { font-size: 10.5px; color: var(--text-2); }
.dq-action-type {
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  font-size: 9.5px;
  padding: 0 5px;
  border-radius: 6px;
}
.dq-action-type--governance { color: var(--dq-interpretation); background: var(--accent-light); }
.dq-action-type--data { color: var(--warn-col); background: var(--accent-light); }


.el-action-btn {
  display: flex;
  align-items: center;
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid var(--border);
  cursor: pointer;
  font-weight: 600;
  transition: background .12s;
}

.el-action-btn--blue { background: #eaf1fb; border-color: #b0c8e8; color: var(--defined-col); }
.el-action-btn--blue:hover { background: var(--defined-col); color: #fff; }
.el-action-btn--green { background: #eaf4ec; border-color: #aed6b3; color: var(--approved-col); }
.el-action-btn--green:hover { background: var(--approved-col); color: #fff; }
.el-action-btn--ghost { background: transparent; color: var(--text-2); }
.el-action-btn--ghost:hover { background: var(--paper); }

.el-desc {
  font-size: 13px;
  color: var(--text-2);
  margin-bottom: 6px;
  line-height: 1.4;
}
.el-meta-item {
  display: flex;
  align-items: baseline;
  gap: 5px;
}
.el-meta-sep {
  width: 1px;
  height: 12px;
  background: var(--border);
  margin: 0 14px;
  flex-shrink: 0;
}
.el-meta-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-2);
  text-transform: uppercase;
  letter-spacing: .04em;
  white-space: nowrap;
}
.el-meta-value {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
}
.el-meta-value--linked { color: var(--accent); }
.el-meta-value--empty { color: #a09890; font-weight: 400; font-style: italic; }

/* ── Semantic type panel ──────────────────────────────────────────────── */
.sem-panel { display: flex; align-items: flex-start; gap: 14px; }
.sem-icon { flex-shrink: 0; margin-top: 2px; }
.sem-body { flex: 1; }
.sem-name { font-size: 13.5px; font-weight: 700; color: var(--text); margin-bottom: 4px; }
.sem-desc { font-size: 12px; color: var(--text-2); line-height: 1.5; }

/* ── Profile data-quality facts ───────────────────────────────────────── */
.dq-facts { display: flex; flex-direction: column; gap: 7px; }
.dq-fact { display: flex; align-items: flex-start; gap: 8px; font-size: 12px; line-height: 1.45; color: var(--text); }
.dq-fact-ic { flex-shrink: 0; margin-top: 1px; }
.dq-fact-text { flex: 1; }
.dq-fact--good .dq-fact-ic { color: #0d7a5f; }
.dq-fact--neutral .dq-fact-ic { color: #86827a; }
.dq-fact--warn .dq-fact-ic { color: #b8860b; }
.dq-fact--bad .dq-fact-ic { color: #b3261e; }
.dq-sem-status { display: flex; align-items: center; gap: 4px; margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border); font-size: 11.5px; font-weight: 600; }
.dq-ss-ok { color: #0d7a5f; }
.dq-ss-rej { color: #b3261e; }
.dq-ss-pending { color: #86827a; }
.dq-sem-link { margin-left: auto; background: none; border: none; color: var(--accent); font-size: 11.5px; font-weight: 600; cursor: pointer; padding: 0; }
.dq-sem-link:hover { text-decoration: underline; }

.sem-dist-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }

/* ── Characteristics + Sample grid ───────────────────────────────────── */
.char-samp-grid { display: grid; grid-template-columns: 1.1fr 0.9fr; gap: 14px; }
.char-kv { display: grid; grid-template-columns: auto 1fr; gap: 5px 14px; align-items: baseline; }
.char-k { font-size: 11.5px; color: var(--text-2); }
.char-v { font-size: 12px; color: var(--text); }
.char-profile-badge { display: inline-block; background: #dbeafe; color: #1e40af; font-size: 11.5px; font-weight: 600; padding: 1px 8px; border-radius: 4px; }
.samp-table { width: 100%; border-collapse: collapse; }
.samp-table td { padding: 3px 6px; font-size: 12px; border-bottom: 1px solid var(--border); }
.samp-n { color: var(--text-2); font-size: 11px; width: 22px; }
.samp-v { color: var(--text); word-break: break-all; }
.profile-note { font-size: 11px; color: #a09890; font-style: italic; margin-top: 8px; line-height: 1.5; }

/* ── Profile header with timestamp and refresh button ───────────────────── */
.profile-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--paper);
  border: 1px solid var(--border);
  border-radius: 8px;
}

.profile-timestamp {
  display: flex;
  align-items: center;
  font-size: 12px;
  color: var(--text-2);
}

/* ── Pipeline ─────────────────────────────────────────────────────────── */
.pipeline-strip { display: flex; align-items: center; }

.pipeline-strip-inline { display: flex; align-items: center; gap: 18px; margin-left: 24px; white-space: nowrap; }

.pipeline-step { display: flex; align-items: center; gap: 4px; flex: 0 0 auto; }

.ps-dot {
  width: 18px; height: 18px;
  border-radius: 50%;
  background: var(--pending-col);
  display: flex; align-items: center; justify-content: center;
  font-size: 9px; font-weight: 700;
  color: #fff;
}

.ps--draft.ps--done .ps-dot { background: var(--draft-col); color: #fff; }
.ps--defined.ps--done .ps-dot { background: var(--defined-col); color: #fff; }
.ps--done .ps-dot { background: var(--approved-col); color: #fff; }
.ps--active .ps-dot { background: var(--defined-col); color: #fff; }
.ps--pending .ps-dot { background: var(--pending-col); color: var(--text-2); }

.ps-label { font-size: 11px; color: var(--pending-col); white-space: nowrap; }
.ps--draft.ps--done .ps-label { color: var(--draft-col); font-weight: 600; }
.ps--defined.ps--done .ps-label { color: var(--defined-col); font-weight: 600; }
.ps--done .ps-label { color: var(--approved-col); font-weight: 600; }
.ps--active .ps-label { color: var(--defined-col); font-weight: 600; }
.ps--pending .ps-label { color: var(--pending-col); font-weight: 600; }

.ps-connector { width: 28px; height: 2px; background: var(--pending-col); margin: 0 4px; }
.ps-connector--done { background: var(--approved-col); }

/* ── Custom tab bar ───────────────────────────────────────────────────── */
.tab-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  margin-left: -2px;
  border-bottom: none;
}

.tab-bar-status {
  margin-left: auto;
  font-size: 11.5px;
  color: var(--text-2, #86827a);
  white-space: nowrap;
}

.tab-btn {
  font-size: 12.5px;
  padding: 7px 14px;
  border: 1px solid rgba(13, 92, 84, 0.14);
  border-radius: 9px;
  background: linear-gradient(180deg, rgba(13, 92, 84, 0.09), rgba(13, 92, 84, 0.035));
  color: var(--text);
  cursor: pointer;
  font-weight: 600;
  position: relative;
  display: flex;
  align-items: center;
  gap: 5px;
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  transition: color .15s, background .15s, border-color .15s, box-shadow .15s;
}

.tab-btn:not(.tab-btn--active):hover {
  color: var(--text);
  background: linear-gradient(180deg, rgba(13, 92, 84, 0.09), rgba(13, 92, 84, 0.035));
  border-color: #1c1b18;
}

.tab-btn--active {
  color: #fdfffe;
  background: linear-gradient(160deg, #16887c 0%, var(--accent) 55%, #0a4a43 100%);
  border-color: #0a4a43;
  font-weight: 700;
  box-shadow: 0 3px 10px -2px rgba(13, 92, 84, 0.45), inset 0 1px 0 rgba(255, 255, 255, 0.28);
}

.tab-btn--active:hover {
  color: #fdfffe;
  background: linear-gradient(160deg, #16887c 0%, var(--accent) 55%, #0a4a43 100%);
  border-color: #0a4a43;
}

.tab-btn--disabled {
  opacity: .45;
  cursor: not-allowed;
}

/* U2d — component-tab identity accent: a small colour dot on the label; the
   active underline + text colour are set inline from the --dq-* token so the
   tab and its donut segment always share one source of colour. Text stays
   legible (an accent, not a background fill). */
.tab-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex: 0 0 auto;
  display: inline-block;
}

/* Task 8(a) — small marker on the tab header when any DQ component is
   Critical, visible without opening the tab. */
.tab-critical-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--danger-col);
  flex: 0 0 auto;
  display: inline-block;
}

.tab-badge {
  font-size: 9px;
  padding: 1px 4px;
  border-radius: 4px;
  background: #e0e0e0;
  color: #555;
  font-weight: 700;
}

.tab-badge--danger { background: #fde8e6; color: var(--danger-col); }
.tab-badge--warn { background: #fdf3e6; color: var(--warn-col); }
.tab-badge--ok { background: var(--accent-light); color: var(--accent); }

.el-body {
  padding-bottom: 24px;
}

.tab-panel { /* each tab's content div */ }

/* ── Stat cards with meter bars ───────────────────────────────────────── */
.stat-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}

.stat-card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 14px 10px;
  text-align: center;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}

.stat-card-val {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 17px;
  font-weight: 700;
  color: var(--text);
}

.stat-card-lbl {
  font-size: 9.5px;
  text-transform: uppercase;
  letter-spacing: .08em;
  color: var(--text-2);
  margin-top: 2px;
  margin-bottom: 6px;
}

.stat-meter {
  height: 4px;
  border-radius: 2px;
  background: var(--border);
  overflow: hidden;
}

.stat-meter-fill {
  height: 100%;
  border-radius: 2px;
  transition: width .3s;
}

.stat-meter-fill--green { background: var(--approved-col); }
.stat-meter-fill--amber { background: var(--warn-col); }
.stat-meter-fill--red { background: var(--danger-col); }
.stat-meter-fill--neutral { background: var(--accent); opacity: .4; }

/* color helpers */
.color-green { color: var(--approved-col) !important; }
.color-amber { color: var(--warn-col) !important; }
.color-red { color: var(--danger-col) !important; }

/* ── Distribution histogram ───────────────────────────────────────────── */
.dist-histogram {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  height: 72px;
  padding: 0 4px 0;
}

.dist-bar-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
  height: 100%;
}

.dist-bar-track {
  flex: 1;
  width: 100%;
  display: flex;
  align-items: flex-end;
}

.dist-bar-fill {
  width: 100%;
  border-radius: 3px 3px 0 0;
  background: linear-gradient(to top, var(--accent), #56a89c);
  min-height: 2px;
  transition: height .3s;
}

.dist-bar-label {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 9px;
  color: var(--text-2);
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  width: 100%;
  margin-top: 3px;
}

.dist-mode-btns { display: flex; gap: 4px; }
.dist-mode-btn {
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-2);
  cursor: pointer;
  font-weight: 500;
  transition: background .15s, color .15s;
}
.dist-mode-btn:hover { background: var(--bg-hover); color: var(--text); }
.dist-mode-btn--active { background: var(--accent); color: #fff; border-color: var(--accent); }

/* ── Panel cards ──────────────────────────────────────────────────────── */
.panel-card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}

/* Consistent section-header bar for the Interpretation decision blocks
   (Definition, Business Name, Glossary, Definition Status, Semantic Type).
   Palette B: soft accent-green gradient + accent left edge. */
.block-card {
  padding: 0;
  overflow: hidden;
}
.block-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  height: 30px;
  padding: 0 14px;
  background: linear-gradient(90deg, #0d5c5433, #0d5c5414);
  border-left: 3px solid var(--accent, #0d5c54);
  border-bottom: 1px solid var(--border);
}
/* Status block (formerly "Definition Status") — distinct, darker blue
   gradient so it doesn't visually blend with the surrounding teal-accented
   blocks. Uses a solid deep-blue hex (not the muted --info-col) so alpha
   blending over the white card reads as blue, not washed-out gray. */
.def-wf-bar {
  background: linear-gradient(90deg, #1d4e8955, #1d4e891f);
  border-left-color: #1d4e89;
}
/* Keep every bar the same height: compact whatever action controls sit in it
   so a button never makes one bar taller than the plain (chip-only) ones. */
.block-bar .icon-btn { width: 22px; height: 22px; }
.block-bar .st-btn { padding: 2px 10px; font-size: 12px; }
.block-bar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}
.block-bar-title {
  font-size: 13px;
  font-weight: 700;
  letter-spacing: .01em;
  color: var(--text);
}
.block-bar-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 10px;
  font-weight: 600;
  padding: 1px 7px;
  border-radius: 4px;
  background: #f3f0fc;
  color: #8b5cf6;
  white-space: nowrap;
}
.block-bar-time {
  font-size: 10.5px;
  color: var(--text-2);
  white-space: nowrap;
}
.block-bar-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

/* Business-name review-state chip (shown in the Business Name block bar) */
.bn-state {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: .05em;
}
.bn-state--approved { background: var(--accent-light); color: var(--accent); }
.bn-state--pending  { background: #e8f0fb; color: #2f5d8a; }
.bn-state--draft    { background: #fdf3e6; color: var(--draft-col); }
.bn-state--none     { background: var(--border); color: var(--text-2); }

.panel-card-title {
  font-size: 12.5px;
  font-weight: 700;
  color: var(--text);
}

.panel-empty {
  font-size: 12px;
  color: var(--text-2);
  display: flex;
  align-items: center;
}

.panel-empty-ok {
  display: flex;
  align-items: center;
  font-size: 13px;
  color: var(--approved-col);
  background: #edf7ef;
  border-color: #b8dfc0;
}

/* ── Sample chips ─────────────────────────────────────────────────────── */
.sample-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.sample-chip {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11px;
  padding: 2px 8px;
  border: 1px solid var(--border);
  border-radius: 5px;
  background: var(--paper);
  color: var(--text);
}

/* ── Finding cards ────────────────────────────────────────────────────── */
.finding-card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px 8px;
  border-left-width: 4px;
  border-left-style: solid;
}

.finding-card--high { border-left-color: var(--danger-col); }
.finding-card--attention { border-left-color: var(--warn-col); }
.finding-card--info { border-left-color: var(--info-col); }

.finding-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 4px;
}

.finding-sev-badge {
  font-size: 9px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 4px;
  text-transform: uppercase;
  color: #fff;
}

.fsev--high { background: var(--danger-col); }
.fsev--attention { background: var(--warn-col); }
.fsev--info { background: var(--info-col); }

.finding-prov-badge {
  font-size: 9px;
  padding: 1px 6px;
  border-radius: 4px;
  border: 1px solid currentColor;
  display: flex;
  align-items: center;
}

.fprov--ai { color: var(--ai-col); }
.fprov--rule { color: var(--text-2); }

.finding-dim-badge { display: inline-flex; align-items: center; padding: 1px 7px; border-radius: 9px; font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; background: #eef0f2; color: #555; }
.fdim--completeness { background: #e6f0fb; color: #1e5a9c; }
.fdim--validity { background: #fdeeea; color: #b3492a; }
.fdim--uniqueness { background: #eaf3ec; color: #2e6b3e; }
.fdim--consistency { background: #f3eefb; color: #6b3ea8; }
.fdim--regulatory { background: #fbf3e2; color: #92651a; }
.fdim--metadata { background: #eef0f2; color: #555; }

.finding-title { font-size: 13px; font-weight: 600; color: var(--text); flex: 1; }

.finding-rationale {
  font-size: 12px;
  color: var(--text-2);
  line-height: 1.45;
}

.finding-regnote {
  display: flex;
  align-items: flex-start;
  font-size: 11.5px;
  color: var(--danger-col);
  margin-top: 4px;
}

.finding-evidence {
  margin-top: 6px;
}

.finding-evidence-toggle {
  font-size: 11px;
  color: var(--accent);
  cursor: pointer;
  list-style: none;
}

.finding-evidence-body {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10.5px;
  background: var(--paper);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 6px 8px;
  margin-top: 4px;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--text);
}

/* ── Definition tab ───────────────────────────────────────────────────── */
.desc-input :deep(.q-field__control) { font-size: 13px; }

.desc-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  display: flex;
  align-items: center;
  font-size: 12px;
  font-weight: 600;
  padding: 5px 12px;
  border-radius: 6px;
  border: 1px solid var(--border);
  cursor: pointer;
  transition: background .12s, opacity .12s;
}

.action-btn:disabled { opacity: .45; cursor: default; }

.action-btn--primary { background: var(--accent); color: #fff; border-color: var(--accent); }
.action-btn--primary:not(:disabled):hover { background: #0a4d46; }
.action-btn--confirm { background: var(--released-col, #2f6b3a); color: #fff; border-color: var(--released-col, #2f6b3a); }
.action-btn--confirm:not(:disabled):hover { background: #244f2c; }
.action-btn--ai { background: #f3f0fc; color: var(--ai-col); border-color: #c4b5fd; }
.action-btn--ai:not(:disabled):hover { background: var(--ai-col); color: #fff; }
.action-btn--secondary { background: #f5f3f0; color: var(--text); border-color: var(--border); }
.action-btn--secondary:not(:disabled):hover { background: #ede8e0; }

/* Description read-only view */
.desc-view {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.desc-content {
  flex: 1;
}

.desc-text {
  font-size: 13px;
  line-height: 1.5;
  color: var(--text);
  white-space: pre-wrap;
  word-break: break-word;
}

.desc-empty {
  font-size: 13px;
  color: var(--text-2);
  font-style: italic;
}

.desc-icons {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: #f5f3f0;
  color: var(--text-2);
  cursor: pointer;
  transition: background .12s, color .12s;
}

.icon-btn:hover {
  background: var(--accent);
  color: #fff;
}

.desc-ai-badge {
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  background: #f3f0fc;
  color: #8b5cf6;
  font-weight: 600;
}

.desc-meta {
  font-size: 11px;
  color: #a09890;
  margin-top: 4px;
}

/* Steward approval note */
.steward-note {
  font-size: 11px;
  color: var(--text-2);
  font-style: italic;
  margin-top: 4px;
}

.gterm-desc { font-size: 13px; color: var(--text-2); margin-bottom: 6px; }

/* ── Mapping Type tab ─────────────────────────────────────────────────── */
.sem-type-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.sem-type-id {
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
}

.sem-type-conflict {
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  color: var(--danger-col);
  font-weight: 600;
}

.sem-type-meta-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  font-size: 12.5px;
}

.sem-type-meta-label {
  color: var(--text-2);
  font-weight: 600;
}

.sem-type-meta-val {
  color: var(--text);
  font-weight: 500;
}

.sem-type-mismatch {
  display: inline-flex;
  align-items: center;
  font-size: 11.5px;
  color: var(--warn-col);
}

.sem-type-disposition {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  color: var(--text-2);
}

.sem-candidate-row {
  display: flex;
  align-items: center;
  padding: 4px 0;
  border-bottom: 1px solid var(--border);
}

.sem-candidate-row:last-child { border-bottom: none; }
.sem-candidate-id { font-size: 13px; font-weight: 600; color: var(--text); }

.sem-evidence-row {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  padding: 4px 0;
  font-size: 12.5px;
  border-bottom: 1px solid var(--border);
}

.sem-evidence-row:last-child { border-bottom: none; }
.sem-evidence-type { font-weight: 600; color: var(--text); }
.sem-evidence-detail { line-height: 1.4; }

/* ── Mapping Type tab ─────────────────────────────────────────────────── */
.semtype-panel { display: flex; flex-direction: column; gap: 14px; }
.semtype-panel .st-card { padding: 0; overflow: hidden; }
.st-ph { display: flex; align-items: center; gap: 9px; padding: 12px 15px; border-bottom: 1px solid var(--border); flex-wrap: wrap; }
.st-ph h3 { font-size: 13.5px; font-weight: 700; color: var(--text); margin: 0; }
.st-ph-left { display: flex; align-items: center; gap: 7px; flex: 1; min-width: 0; }
.st-section-n { width: 22px; height: 22px; border-radius: 50%; background: var(--accent); color: #fff; font-size: 11px; font-weight: 700; display: flex; align-items: center; justify-content: center; flex: 0 0 auto; }
.st-section-q { font-size: 11.5px; color: var(--text-2); font-style: italic; }
.st-lbl { margin-left: auto; font-size: 10px; letter-spacing: .08em; text-transform: uppercase; color: var(--text-2); font-weight: 700; }
.st-pc { padding: 14px 15px; }
.st-muted { font-size: 12.5px; color: var(--text-2); line-height: 1.5; }

/* Confidence phrase */
.st-phrase { font-size: 11.5px; font-weight: 700; padding: 3px 10px; border-radius: 20px; margin-left: auto; flex: 0 0 auto; }
.phrase--ok { color: var(--approved-col); background: #2f6b3a14; }
.phrase--warn { color: var(--warn-col); background: #a9651b14; }
.phrase--neutral { color: var(--info-col); background: #2f5d8a14; }
.phrase--na { color: var(--text-2); background: #0000000a; }
.st-phrase--entity { }

/* Hierarchy: Role → Type → Scope */
.st-hier { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 11px; }
.st-hier-item { display: flex; flex-direction: column; gap: 1px; }
.st-hier-l { font-size: 9.5px; letter-spacing: .09em; text-transform: uppercase; color: var(--text-2); font-weight: 700; }
.st-hier-v { font-size: 13.5px; font-weight: 700; color: var(--text); }
.st-hier-v.mono { font-family: 'IBM Plex Mono', monospace; }
.st-hier-arr { font-size: 18px; color: var(--text-2); line-height: 1; margin-top: 8px; }
.st-hier-facet { font-size: 10px; font-weight: 700; padding: 3px 8px; border-radius: 6px; margin-top: 6px; align-self: flex-end; }
.st-axes { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 10px 0; }
.st-axis { display: flex; flex-direction: column; gap: 2px; padding: 9px 11px; border-radius: 7px; border: 1px solid var(--border); border-left-width: 3px; background: #00000004; }
.st-axis-k { font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-2); font-weight: 700; }
.st-axis-v { font-size: 13px; font-weight: 700; color: var(--text); }
.st-axis-d { font-size: 11px; color: var(--text-2); line-height: 1.4; }
.st-axis--good { border-left-color: #0d7a5f; }
.st-axis--warn { border-left-color: #b8860b; }
.st-axis--bad { border-left-color: #b3261e; }
.st-axis--neutral { border-left-color: #6b7280; }
.st-axis--muted { border-left-color: #c9c4bb; }

/* Recalculation receipt */
.st-receipt { margin-top: 10px; border: 1px solid var(--border); border-radius: 8px; background: #00000003; }
.st-receipt-toggle { display: flex; align-items: center; gap: 6px; width: 100%; padding: 7px 11px; background: transparent; border: 0; cursor: pointer; font-size: 12px; font-weight: 600; color: var(--text); }
.st-receipt-toggle:hover { background: #00000005; }
.st-receipt-final { margin-left: auto; font-size: 12px; font-weight: 700; color: var(--text); }
.st-receipt-body { padding: 4px 11px 11px; }
.st-wf { display: flex; flex-direction: column; }
.st-wf-row { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; padding: 4px 0; font-size: 12px; border-bottom: 1px dashed var(--border); }
.st-wf-row:last-child { border-bottom: 0; }
.st-wf-k { color: var(--text-2); }
.st-wf-v { color: var(--text); font-weight: 600; }
.st-wf-row--base .st-wf-k { color: var(--text); font-weight: 600; }
.st-wf-row--cap .st-wf-k { color: #b8860b; }
.st-wf-row--sub .st-wf-k { font-style: italic; }
.st-wf-row--final { margin-top: 2px; padding-top: 7px; border-top: 1px solid var(--border); }
.st-wf-row--final .st-wf-k { font-weight: 700; color: var(--text); }
.st-wf-row--final .st-wf-v { font-size: 13px; font-weight: 800; }
.st-cand { margin-top: 11px; }
.st-cand-h { font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-2); font-weight: 700; margin-bottom: 5px; }
.st-cand-row { display: grid; grid-template-columns: 120px 1fr 42px; align-items: center; gap: 8px; padding: 2px 0; }
.st-cand-k { font-size: 11px; color: var(--text-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.st-cand-row--win .st-cand-k { color: var(--text); font-weight: 700; }
.st-cand-bar { height: 8px; background: #00000010; border-radius: 4px; overflow: hidden; }
.st-cand-fill { display: block; height: 100%; background: #c9c4bb; border-radius: 4px; }
.st-cand-row--win .st-cand-fill { background: #0d7a5f; }
.st-cand-v { font-size: 11px; text-align: right; color: var(--text-2); }
.st-cand-row--win .st-cand-v { color: var(--text); font-weight: 700; }

/* Semantic Deduction Model help / legend */
.sdm-help { margin-bottom: 12px; padding: 0; overflow: hidden; }
.sdm-toggle { display: flex; align-items: center; gap: 8px; width: 100%; padding: 10px 13px; background: transparent; border: 0; cursor: pointer; color: var(--text); }
.sdm-toggle:hover { background: #00000004; }
.sdm-toggle-t { font-size: 13px; font-weight: 600; }
.sdm-toggle-h { margin-left: auto; font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-2); }
.sdm-body { padding: 4px 14px 14px; border-top: 1px solid var(--border); }
.sdm-lead { font-size: 12px; color: var(--text-2); line-height: 1.5; margin: 10px 0; }
.sdm-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.sdm-col-h { font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-2); font-weight: 700; margin-bottom: 7px; }
.sdm-tier { display: grid; grid-template-columns: 26px 1fr auto; grid-template-rows: auto auto; column-gap: 7px; align-items: center; padding: 4px 0; border-bottom: 1px dashed var(--border); }
.sdm-tier-b { grid-row: 1 / 3; display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 24px; border-radius: 6px; font-size: 11px; font-weight: 800; color: #fff; }
.sdm-t1 { background: #0d7a5f; }
.sdm-t2 { background: #2e6b9c; }
.sdm-t3 { background: #8a7d68; }
.sdm-tier-n { font-size: 12px; font-weight: 600; color: var(--text); }
.sdm-tier-w { font-size: 12px; font-weight: 700; color: var(--text); }
.sdm-tier-d { grid-column: 2 / 4; font-size: 10px; color: var(--text-2); }
.sdm-nudge { display: flex; justify-content: space-between; font-size: 12px; padding: 4px 0; border-bottom: 1px dashed var(--border); color: var(--text-2); }
.sdm-nudge span:last-child { color: var(--text); font-weight: 600; }
.sdm-band { display: flex; align-items: center; gap: 7px; font-size: 12px; padding: 4px 0; color: var(--text-2); }
.sdm-band-dot { width: 9px; height: 9px; border-radius: 50%; flex: none; }
.sdm-bd-good { background: #0d7a5f; }
.sdm-bd-warn { background: #b8860b; }
.sdm-bd-bad { background: #b3261e; }
.sdm-foot { font-size: 11px; color: var(--text-2); line-height: 1.5; margin: 12px 0 0; padding-top: 10px; border-top: 1px solid var(--border); }
.st-hf-pii { color: var(--danger-col); background: #9e332614; }
.st-hf-conflict { color: var(--warn-col); background: #a9651b14; }
.st-hf-storage { color: var(--info-col); background: #2f5d8a14; }

/* Why line */
.st-why-line { font-size: 12px; color: var(--text-2); line-height: 1.55; margin-bottom: 12px; padding: 8px 10px; background: #00000005; border-left: 3px solid var(--border); border-radius: 0 6px 6px 0; }

/* U1b: near-miss — signals present but no channel could initiate */
.st-nearmiss { margin-bottom: 12px; padding: 8px 10px; border: 1px dashed var(--warn-col, #b8860b); border-radius: 6px; background: #b8860b0d; }
.st-nearmiss-h { font-size: 11px; font-weight: 700; color: var(--text-2); margin-bottom: 4px; }

/* Two-column evidence */
.st-ev2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 6px; }
@media (max-width: 820px) { .st-ev2 { grid-template-columns: 1fr; } }
.st-ev2-h { font-size: 10px; letter-spacing: .08em; text-transform: uppercase; font-weight: 700; padding: 5px 0 7px; border-bottom: 2px solid; margin-bottom: 8px; }
.st-ev2-h--data { color: var(--approved-col); border-color: var(--approved-col); }
.st-ev2-h--meaning { color: var(--info-col); border-color: var(--info-col); }
.st-evr { display: flex; align-items: baseline; gap: 8px; padding: 5px 0; font-size: 12px; }
.st-evr--na { opacity: .55; }
.st-mk { width: 9px; height: 9px; border-radius: 50%; flex: 0 0 auto; margin-top: 2px; }
.mk-confirm-data { background: var(--approved-col); }
.mk-confirm-meaning { background: var(--info-col); }
.mk-support-data { background: var(--approved-col); opacity: .5; }
.mk-support-meaning { background: var(--info-col); opacity: .5; }
.mk-refute { background: var(--danger-col); }
.mk-neutral { background: var(--text-2); opacity: .45; }
.st-mk.na { border: 1.5px dashed var(--text-2); background: transparent; opacity: .45; }
.st-evr-k { font-weight: 700; color: var(--text); width: 78px; flex: 0 0 auto; font-size: 11.5px; }
.st-evr-s { color: var(--text-2); flex: 1; line-height: 1.4; }
.st-ent-ev { display: flex; flex-direction: column; }

/* Steward decision strip */
.st-decision { padding: 11px 15px; border-top: 1px solid var(--border); background: #00000003; display: flex; flex-direction: column; gap: 9px; }
.st-decide { display: flex; gap: 9px; align-items: center; flex-wrap: wrap; }
.st-dq { font-size: 12px; color: var(--text-2); flex: 1; min-width: 180px; line-height: 1.4; }
.st-disposition { display: flex; align-items: center; font-size: 12.5px; flex-wrap: wrap; gap: 4px; }
.st-disposition.ok { color: var(--approved-col); }
.st-disposition.rej { color: var(--danger-col); }
.st-disposition span { color: var(--text-2); }

/* Cascading override */
.st-override-cascade { display: flex; align-items: flex-end; gap: 8px; flex-wrap: wrap; padding-top: 6px; }
.st-ov-row { display: flex; flex-direction: column; gap: 3px; }
.st-ov-row label { font-size: 10px; text-transform: uppercase; letter-spacing: .07em; color: var(--text-2); font-weight: 700; }
.st-ov-arr { font-size: 18px; color: var(--text-2); padding-bottom: 4px; }

/* SD-R3b: Semantic Type — subdued analyst annotation inside the Definition tab */
.sem-annot { border-left: 3px solid var(--border); }
.sem-annot-head { display: flex; align-items: baseline; gap: 8px; margin-bottom: 10px; }
.sem-annot-title { font-size: 13px; font-weight: 700; color: var(--text); }
.sem-annot-hint { font-size: 11.5px; color: var(--text-2); }
.sem-annot-line { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.sem-annot-type { font-size: 14px; font-weight: 600; color: var(--text); }
.sem-annot-type--none { color: var(--text-2); font-style: italic; }
.sem-annot-tag { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; padding: 2px 8px; border-radius: 999px; border: 1px solid var(--border); color: var(--text-2); }
.sem-annot-tag--high { background: #e8f3ec; border-color: #b7d9c3; color: #2f6b3a; }
.sem-annot-tag--medium { background: #fbf1e0; border-color: #e6cfa0; color: #a9651b; }
.sem-annot-tag--low { background: #f3eee6; border-color: #ddd6c8; color: #86827a; }
.sem-annot-tag--accepted { background: #e8f3ec; border-color: #b7d9c3; color: #2f6b3a; }
.sem-annot-pii { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; padding: 2px 7px; border-radius: 4px; border: 1px solid #e0b6b0; background: #9e33260f; color: #9e3326; }
.sem-annot-warn { font-size: 11.5px; color: #9e3326; display: inline-flex; align-items: center; }
.sem-annot-taxo { margin-top: 6px; font-size: 12px; color: var(--text-2); display: flex; align-items: center; gap: 6px; }
.sem-annot-taxo-item { color: var(--text-2); }
.sem-annot-taxo-sep { color: var(--border); }
.sem-annot-actions { display: inline-flex; gap: 6px; margin-left: auto; }
.sem-annot-picker { margin-top: 10px; }
.sem-annot-sep { height: 1px; background: var(--border); margin: 12px 0 6px; }
.sem-plate-toggle { display: inline-flex; align-items: center; gap: 4px; font: inherit; font-size: 12px; font-weight: 600; color: var(--text-2); background: none; border: none; cursor: pointer; padding: 2px 0; }
.sem-plate-body { margin-top: 6px; font-size: 12.5px; color: var(--text); }
.sem-plate-why { margin: 0 0 8px; color: var(--text); }
.sem-plate-block { margin: 6px 0; }
.sem-plate-h { font-size: 10.5px; text-transform: uppercase; letter-spacing: .06em; color: var(--text-2); font-weight: 700; margin-bottom: 2px; }
.sem-plate-row { font-size: 12.5px; color: var(--text); padding: 1px 0; }
.sem-plate-conflict { color: #9e3326; font-weight: 600; margin-bottom: 6px; }
.sem-plate-h--warn { color: #9e3326; }
.sem-plate-caveat { color: #9e3326; }
.sem-plate-strengthen { margin-top: 8px; color: var(--text-2); display: inline-flex; align-items: center; }
.sem-plate-ai { display: inline-flex; align-items: center; margin-top: 10px; font: inherit; font-size: 12px; font-weight: 600; color: var(--accent); background: none; border: none; cursor: pointer; padding: 0; }
.sem-annot--empty { display: flex; align-items: center; }

/* Buttons */
.st-btn { font: inherit; font-size: 12.5px; font-weight: 600; border: 1px solid var(--border); background: #fff; border-radius: 8px; padding: 6px 12px; cursor: pointer; display: inline-flex; align-items: center; color: var(--text); transition: background .12s; }
.st-btn:hover:not(:disabled) { background: #00000005; }
.st-btn:disabled { opacity: .55; cursor: default; }
.st-btn--confirm { background: var(--accent); border-color: var(--accent); color: #fff; }
.st-btn--confirm:hover:not(:disabled) { background: #0a4a44; }
.st-btn--ghost { box-shadow: none; color: var(--text-2); }
.st-btn--ai { border-color: var(--ai-col); color: var(--ai-col); margin-left: auto; flex: 0 0 auto; align-self: center; }
.st-btn--ai:hover:not(:disabled) { background: #8b5cf60d; }
.st-btn--full { width: 100%; justify-content: center; margin-top: 8px; }

/* AI assistance anchor */
.st-ai { background: #f6f3fc; border: 1px solid #e3d9f5; border-radius: 12px; padding: 14px 15px; }
.st-ai-head { display: flex; gap: 12px; align-items: flex-start; }
.st-ai-ic { width: 30px; height: 30px; border-radius: 8px; background: var(--ai-col); color: #fff; display: flex; align-items: center; justify-content: center; flex: 0 0 auto; }
.st-ai b { font-size: 13px; color: var(--text); }
.st-ai p { font-size: 12px; color: var(--text-2); margin-top: 2px; line-height: 1.5; max-width: 560px; }

/* Readiness panel */
.st-readiness { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 12px; }
@media (max-width: 720px) { .st-readiness { grid-template-columns: 1fr 1fr; } }
.st-rd-item { display: flex; align-items: center; gap: 7px; padding: 10px 12px; border-radius: 9px; border: 1px solid var(--border); font-size: 12px; font-weight: 600; }
.st-rd-item.rd-ok { color: var(--approved-col); background: #2f6b3a08; border-color: #2f6b3a28; }
.st-rd-item.rd-warn { color: var(--warn-col); background: #a9651b08; border-color: #a9651b28; }
.st-rd-item.rd-na { color: var(--text-2); background: #0000000a; }
.st-rd-label { flex: 1; }
.st-rd-note { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; opacity: .75; }
.st-review-note { font-size: 11.5px; color: var(--text-2); line-height: 1.5; padding: 8px 10px; background: var(--accent-light); border-radius: 8px; margin-bottom: 4px; }

/* Tier label chip — legacy .st-tier--* colour utilities (retained; semConfClass helper removed in SD-R2) */
.st-tier-lbl { font-size: 10px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; padding: 2px 8px; border-radius: 5px; color: #fff; background: var(--accent); }
.st-tier--ok .cv, .st-tier--ok.cv { color: var(--approved-col); }
.st-tier--ok.tl, .st-tier--ok.st-tier-lbl { background: var(--approved-col); }
.st-tier--warn .cv, .st-tier--warn.cv { color: var(--warn-col); }
.st-tier--warn.tl, .st-tier--warn.st-tier-lbl { background: var(--warn-col); }
.st-tier--muted .cv, .st-tier--muted.cv { color: var(--text-2); }
.st-tier--muted.tl, .st-tier--muted.st-tier-lbl { background: var(--pending-col); color: var(--text); }

.gterm-detail { font-size: 11.5px; color: var(--text-2); }
.gterm-steward { font-size: 11px; color: var(--text-2); margin-top: 4px; }
.gterm-status { font-size: 10px; padding: 1px 6px; border-radius: 4px; font-weight: 600; text-transform: capitalize; }
.gterm-status--ok { background: #edf7ef; color: var(--approved-col); }
.gterm-status--warn { background: #fdf3e6; color: var(--warn-col); }

.readiness-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}

.readiness-card {
  background: var(--paper);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px;
  text-align: center;
}

.readiness-val { font-family: 'IBM Plex Mono', monospace; font-size: 20px; font-weight: 700; }
.readiness-lbl { font-size: 9.5px; text-transform: uppercase; letter-spacing: .07em; color: var(--text-2); margin-top: 2px; }

/* ── Hypothesis cards (dashed) ────────────────────────────────────────── */
.hypo-card {
  background: var(--card-bg);
  border: 1.5px dashed #c4b5fd;
  border-radius: 8px;
  padding: 10px 12px;
}

.hypo-card--high { border-color: #f5a49f; }
.hypo-card--attention { border-color: #f0c99a; }
.hypo-card--info { border-color: #9fc5e8; }

.hypo-title { font-size: 13px; font-weight: 600; color: var(--text); flex: 1; }
.hypo-conf { font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 4px; }
.hypo-conf--high { background: #fde8e6; color: var(--danger-col); }
.hypo-conf--attention { background: #fdf3e6; color: var(--warn-col); }
.hypo-conf--info { background: #eaf1fb; color: var(--info-col); }

.hypo-body { font-size: 12px; color: var(--text-2); margin: 4px 0; }
.hypo-rec { font-size: 12px; color: var(--text-2); display: flex; align-items: flex-start; gap: 4px; }
.hypo-cols { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.hypo-col-chip {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  padding: 1px 6px;
  border: 1px solid #c4b5fd;
  border-radius: 4px;
  color: var(--ai-col);
  background: #f3f0fc;
}

/* ── Observations in drawer ───────────────────────────────────────────── */
.obs-count {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--paper);
  border: 1px solid var(--border);
  color: var(--text-2);
}

.obs-item {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 10px;
  border-left: 3px solid var(--border);
}

.obs-item--high { border-left-color: var(--danger-col); }
.obs-item--attention { border-left-color: var(--warn-col); }
.obs-item--info { border-left-color: var(--info-col); }

.obs-item-hdr { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.obs-target { font-family: 'IBM Plex Mono', monospace; font-size: 10.5px; color: var(--text-2); }
.obs-title { font-size: 12px; font-weight: 600; color: var(--text); }
.obs-rationale { font-size: 11.5px; color: var(--text-2); margin-top: 3px; }

/* ── Utility ──────────────────────────────────────────────────────────── */
.mono { font-family: 'IBM Plex Mono', monospace; }

/* ── Dataset Overview ─────────────────────────────────────────────────── */
.ds-header {
  padding: 14px 20px 12px;
  border-bottom: 1px solid var(--border);
  background: var(--card-bg);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  flex: 0 0 auto;
}

.ds-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}


.ds-name {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 19px;
  font-weight: 700;
  color: var(--text);
}

.ds-col-count {
  font-size: 12px;
  padding: 2px 8px;
  background: var(--paper);
  border: 1px solid var(--border);
  border-radius: 5px;
  color: var(--text-2);
}

.ds-desc {
  font-size: 13px;
  color: var(--text-2);
  margin-top: 6px;
  line-height: 1.4;
}

.ds-sub {
  font-size: 11.5px;
  color: #a09890;
  font-style: italic;
  margin-top: 5px;
  line-height: 1.55;
}

/* Data Story tagline row */
.ds-tagline-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-top: 6px;
}
.ds-tagline {
  flex: 1;
  font-size: 12.5px;
  color: var(--text);
  font-style: italic;
  line-height: 1.5;
}
.ds-tagline-ai-badge {
  display: inline-flex;
  align-items: center;
  font-size: 10px;
  font-style: normal;
  background: var(--accent-light);
  color: var(--accent);
  padding: 1px 5px;
  border-radius: 3px;
  margin-left: 6px;
  vertical-align: middle;
}
.ds-story-btn {
  flex-shrink: 0;
  white-space: nowrap;
}

/* Data Story narrative block */
.ds-narrative-card {}
.ds-narrative-body {
  font-size: 12.5px;
  color: var(--text-2);
  line-height: 1.65;
  white-space: pre-wrap;
}
.ds-narrative-toggle {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 11px;
  color: var(--accent);
  padding: 0;
  margin-left: auto;
}

/* ds-stat-sub — demoted col count in Total Rows card */
.ds-stat-sub {
  font-size: 10px;
  color: var(--text-2);
  font-weight: 400;
  margin-left: 4px;
}

/* Tab bar far-right meta area */
.tab-bar-spacer { flex: 1; }
.tab-bar-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  padding-right: 2px;
}
.tab-bar-profiled {
  font-size: 11px;
  color: var(--text-2);
  display: flex;
  align-items: center;
}

.ds-legend-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 8px;
  padding-top: 7px;
  padding-bottom: 8px;
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
}
.ds-legend-group {
  display: flex;
  align-items: center;
  gap: 10px;
}
/* Dataset-header DQ Grade legend never wraps mid-list — ranges moved to a
   hover tooltip (see template) frees enough width for this to hold true. */
.ds-legend-row .dq-grade-legend--inline {
  flex-wrap: nowrap;
}
.ds-legend-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: .05em;
  color: var(--text-2);
  margin-right: 2px;
}
.ds-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--text-2);
}
.ds-legend-pip {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.ds-pk-row {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 6px;
  flex-wrap: wrap;
}

.ds-pk-row--inferred {
  opacity: 0.75;
}

.ds-pk-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
  text-transform: uppercase;
  letter-spacing: .04em;
}

.ds-pk-row--inferred .ds-pk-label {
  color: #7c8fa6;
}

/* "Relationships:" with no outgoing FK (§ follow-up) — a plain, muted "None"
   rather than leaving the label with nothing after it. */
.ds-rel-none {
  font-size: 12px;
  font-style: italic;
  color: var(--text-2);
}
/* "Referenced by:" sits after the outgoing-FK chips (or "None"), its own
   label so it's never mistaken for this table's own FK. */
.ds-rel-refby-label {
  margin-left: 6px;
}

/* Separator dot between the Primary Key chip(s) and the "Referenced by…"
   summary on the same header row. */
.ds-rel-dot {
  color: #b8b2a4;
  margin: 0 2px;
}

.ds-rel-summary {
  font-size: 12px;
  color: var(--text-2);
}

/* The count itself IS the expand/collapse control (no separate "See" link) —
   a prominent pill so it reads as clickable, not just a number. One click
   expands the chip list below; the same click again collapses it. */
.ds-rel-count-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 18px;
  padding: 0 6px;
  margin: 0 3px;
  border: none;
  border-radius: 9px;
  background: var(--accent);
  color: #fff;
  font: inherit;
  font-weight: 700;
  font-size: 11px;
  cursor: pointer;
  vertical-align: middle;
}

.ds-rel-count-pill:hover {
  background: #0a3f39;
}

.ds-rel-count-pill--fk {
  background: #16345c;
}

.ds-rel-count-pill--fk:hover {
  background: #0f2540;
}

.ds-rel-chip-row {
  margin-top: 2px;
}

.ds-pk-chip {
  font-size: 11px;
  padding: 1px 8px;
  background: var(--accent-light);
  border: 1px solid var(--accent);
  border-radius: 4px;
  color: var(--accent);
}

.ds-pk-chip--inferred {
  background: #f1f5f9;
  border: 1px dashed #7c8fa6;
  color: #475569;
}

.ds-fk-chip,
.ds-rb-chip {
  display: inline-flex;
  align-items: center;
  background: #eaf1f8;
  border: 1px solid #2f5d8a;
  color: #2f5d8a;
  cursor: pointer;
  transition: background 0.15s ease;
}

.ds-fk-chip:hover,
.ds-rb-chip:hover {
  background: #d9e6f2;
}

.ds-rb-chip {
  background: #f1eefa;
  border: 1px solid #6d5ba6;
  color: #6d5ba6;
}

.ds-rb-chip:hover {
  background: #e5ddf5;
}

.ds-fk-chip--inferred,
.ds-rb-chip--inferred {
  background: #f4f0fa;
  border: 1px dashed #8b6bb1;
  color: #6d4f96;
}

.ds-fk-chip--inferred:hover,
.ds-rb-chip--inferred:hover {
  background: #ebe3f7;
}

.ds-fk-chip--orphan {
  background: #fbeae8;
  border: 1px solid var(--danger-col);
  color: var(--danger-col);
}

.ds-fk-chip--orphan:hover {
  background: #f5d9d5;
}

.ds-orphan-pill {
  display: inline-flex;
  align-items: center;
  margin-left: 6px;
  padding: 1px 7px;
  border-radius: 9px;
  font-size: 10.5px;
  font-weight: 700;
  background: #fdf3e6;
  color: var(--warn-col);
  vertical-align: middle;
}

.char-fk-link {
  display: inline-flex;
  align-items: center;
  background: none;
  border: none;
  padding: 0;
  font: inherit;
  color: #2f5d8a;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.char-fk-link:hover {
  color: #1f3f61;
}

.char-fk-link--inferred {
  color: #8b6bb1;
}

.char-fk-link--inferred:hover {
  color: #6d4f96;
}

.char-fk-link--orphan {
  color: var(--danger-col);
}

.char-fk-link--orphan:hover {
  color: #7a281d;
}

.ds-meta-row {
  margin-top: 4px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}

.ds-ai-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}

.ds-ai-link {
  display: inline-flex;
  align-items: center;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--accent);
  padding: 0;
  transition: opacity .15s;
}
.ds-ai-link:hover { opacity: 0.75; text-decoration: underline; }
.ds-ai-link:disabled { opacity: 0.4; cursor: default; text-decoration: none; }

.ds-ai-sep {
  font-size: 12px;
  color: var(--text-2);
  user-select: none;
}

/* Data Story block extras */
.ds-narrative-empty {
  font-size: 12px;
  color: var(--text-2);
  font-style: italic;
  margin: 0 0 8px;
}
.ds-narrative-tagline {
  margin-top: 10px;
  font-size: 12px;
  color: var(--text-2);
  font-style: italic;
  border-top: 1px solid var(--border);
  padding-top: 8px;
}
.ds-narrative-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
}
.ds-story-textarea {
  width: 100%;
  font-size: 12.5px;
  font-family: inherit;
  color: var(--text);
  background: var(--paper);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 8px;
  resize: vertical;
  line-height: 1.6;
  box-sizing: border-box;
  margin-bottom: 6px;
}
.ds-story-textarea:focus { outline: none; border-color: var(--accent); }
.ds-story-tagline-input {
  width: 100%;
  font-size: 12px;
  font-family: inherit;
  color: var(--text);
  background: var(--paper);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 6px 8px;
  box-sizing: border-box;
  margin-bottom: 8px;
}
.ds-story-tagline-input:focus { outline: none; border-color: var(--accent); }
.ds-save-btn { font-weight: 700; }
.ds-story-icon-btns {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  margin-left: auto;
}
.ds-story-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  border-radius: 4px;
  padding: 3px 5px;
  cursor: pointer;
  color: var(--text-2);
  transition: background 0.15s, color 0.15s;
}
.ds-story-icon-btn:hover { background: var(--border); color: var(--text); }
.ds-story-edit-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  flex-wrap: wrap;
}
.ds-story-save-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 12px;
  font-size: 12px;
  font-weight: 600;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  background: var(--accent);
  color: #fff;
  transition: opacity 0.15s;
}
.ds-story-save-btn:disabled { opacity: 0.55; cursor: default; }
.ds-story-save-btn:not(:disabled):hover { opacity: 0.88; }
.ds-story-ai-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 12px;
  font-size: 12px;
  font-weight: 600;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  background: #6b46c1;
  color: #fff;
  transition: opacity 0.15s;
}
.ds-story-ai-btn:disabled { opacity: 0.55; cursor: default; }
.ds-story-ai-btn:not(:disabled):hover { opacity: 0.88; }
.ds-story-cancel-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 10px;
  font-size: 12px;
  font-weight: 500;
  border: 1px solid var(--border);
  border-radius: 4px;
  cursor: pointer;
  background: var(--paper);
  color: var(--text-2);
  transition: background 0.15s;
}
.ds-story-cancel-btn:hover { background: var(--border); }
.ds-story-saved-banner {
  display: inline-flex;
  align-items: center;
  margin-top: 8px;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 11.5px;
  font-weight: 600;
  background: #e6f4f0;
  color: var(--accent);
  border: 1px solid #b6ddd4;
}
.ds-story-save-error {
  display: inline-flex;
  align-items: center;
  margin-top: 8px;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 11.5px;
  font-weight: 600;
  background: #fdecea;
  color: #b91c1c;
  border: 1px solid #f5c6c6;
}

.bulk-banner {
  display: flex;
  align-items: center;
  border-radius: 6px;
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 600;
  margin-top: 8px;
  gap: 2px;
}
.bulk-banner--success {
  background: #eaf6ee;
  border: 1px solid var(--approved-col);
  color: #1e5c2e;
}
.bulk-banner--info {
  background: #f0f4ff;
  border: 1px solid #6b8cda;
  color: #2c3e7a;
}
.bulk-banner--error {
  background: #fff0f0;
  border: 1px solid var(--danger-col);
  color: #7a2020;
}
.bulk-banner-close {
  background: none;
  border: none;
  cursor: pointer;
  opacity: 0.6;
  margin-left: auto;
  padding: 0 2px;
  display: flex;
  align-items: center;
  color: inherit;
}
.bulk-banner-close:hover { opacity: 1; }

.bulk-banner-enter-active, .bulk-banner-leave-active { transition: opacity .3s, transform .3s; }
.bulk-banner-enter-from, .bulk-banner-leave-to { opacity: 0; transform: translateY(-4px); }

.ds-profiled {
  font-size: 11px;
  color: var(--text-2);
  display: flex;
  align-items: center;
}

.ds-body {
  padding: 16px 20px 24px;
}

.ds-stat-cards {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 10px;
}

.ds-stat-card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 14px 10px;
  text-align: center;
}

.ds-stat-val {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 20px;
  font-weight: 700;
  color: var(--text);
}

.ds-stat-lbl {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: .08em;
  color: var(--text-2);
  margin-top: 2px;
}

/* Semantic type bar */
.sem-type-bar {
  display: flex;
  height: 14px;
  border-radius: 4px;
  overflow: hidden;
  gap: 1px;
}

.sem-type-segment {
  min-width: 4px;
  transition: flex .3s;
}

.sem-type-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.sem-leg-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--text-2);
}

.sem-leg-dot {
  width: 10px;
  height: 10px;
  border-radius: 3px;
}

.sem-leg-label {
  text-transform: capitalize;
}

.sem-leg-count {
  font-weight: 700;
  color: var(--text);
}

/* Governance bar */
.gov-bar {
  display: flex;
  height: 14px;
  border-radius: 4px;
  overflow: hidden;
  gap: 1px;
}

.gov-seg {
  min-width: 4px;
  transition: flex .3s;
}

.gov-seg--draft { background: var(--draft-col); }
.gov-seg--reviewed { background: var(--defined-col); }
.gov-seg--released { background: var(--approved-col); }

.gov-legend {
  display: flex;
  gap: 16px;
}

.gov-leg-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--text-2);
}

.gov-dot {
  width: 10px;
  height: 10px;
  border-radius: 3px;
}

.gov-dot--draft { background: var(--draft-col); }
.gov-dot--reviewed { background: var(--defined-col); }
.gov-dot--released { background: var(--approved-col); }

/* Observation matrix */
.obs-matrix {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.obs-matrix th {
  text-align: left;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: .06em;
  color: var(--text-2);
  padding: 4px 8px;
  border-bottom: 1px solid var(--border);
}

.obs-matrix td {
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
}

/* Columns table */
.col-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.col-table th {
  text-align: left;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: .06em;
  color: var(--text-2);
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
}

.col-table td {
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
}

.col-row {
  cursor: pointer;
  transition: background .1s;
}

.col-row:hover {
  background: rgba(13,92,84,.04);
}

.col-num-th {
  width: 28px;
  text-align: right;
  padding-right: 10px;
}
.col-num-cell {
  width: 28px;
  text-align: right;
  padding-right: 10px;
  font-size: 10.5px;
  color: var(--text-2);
  font-variant-numeric: tabular-nums;
}

.col-name-cell {
  font-size: 11.5px;
  color: var(--text);
  font-weight: 700;
}

/* PK/FK markers — circular filled badges after the column name (was a bare
   icon before it) so they read as a distinct status pill, not decoration.
   Real emoji glyphs (not q-icon) on a dark, high-contrast pill for maximum
   visibility in the dense table; FK gets its own hue so the two are never
   confused with each other at a glance. */
.col-key-badge,
.col-fk-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  margin-left: 5px;
  vertical-align: middle;
  font-size: 10px;
  line-height: 1;
  box-shadow: 0 1px 2px rgba(0,0,0,.3);
}

.col-key-badge { background: #0a3f39; }
.col-key-badge--candidate { background: #4a5568; }
.col-fk-badge { background: #16345c; }
.col-fk-badge--inferred { background: #4a2e73; }

.col-type-cell, .col-sem-cell {
  font-size: 11px;
  color: var(--text-2);
}

.col-comp-bar {
  display: inline-block;
  width: 48px;
  height: 4px;
  background: var(--border);
  border-radius: 2px;
  overflow: hidden;
  vertical-align: middle;
  margin-right: 6px;
}

.col-comp-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 2px;
}

.col-comp-pct {
  font-size: 10px;
  color: var(--text-2);
}

/* Footnotes */
.ds-footnotes {
  display: flex;
  gap: 16px;
  padding: 8px 0;
}

.fn-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-2);
}

/* ── Reference Data Tab ───────────────────────────────────────────────── */
.refdata-status-badge {
  font-size: 9px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
  background: #f3f0fc;
  color: #5a3e8c;
  text-transform: capitalize;
}
.rdstatus--approved { background: var(--accent-light); color: var(--accent); }
.rdstatus--under_review { background: #fdf3e6; color: var(--warn-col); }
.rdstatus--candidate { background: #f3f0fc; color: #5a3e8c; }
/* Per-code set-badge tokens (Postgres per-code mode). */
.rdstatus--empty { background: #eceae6; color: #6b6862; }
.rdstatus--draft { background: #e7f0fb; color: #1e5aa8; }
.rdstatus--in_review { background: #fdf3e6; color: var(--warn-col); }
.rdstatus--partially_approved { background: #fdf3e6; color: var(--warn-col); }

.refdata-domain {
  display: flex;
  align-items: center;
  font-size: 12px;
  color: var(--text);
}

.refdata-domain--none {
  color: var(--text-2);
}

.rd-binding {
  font-size: 12px;
  color: var(--text);
}
.rd-binding-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.rd-binding-select {
  flex: 1;
  min-width: 0;
}
.rd-binding-bound {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}
.rd-binding-kind {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-2);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 1px 5px;
  margin-left: 6px;
}
.rd-binding-status {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  border-radius: 4px;
  padding: 1px 6px;
  margin-left: 6px;
}
.rd-binding-status--draft { background: var(--surface-2); color: var(--text-2); }
.rd-binding-status--in_review { background: #fef3c7; color: #92400e; }
.rd-binding-status--approved { background: #dcfce7; color: #166534; }
.rd-row-governed {
  background: var(--surface-2);
}
.rd-binding-note,
.rd-binding-suggest {
  font-size: 11px;
  color: var(--text-2);
  margin-top: 4px;
}
.rd-suggest-link {
  background: none;
  border: none;
  color: var(--primary);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  margin-left: 6px;
  padding: 0;
}
.rd-suggest-link:disabled {
  opacity: 0.5;
  cursor: default;
}
.rd-bound-hint {
  font-size: 11px;
  color: var(--text-2);
  display: inline-flex;
  align-items: center;
}

.code-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.code-table th {
  text-align: left;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: .06em;
  color: var(--text-2);
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
}

.code-table td {
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
}

.code-bar {
  height: 8px;
  background: var(--border);
  border-radius: 4px;
  overflow: hidden;
}

.code-bar-fill {
  height: 100%;
  background: #5a3e8c;
  border-radius: 4px;
  transition: width .3s;
}

.rd-meaning-input {
  width: 100%;
  font-size: 12px;
  padding: 3px 6px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--surface-2, #faf9f7);
  color: var(--text);
  outline: none;
}
.rd-meaning-input:focus { border-color: var(--accent); }
.rd-edit-row { display: flex; gap: 8px; align-items: center; }

/* ── Per-code Reference Data (5b.2) ───────────────────────────────────── */
.rd-gate-banner {
  display: flex; align-items: center;
  font-size: 12px; color: var(--text-muted, #6b6862);
  background: var(--surface-2, #faf9f7);
  border: 1px dashed var(--border);
  border-radius: 6px; padding: 8px 10px;
}
.rd-code-table th { white-space: nowrap; }
.rd-row-locked { background: var(--surface-2, #faf9f7); opacity: 0.92; }
.rd-declared-mark { color: var(--accent); vertical-align: middle; }
.rd-origin-select {
  width: 100%; font-size: 12px; padding: 3px 6px;
  border: 1px solid var(--border); border-radius: 4px;
  background: var(--surface-2, #faf9f7); color: var(--text); outline: none;
}
.rd-origin-select:focus { border-color: var(--accent); }
.rd-origin-static { font-size: 12px; color: var(--text-muted, #6b6862); }
.rd-code-status {
  display: inline-flex; align-items: center;
  font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 10px;
  background: #eceae6; color: #6b6862;
}
.rdcode--draft { background: #e7f0fb; color: #1e5aa8; }
.rdcode--in_review { background: #fdf3e0; color: #97701a; }
.rdcode--approved { background: #e4f4e9; color: #1f7a44; }
.rd-code-actions { display: flex; align-items: center; }
.rd-add-row { display: flex; gap: 8px; align-items: center; }
.rd-add-input { width: 180px; }
.rd-code-footer { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.rd-code-footer-hint { font-size: 11px; color: var(--text-muted, #6b6862); }

/* ── Reference Data multi-select + bulk pull-backs (5b.3.1) ───────────── */
.rd-bulk-bar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.rd-bulk-count { font-size: 12px; font-weight: 600; color: var(--text-muted, #6b6862); margin-right: 4px; }
.rd-row-selected { background: var(--accent-soft, #eef4fc); }
.submit-panel-cascade { display: flex; align-items: center; gap: 8px; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border); font-size: 13px; cursor: pointer; }
.submit-panel-cascade-row { display: flex; gap: 8px; align-items: center; font-size: 13px; cursor: pointer; }

/* ── Submit-for-review preview dialog (5b.3.2 #10) ─────────────────────── */
.submit-panel-card { border-radius: 12px; overflow: hidden; }
.submit-panel-head { background: var(--surface-2, #f5f3ef); border-bottom: 1px solid var(--border); padding: 14px 18px; }
.submit-panel-head-row { display: flex; align-items: center; gap: 12px; }
.submit-panel-head-icon { display: inline-flex; align-items: center; justify-content: center; width: 34px; height: 34px; border-radius: 8px; background: var(--accent-light, #e4f4ef); color: var(--accent, #0d5c54); flex: 0 0 auto; }
.submit-panel-title { font-size: 15px; font-weight: 700; color: var(--text); }
.submit-panel-sub { font-size: 12.5px; color: var(--text-muted, #6b6862); margin-top: 1px; }
.submit-panel-body { padding: 16px 18px; }
.submit-panel-label { font-size: 10.5px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-muted, #6b6862); margin-bottom: 10px; }
.sp-item { display: flex; align-items: flex-start; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--border); }
.sp-item:last-of-type { border-bottom: none; }
.sp-item-check { color: var(--positive, #1f7a44); margin-top: 1px; flex: 0 0 auto; }
.sp-item-main { min-width: 0; }
.sp-item-key { font-size: 11px; font-weight: 600; color: var(--text-muted, #6b6862); }
.sp-item-val { font-size: 13px; color: var(--text); line-height: 1.4; word-break: break-word; }
.submit-panel-actions { padding: 12px 18px; border-top: 1px solid var(--border); gap: 8px; }

/* ── Definition + Reference Data workflow ─────────────────────────────── */
.def-workflow { }
.def-wf-header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.def-wf-title { font-size: 12px; font-weight: 700; color: var(--text); }
.def-wf-state {
  font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 4px;
  text-transform: uppercase; letter-spacing: 0.05em;
}
.def-wf-state--draft { background: #f3f0f0; color: #b3261e; }
.def-wf-state--defined { background: #fdf3e6; color: var(--warn-col); }
.def-wf-state--approved { background: var(--accent-light); color: var(--accent); }
.def-wf-steps {
  display: flex; align-items: center; gap: 6px;
  font-size: 11px; color: var(--text-2); margin-bottom: 8px;
}
.def-wf-step { padding: 3px 8px; border-radius: 4px; background: #00000007; }
.def-wf-step.active { color: var(--text); font-weight: 600; background: #00000012; }
.def-wf-arr { color: var(--text-2); font-size: 13px; }
.def-wf-hint { font-size: 11px; color: var(--text-2); margin-bottom: 10px; line-height: 1.5; }
.def-wf-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.def-submission-status {
  margin-top: 10px;
  padding: 7px 10px;
  border-radius: 5px;
  font-size: 12px;
  display: flex;
  align-items: center;
}
.def-ss--pending { background: #fef3c7; color: #92400e; }
.def-ss--approved { background: #d1fae5; color: #065f46; }
.def-ss--rejected { background: #fee2e2; color: #991b1b; }
.st-submitted-badge { font-size: 12px; color: #92400e; display: flex; align-items: center; padding: 0 6px; }

/* Definition tab badge — no definition yet (red) */
.tab-badge--no { background: #fde8e6; color: var(--danger-col, #b3261e); }

/* ── Source Info Panel ────────────────────────────────────────────────── */
.src-header {
  padding: 14px 20px 12px;
  border-bottom: 1px solid var(--border);
  background: var(--card-bg);
  flex: 0 0 auto;
}

.src-title-row {
  display: flex;
  align-items: center;
}

.src-name {
  font-family: 'IBM Plex Serif', serif;
  font-size: 22px;
  font-weight: 700;
  color: var(--text);
}

.src-count-badge {
  margin-left: 14px;
  font-size: 12px;
  padding: 2px 10px;
  background: var(--paper);
  border: 1px solid var(--border);
  border-radius: 5px;
  color: var(--text-2);
}

.src-generated {
  font-size: 11px;
  color: var(--text-2);
  margin-top: 4px;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.src-rebuild-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
  background: var(--accent-light);
  border: 1px solid var(--accent);
  border-radius: 5px;
  padding: 2px 9px;
  cursor: pointer;
  transition: opacity .15s;
}
.src-rebuild-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.src-rebuild-btn:not(:disabled):hover { opacity: 0.85; }

.src-reset-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 600;
  color: var(--danger-col);
  background: #fde8e6;
  border: 1px solid var(--danger-col);
  border-radius: 5px;
  padding: 2px 9px;
  cursor: pointer;
  transition: opacity .15s;
  margin-left: 6px;
}
.src-reset-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.src-reset-btn:not(:disabled):hover { opacity: 0.85; }

/* Rebuild warning dialog */
.rebuild-warn-dialog {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  background: #fffbeb;
  border: 1px solid #fcd34d;
  border-radius: 12px;
  padding: 14px 16px;
  margin-top: 10px;
}

.rebuild-warn-body { flex: 1; }
.rebuild-warn-title {
  font-size: 13px;
  font-weight: 700;
  color: #92400e;
  margin-bottom: 6px;
}
.rebuild-warn-msg {
  font-size: 12px;
  color: #78350f;
  line-height: 1.6;
}
.rebuild-warn-checks {
  display: flex;
  gap: 18px;
  margin-top: 8px;
}
.rebuild-warn-checks :deep(.q-checkbox__label) {
  font-size: 12px;
  color: #78350f;
  font-weight: 600;
}
.rebuild-warn-note {
  font-size: 11.5px;
  color: #92400e;
  line-height: 1.5;
  margin-top: 4px;
  font-style: italic;
}

.rebuild-warn-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}
.rebuild-confirm-btn {
  font-size: 12px;
  font-weight: 700;
  padding: 5px 16px;
  border-radius: 7px;
  border: none;
  background: #d97706;
  color: #fff;
  cursor: pointer;
}
.rebuild-confirm-btn:hover { background: #b45309; }
.rebuild-confirm-btn--danger { background: var(--danger-col); }
.rebuild-confirm-btn--danger:hover { background: #7a281e; }
.rebuild-cancel-btn {
  font-size: 12px;
  font-weight: 600;
  padding: 5px 14px;
  border-radius: 7px;
  border: 1px solid #d1d5db;
  background: #fff;
  color: #374151;
  cursor: pointer;
}
.rebuild-cancel-btn:hover { background: #f3f4f6; }

/* Rebuild progress panel */
.rebuild-progress-panel {
  margin-top: 10px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 12px 16px;
}
.rebuild-prog-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}
.rebuild-prog-title {
  flex: 1;
  font-size: 12.5px;
  font-weight: 600;
  color: #1e293b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.rebuild-abort-btn {
  display: inline-flex;
  align-items: center;
  background: transparent;
  border: 1px solid #cbd5e1;
  border-radius: 5px;
  padding: 2px 6px;
  cursor: pointer;
  color: #64748b;
}
.rebuild-abort-btn:hover { background: #f1f5f9; }
.rebuild-prog-bar-wrap {
  height: 6px;
  background: #e2e8f0;
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 8px;
}
.rebuild-prog-bar {
  height: 100%;
  background: var(--accent);
  border-radius: 4px;
  transition: width .3s ease;
}
.rebuild-prog-bar--done { background: var(--approved-col); }
.rebuild-prog-bar--error { background: #d97706; }
.rebuild-prog-stats {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  font-size: 11px;
  color: #64748b;
}
.rebuild-stat { display: inline-flex; align-items: center; }
.rebuild-stat--ok { color: var(--approved-col); font-weight: 600; }
.rebuild-stat--err { color: var(--danger-col); font-weight: 600; }
.rebuild-stat--time { color: #475569; }

@keyframes spin { to { transform: rotate(360deg); } }
.spin { display: inline-block; animation: spin 1.5s linear infinite; }

.src-sub {
  font-size: 11.5px;
  color: #a09890;
  font-style: italic;
  margin-top: 6px;
  line-height: 1.55;
}

.src-ai-actions {
  margin-top: 8px;
}

.src-body {
  padding: 16px 20px 24px;
}

/* Connection metadata card — screenshot1 style */
.src-conn-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px 0;
}

.src-conn-caption {
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: .1em;
  text-transform: uppercase;
  color: var(--text-2);
}

.src-conn-divider {
  height: 1px;
  background: var(--border);
  margin: 10px 16px;
}

.src-conn-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px 20px;
  padding: 0 16px 16px;
}

.src-conn-item {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.src-conn-lbl {
  font-size: 10.5px;
  color: var(--text-2);
}

.src-conn-val {
  font-size: 13.5px;
  color: var(--text);
}

/* Charts row */
.ds-charts-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.ds-chart-half { /* each chart takes half width */ }

/* §7 redesign — dataset-level Semantic Type Mix / Governance State / DQ Grade
   Distribution, one row of three. Each panel is a single proportional bar
   (segments sized by share of that panel's own total) plus a wrapping legend
   underneath — full label text always, unlike the old fixed-width vertical
   bars which truncated (e.g. "Identifi..."). */
.ds-charts-row-3 {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
@media (max-width: 900px) {
  .ds-charts-row-3 { grid-template-columns: 1fr; }
}
.prop-bar {
  display: flex;
  width: 100%;
  height: 14px;
  border-radius: 7px;
  overflow: hidden;
  background: var(--paper);
  border: 1px solid var(--border);
}
.prop-bar-seg {
  height: 100%;
  min-width: 3px;
  transition: width .4s ease;
}
.prop-bar-seg:not(:last-child) { border-right: 1px solid var(--card-bg); }
.prop-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  margin-top: 12px;
}
.prop-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}
.prop-legend-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex-shrink: 0;
}
.prop-legend-label { color: var(--text); font-weight: 600; white-space: nowrap; }
.prop-legend-count { color: var(--text-2); font-size: 11px; font-weight: 700; }

.ds-panel-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.ds-panel-caption {
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: var(--text-2);
}

/* Labeled semantic type bar */
.sem-type-bar-labeled {
  display: flex;
  height: 32px;
  border-radius: 4px;
  overflow: hidden;
  gap: 1px;
}

.sem-type-seg-labeled {
  min-width: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  transition: flex .3s;
}

.sem-seg-text {
  font-size: 11px;
  font-weight: 600;
  color: #fff;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding: 0 6px;
}

/* Labeled governance bar */
.gov-bar-labeled {
  display: flex;
  height: 32px;
  border-radius: 4px;
  overflow: hidden;
  gap: 1px;
}

.gov-seg-labeled {
  min-width: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
  color: #fff;
  overflow: hidden;
  white-space: nowrap;
  transition: flex .3s;
  padding: 0 6px;
}

.gov-detail {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin-top: 8px;
}

.gov-detail-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  color: var(--text-2);
}

.gov-detail-lbl { flex: 1; }

.gov-detail-count {
  font-weight: 700;
  color: var(--text);
}

.ldm-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px 16px;
  text-align: center;
  color: var(--text-2);
  font-size: 12px;
  background: var(--paper);
  border: 1px dashed var(--border);
  border-radius: 8px;
}

.ldm-hint {
  font-size: 11px;
  color: var(--text-2);
  opacity: .7;
}

.ldm-diagram-wrap {
  width: 100%;
}

.ldm-panel {
  position: relative;
}

.ldm-panel > .panel-card-title {
  padding-right: 200px;
}

.ldm-panel--fullscreen {
  position: fixed;
  inset: 0;
  width: 100vw;
  height: 100vh;
  z-index: 5000;
  background: #ffffff;
  display: flex;
  flex-direction: column;
  padding: 16px 20px !important;
  border-radius: 0;
  margin: 0;
}

.ldm-title-actions {
  position: absolute;
  top: 12px;
  right: 16px;
  display: flex;
  align-items: center;
  gap: 6px;
  z-index: 1;
}

.ldm-action-btn {
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-2);
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px 9px;
  cursor: pointer;
  transition: color .12s, border-color .12s;
}

.ldm-action-btn:hover {
  color: var(--accent);
  border-color: var(--accent);
}

.ldm-action-btn--icon {
  padding: 4px 6px;
}

.ldm-svg {
  width: 100%;
  height: 380px;
  display: block;
}

.ldm-panel--fullscreen .ldm-diagram-wrap {
  flex: 1;
  min-height: 0;
  display: flex;
}

.ldm-svg--fullscreen {
  width: 100%;
  height: 100%;
  max-height: none;
  flex: 1;
}

.ldm-node {
  cursor: grab;
  touch-action: none;
}

.ldm-node:active { cursor: grabbing; }

.ldm-node-box {
  fill: url(#ldmNodeGradient);
  stroke: #163d6b;
  stroke-width: 1.4;
  filter: drop-shadow(0 1px 2px rgba(20, 40, 70, 0.35));
  transition: filter .12s, stroke .12s;
}

.ldm-node:hover .ldm-node-box {
  stroke: #7dd3fc;
  filter: drop-shadow(0 2px 5px rgba(20, 40, 70, 0.5));
}

.ldm-node-label {
  font-size: 10px;
  font-weight: 700;
  fill: #ffffff;
  pointer-events: none;
}

.ldm-edge {
  stroke-width: 1.4;
  fill: none;
}

.ldm-edge--declared { stroke: #2f5d8a; }
.ldm-edge--inferred { stroke: #8b6bb1; stroke-dasharray: 4 3; }

/* Crow's-foot marks (many-side prongs, one-side ticks) — solid even on
   inferred (dashed) edges so the cardinality symbols stay crisp. */
.ldm-edge-mark { stroke-dasharray: none; }

.ldm-verb-label {
  font-size: 9.5px;
  font-weight: 600;
  font-style: italic;
  fill: var(--text-2);
}

.ldm-legend {
  display: flex;
  gap: 14px;
  margin-top: 8px;
  font-size: 11px;
  color: var(--text-2);
}

.ldm-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.ldm-legend-swatch {
  width: 16px;
  height: 2px;
  display: inline-block;
}

.ldm-legend-swatch--declared { background: #2f5d8a; }
.ldm-legend-swatch--inferred {
  background: repeating-linear-gradient(90deg, #8b6bb1 0 4px, transparent 4px 7px);
}

.src-schemas {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.src-schema-chip {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11px;
  padding: 3px 10px;
  background: var(--paper);
  border: 1px solid var(--border);
  border-radius: 5px;
  color: var(--text);
}

/* ── Vertical bar charts (semantic type mix & governance) ─────────────── */
/* Polish Batch Task 12 — legibility pass: more breathing room between bars,
   slightly larger/darker value + label text, wider bars. What each chart
   measures is unchanged. */
.vert-chart {
  display: flex;
  align-items: flex-end;
  justify-content: center;
  gap: 18px;
  height: 148px;
  padding: 0 4px;
}

.vert-bar-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  width: 60px;
  flex-shrink: 0;
}

.vert-bar-count {
  font-size: 12.5px;
  font-weight: 800;
  color: var(--text);
  line-height: 1;
  font-variant-numeric: tabular-nums;
}

.vert-bar-track {
  position: relative;
  width: 44px;
  height: 100px;
  background: var(--paper);
  border: 1px solid var(--border);
  border-radius: 5px;
  overflow: hidden;
}

.vert-bar-fill {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  border-radius: 4px 4px 0 0;
  transition: height .4s ease;
  min-height: 3px;
}

.vert-bar-lbl {
  font-size: 10px;
  font-weight: 700;
  text-align: center;
  text-transform: uppercase;
  letter-spacing: .03em;
  line-height: 1.25;
  width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* DQ grade distribution bars (Task 9) — band palette fill. Used by both the
   §7 proportional-bar segments and their legend dots. */
.dq-band-fill--positive-strong { background: var(--dq-excellent); }
.dq-band-fill--positive { background: var(--dq-good); }
.dq-band-fill--warning { background: var(--dq-adequate); }
.dq-band-fill--warning-strong { background: var(--dq-weak); }
.dq-band-fill--negative { background: var(--dq-critical); }
.dq-band-fill--neutral { background: var(--pending-col); }

/* ── Datasets summary table ───────────────────────────────────────────── */
.src-datasets-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.src-datasets-table th {
  text-align: left;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: .05em;
  color: var(--text-2);
  padding: 4px 8px;
  border-bottom: 1px solid var(--border);
  font-weight: 600;
}

.src-datasets-table td {
  padding: 5px 8px;
  border-bottom: 1px solid var(--border);
  color: var(--text);
  vertical-align: middle;
  text-align: left;
}

.src-datasets-table tr:last-child td {
  border-bottom: none;
}

.src-datasets-table tr:hover td {
  background: var(--accent-light);
}

.src-ds-row { cursor: pointer; }

.src-ds-name-cell {
  max-width: 200px;
}

/* A <td> must keep table-cell display for the table's row borders/layout to
   work — the flex row that keeps the badge from being ellipsis-clipped lives
   on this inner wrapper instead (a bug fixed after display:flex directly on
   the <td> broke the row's border-bottom across the other columns). */
.src-ds-name-inner {
  display: flex;
  align-items: center;
}

.src-ds-name {
  font-family: 'IBM Plex Mono', monospace;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

/* "Never profiled" badge — a freshly-onboarded table, or one reset back to
   its pre-profiling baseline (D11's is_profiled flag). Same circular-pill
   convention as the PK/FK column badges: a filled red "R" so it reads as an
   unambiguous reset/pending-profile marker, not decoration; reused verbatim
   (bigger) next to the source name when every dataset in the source is in
   this state. */
.unprofiled-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  margin-left: 5px;
  vertical-align: middle;
  font-size: 9px;
  font-weight: 700;
  line-height: 1;
  color: #fff;
  background: #c62828;
  box-shadow: 0 1px 2px rgba(0,0,0,.3);
  flex-shrink: 0;
}

.unprofiled-badge--src {
  width: 20px;
  height: 20px;
  font-size: 11px;
  margin-left: 8px;
}

/* .ds-title-row already applies a 10px flex gap between children — avoid
   doubling up on spacing when the (base-sized) badge is reused there. */
.ds-title-row .unprofiled-badge {
  margin-left: 0;
}

.ds-released-count {
  font-weight: 600;
  color: var(--approved-col);
}

.src-ds-dq-chip {
  display: inline-flex;
}

.ds-dq-not-scored {
  color: var(--text-2);
}

.src-datasets-table .num {
  text-align: left;
  font-variant-numeric: tabular-nums;
  font-size: 11px;
}

.src-ds-num-th {
  width: 28px;
  text-align: left;
}
.src-ds-num-cell {
  width: 28px;
  text-align: left;
  font-size: 10.5px;
  color: var(--text-2);
  font-variant-numeric: tabular-nums;
}

.ok-zero {
  color: var(--text-2);
  opacity: .5;
}

/* ── Semantic Type × Governance State grouped bar chart ───────────────── */
.sem-gov-chart {
  display: flex;
  align-items: flex-end;
  gap: 22px;
  overflow-x: auto;
  padding: 4px 4px 2px;
}

.sem-gov-group {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.sem-gov-bars {
  display: flex;
  align-items: flex-end;
  gap: 3px;
  height: 128px;
}

.sem-gov-bar-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
  height: 100%;
  width: 20px;
}

.sem-gov-bar-count {
  font-size: 10px;
  font-weight: 800;
  color: var(--text);
  line-height: 1;
  font-variant-numeric: tabular-nums;
  min-height: 12px;
}

.sem-gov-bar-track {
  position: relative;
  width: 16px;
  height: 100px;
  background: var(--paper);
  border: 1px solid var(--border);
  border-radius: 4px;
  overflow: hidden;
}

.sem-gov-bar-fill {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  border-radius: 3px 3px 0 0;
  transition: height .4s ease;
  min-height: 0;
}

.sem-gov-group-lbl {
  font-size: 10.5px;
  font-weight: 700;
  text-transform: capitalize;
  white-space: nowrap;
}

/* ── Mini governance bar inside datasets table ────────────────────────── */
.ds-mini-gov {
  display: flex;
  height: 6px;
  border-radius: 3px;
  overflow: hidden;
  min-width: 60px;
  gap: 1px;
}

.ds-mini-gov-seg {
  display: block;
  height: 100%;
  min-width: 3px;
}

.gov-seg--draft { background: var(--draft-col); }
.gov-seg--reviewed { background: var(--defined-col); }
.gov-seg--released { background: var(--approved-col); }

/* ── Source-level tab bar ─────────────────────────────────────────────── */
.src-tab-bar {
  margin-top: 10px;
}

/* ── Tab badge ────────────────────────────────────────────────────────── */
.tab-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 17px;
  height: 17px;
  padding: 0 5px;
  border-radius: 9px;
  font-size: 10px;
  font-weight: 700;
  background: var(--accent-light);
  color: var(--accent);
  margin-left: 5px;
}
.tab-badge--warn {
  background: #fff0e0;
  color: var(--draft-col);
}

/* ── Bulk AI Draft tab ────────────────────────────────────────────────── */
.bulk-ai-tab {
  padding: 16px 20px 48px;
}

.data-model-tab {
  padding: 16px 20px 48px;
}

.bulk-stats-row {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  flex-wrap: wrap;
  align-items: center;
}

.bulk-stat-card {
  display: flex;
  align-items: center;
  gap: 12px;
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px 16px;
  backdrop-filter: blur(8px);
  flex: 0 0 auto;
}

.bulk-stat-card--ok {
  color: var(--approved-col);
}

.bulk-stat-icon {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
}

.bulk-stat-body {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.bulk-stat-val {
  font-size: 22px;
  font-weight: 700;
  font-family: 'IBM Plex Mono', monospace;
  line-height: 1.1;
}

.bulk-stat-lbl {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--text);
}

.bulk-stat-sub {
  font-size: 10.5px;
  color: var(--text-2);
}

.bulk-section {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
  margin-bottom: 14px;
  backdrop-filter: blur(8px);
}

.bulk-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 11px 16px;
  border-bottom: 1px solid var(--border);
  background: rgba(255,255,255,0.3);
  gap: 12px;
}
.bulk-section:not(.bulk-section--open) .bulk-section-header {
  border-bottom: none;
}

.bulk-section-title {
  display: flex;
  align-items: center;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text);
}
.bulk-section-title--toggle {
  cursor: pointer;
  flex: 1;
  user-select: none;
}
.bulk-section-title--toggle:hover { color: var(--accent); }
.bulk-toggle-chevron { flex: 0 0 auto; opacity: .55; }
.bulk-section-title--toggle:hover .bulk-toggle-chevron { opacity: 1; }

.bulk-section-scope {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .10em;
  text-transform: uppercase;
  color: var(--text-2);
  margin-left: 10px;
}

.bulk-last-run {
  display: inline-flex;
  align-items: center;
  font-size: 10px;
  font-weight: 400;
  letter-spacing: 0;
  text-transform: none;
  color: var(--text-2);
  margin-left: 10px;
  opacity: .75;
}

.bulk-section-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex: 0 0 auto;
}

.bulk-run-btn {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  font-weight: 600;
  padding: 7px 14px;
  border-radius: 8px;
  border: 1px solid var(--accent);
  background: var(--accent);
  color: #fff;
  cursor: pointer;
  transition: filter .12s;
}
.bulk-run-btn:hover:not(:disabled) { filter: brightness(1.08); }
.bulk-run-btn:disabled { opacity: .45; cursor: not-allowed; }

.bulk-empty-ok {
  display: flex;
  align-items: center;
  padding: 14px 16px;
  font-size: 12.5px;
  color: var(--approved-col);
  font-weight: 600;
}

.bulk-item-list {
  padding: 4px 0;
  max-height: 320px;
  overflow-y: auto;
}

.bulk-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 16px;
  border-bottom: 1px solid var(--border);
  font-size: 12.5px;
  transition: background .1s;
}
.bulk-item:last-child { border-bottom: none; }
.bulk-item:hover { background: rgba(0,0,0,.03); }

.bulk-item-icon {
  width: 24px;
  height: 24px;
  border-radius: 7px;
  background: var(--accent-light);
  color: var(--accent);
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
}

.bulk-item-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.bulk-item-name {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text);
}

.bulk-item-meta {
  font-size: 10.5px;
  color: var(--text-2);
}

.bulk-item-missing-badge {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .05em;
  padding: 2px 8px;
  border-radius: 5px;
  background: #fff0e0;
  color: var(--draft-col);
  white-space: nowrap;
  flex: 0 0 auto;
}

.bulk-item-link {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--accent);
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  flex: 0 0 auto;
  white-space: nowrap;
}
.bulk-item-link:hover { text-decoration: underline; }

/* History */
.bulk-history-list {
  padding: 4px 0;
}

.bulk-history-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 16px;
  border-bottom: 1px solid var(--border);
  font-size: 12px;
}
.bulk-history-item:last-child { border-bottom: none; }

.bulk-history-icon {
  color: var(--accent);
  flex: 0 0 auto;
}

.bulk-history-body {
  flex: 1;
  min-width: 0;
}

.bulk-history-title {
  font-weight: 600;
  font-size: 12.5px;
  color: var(--text);
}

.bulk-history-meta {
  font-size: 11px;
  color: var(--text-2);
  margin-top: 1px;
}

.bulk-history-ts {
  font-size: 10.5px;
  color: var(--text-2);
  white-space: nowrap;
  flex: 0 0 auto;
}

.bulk-history-empty {
  display: flex;
  align-items: center;
  padding: 12px 0 4px;
  font-size: 12px;
  color: var(--text-2);
}

/* ── AI Draft Acceptance chart ────────────────────────────────────────── */
.ai-accept-card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px 16px 12px;
  margin-bottom: 14px;
  backdrop-filter: blur(8px);
}
.ai-accept-header {
  display: flex;
  align-items: center;
  margin-bottom: 14px;
  gap: 2px;
}
.ai-accept-title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text);
}
.ai-accept-scope {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .10em;
  text-transform: uppercase;
  color: var(--text-2);
  margin-left: 10px;
}
.ai-accept-rows {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 10px;
}
.ai-accept-row {
  display: grid;
  grid-template-columns: 130px 1fr auto;
  align-items: center;
  gap: 10px;
}
.ai-accept-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text);
  white-space: nowrap;
}
.ai-accept-track {
  height: 10px;
  border-radius: 999px;
  background: #e8e4de;
  overflow: hidden;
  display: flex;
}
.ai-accept-seg {
  height: 100%;
  transition: width .4s ease;
  min-width: 0;
}
.ai-accept-seg--ai     { background: var(--ai-col); }
.ai-accept-seg--manual { background: var(--approved-col); }
.ai-accept-pct {
  font-size: 11px;
  white-space: nowrap;
}
.ai-accept-pct--ai      { color: var(--ai-col); font-weight: 700; }
.ai-accept-pct--manual  { color: var(--approved-col); font-weight: 700; }
.ai-accept-pct--absent  { color: var(--text-2); font-weight: 600; }
.ai-accept-pct-lbl      { color: var(--text-2); }
.ai-accept-legend {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  padding-top: 8px;
  border-top: 1px solid var(--border);
}
.ai-accept-leg-item {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: var(--text-2);
}
.ai-accept-leg-pip {
  width: 8px;
  height: 8px;
  border-radius: 2px;
  flex-shrink: 0;
}
.ai-accept-leg-pip--ai      { background: var(--ai-col); }
.ai-accept-leg-pip--manual  { background: var(--approved-col); }
.ai-accept-leg-pip--missing { background: #e8e4de; border: 1px solid var(--border); }

/* ── Documents tab ────────────────────────────────────────────────────── */
.docs-tab {
  padding: 16px 20px 48px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.docs-header-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
}

.docs-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 4px;
}

.docs-subtitle {
  font-size: 12.5px;
  color: var(--text-2);
  max-width: 580px;
  line-height: 1.6;
}

.docs-upload-btn {
  display: inline-flex;
  align-items: center;
  font-size: 12.5px;
  font-weight: 600;
  padding: 9px 16px;
  border-radius: 9px;
  border: 1px solid var(--accent);
  background: var(--accent);
  color: #fff;
  cursor: pointer;
  white-space: nowrap;
  flex: 0 0 auto;
  transition: filter .12s;
}
.docs-upload-btn:hover { filter: brightness(1.08); }

.docs-compliance {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 11px 14px;
  border-radius: 10px;
  background: var(--accent-light);
  border: 1px solid rgba(13,92,84,.25);
  font-size: 11.5px;
  color: var(--text);
  line-height: 1.6;
}

.docs-compliance-icon {
  flex: 0 0 auto;
  color: var(--accent);
  margin-top: 1px;
}

.docs-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.docs-search-wrap {
  display: flex;
  align-items: center;
  gap: 7px;
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 7px 11px;
}

.docs-search-icon { color: var(--text-2); flex: 0 0 auto; }

.docs-search-input {
  border: none;
  background: transparent;
  font: inherit;
  font-size: 12.5px;
  color: var(--text);
  outline: none;
  width: 180px;
}

.docs-filter-chips { display: flex; gap: 7px; flex-wrap: wrap; }

.docs-fchip {
  font-size: 10.5px;
  font-weight: 600;
  padding: 4px 11px;
  border-radius: 20px;
  border: 1px solid var(--border);
  background: var(--card-bg);
  color: var(--text-2);
  cursor: pointer;
  transition: border-color .12s, color .12s;
}
.docs-fchip--on {
  border-color: var(--text);
  color: var(--text);
}

.docs-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  text-align: center;
}

.docs-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.docs-card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
  backdrop-filter: blur(8px);
  transition: border-color .12s;
}

.docs-card:hover { border-color: #c0bbb2; }
.docs-card--open { border-color: var(--accent); }

.docs-card-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  cursor: pointer;
}

.docs-card-icon {
  width: 34px;
  height: 34px;
  border-radius: 9px;
  background: var(--accent-light);
  color: var(--accent);
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
}

.docs-card-body {
  flex: 1;
  min-width: 0;
}

.docs-card-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 3px;
}

.docs-card-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 11px;
  color: var(--text-2);
  flex-wrap: wrap;
}

.docs-type-badge {
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: .05em;
  text-transform: uppercase;
  padding: 2px 7px;
  border-radius: 5px;
  background: var(--accent-light);
  color: var(--accent);
}

.docs-status-badge {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .05em;
  text-transform: uppercase;
  padding: 3px 9px;
  border-radius: 6px;
  flex: 0 0 auto;
}
.docs-status--processing { background: #fff0e0; color: var(--draft-col); }
.docs-status--ready { background: var(--accent-light); color: var(--accent); }
.docs-status--failed { background: #fde8e6; color: var(--danger-col); }

.docs-ai-perms {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
  flex: 0 0 auto;
}

.docs-perm-chip {
  font-size: 9.5px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 5px;
  background: #e8f3ff;
  color: var(--defined-col);
}

/* AI Knowledge Preview panel */
.docs-ai-preview {
  border-top: 1px solid var(--border);
  background: rgba(13,92,84,.04);
}

.docs-ai-preview-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  font-size: 12.5px;
}

.docs-ai-preview-title {
  font-weight: 700;
  color: var(--text);
}

.docs-ai-preview-badge {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .05em;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 5px;
  background: var(--accent-light);
  color: var(--accent);
  margin-left: auto;
}

.docs-ai-preview-body {
  padding: 14px 16px;
  font-size: 13px;
  color: var(--text);
  line-height: 1.6;
}

.docs-ai-preview-body--loading {
  display: flex;
  align-items: center;
  color: var(--text-2);
  font-style: italic;
}

.docs-ai-preview-body--empty {
  display: flex;
  align-items: center;
  color: var(--text-2);
  font-size: 12.5px;
}

.docs-ai-preview-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
  flex-wrap: wrap;
}

.docs-ai-action-btn {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  font-weight: 600;
  padding: 7px 13px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--card-bg);
  color: var(--text);
  cursor: pointer;
  transition: border-color .12s;
}
.docs-ai-action-btn:hover { border-color: var(--accent); color: var(--accent); }
.docs-ai-action-btn--accept {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}
.docs-ai-action-btn--accept:hover { filter: brightness(1.08); color: #fff; }

/* Upload modal */
.docs-modal-icon {
  width: 38px;
  height: 38px;
  border-radius: 11px;
  background: linear-gradient(135deg, var(--accent), #0a4a44);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex: 0 0 auto;
}

.docs-dropzone {
  border: 2px dashed var(--border);
  border-radius: 12px;
  padding: 28px 20px;
  text-align: center;
  cursor: pointer;
  background: rgba(0,0,0,.02);
  transition: border-color .15s, background .15s;
  user-select: none;
}
.docs-dropzone:hover,
.docs-dropzone--drag { border-color: var(--accent); background: var(--accent-light); }

.docs-modal-ai-section {
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
}

.docs-modal-ai-header {
  display: flex;
  align-items: center;
  padding: 11px 16px;
  background: rgba(0,0,0,.03);
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}

.docs-modal-ai-perms {
  padding: 10px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.docs-perm-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  cursor: pointer;
}
</style>

<style>
/* Global: expose warm-palette vars at :root so teleported dialogs (q-dialog) can inherit them */
:root {
  --accent: #0d5c54;
  --accent-light: #e6f2f0;
  --paper: #f6f4f0;
  --card-bg: rgba(255, 253, 248, 0.62);
  --border: #ddd6c8;
  --text: #1c1b18;
  --text-2: #86827a;
  --draft-col: var(--gov-draft);
  --reviewed-col: var(--gov-in-review);
  --released-col: var(--gov-approved);
  --empty-col: var(--gov-empty);
  --in-review-col: var(--gov-in-review);
  --bounced-col: var(--gov-bounced);
  --danger-col: #9e3326;
  --warn-col: #a9651b;
}

/* DQ score-change toast (bottom-right) — matches the app's own card look + lifecycle
   palette (draft/approved colours) instead of Quasar's generic flat positive/warning. */
.dq-toast.q-notification {
  background: var(--card-bg);
  backdrop-filter: blur(10px);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 10px;
  font-weight: 600;
  box-shadow: 0 10px 28px rgba(28, 27, 24, 0.18);
}
.dq-toast--up.q-notification { border-left: 4px solid var(--released-col); }
.dq-toast--down.q-notification { border-left: 4px solid var(--warn-col); }
.dq-toast--up .q-icon { color: var(--released-col); }
.dq-toast--down .q-icon { color: var(--warn-col); }
</style>
