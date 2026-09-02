/**
 * Deep-link resolution for the Asset Workspace (Phase 4).
 *
 * Pure helpers that turn a `/workspace?source=&schema=&table=&column=&tab=` query into a validated
 * selection plan. Kept side-effect-free so the component wiring stays thin and unit-testable.
 */
import type { TableEntry } from 'src/api/element';

export interface DeepLinkQuery {
  source: string | null;
  schema: string | null;
  table: string | null;
  column: string | null;
  tab: string | null;
}

export type DeepLinkLevel = 'source' | 'table' | 'column';

export interface ResolvedDeepLink {
  level: DeepLinkLevel;
  table: string | null;
  schema: string | null;
  column: string | null;
}

/** Tab keys the Asset Workspace recognizes (`definition` is healed to `interpretation`). */
const KNOWN_TABS = new Set(['profile', 'interpretation', 'refdata', 'observations', 'mapping', 'history']);

function firstString(value: unknown): string | null {
  if (Array.isArray(value)) return value.length ? firstString(value[0]) : null;
  return typeof value === 'string' && value.length > 0 ? value : null;
}

/** Normalize a raw route query into a `DeepLinkQuery`, healing and validating the tab. */
export function parseDeepLinkQuery(query: Record<string, unknown>): DeepLinkQuery {
  const rawTab = firstString(query.tab);
  const healedTab = rawTab === 'definition' ? 'interpretation' : rawTab;
  const tab = healedTab && KNOWN_TABS.has(healedTab) ? healedTab : null;
  return {
    source: firstString(query.source),
    schema: firstString(query.schema),
    table: firstString(query.table),
    column: firstString(query.column),
    tab,
  };
}

/**
 * Whether the deep-link query should take precedence over the stored selection: only when it names
 * a `source` that exists in the loaded source list.
 */
export function shouldApplyDeepLink(parsed: DeepLinkQuery, sources: string[]): boolean {
  return !!parsed.source && sources.includes(parsed.source);
}

/**
 * Validate `table`/`column` against the loaded tables and return the deepest valid level.
 * Matches `schema` when provided; otherwise the first table with the given name.
 */
export function resolveTableColumn(
  tables: TableEntry[],
  table: string | null,
  schema: string | null,
  column: string | null,
): ResolvedDeepLink {
  if (!table) return { level: 'source', table: null, schema: null, column: null };
  const match = tables.find(t => t.table_name === table && (!schema || t.schema === schema));
  if (!match) return { level: 'source', table: null, schema: null, column: null };
  if (!column) return { level: 'table', table: match.table_name, schema: match.schema, column: null };
  const hasColumn = match.columns.some(c => c.name === column);
  if (!hasColumn) return { level: 'table', table: match.table_name, schema: match.schema, column: null };
  return { level: 'column', table: match.table_name, schema: match.schema, column };
}
