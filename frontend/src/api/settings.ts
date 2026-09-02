import { apiFetch } from './client';

export interface ExportInventory {
  glossary_terms: number;
  term_options: { id: string; title: string }[];
  source_datasets: string[];
  target_datasets: string[];
  mapping_files: string[];
  annotation_count: number;
}

export interface ExportConfig {
  components: string[];
  glossary_enabled: boolean;
  glossary_scope: 'entire' | 'selected';
  selected_term_ids: string[];
  include_meta: boolean;
  include_descriptions: boolean;
  include_synonyms_tags: boolean;
  include_related: boolean;
  include_governance: boolean;
  include_ai: boolean;
  selected_sources: string[];
  selected_targets: string[];
  include_annotations: boolean;
  selected_mappings: string[];
}

export async function fetchExportInventory(): Promise<ExportInventory> {
  return apiFetch<ExportInventory>('/api/settings/export/inventory');
}

async function downloadBlob(url: string, body: ExportConfig, filename: string): Promise<void> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Export failed: ${res.status}`);
  const blob = await res.blob();
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

export async function downloadZip(config: ExportConfig): Promise<void> {
  const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  return downloadBlob('/api/settings/export/zip', config, `adirra-export-${ts}.zip`);
}

export async function downloadPdf(config: ExportConfig): Promise<void> {
  const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  return downloadBlob('/api/settings/export/pdf', config, `adirra-export-summary-${ts}.pdf`);
}

export interface ImportResult {
  status: string;
  stats?: { created: number; updated: number; skipped: number; unchanged?: number };
  destination?: string;
}

export async function importGlossary(file: File, mergeMode: string): Promise<ImportResult> {
  const form = new FormData();
  form.append('file', file);
  form.append('merge_mode', mergeMode);
  const res = await fetch('/api/settings/import/glossary', { method: 'POST', body: form });
  if (!res.ok) throw new Error(`Import failed: ${res.status}`);
  return res.json();
}

export async function importMapping(file: File, destination: string, replace: boolean): Promise<ImportResult> {
  const form = new FormData();
  form.append('file', file);
  form.append('destination', destination);
  form.append('replace', String(replace));
  const res = await fetch('/api/settings/import/mapping', { method: 'POST', body: form });
  if (!res.ok) throw new Error(`Import failed: ${res.status}`);
  return res.json();
}
