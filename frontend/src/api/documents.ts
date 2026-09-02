import { apiFetch, apiPost } from './client'

export interface AiPermissions {
  definitions: boolean
  mapping: boolean
  quality: boolean
}

export interface SourceDocument {
  id: string
  source: string
  name: string
  doc_type: 'Data Dictionary' | 'Mapping Spec' | 'System Spec' | 'Quality Rules' | 'Other'
  description: string
  owner: string
  scope: string
  file_name: string | null
  file_path: string | null
  file_size_kb: number | null
  uploaded_at: string
  ai_permissions: AiPermissions
  synopsis: string | null
  synopsis_generated_at: string | null
  synopsis_is_ai: boolean
}

const BASE = '/api/documents'

export async function listDocuments(source: string): Promise<SourceDocument[]> {
  const resp = await apiFetch<{ source: string; documents: SourceDocument[] }>(
    `${BASE}/${encodeURIComponent(source)}`
  )
  return resp.documents
}

export async function uploadDocument(
  source: string,
  fields: {
    name: string
    doc_type: string
    description?: string
    owner?: string
    scope?: string
    ai_def?: boolean
    ai_map?: boolean
    ai_quality?: boolean
  },
  file?: File | null,
): Promise<SourceDocument> {
  const form = new FormData()
  form.append('name', fields.name)
  form.append('doc_type', fields.doc_type)
  form.append('description', fields.description ?? '')
  form.append('owner', fields.owner ?? '')
  form.append('scope', fields.scope ?? 'Source-level')
  form.append('ai_def', String(fields.ai_def ?? true))
  form.append('ai_map', String(fields.ai_map ?? true))
  form.append('ai_quality', String(fields.ai_quality ?? false))
  if (file) form.append('file', file)

  const res = await fetch(`${BASE}/${encodeURIComponent(source)}`, {
    method: 'POST',
    body: form,
    // No Content-Type header — browser sets multipart boundary automatically
  })
  if (!res.ok) throw new Error(`Upload failed: HTTP ${res.status}`)
  return res.json() as Promise<SourceDocument>
}

export async function deleteDocument(source: string, docId: string): Promise<{ deleted: boolean; doc_id: string }> {
  const res = await fetch(`${BASE}/${encodeURIComponent(source)}/${encodeURIComponent(docId)}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error(`Delete failed: HTTP ${res.status}`)
  return res.json() as Promise<{ deleted: boolean; doc_id: string }>
}

export async function generateDocumentSynopsis(source: string, docId: string): Promise<SourceDocument> {
  return apiPost<SourceDocument>(
    `${BASE}/${encodeURIComponent(source)}/${encodeURIComponent(docId)}/synopsis`,
    {},
  )
}
