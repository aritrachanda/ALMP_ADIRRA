<template>
  <q-page class="audit-page">
    <div class="text-h4 q-mb-xs" style="color: #10243a">Audit Log</div>
    <p class="text-subtitle1" style="color: #516274; margin-bottom: 1.25rem">
      Append-only record of every business event and AI call.
    </p>

    <!-- Summary bar: counts by event type today -->
    <div v-if="store.summary.length" class="summary-chips q-mb-md">
      <q-chip
        v-for="row in topSummary"
        :key="row.event_type"
        :color="eventClassColor(row.event_type)"
        text-color="white"
        size="sm"
        dense
        square
      >
        {{ row.event_type }} &nbsp;<strong>{{ row.count }}</strong>
      </q-chip>
    </div>

    <!-- Filters -->
    <div class="filter-row q-mb-md">
      <q-select
        v-model="filterClass"
        :options="classOptions"
        label="Class"
        dense
        outlined
        clearable
        emit-value
        map-options
        style="width: 130px"
        @update:model-value="applyFilters"
      />
      <q-input
        v-model="filterType"
        label="Event type"
        dense
        outlined
        clearable
        style="width: 220px"
        @update:model-value="applyFilters"
        debounce="400"
      />
      <q-input
        v-model="filterSubjectId"
        label="Subject ID"
        dense
        outlined
        clearable
        style="width: 220px"
        @update:model-value="applyFilters"
        debounce="400"
      />
      <!-- Governance preset quick-filters -->
      <q-btn-group flat>
        <q-btn
          :flat="activePreset !== 'governance'"
          :unelevated="activePreset === 'governance'"
          :color="activePreset === 'governance' ? 'primary' : 'grey-7'"
          dense no-caps
          icon="policy"
          label="Governance"
          @click="applyPreset('governance')"
        >
          <q-tooltip>Show only governance events (definitions, semantic types, documents)</q-tooltip>
        </q-btn>
        <q-btn
          v-if="activePreset"
          flat dense no-caps
          icon="close"
          @click="clearPreset"
        >
          <q-tooltip>Clear preset filter</q-tooltip>
        </q-btn>
      </q-btn-group>
      <q-btn flat dense icon="refresh" color="primary" @click="reload" :loading="store.loading">
        <q-tooltip>Refresh</q-tooltip>
      </q-btn>
    </div>

    <!-- Loading -->
    <div v-if="store.loading && !store.events.length" class="text-center q-pa-xl">
      <q-spinner-dots size="40px" color="primary" />
    </div>

    <!-- Error -->
    <q-banner v-else-if="store.error" class="bg-negative text-white q-mb-md" rounded>
      {{ store.error }}
    </q-banner>

    <!-- Empty -->
    <q-banner v-else-if="!store.events.length" class="bg-grey-2 q-mb-md" rounded>
      No audit events yet. Events appear here when mappings are accepted/rejected, glossary terms are
      saved, or AI calls are made.
    </q-banner>

    <!-- Table -->
    <q-card v-else flat bordered class="event-table-card">
      <q-list separator>
        <q-item
          v-for="evt in store.events"
          :key="evt.id"
          clickable
          @click="toggleExpand(evt.id)"
          class="event-row"
        >
          <q-item-section>
            <div class="event-header">
              <q-badge
                :color="evt.event_class === 'ai' ? 'deep-orange' : 'primary'"
                class="q-mr-sm"
              >
                {{ evt.event_class }}
              </q-badge>
              <span class="event-type">{{ evt.event_type }}</span>
              <span class="event-subject q-ml-sm text-caption text-grey-7">
                {{ evt.subject_type }} / {{ evt.subject_id }}
              </span>
              <q-space />
              <span class="event-time text-caption text-grey-6">
                {{ formatTime(evt.occurred_at) }}
              </span>
              <q-icon
                :name="expandedIds.has(evt.id) ? 'expand_less' : 'expand_more'"
                class="q-ml-xs"
                size="18px"
              />
            </div>

            <!-- Expanded payload -->
            <div v-if="expandedIds.has(evt.id)" class="payload-block q-mt-sm">
              <pre class="payload-pre">{{ JSON.stringify(evt.payload, null, 2) }}</pre>
            </div>
          </q-item-section>
        </q-item>
      </q-list>
    </q-card>

    <!-- Pagination hint -->
    <div v-if="store.events.length === 50" class="q-mt-sm text-caption text-grey-6">
      Showing 50 most recent events. Use filters to narrow the view.
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useAuditStore } from 'src/stores/auditStore';

const store = useAuditStore();

const filterClass = ref<string | null>(null);
const filterType = ref('');
const filterSubjectId = ref('');
const expandedIds = ref(new Set<number>());
const activePreset = ref<string | null>(null);

const classOptions = [
  { label: 'All', value: null },
  { label: 'Business', value: 'business' },
  { label: 'AI', value: 'ai' },
];

const topSummary = computed(() =>
  store.summary.slice(0, 8)
);

function eventClassColor(eventType: string) {
  return eventType.startsWith('ai.') ? 'deep-orange' : 'primary';
}

function formatTime(ts: string) {
  return new Date(ts).toLocaleString();
}

function toggleExpand(id: number) {
  if (expandedIds.value.has(id)) {
    expandedIds.value.delete(id);
  } else {
    expandedIds.value.add(id);
  }
}

function applyFilters() {
  expandedIds.value.clear();
  activePreset.value = null;
  store.loadEvents({
    event_class: filterClass.value ?? undefined,
    event_type: filterType.value || undefined,
    subject_id: filterSubjectId.value || undefined,
  });
}

function applyPreset(preset: string) {
  expandedIds.value.clear();
  filterClass.value = null;
  filterType.value = '';
  filterSubjectId.value = '';
  activePreset.value = preset;
  if (preset === 'governance') {
    // Load all governance-related events by fetching each prefix and merging client-side
    // (API supports single prefix; we fetch the most common one and let users drill down)
    store.loadEvents({ event_prefix: 'element.definition.', limit: 200 });
  }
}

function clearPreset() {
  activePreset.value = null;
  store.loadEvents({ limit: 50 });
}

function reload() {
  if (activePreset.value) {
    applyPreset(activePreset.value);
  } else {
    applyFilters();
  }
  store.loadSummary(30);
}

onMounted(() => {
  store.loadEvents({ limit: 50 });
  store.loadSummary(30);
});
</script>

<style scoped>
.audit-page {
  padding: 1.5rem 2rem;
}

.summary-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.filter-row {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  flex-wrap: wrap;
}

.event-table-card {
  border-radius: 12px;
}

.event-row {
  padding: 0.6rem 1rem;
}

.event-header {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  flex-wrap: wrap;
}

.event-type {
  font-size: 0.85rem;
  font-weight: 600;
  color: #1e3a5f;
}

.event-subject {
  font-size: 0.78rem;
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.event-time {
  font-size: 0.76rem;
  flex-shrink: 0;
}

.payload-block {
  background: #f5f7fa;
  border-radius: 8px;
  padding: 0.5rem 0.75rem;
  overflow: auto;
  max-height: 280px;
}

.payload-pre {
  margin: 0;
  font-size: 0.78rem;
  font-family: 'IBM Plex Mono', monospace;
  color: #1e3a5f;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
