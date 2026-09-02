import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

describe('AuditPage.vue — structure', () => {
  const src = readFileSync(
    resolve(__dirname, '../src/pages/AuditPage.vue'),
    'utf-8',
  );

  it('renders the Audit Log heading', () => {
    expect(src).toContain('Audit Log');
  });

  it('uses auditStore', () => {
    expect(src).toContain('useAuditStore');
  });

  it('has filter controls for event_class, event_type and subject_id', () => {
    expect(src).toContain('filterClass');
    expect(src).toContain('filterType');
    expect(src).toContain('filterSubjectId');
  });

  it('has expandable payload view', () => {
    expect(src).toContain('payload-pre');
    expect(src).toContain('toggleExpand');
  });

  it('handles empty state with a q-banner', () => {
    expect(src).toContain('No audit events yet');
  });
});

describe('auditStore.ts — structure', () => {
  const src = readFileSync(
    resolve(__dirname, '../src/stores/auditStore.ts'),
    'utf-8',
  );

  it('exports useAuditStore', () => {
    expect(src).toContain('useAuditStore');
  });

  it('exposes loadEvents and loadSummary', () => {
    expect(src).toContain('loadEvents');
    expect(src).toContain('loadSummary');
  });
});
