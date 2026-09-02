import { apiFetch } from './client';

export interface BirdGroup {
  cube_group_id: string;
  name: string;
  code: string;
  description: string | null;
  entity_count: number;
}

export interface BirdEntity {
  cube_id: string;
  code: string;
  name: string;
  cube_type: string;
  framework_id: string;
  description: string | null;
}

export interface BirdAttribute {
  csi_id: string;
  role: string;
  role_label: string;
  is_mandatory: boolean;
  subdomain_id: string | null;
  order_num: number;
  attribute_associated_variable: string | null;
  variable_id: string;
  variable_code: string;
  variable_name: string;
  variable_description: string | null;
  domain_id: string;
  domain_name: string;
  data_type: string;
  is_enumerated: boolean;
  is_nevs: boolean;
}

export interface LegalRef {
  legal_reference_id: string;
  legal_code: string;
  legal_description: string | null;
  business_description: string | null;
  article: string | null;
}

export interface BirdEntityDetail extends BirdEntity {
  attributes: BirdAttribute[];
  legal_references: LegalRef[];
}

export interface GraphNode {
  id: string;
  label: string;
  title: string;
  value?: number;
  group: string;
  framework_id?: string;
}

export interface GraphEdge {
  id: string;
  from: string;
  to: string;
  label: string;
  title: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  level: number;
}

export interface ChainHop {
  ltr_id: string;
  transformation_type: string;
  source_layer: string;
  destination_layer: string;
  algorithm: string | null;
  source_cube_id: string;
  destination_cube_id: string;
  source_name: string;
  destination_name: string;
}

export interface MemberItem {
  member_id: string;
  code: string;
  name: string;
  description: string | null;
}

export interface TableRow {
  csi_id: string;
  cube_group_id: string;
  group_name: string;
  cube_id: string;
  entity_name: string;
  entity_code: string;
  framework_id: string;
  role: string;
  role_label: string;
  is_mandatory: boolean;
  variable_id: string;
  variable_code: string;
  variable_name: string;
  domain_id: string;
  domain_name: string;
  data_type: string;
  is_enumerated: boolean;
  is_nevs: boolean;
}

export interface TableData {
  rows: TableRow[];
  total: number;
  capped: boolean;
}

export interface Suggestion {
  text: string;
  type: 'entity' | 'variable';
}

export async function getGroups(layer: string, framework?: string): Promise<BirdGroup[]> {
  const params = new URLSearchParams({ layer });
  if (framework && framework !== 'All') params.set('framework', framework);
  return apiFetch(`/api/bird/groups?${params.toString()}`);
}

export async function getEntities(group: string, layer: string, framework?: string): Promise<BirdEntity[]> {
  const params = new URLSearchParams({ group, layer });
  if (framework && framework !== 'All') params.set('framework', framework);
  return apiFetch(`/api/bird/entities?${params.toString()}`);
}

export async function getEntityDetail(cubeId: string): Promise<BirdEntityDetail> {
  return apiFetch(`/api/bird/entity/${encodeURIComponent(cubeId)}`);
}

export async function getGraph(layer: string, group?: string, framework?: string): Promise<GraphData> {
  const params = new URLSearchParams({ layer });
  if (group) params.set('group', group);
  if (framework && framework !== 'All') params.set('framework', framework);
  return apiFetch(`/api/bird/graph?${params.toString()}`);
}

export async function getChain(cubeId: string): Promise<{ cube_id: string; chain: ChainHop[] }> {
  return apiFetch(`/api/bird/chain/${encodeURIComponent(cubeId)}`);
}

export async function getMembers(domainId: string): Promise<{ domain: BirdGroup; members: MemberItem[] }> {
  return apiFetch(`/api/bird/members/${encodeURIComponent(domainId)}`);
}

export async function getMappingCandidates(type: string, subject: string): Promise<BirdAttribute[]> {
  const params = new URLSearchParams({ type, subject });
  return apiFetch(`/api/bird/mapping-candidates?${params.toString()}`);
}

export async function getTable(params: {
  layer: string;
  group?: string;
  framework?: string;
  limit?: number;
}): Promise<TableData> {
  const p = new URLSearchParams({ layer: params.layer });
  if (params.group) p.set('group', params.group);
  if (params.framework && params.framework !== 'All') p.set('framework', params.framework);
  if (params.limit) p.set('limit', String(params.limit));
  return apiFetch(`/api/bird/table?${p.toString()}`);
}

export async function getSuggestions(q: string, layer: string, scope?: string, exact?: boolean): Promise<Suggestion[]> {
  if (!q || q.length < 2) return [];
  const p = new URLSearchParams({ q, layer });
  if (scope && scope !== 'All') p.set('scope', scope);
  if (exact) p.set('exact', 'true');
  return apiFetch(`/api/bird/suggest?${p.toString()}`);
}
