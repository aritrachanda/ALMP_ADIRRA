import { apiFetch, apiPost } from './client';
import type { Catalog, CatalogListItem, Table } from 'src/types';

export async function listCatalogs(type: 'sources' | 'targets'): Promise<{ type: string; catalogs: CatalogListItem[] }> {
  return apiFetch(`/api/catalogs/${type}`);
}

export async function getCatalog(type: 'sources' | 'targets', name: string): Promise<Catalog> {
  return apiFetch(`/api/catalogs/${type}/${name}`);
}

export async function getTable(type: 'sources' | 'targets', name: string, table: string): Promise<Table> {
  return apiFetch(`/api/catalogs/${type}/${name}/${table}`);
}

export async function aiGenerate(
  type: 'sources' | 'targets',
  name: string,
  table: string,
  field: string,
  columnName?: string | null,
): Promise<Record<string, string>> {
  return apiPost(`/api/catalogs/${type}/${name}/${table}/ai-generate`, {
    field,
    column_name: columnName ?? null,
  });
}
