import { apiFetch, apiPost, apiPut, apiPatch } from './client';
import type { MappingResult, MappingListItem } from 'src/types';

export async function listMappings(): Promise<MappingListItem[]> {
  return apiFetch('/api/mappings');
}

export async function getMapping(source: string, target: string): Promise<MappingResult> {
  return apiFetch(`/api/mappings/${source}/${target}`);
}

export async function runMapping(source: string, target: string, body: {
  dataset_context?: string;
  agent_choice?: string;
  selected_tables?: string[] | null;
}): Promise<MappingResult> {
  return apiPost(`/api/mappings/${source}/${target}/run`, body);
}

export async function updateCandidates(source: string, target: string, updates: {
  target_schema: string;
  target_table: string;
  target_column: string;
  status: string;
}[]): Promise<MappingResult> {
  return apiPatch(`/api/mappings/${source}/${target}/candidates`, { updates });
}

export async function saveMapping(source: string, target: string, data: MappingResult): Promise<{ status: string }> {
  return apiPut(`/api/mappings/${source}/${target}`, data);
}
