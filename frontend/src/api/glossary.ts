import { apiFetch, apiPut, apiPost, apiDelete } from './client';
import type { GlossaryTerm, UncoveredConcept } from 'src/types';

export async function getGlossary(): Promise<GlossaryTerm[]> {
  return apiFetch('/api/glossary');
}

export async function getTerm(id: string): Promise<GlossaryTerm> {
  return apiFetch(`/api/glossary/terms/${id}`);
}

export async function upsertTerm(term: Partial<GlossaryTerm>): Promise<GlossaryTerm> {
  return apiPut('/api/glossary/terms', term);
}

export async function deleteTerm(id: string): Promise<{ status: string }> {
  return apiDelete(`/api/glossary/terms/${id}`);
}

export async function aiSuggest(id: string): Promise<Record<string, unknown>> {
  return apiPost(`/api/glossary/terms/${id}/ai-suggest`, {});
}

export async function aiSuggestFields(id: string, fields: string[]): Promise<Record<string, unknown>> {
  return apiPost(`/api/glossary/terms/${id}/ai-suggest-fields`, { fields });
}

export async function generateCRRContext(id: string): Promise<Record<string, string>> {
  return apiPost(`/api/glossary/terms/${id}/crr-context`, {});
}

export async function generateDPMContext(id: string): Promise<Record<string, string>> {
  return apiPost(`/api/glossary/terms/${id}/dpm-context`, {});
}

export async function getUncovered(): Promise<UncoveredConcept[]> {
  return apiFetch('/api/glossary/uncovered');
}

export function exportGlossaryUrl(): string {
  return '/api/glossary/export';
}

export async function crossRef(ref: string): Promise<GlossaryTerm[]> {
  return apiFetch(`/api/glossary/cross-ref?ref=${encodeURIComponent(ref)}`);
}
