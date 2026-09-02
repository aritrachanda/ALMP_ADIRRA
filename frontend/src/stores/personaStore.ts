import { defineStore } from 'pinia';
import { ref, computed } from 'vue';

// Use relative /api path so Vite proxy handles routing — no hardcoded port
const API = '/api';

export interface PersonaContext {
  glossary_links: boolean;
  mapping_candidates: boolean;
  profiling_stats: boolean;
  audit_history: boolean;
}

export interface PersonaKnowledgeSources {
  crr3_regulation: boolean;
  eba_dpm: boolean;
  internal_kb: boolean;
  policy_documents: boolean;
}

export interface PersonaInference {
  temperature: number | null;
}

export interface Persona {
  name: string;
  role: string;
  expertise: string[];
  tone: 'precise' | 'friendly' | 'formal' | 'concise';
  verbosity: 'terse' | 'balanced' | 'detailed';
  response_format: 'prose' | 'bullets' | 'auto';
  avatar_url: string;
  context: PersonaContext;
  knowledge_sources: PersonaKnowledgeSources;
  inference: PersonaInference;
}

const DEFAULTS: Persona = {
  name: 'Assistant',
  role: 'Senior Data Governance Analyst and AI assistant',
  expertise: ['CRR3', 'BIRD', 'FINREP', 'COREP', 'IFRS 9'],
  tone: 'precise',
  verbosity: 'balanced',
  response_format: 'prose',
  avatar_url: '',
  context: {
    glossary_links: true,
    mapping_candidates: true,
    profiling_stats: true,
    audit_history: false,
  },
  knowledge_sources: {
    crr3_regulation: true,
    eba_dpm: true,
    internal_kb: false,
    policy_documents: false,
  },
  inference: {
    temperature: 0.3,
  },
};

export const usePersonaStore = defineStore('persona', () => {
  const persona = ref<Persona>({ ...DEFAULTS });
  const loading = ref(false);
  const saving = ref(false);
  const error = ref<string | null>(null);
  const saveSuccess = ref(false);

  const name = computed(() => persona.value.name || DEFAULTS.name);
  const avatarUrl = computed(() => persona.value.avatar_url || '');

  async function loadPersona() {
    loading.value = true;
    error.value = null;
    try {
      const res = await fetch(`${API}/settings/persona`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      persona.value = await res.json() as Persona;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      loading.value = false;
    }
  }

  async function savePersona(updated: Persona) {
    saving.value = true;
    saveSuccess.value = false;
    error.value = null;
    try {
      const res = await fetch(`${API}/settings/persona`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updated),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      persona.value = await res.json() as Persona;
      saveSuccess.value = true;
      setTimeout(() => { saveSuccess.value = false; }, 3000);
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      saving.value = false;
    }
  }

  async function resetPersona() {
    saving.value = true;
    error.value = null;
    try {
      const res = await fetch(`${API}/settings/persona/reset`, { method: 'POST' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      persona.value = await res.json() as Persona;
      saveSuccess.value = true;
      setTimeout(() => { saveSuccess.value = false; }, 3000);
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      saving.value = false;
    }
  }

  return {
    persona,
    loading,
    saving,
    error,
    saveSuccess,
    name,
    avatarUrl,
    loadPersona,
    savePersona,
    resetPersona,
  };
});
