export type ReferenceStatus = 'in_review' | 'approved';

export interface ReferenceCode {
  code: string;
  value: string | null;
  meaning: string | null;
  status: ReferenceStatus;
  origin: string | null;
  share_pct: number | null;
  in_source: boolean;
  in_list: boolean;
}

export interface ReferenceField {
  source: string;
  schema: string;
  table: string;
  column: string;
  business_name: string;
  business_name_is_fallback: boolean;
  semantic_type: string;
  status: ReferenceStatus;
  code_source: 'reference_code';
  set_kind: 'local' | 'standard';
  bound_set_id: string | null;
  codes: ReferenceCode[];
  counts: { total: number; documented: number; approved: number; in_review: number; rogue: number; unused: number };
  approved_by: string | null;
  approved_at: string | null;
  asset_link: string;
}

export interface ReferenceSummary {
  total_fields: number;
  status_counts: Record<ReferenceStatus, number>;
  gaps: number;
  approved_codes?: number;
  in_review_codes?: number;
  codes_of_record: number;
}

export interface ReferenceDataspaceResponse {
  summary: ReferenceSummary;
  sources: Array<{
    source: string;
    schemas: Array<{ schema: string; tables: Array<{ table: string; fields: ReferenceField[] }> }>;
  }>;
}

export function displayStatus(field: ReferenceField): 'submitted' | 'approved' {
  return field.status === 'approved' ? 'approved' : 'submitted';
}

export function displayStatusLabel(field: ReferenceField): string {
  return field.status === 'approved' ? 'Approved' : 'In review';
}

export function flattenedFields(data: ReferenceDataspaceResponse | null): ReferenceField[] {
  return data?.sources.flatMap(source => source.schemas.flatMap(schema =>
    schema.tables.flatMap(table => table.fields),
  )) ?? [];
}

export function filterFields(
  fields: ReferenceField[],
  filters: { q?: string; status?: string; semanticType?: string; source?: string[]; schema?: string[]; table?: string[] },
): ReferenceField[] {
  const needle = filters.q?.trim().toLowerCase() ?? '';
  return fields.filter(field => {
    if (filters.status && field.status !== filters.status) return false;
    if (filters.semanticType && field.semantic_type !== filters.semanticType) return false;
    if (filters.source?.length && !filters.source.includes(field.source)) return false;
    if (filters.schema?.length && !filters.schema.includes(`${field.source}|${field.schema}`)) return false;
    if (filters.table?.length && !filters.table.includes(`${field.source}|${field.schema}|${field.table}`)) return false;
    if (!needle) return true;
    return [field.business_name, field.column, ...field.codes.flatMap(code => [code.code, code.meaning ?? ''])]
      .some(value => value.toLowerCase().includes(needle));
  });
}

export interface ReferenceGroup {
  source: string;
  fields: ReferenceField[];
  schemas: Array<{
    schema: string;
    fields: ReferenceField[];
    tables: Array<{ table: string; fields: ReferenceField[] }>;
  }>;
}

export function groupReferenceFields(fields: ReferenceField[]): ReferenceGroup[] {
  const sources = new Map<string, { source: string; fields: ReferenceField[]; schemas: Map<string, { schema: string; fields: ReferenceField[]; tables: Map<string, { table: string; fields: ReferenceField[] }> }> }>();
  for (const field of fields) {
    let source = sources.get(field.source);
    if (!source) {
      source = { source: field.source, fields: [], schemas: new Map() };
      sources.set(field.source, source);
    }
    source.fields.push(field);
    let schema = source.schemas.get(field.schema);
    if (!schema) {
      schema = { schema: field.schema, fields: [], tables: new Map() };
      source.schemas.set(field.schema, schema);
    }
    schema.fields.push(field);
    let table = schema.tables.get(field.table);
    if (!table) {
      table = { table: field.table, fields: [] };
      schema.tables.set(field.table, table);
    }
    table.fields.push(field);
  }
  return [...sources.values()].map(source => ({
    source: source.source,
    fields: source.fields,
    schemas: [...source.schemas.values()].map(schema => ({
      schema: schema.schema,
      fields: schema.fields,
      tables: [...schema.tables.values()],
    })),
  }));
}

export interface ReferenceSetEntry {
  code: string;
  value: string | null;
  meaning: string | null;
  status: string;
}

export interface ReferenceSetSummary {
  id: string;
  name: string;
  kind: 'local' | 'standard';
  standard_ref: string | null;
  status: string;
  entry_count: number;
  entries?: ReferenceSetEntry[];
}

export interface ReferenceSetGroup extends ReferenceSetSummary {
  usedByCount: number;
  fields: ReferenceField[];
}

/**
 * Join reference sets with the fields bound to them (by `bound_set_id`) so the
 * "Browse by set" view can show each set once with a "used by N fields" count.
 */
export function groupBySet(sets: ReferenceSetSummary[], fields: ReferenceField[]): ReferenceSetGroup[] {
  const boundBySet = new Map<string, ReferenceField[]>();
  for (const field of fields) {
    if (!field.bound_set_id) continue;
    const list = boundBySet.get(field.bound_set_id) ?? [];
    list.push(field);
    boundBySet.set(field.bound_set_id, list);
  }
  return sets
    .map(set => {
      const bound = boundBySet.get(set.id) ?? [];
      return { ...set, usedByCount: bound.length, fields: bound };
    })
    .sort((a, b) => b.usedByCount - a.usedByCount || a.name.localeCompare(b.name));
}