<template>
  <q-btn flat dense round size="sm" class="dq-share-btn" @click.stop>
    <q-icon name="ios_share" size="14px" />
    <q-tooltip>Share this action</q-tooltip>
    <q-menu anchor="bottom right" self="top right" :offset="[0, 4]">
      <q-list dense style="min-width: 230px">
        <q-item clickable v-close-popup dense @click="handleCopy">
          <q-item-section avatar><q-icon name="content_copy" size="16px" color="cyan-8" /></q-item-section>
          <q-item-section>
            <q-item-label class="text-weight-bold text-body2">Copy to Clipboard</q-item-label>
            <q-item-label caption>Paste into Jira, Teams, Confluence, email…</q-item-label>
          </q-item-section>
        </q-item>
        <q-item clickable v-close-popup dense @click="handleTeams">
          <q-item-section avatar><q-icon name="groups" size="16px" color="indigo-8" /></q-item-section>
          <q-item-section>
            <q-item-label class="text-weight-bold text-body2">Open in Teams</q-item-label>
            <q-item-label caption>Prefilled chat message — pick who to send it to</q-item-label>
          </q-item-section>
        </q-item>
        <q-item clickable v-close-popup dense @click="handleEmail">
          <q-item-section avatar><q-icon name="mail_outline" size="16px" color="deep-orange-8" /></q-item-section>
          <q-item-section>
            <q-item-label class="text-weight-bold text-body2">Email</q-item-label>
            <q-item-label caption>Prefilled subject &amp; body</q-item-label>
          </q-item-section>
        </q-item>
      </q-list>
    </q-menu>
  </q-btn>
</template>

<script setup lang="ts">
// Lets a DQ Insights "Actions to improve" item be handed off to whatever tool
// a team actually tracks work in — no ADIRRA-side ticket/ID tracking, just a
// tool-agnostic copy plus two prefilled deep links. No credentials, no
// stored config, no server-side calls (see tech-debt #2 for the full
// rationale on why a real Jira/Teams API integration was deliberately not
// built here).
import { copyToClipboard, Notify } from 'quasar';
import type { DQAction, DQObservation } from 'src/pages/dqBadgeDisplay';

const props = defineProps<{
  action: DQAction;
  observations: DQObservation[];
  source: string;
  schema: string;
  table: string;
  column: string;
}>();

function identity(): string {
  return `${props.source}.${props.schema}.${props.table}.${props.column}`;
}

function buildText(): string {
  const lines = [
    `DQ Action — ${identity()}`,
    '',
    `Recommended fix: ${props.action.step}`,
    `Recoverable points: +${props.action.points}`,
  ];
  if (props.action.resulting_score != null) {
    const grade = props.action.resulting_grade ? ` (${props.action.resulting_grade})` : '';
    lines.push(`Raises this column to: ${props.action.resulting_score}${grade}`);
  }
  for (const o of props.observations) {
    const text = o.rationale || o.title;
    if (text) lines.push(`Why: ${text}`);
  }
  lines.push('', '— from ADIRRA Data Quality Insights');
  return lines.join('\n');
}

function notify(msg: string) {
  Notify.create({ message: msg, color: 'positive', position: 'top', timeout: 1500, icon: 'check' });
}

function handleCopy() {
  copyToClipboard(buildText());
  notify('Copied — ready to paste into Jira, Teams, Confluence, or email');
}

function handleTeams() {
  const url = `https://teams.microsoft.com/l/chat/0/0?message=${encodeURIComponent(buildText())}`;
  window.open(url, '_blank');
}

function handleEmail() {
  const subject = `DQ Action — ${identity()}`;
  const url = `mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(buildText())}`;
  window.location.href = url;
}
</script>

<style scoped>
.dq-share-btn {
  color: var(--text-2, #86827a);
  flex-shrink: 0;
}
</style>
