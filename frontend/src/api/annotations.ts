import { apiFetch, apiPut } from './client';
import type { AnnotationOverlay, TableAnnotation } from 'src/types';

export async function getAnnotations(dataset: string): Promise<AnnotationOverlay> {
  return apiFetch(`/api/annotations/${dataset}`);
}

export async function setAnnotations(dataset: string, table: string, body: TableAnnotation): Promise<{ status: string }> {
  return apiPut(`/api/annotations/${dataset}/${table}`, body);
}
