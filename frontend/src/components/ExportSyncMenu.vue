<template>
  <div class="export-sync-menu">
    <q-btn outline color="primary" no-caps dense class="export-btn">
      <q-icon name="upload" size="14px" class="q-mr-xs" />
      Export / Sync
      <q-icon name="expand_more" size="14px" class="q-ml-xs" />
      <q-menu anchor="bottom right" self="top right" class="export-menu-popup" :offset="[0, 4]">
        <!-- Header -->
        <div class="menu-header q-pa-sm">
          <div class="text-subtitle2 text-weight-bold">Export &amp; Sync</div>
          <div class="text-caption text-grey-6">{{ headerCaption }}</div>
        </div>

        <q-separator />

        <!-- Section 1: Local Exports -->
        <div class="q-pa-sm">
          <div class="section-heading">LOCAL EXPORTS</div>

          <q-item v-if="term || exportData" clickable v-close-popup @click="handlePDF" dense class="menu-row">
            <q-item-section avatar><div class="icon-badge bg-red-1"><q-icon name="picture_as_pdf" color="red" size="16px" /></div></q-item-section>
            <q-item-section>
              <q-item-label class="text-weight-bold text-body2">Print / Save as PDF</q-item-label>
              <q-item-label caption>{{ pdfCaption }}</q-item-label>
            </q-item-section>
          </q-item>

          <q-item clickable v-close-popup @click="handleDownload" dense class="menu-row">
            <q-item-section avatar><div class="icon-badge bg-green-1"><q-icon name="code" color="green" size="16px" /></div></q-item-section>
            <q-item-section>
              <q-item-label class="text-weight-bold text-body2">Download {{ exportLabel }}</q-item-label>
              <q-item-label caption>Current read-only data</q-item-label>
            </q-item-section>
            <q-item-section side>
              <q-btn-toggle
                v-model="exportFmt"
                dense no-caps size="xs"
                toggle-color="primary"
                :options="exportOptions"
                @click.stop
              />
            </q-item-section>
          </q-item>
        </div>

        <q-separator />

        <!-- Section 2: Copy & Share -->
        <div v-if="term || exportData" class="q-pa-sm">
          <div class="section-heading">COPY &amp; SHARE</div>

          <q-item clickable v-close-popup @click="handleCopyMarkdown" dense class="menu-row">
            <q-item-section avatar><div class="icon-badge bg-cyan-1"><q-icon name="content_copy" color="cyan-8" size="16px" /></div></q-item-section>
            <q-item-section>
              <q-item-label class="text-weight-bold text-body2">Copy to Clipboard</q-item-label>
              <q-item-label caption>Ready to paste in Confluence, Jira, Teams or email</q-item-label>
            </q-item-section>
          </q-item>

          <q-item clickable v-close-popup @click="handleCopyRow" dense class="menu-row">
            <q-item-section avatar><div class="icon-badge bg-amber-1"><q-icon name="table_rows" color="amber-9" size="16px" /></div></q-item-section>
            <q-item-section>
              <q-item-label class="text-weight-bold text-body2">{{ copyRowLabel }}</q-item-label>
              <q-item-label caption>{{ copyRowCaption }}</q-item-label>
            </q-item-section>
            <q-item-section side>
              <q-btn-toggle
                v-model="rowFmt"
                dense no-caps size="xs"
                toggle-color="primary"
                :options="[{label:'CSV',value:'csv'},{label:'Tab',value:'tab'}]"
                @click.stop
              />
            </q-item-section>
          </q-item>

          <q-item v-if="term || apiPath" clickable v-close-popup @click="handleCopyURL" dense class="menu-row">
            <q-item-section avatar><div class="icon-badge bg-green-1"><q-icon name="link" color="green" size="16px" /></div></q-item-section>
            <q-item-section>
              <q-item-label class="text-weight-bold text-body2">Copy API URL</q-item-label>
              <q-item-label caption class="api-url-text">{{ apiUrl }}</q-item-label>
            </q-item-section>
          </q-item>
        </div>
      </q-menu>
    </q-btn>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { copyToClipboard, Notify } from 'quasar';
import type { GlossaryTerm } from 'src/types';
import { getStatusTone } from 'src/utils/statusDisplay';

const props = defineProps<{
  term?: GlossaryTerm;
  exportData?: unknown;
  exportDetail?: unknown;
  exportFilename?: string;
  exportTitle?: string;
  apiPath?: string;
}>();

const exportFmt = ref<'json' | 'xml' | 'csv'>('json');
const rowFmt = ref<'csv' | 'tab'>('csv');

const apiUrl = computed(() => props.term
  ? `${window.location.origin}/api/glossary/v2/terms/${props.term.id ?? ''}`
  : (props.apiPath ? `${window.location.origin}${props.apiPath}` : ''));
const headerCaption = computed(() => props.term ? 'Choose an action for this glossary term' : 'Choose an action for this register');
const pdfCaption = computed(() => props.term ? 'Formatted term summary' : 'Formatted register summary');
const copyRowLabel = computed(() => props.term ? 'Copy as Single Row' : 'Copy as Rows');
const copyRowCaption = computed(() => props.term ? 'Comma or tab-separated format with headers' : 'All rows, comma or tab-separated with headers');
const exportOptions = computed(() => props.term
  ? [{ label: 'JSON', value: 'json' }, { label: 'XML', value: 'xml' }]
  : [{ label: 'CSV', value: 'csv' }, { label: 'JSON', value: 'json' }]);
const exportLabel = computed(() => props.term ? 'JSON / XML' : 'CSV / JSON');

// region Helpers
function toArr(v: unknown): string[] {
  if (Array.isArray(v)) return v as string[];
  if (typeof v === 'string' && v.trim()) return v.split(',').map(s => s.trim());
  return [];
}

function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function originSummary(): string {
  const refs = props.term?.related_objects ?? [];
  if (!refs.length) return 'Not linked.';
  const known: Record<string, string> = { bird: 'BIRD', crdm: 'CRDM' };
  const seen = new Set<string>();
  const labels: string[] = [];
  for (const r of refs) {
    const parts = r.split('|');
    if (parts.length < 2) continue;
    const label = known[parts[1].toLowerCase()] ?? parts[1];
    if (!seen.has(label)) { seen.add(label); labels.push(label); }
  }
  return labels.length ? labels.join(' | ') : 'Not linked.';
}

function notify(msg: string) {
  Notify.create({ message: msg, color: 'positive', position: 'top', timeout: 1500, icon: 'check' });
}
// endregion

// region PDF
function dataRows(): Array<Record<string, unknown>> {
  return Array.isArray(props.exportData) ? props.exportData as Array<Record<string, unknown>> : [];
}

function dataHeaders(rows: Array<Record<string, unknown>>): string[] {
  return [...new Set(rows.flatMap(row => Object.keys(row)))];
}

function printHtml(html: string) {
  const win = window.open('', '_blank', 'width=900,height=700');
  if (!win) return;
  win.document.write(html);
  win.document.close();
  win.focus();
}

function detailRows(): Array<Record<string, unknown>> {
  return Array.isArray(props.exportDetail) ? props.exportDetail as Array<Record<string, unknown>> : [];
}

function registerDetailBody(): { body: string; count: number } {
  const sets = detailRows();
  const body = sets.map(set => {
    const codes = Array.isArray(set.codes) ? set.codes as Array<Record<string, unknown>> : [];
    const rowsHtml = codes.length
      ? codes.map(c =>
          `<tr><td><code>${esc(String(c.code ?? ''))}</code></td><td>${esc(String(c.value ?? ''))}</td><td>${esc(String(c.meaning ?? ''))}</td><td>${esc(String(c.status ?? ''))}</td></tr>`
        ).join('')
      : '<tr><td colspan="4" class="empty">No codes.</td></tr>';
    return `<div class="cs">
<div class="cs-head"><span class="cs-name">${esc(String(set.business_name ?? ''))}</span><span class="cs-badge">${esc(String(set.status ?? ''))}</span></div>
<div class="cs-path">${esc(String(set.path ?? ''))}${set.semantic_type ? ' · ' + esc(String(set.semantic_type)) : ''}</div>
<table><thead><tr><th>Code</th><th>Value</th><th>Meaning</th><th>Status</th></tr></thead><tbody>${rowsHtml}</tbody></table>
</div>`;
  }).join('');
  return { body, count: sets.length };
}

function handlePDFData() {
  const useDetail = detailRows().length > 0;
  const rows = dataRows();
  const headers = dataHeaders(rows);
  const title = props.exportTitle ?? 'ADIRRA Export';
  const now = new Date();
  const dateStr = now.toLocaleDateString('en-GB', { year: 'numeric', month: 'long', day: 'numeric' })
    + ', ' + now.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  let bodyHtml: string;
  let count: number;
  if (useDetail) {
    const detail = registerDetailBody();
    bodyHtml = detail.body;
    count = detail.count;
  } else {
    const thead = headers.map(h => `<th>${esc(h)}</th>`).join('');
    const tbody = rows.map(r =>
      `<tr>${headers.map(h => `<td>${esc(String(r[h] ?? ''))}</td>`).join('')}</tr>`
    ).join('');
    bodyHtml = `<table><thead><tr>${thead}</tr></thead><tbody>${tbody}</tbody></table>`;
    count = rows.length;
  }
  const html = `<!DOCTYPE html><html><head><meta charset="utf-8">
<title>${esc(title)} — ADIRRA</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:#1e293b;margin:0;padding:36px 44px;}
h1{font-size:24px;font-weight:700;margin:6px 0 4px;color:#0f172a;}
.sub{font-size:12px;color:#64748b;margin-bottom:18px;}
table{border-collapse:collapse;width:100%;font-size:12px;}
th{text-align:left;background:#f1f5f9;color:#475569;font-weight:700;text-transform:uppercase;letter-spacing:.05em;font-size:10px;padding:7px 9px;border-bottom:2px solid #e2e8f0;}
td{padding:6px 9px;border-bottom:1px solid #eef2f6;vertical-align:top;}
tr:nth-child(even) td{background:#fafbfc;}
code{font-family:"SFMono-Regular",Consolas,monospace;font-size:11px;}
.empty{color:#94a3b8;font-style:italic;}
.cs{margin-bottom:20px;break-inside:avoid;}
.cs-head{display:flex;align-items:center;gap:10px;margin-bottom:2px;}
.cs-name{font-size:14px;font-weight:700;color:#0f172a;}
.cs-badge{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#0d5c54;background:#0d5c541a;padding:2px 8px;border-radius:999px;}
.cs-path{font-size:11px;color:#64748b;margin-bottom:6px;}
.foot{margin-top:22px;font-size:11px;color:#94a3b8;border-top:1px solid #e2e8f0;padding-top:10px;}
@page{margin:14mm;}
</style></head><body>
<div style="background:#0d5c54;color:#fff;padding:7px 13px;border-radius:6px;font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;display:inline-block;margin-bottom:10px;">Reference Register</div>
<h1>${esc(title)}</h1>
<div class="sub">${count} code set${count === 1 ? '' : 's'} · exported ${dateStr}</div>
${bodyHtml}
<div class="foot">Generated ${dateStr} by ADIRRA</div>
<script>window.addEventListener("load",function(){window.print();});<\u002fscript>
</body></html>`;
  printHtml(html);
}

// region PDF (term)
function handlePDF() {
  if (!props.term) { handlePDFData(); return; }
  const t = props.term;
  const now = new Date();
  const dateStr = now.toLocaleDateString('en-GB', { year: 'numeric', month: 'long', day: 'numeric' })
    + ', ' + now.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  const tone = getStatusTone(t.status || 'draft');
  const statusColor = tone.textColor;
  const statusBg = tone.bgColor;
  const statusBorder = tone.borderColor;

  const sections = [
    { label: 'Business Description', value: t.business_description },
    { label: 'Detailed Description', value: t.detailed_description },
    { label: 'Regulatory Context (CRR3)', value: t.CRR_context },
    { label: 'DPM 2.0 Context', value: t.DPM_context },
    { label: 'Synonyms', value: toArr(t.synonyms).join(', ') },
    { label: 'Tags', value: toArr(t.tags).join(', ') },
    { label: 'Related Objects', value: toArr(t.related_objects).join('\n') },
  ];
  const sectionsHtml = sections.map(s =>
    `<div class="sh">${esc(s.label)}</div><div class="sb">${s.value ? esc(s.value) : '<span class="empty">Not set.</span>'}</div>`
  ).join('');

  const html = `<!DOCTYPE html><html><head><meta charset="utf-8">
<title>${esc(t.title)} — Business Glossary</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:#1e293b;margin:0;padding:40px 52px;max-width:860px;}
h1{font-size:28px;font-weight:700;margin:4px 0 16px;color:#0f172a;}
.badge{display:inline-block;padding:4px 10px;border-radius:999px;font-size:12px;font-weight:600;}
.sh{font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#94a3b8;margin:24px 0 6px;}
.sb{font-size:14px;line-height:1.75;color:#334155;white-space:pre-wrap;}
.empty{color:#94a3b8;font-style:italic;}
.hr{height:1px;background:#e2e8f0;margin:22px 0;}
.foot{margin-top:28px;font-size:11px;color:#94a3b8;border-top:1px solid #e2e8f0;padding-top:12px;}
@page{margin:0;}
</style></head><body>
<div style="background:#1e40af;color:#fff;padding:8px 14px;border-radius:6px;font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;display:inline-block;margin-bottom:10px;">Business Glossary</div>
<h1>${esc(t.title)}</h1>
<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
<span style="font-size:16px;color:${statusColor};">●</span>
<span style="font-weight:700;">${esc(t.domain || '—')}</span>
<span style="color:#6b7280;">›</span>
<span style="font-weight:700;">${esc(t.category || '—')}</span>
<span class="badge" style="background:${statusBg};color:${statusColor};border:1px solid ${statusBorder};">${esc(tone.label)}</span>
</div>
<div style="font-size:12px;color:#64748b;margin-bottom:6px;">Steward: ${esc(t.steward || 'Not assigned')} &nbsp;|&nbsp; Origin: ${esc(originSummary())}</div>
<div class="hr"></div>
${sectionsHtml}
<div class="hr"></div>
<div class="sh">Reference Details</div>
<table style="border-collapse:collapse;width:100%;">
<tr><td style="font-weight:600;color:#475569;padding:5px 14px 5px 0;font-size:13px;">Term ID</td><td style="font-size:13px;"><code>${esc(t.id)}</code></td></tr>
<tr><td style="font-weight:600;color:#475569;padding:5px 14px 5px 0;font-size:13px;">API Endpoint</td><td style="font-size:13px;"><code>${esc(apiUrl.value)}</code></td></tr>
</table>
<div class="foot">Generated ${dateStr} by ADIRRA</div>
<script>window.addEventListener("load",function(){window.print();});<\u002fscript>
</body></html>`;

  const win = window.open('', '_blank', 'width=900,height=700');
  if (!win) return;
  win.document.write(html);
  win.document.close();
  win.focus();
}
// endregion

// region JSON / XML download
function handleDownload() {
  if (!props.term) {
    const data = props.exportData ?? [];
    const filename = props.exportFilename ?? 'adirra_export';
    if (exportFmt.value === 'csv') {
      const rows = Array.isArray(data) ? data as Array<Record<string, unknown>> : [];
      const headers = [...new Set(rows.flatMap(row => Object.keys(row)))];
      const quote = (value: unknown) => `"${String(value ?? '').replaceAll('"', '""')}"`;
      const csv = [headers.join(','), ...rows.map(row => headers.map(key => quote(row[key])).join(','))].join('\n');
      downloadBlob(csv, 'text/csv;charset=utf-8', `${filename}.csv`);
    } else {
      downloadBlob(JSON.stringify(data, null, 2), 'application/json', `${filename}.json`);
    }
    return;
  }
  const t = props.term;
  const now = new Date();
  const ds = now.toISOString().slice(0, 10);

  if (exportFmt.value === 'xml') {
    const xml = buildXML(t, now);
    downloadBlob(xml, 'application/xml', `${t.id}_${ds}_export.xml`);
  } else {
    const payload = {
      meta: { schema_version: '1.0', source: 'ADIRRA Business Glossary', exported: now.toISOString() },
      term: {
        id: t.id, title: t.title, domain: t.domain, category: t.category,
        status: t.status, steward: t.steward || null, origin: originSummary(),
        business_description: t.business_description,
        detailed_description: t.detailed_description || null,
        synonyms: toArr(t.synonyms), related_objects: toArr(t.related_objects),
        tags: toArr(t.tags), CRR_context: t.CRR_context || null,
        DPM_context: t.DPM_context || null,
        ai_generated_fields: toArr(t.ai_generated_fields),
        api_endpoint: apiUrl.value,
      },
    };
    downloadBlob(JSON.stringify(payload, null, 2), 'application/json', `${t.id}_${ds}_export.json`);
  }
}

function buildXML(t: GlossaryTerm, now: Date): string {
  const xt = (name: string, val: string) => val ? `<${name}>${esc(val)}</${name}>` : `<${name}/>`;
  const list = (name: string, items: string[], child: string) =>
    items.length ? `<${name}>${items.map(i => xt(child, i)).join('')}</${name}>` : `<${name}/>`;
  return `<?xml version="1.0" encoding="UTF-8"?>
<glossaryExport>
  <meta>
    ${xt('schemaVersion', '1.0')}
    ${xt('source', 'ADIRRA Business Glossary')}
    ${xt('exported', now.toISOString())}
  </meta>
  <term>
    ${xt('id', t.id)}
    ${xt('title', t.title)}
    ${xt('domain', t.domain || '')}
    ${xt('category', t.category || '')}
    ${xt('status', t.status || '')}
    ${xt('steward', t.steward || '')}
    ${xt('origin', originSummary())}
    ${xt('businessDescription', t.business_description || '')}
    ${xt('detailedDescription', t.detailed_description || '')}
    ${list('synonyms', toArr(t.synonyms), 'synonym')}
    ${list('relatedObjects', toArr(t.related_objects), 'object')}
    ${list('tags', toArr(t.tags), 'tag')}
    ${xt('crrContext', t.CRR_context || '')}
    ${xt('dpmContext', t.DPM_context || '')}
    ${list('aiGeneratedFields', toArr(t.ai_generated_fields), 'field')}
    ${xt('apiEndpoint', apiUrl.value)}
  </term>
</glossaryExport>`;
}

function downloadBlob(content: string, mime: string, filename: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 500);
}
// endregion

// region Copy & Share
function copyDataMarkdown() {
  const rows = dataRows();
  const headers = dataHeaders(rows);
  const title = props.exportTitle ?? 'ADIRRA Export';
  const cell = (v: unknown) => String(v ?? '').replace(/\r?\n/g, ' ').replace(/\|/g, '\\|');
  const md = [
    `## ${title}`, '',
    `| ${headers.join(' | ')} |`,
    `| ${headers.map(() => '---').join(' | ')} |`,
    ...rows.map(r => `| ${headers.map(h => cell(r[h])).join(' | ')} |`),
    '', `_${rows.length} row${rows.length === 1 ? '' : 's'} · ADIRRA_`,
  ].join('\n');
  copyToClipboard(md);
  notify('Copied as Markdown');
}

function copyDataRows() {
  const rows = dataRows();
  const headers = dataHeaders(rows);
  let text: string;
  if (rowFmt.value === 'tab') {
    const e = (v: unknown) => String(v ?? '').replace(/\r?\n/g, ' ');
    text = [headers.join('\t'), ...rows.map(r => headers.map(h => e(r[h])).join('\t'))].join('\n');
  } else {
    const e = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`;
    text = [headers.map(e).join(','), ...rows.map(r => headers.map(h => e(r[h])).join(','))].join('\n');
  }
  copyToClipboard(text);
  notify(`Copied ${rows.length} row${rows.length === 1 ? '' : 's'} as ${rowFmt.value === 'tab' ? 'tab-separated' : 'CSV'}`);
}

function handleCopyMarkdown() {
  if (!props.term) { copyDataMarkdown(); return; }
  const t = props.term;
  const status = (t.status || 'draft').charAt(0).toUpperCase() + (t.status || 'draft').slice(1);
  const lines = [
    `## ${t.title}`, '',
    '### Summary',
    `- Domain: ${t.domain || '—'}`,
    `- Category: ${t.category || '—'}`,
    `- Status: ${status}`,
    `- Origin: ${originSummary()}`,
    `- Steward: ${t.steward || 'Not assigned'}`,
  ];

  const sections: { label: string; value: string }[] = [
    { label: 'Business Description', value: t.business_description || '' },
    { label: 'Detailed Description', value: t.detailed_description || '' },
    { label: 'Regulatory Context (CRR3)', value: t.CRR_context || '' },
    { label: 'DPM 2.0 Context', value: t.DPM_context || '' },
  ];
  for (const s of sections) {
    lines.push('', `### ${s.label}`, s.value || 'Not set.');
  }

  const synonyms = toArr(t.synonyms);
  const tags = toArr(t.tags);
  lines.push('', '### Synonyms & Tags');
  if (synonyms.length) { lines.push('Synonyms:'); synonyms.forEach(s => lines.push(`- ${s}`)); }
  if (tags.length) { if (synonyms.length) lines.push(''); lines.push('Tags:'); tags.forEach(tg => lines.push(`- ${tg}`)); }
  if (!synonyms.length && !tags.length) lines.push('None set.');

  const relObjs = toArr(t.related_objects);
  lines.push('', '### Related Objects');
  if (relObjs.length) relObjs.forEach(r => lines.push(`- ${r}`));
  else lines.push('No related catalog objects linked.');

  lines.push('', '### Reference', `- Term ID: ${t.id}`, `- API Endpoint: ${apiUrl.value}`, '- Source: ADIRRA Business Glossary');

  copyToClipboard(lines.join('\n'));
  notify('Copied as Markdown');
}

function handleCopyRow() {
  if (!props.term) { copyDataRows(); return; }
  const t = props.term;
  const headers = ['id', 'title', 'domain', 'category', 'status', 'steward', 'origin',
    'business_description', 'detailed_description', 'synonyms', 'related_objects', 'tags',
    'CRR_context', 'DPM_context', 'ai_generated_fields', 'api_endpoint'];
  const values = [
    t.id, t.title, t.domain, t.category, t.status, t.steward, originSummary(),
    t.business_description, t.detailed_description,
    toArr(t.synonyms).join('; '), toArr(t.related_objects).join('; '),
    toArr(t.tags).join('; '), t.CRR_context, t.DPM_context,
    toArr(t.ai_generated_fields).join('; '), apiUrl.value,
  ];

  let text: string;
  if (rowFmt.value === 'tab') {
    const escTab = (v: string | null | undefined) => String(v ?? '').replace(/\r?\n/g, ' ');
    text = headers.map(escTab).join('\t') + '\n' + values.map(escTab).join('\t');
  } else {
    const escCsv = (v: string | null | undefined) => `"${String(v ?? '').replace(/"/g, '""')}"`;
    text = headers.map(escCsv).join(',') + '\n' + values.map(escCsv).join(',');
  }
  copyToClipboard(text);
  notify(`Copied as ${rowFmt.value === 'tab' ? 'tab-separated' : 'CSV'} row`);
}

function handleCopyURL() {
  copyToClipboard(apiUrl.value);
  notify('Copied API URL');
}
// endregion
</script>

<style scoped lang="scss">
.export-btn {
  font-size: 13px;
  font-weight: 600;
  padding: 6px 14px;
  border-radius: 10px;
}

.export-menu-popup {
  min-width: 380px;
  max-width: 420px;
  border-radius: 14px !important;
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.13), 0 6px 20px rgba(0, 0, 0, 0.08) !important;
}

.menu-header {
  padding: 12px 14px 8px;
}

.section-heading {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.13em;
  color: #94a3b8;
  text-transform: uppercase;
  margin-bottom: 4px;
  padding-left: 4px;
}

.menu-row {
  border-radius: 10px;
  margin-bottom: 2px;
}

.icon-badge {
  width: 34px;
  height: 34px;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.amber-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #f59e0b;
  box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.15);
  animation: pulse-dot 2s infinite;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.endpoint-box {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 10px 14px;
  display: flex;
  align-items: center;
}

.endpoint-box-azure {
  background: #f0f9ff;
  border-color: #bae6fd;
}

.payload-preview {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 14px;
  max-height: 220px;
  overflow: auto;
  font-size: 11px;
  line-height: 1.55;
  color: #334155;
  white-space: pre-wrap;
  word-break: break-word;
}

.api-url-text {
  font-family: monospace;
  font-size: 10px;
  word-break: break-all;
}
</style>
