import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const scss = readFileSync(
  resolve(__dirname, '../src/styles/app.scss'),
  'utf-8',
);

describe('app.scss — dropdown color rule scoping', () => {
  it('does NOT have a bare top-level .q-item__label selector', () => {
    // A bare selector would start a line with optional whitespace then .q-item__label
    // without a parent .q-menu prefix on the same line.
    const bareSelector = /^\s*\.q-item__label\b/m;
    expect(scss).not.toMatch(bareSelector);
  });

  it('scopes .q-item__label and .q-item__section inside .q-menu', () => {
    expect(scss).toContain('.q-menu .q-item__label');
    expect(scss).toContain('.q-menu .q-item__section');
  });
});
