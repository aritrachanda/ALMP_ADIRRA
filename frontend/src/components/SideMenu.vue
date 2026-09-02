<template>
  <q-list class="text-white side-menu-list">
    <!-- Collapse / expand toggle — inline on the Home row when expanded (see below);
         kept as its own compact row here only for the mini/collapsed state. -->
    <div class="sidebar-toggle-row" v-if="mini">
      <q-btn
        flat round dense
        icon="chevron_right"
        class="sidebar-toggle-btn"
        @click="$emit('toggle-mini')"
      >
        <q-tooltip anchor="center right" self="center left">Expand</q-tooltip>
      </q-btn>
    </div>

    <!-- Home (top-level) -->
    <div class="home-row">
      <q-item
        clickable
        active-class="side-nav-active"
        :class="['side-nav-item', 'home-row-item', { 'side-nav-active': route.name === 'assistant-home' }]"
        @click="goHome"
      >
        <q-item-section avatar>
          <q-icon name="home" />
        </q-item-section>
        <q-item-section v-if="!mini">Home</q-item-section>
        <q-tooltip v-if="mini" anchor="center right" self="center left">Home</q-tooltip>
      </q-item>
      <q-btn
        v-if="!mini"
        flat round dense
        icon="chevron_left"
        class="sidebar-toggle-btn sidebar-toggle-btn--inline"
        @click="$emit('toggle-mini')"
      >
        <q-tooltip anchor="center right" self="center left">Collapse</q-tooltip>
      </q-btn>
    </div>

    <!-- Dashboard sits beside Home, ungrouped: both are landing surfaces
         (Home asks the assistant, Dashboard shows the numbers) while every
         other entry is work you do. -->
    <div class="nav-group nav-group--mini">
      <NavItem to="/dashboard" icon="dashboard" label="Dashboard" :mini="mini" />
    </div>

    <!-- Workspace group -->
    <div class="nav-group" v-if="!mini">
      <q-expansion-item
        icon="policy"
        label="Workspace"
        :header-class="'text-white'"
        default-opened
      >
        <NavItem to="/workspace/onboarding" icon="input" label="Data Onboarding" :mini="mini" />
        <NavItem to="/workspace" icon="layers" label="Asset Workspace" :mini="mini" />
        <NavItem to="/workspace/mapping" icon="alt_route" label="Mapping Workspace" :mini="mini" />
        <NavItem to="/workspace/review" icon="rate_review" label="Review Workspace" :mini="mini" />
      </q-expansion-item>
    </div>
    <div class="nav-group nav-group--mini" v-if="mini">
      <NavItem to="/workspace/onboarding" icon="input" label="Data Onboarding" :mini="mini" />
      <NavItem to="/workspace" icon="layers" label="Asset Workspace" :mini="mini" />
      <NavItem to="/workspace/mapping" icon="alt_route" label="Mapping Workspace" :mini="mini" />
      <NavItem to="/workspace/review" icon="rate_review" label="Review Workspace" :mini="mini" />
    </div>

    <!-- Data Marketspace group -->
    <div class="nav-group" v-if="!mini">
      <q-expansion-item
        icon="rule"
        label="Data Marketspace"
        :header-class="'text-white'"
        default-opened
      >
        <NavItem to="/standards/glossary" icon="auto_stories" label="Business Glossary" :mini="mini" />
        <NavItem to="/standards/reference-data" icon="format_list_bulleted" label="Reference Dataspace" :mini="mini" />
      </q-expansion-item>
    </div>
    <div class="nav-group nav-group--mini" v-if="mini">
      <NavItem to="/standards/glossary" icon="auto_stories" label="Business Glossary" :mini="mini" />
      <NavItem to="/standards/reference-data" icon="format_list_bulleted" label="Reference Dataspace" :mini="mini" />
    </div>

    <!-- Knowledge Base group -->
    <div class="nav-group" v-if="!mini">
      <q-expansion-item
        icon="school"
        label="Knowledge Base"
        :header-class="'text-white'"
        default-opened
      >
        <NavItem to="/kb/bird" icon="hub" label="BIRD" :mini="mini" />
        <NavItem to="/kb/regulatory" icon="balance" label="Regulatory" :mini="mini" />
      </q-expansion-item>
    </div>
    <div class="nav-group nav-group--mini" v-if="mini">
      <NavItem to="/kb/bird" icon="hub" label="BIRD" :mini="mini" />
      <NavItem to="/kb/regulatory" icon="balance" label="Regulatory" :mini="mini" />
    </div>

    <!-- System group -- moved up, right below Knowledge Base -->
    <div class="nav-group" v-if="!mini">
      <q-expansion-item
        icon="settings"
        label="System"
        :header-class="'text-white'"
      >
        <NavItem to="/system/settings" icon="tune" label="Settings" :mini="mini" />
        <NavItem to="/system/audit" icon="history" label="Audit Log" :mini="mini" />
        <NavItem to="/system/about" icon="info" label="About" :mini="mini" />
      </q-expansion-item>
    </div>
    <div class="nav-group nav-group--mini" v-if="mini">
      <NavItem to="/system/settings" icon="tune" label="Settings" :mini="mini" />
      <NavItem to="/system/audit" icon="history" label="Audit Log" :mini="mini" />
      <NavItem to="/system/about" icon="info" label="About" :mini="mini" />
    </div>

  </q-list>
</template>

<script setup lang="ts">
import NavItem from './NavItem.vue';
import { useRouter, useRoute } from 'vue-router';
import { useAssistantChatStore } from 'src/stores/assistantChatStore';

const router = useRouter();
const route = useRoute();
const assistantChat = useAssistantChatStore();

function goHome() {
  assistantChat.clearActiveConversation();
  if (route.name !== 'assistant-home') {
    void router.push('/home');
  }
}

defineProps<{ mini: boolean }>();
defineEmits<{ 'toggle-mini': [] }>();
</script>

<style scoped>
.side-menu-list {
  padding-top: 0.15rem;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.sidebar-toggle-row {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 4px 8px 2px;
}

.home-row {
  display: flex;
  align-items: center;
  gap: 2px;
  padding-right: 6px;
}

.home-row-item {
  flex: 1 1 auto;
  min-width: 0;
}

.sidebar-toggle-btn--inline {
  flex: 0 0 auto;
}

.side-nav-item {
  border-radius: 10px;
  margin: 0.1rem 0.45rem;
  color: rgba(220, 238, 255, 0.95);
  font-size: 13.5px;
  font-weight: 500;
  letter-spacing: 0.01em;
  transition: background 0.15s;
}
.side-nav-item:hover {
  background: rgba(255,255,255,0.08);
}

.side-nav-item :deep(.q-icon) {
  color: rgba(180, 220, 255, 0.90);
}

/* Group / expansion header labels */
.side-nav-item :deep(.q-item__label),
.side-nav-item :deep(.q-expansion-item__header .q-item__label) {
  color: rgba(220, 238, 255, 0.95);
  font-weight: 500;
}

/* Sidebar labels wrap instead of truncating — never cut text off, even when a
   vertical scrollbar narrows the available width. */
:deep(.q-item__section--main) {
  white-space: normal;
  word-break: break-word;
}
:deep(.q-expansion-item > .q-expansion-item__container > .q-item .q-item__label) {
  white-space: normal;
  word-break: break-word;
}
/* Quasar defaults the avatar section to 56px; the icon is only 20px — reclaim the waste */
:deep(.q-item__section--avatar) {
  min-width: 28px;
  padding-right: 8px;
}

.side-nav-active {
  background: linear-gradient(90deg, rgba(100, 210, 210, 0.25) 0%, rgba(255,255,255,0.10) 100%);
  box-shadow: inset 3px 0 0 #5eead4;
  color: #ffffff;
  font-weight: 700;
}
.side-nav-active:hover {
  background: linear-gradient(90deg, rgba(100, 210, 210, 0.32) 0%, rgba(255,255,255,0.14) 100%);
}

.side-nav-active :deep(.q-icon) {
  color: #7eeadf;
}

.sidebar-toggle-btn {
  color: rgba(180, 220, 255, 0.90);
  background: rgba(255,255,255,0.07);
  border: 1px solid rgba(255,255,255,0.10);
  flex: 0 0 auto;
  border-radius: 8px;
}
.sidebar-toggle-btn:hover {
  background: rgba(255,255,255,0.14);
  color: #ffffff;
}

/* ── Nav groups (expanded sidebar) — each group's header + its items sit
   inside a fat, rounded-corner border so it reads as one distinct area;
   the header row gets a more solid backfill than the plain item rows
   beneath it. No `overflow: hidden` here — it was clipping an expanded
   item's own rounded highlight against the box's rounded corners, so the
   header gets its own top-only radius instead. */
.nav-group {
  margin: 0.35rem 0.3rem;
  padding: 2px;
  border: 2px solid rgba(255, 255, 255, 0.16);
  border-radius: 12px;
}
.nav-group :deep(.q-expansion-item__container > .q-item) {
  background: linear-gradient(180deg, rgba(94, 234, 212, 0.20), rgba(94, 234, 212, 0.05));
  border-radius: 10px 10px 0 0;
}
.nav-group :deep(.q-item__label) {
  font-weight: 700;
  font-size: 13px;
  color: rgba(225, 238, 250, 0.95);
}
.nav-group :deep(.q-expansion-item__container > .q-item .q-icon) {
  color: rgba(180, 220, 255, 0.90);
}
.nav-group :deep(.q-expansion-item__toggle-icon) {
  color: rgba(180, 220, 255, 0.80);
}

/* ── Mini (collapsed) sidebar — the bordered/backfilled box above doesn't
   suit the icon-only layout (misaligns with icon placement/spacing), so
   this reverts to a plain, fat separator line between icon clusters. */
.nav-group--mini {
  margin: 0 0.05rem;
  padding: 0.15rem 0 0.55rem;
  border: none;
  border-radius: 0;
  border-bottom: 2px solid rgba(255, 255, 255, 0.20);
}
</style>
