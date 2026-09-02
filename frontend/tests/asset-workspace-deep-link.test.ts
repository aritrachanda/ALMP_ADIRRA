import { describe, expect, it } from 'vitest';
import type { TableEntry } from '../src/api/element';
import {
  parseDeepLinkQuery,
  resolveTableColumn,
  shouldApplyDeepLink,
} from '../src/pages/assetWorkspaceDeepLink';

function table(schema: string, name: string, columns: string[]): TableEntry {
  return {
    schema,
    table_name: name,
    description: null,
    row_count: null,
    columns: columns.map(c => ({ name: c, data_type: 'text' })),
  };
}

const TABLES: TableEntry[] = [
  table('src', 'accounts', ['currency', 'balance']),
  table('src', 'customers', ['country']),
  table('other', 'accounts', ['legacy_ccy']),
];

describe('parseDeepLinkQuery', () => {
  it('parses a full field deep link', () => {
    expect(parseDeepLinkQuery({ source: 'banking', schema: 'src', table: 'accounts', column: 'currency', tab: 'refdata' }))
      .toEqual({ source: 'banking', schema: 'src', table: 'accounts', column: 'currency', tab: 'refdata' });
  });

  it('heals the legacy definition tab to interpretation', () => {
    expect(parseDeepLinkQuery({ source: 'banking', tab: 'definition' }).tab).toBe('interpretation');
  });

  it('drops an unknown tab', () => {
    expect(parseDeepLinkQuery({ source: 'banking', tab: 'bogus' }).tab).toBeNull();
  });

  it('returns nulls for missing params and takes the first value of an array', () => {
    expect(parseDeepLinkQuery({})).toEqual({ source: null, schema: null, table: null, column: null, tab: null });
    expect(parseDeepLinkQuery({ source: ['banking', 'other'] }).source).toBe('banking');
  });
});

describe('shouldApplyDeepLink (precedence over localStorage)', () => {
  it('applies when the source is present and known', () => {
    expect(shouldApplyDeepLink(parseDeepLinkQuery({ source: 'banking' }), ['banking', 'markets'])).toBe(true);
  });

  it('falls back when the source is unknown or absent', () => {
    expect(shouldApplyDeepLink(parseDeepLinkQuery({ source: 'ghost' }), ['banking'])).toBe(false);
    expect(shouldApplyDeepLink(parseDeepLinkQuery({ table: 'accounts' }), ['banking'])).toBe(false);
  });
});

describe('resolveTableColumn', () => {
  it('resolves a full valid field to column level', () => {
    expect(resolveTableColumn(TABLES, 'accounts', 'src', 'currency'))
      .toEqual({ level: 'column', table: 'accounts', schema: 'src', column: 'currency' });
  });

  it('stops at the dataset when the column does not exist', () => {
    expect(resolveTableColumn(TABLES, 'accounts', 'src', 'ghost'))
      .toEqual({ level: 'table', table: 'accounts', schema: 'src', column: null });
  });

  it('falls back to source level when the table does not exist', () => {
    expect(resolveTableColumn(TABLES, 'ghost', 'src', 'currency').level).toBe('source');
  });

  it('falls back to source level when no table is given', () => {
    expect(resolveTableColumn(TABLES, null, null, null).level).toBe('source');
  });

  it('matches the schema when provided', () => {
    // wrong schema for this column -> the 'other.accounts' table lacks 'currency'
    expect(resolveTableColumn(TABLES, 'accounts', 'other', 'currency'))
      .toEqual({ level: 'table', table: 'accounts', schema: 'other', column: null });
    // matching schema resolves the right table
    expect(resolveTableColumn(TABLES, 'accounts', 'other', 'legacy_ccy'))
      .toEqual({ level: 'column', table: 'accounts', schema: 'other', column: 'legacy_ccy' });
  });

  it('matches the first table by name when no schema is given', () => {
    expect(resolveTableColumn(TABLES, 'accounts', null, 'currency'))
      .toEqual({ level: 'column', table: 'accounts', schema: 'src', column: 'currency' });
  });
});
