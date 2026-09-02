<template>
  <div class="agp-wrap">
    <div class="agp-header">
      <q-icon name="policy" size="18px" class="q-mr-xs" style="color:var(--ink-3)" />
      <span class="agp-title">AI governance — active policy</span>
      <q-space />
      <q-btn icon="refresh" flat dense round size="sm" :loading="loading" @click="load"><q-tooltip>Refresh</q-tooltip></q-btn>
    </div>
    <p class="agp-sub">
      What ADIRRA sends to an LLM, and the rules every AI feature operates under — platform-wide,
      not tied to any one page.
    </p>

    <div v-if="loading" class="agp-loading"><q-spinner size="24px" color="primary" /></div>

    <template v-else-if="gov">
      <!-- Sample policy -->
      <div class="agp-section">
        <div class="agp-section-title">Sample policy</div>
        <p class="agp-section-hint">How much of a column's actual sampled data may accompany a prompt.</p>
        <q-option-group v-model="draftPolicy" :options="policyOptions" class="agp-policy-group">
          <template #label="opt">
            <div class="agp-opt-label">
              <span class="agp-opt-name">{{ opt.label }}</span>
              <span class="agp-opt-meaning">{{ opt.meaning }}</span>
            </div>
          </template>
        </q-option-group>
      </div>

      <!-- Provider / model -->
      <div class="agp-section">
        <div class="agp-section-title">Provider &amp; model</div>
        <div class="agp-kv"><code>{{ providerModelLabel(gov) }}</code></div>
      </div>

      <!-- Standing rules -->
      <div class="agp-section">
        <div class="agp-section-title">Standing rules</div>
        <ul class="agp-rules">
          <li v-for="(rule, i) in gov.rules" :key="i">{{ rule }}</li>
        </ul>
      </div>

      <div class="agp-actions">
        <q-btn label="Apply" icon="check" color="primary" disable>
          <q-tooltip>Needs Admin access to apply the changes</q-tooltip>
        </q-btn>
        <q-btn label="Cancel" flat color="grey-8" class="q-ml-sm" @click="cancelDraft" />
        <q-btn label="Default" flat color="negative" class="q-ml-sm" @click="resetDraftToDefault" />
        <span class="agp-actions-hint">Apply needs Admin access.</span>
      </div>
    </template>

    <div v-else class="agp-loading">
      <q-icon name="error_outline" size="24px" color="negative" />
      <span class="q-ml-sm">Could not load the AI policy.</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  policyLabel,
  providerModelLabel,
  type AiGovernance,
} from 'src/pages/aiGovernanceDisplay'

const props = defineProps<{ api: string }>()

const DEFAULT_POLICY = 'masked'

const loading = ref(false)
const gov = ref<AiGovernance | null>(null)
const draftPolicy = ref<string | null>(null)

const policyOptions = computed(() => (gov.value?.ai_sample_policy_options ?? []).map(opt => ({
  label: policyLabel(opt.value),
  value: opt.value,
  meaning: opt.meaning,
})))

function cancelDraft(): void {
  draftPolicy.value = gov.value?.ai_sample_policy ?? DEFAULT_POLICY
}

function resetDraftToDefault(): void {
  draftPolicy.value = DEFAULT_POLICY
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const resp = await fetch(`${props.api}/semantic-types/ai-governance`)
    gov.value = (await resp.json()) as AiGovernance
    draftPolicy.value = gov.value?.ai_sample_policy ?? null
  } catch {
    gov.value = null
  } finally {
    loading.value = false
  }
}

onMounted(() => { void load() })
</script>

<style scoped>
.agp-wrap { padding: 4px 0; margin-bottom: 24px; }
.agp-header { display: flex; align-items: center; margin-bottom: 4px; }
.agp-title { font-weight: 600; font-size: 14px; color: var(--ink-1); }
.agp-sub { font-size: 12.5px; color: var(--ink-3); margin: 0 0 14px; max-width: 720px; }
.agp-loading { display: flex; align-items: center; padding: 24px 0; color: var(--ink-3); }
.agp-section { margin-bottom: 16px; }
.agp-section-title { font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: var(--ink-3); margin-bottom: 8px; }
.agp-section-hint { font-size: 12px; color: var(--ink-3); margin: -4px 0 10px; }
.agp-policy-group :deep(.q-radio) { align-items: flex-start; padding: 8px 12px; border: 1px solid var(--line-2, #e3e6ea); border-radius: 8px; margin-bottom: 6px; width: 100%; }
.agp-policy-group :deep(.q-radio__label) { width: 100%; }
.agp-opt-label { display: flex; flex-direction: column; }
.agp-opt-name { font-size: 12.5px; font-weight: 600; color: var(--ink-1); }
.agp-opt-meaning { font-size: 12px; color: var(--ink-3); margin-top: 2px; }
.agp-kv code { font-size: 13px; background: var(--surface-2, #f3f5f7); padding: 3px 8px; border-radius: 6px; }
.agp-rules { margin: 0; padding-left: 18px; }
.agp-rules li { font-size: 12.5px; color: var(--ink-2); margin-bottom: 4px; }
.agp-actions { display: flex; align-items: center; gap: 4px; }
.agp-actions-hint { font-size: 12px; color: var(--ink-3); margin-left: 8px; }
</style>
