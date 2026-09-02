<template>
  <q-header class="top-bar-gradient">
    <q-toolbar class="topbar-inner">

      <!-- App identity -->
      <div class="brand-lockup">
        <img src="/adirra-wordmark.png" alt="ADIRRA" class="brand-wordmark" />
      </div>

      <!-- Client logo divider + logo -->
      <div class="topbar-client">
        <div class="topbar-divider" />
        <img src="/alm-partners-logo.png" alt="ALM Partners" class="topbar-client-logo" />
      </div>

      <!-- Breadcrumb — shows which left-nav branch + page the user is on,
           plus (when on a page that publishes one, e.g. Asset Workspace) the
           live drill-down trail (source → dataset → column). Trail segments are
           clickable except the last (the item currently in view). -->
      <div v-if="breadcrumb.title" class="topbar-breadcrumb">
        <div class="topbar-divider" />
        <template v-if="breadcrumb.group">
          <button class="breadcrumb-seg breadcrumb-group" @click="goToGroup(breadcrumb.group)">{{ breadcrumb.group }}</button>
          <q-icon name="chevron_right" size="14px" class="breadcrumb-sep" />
        </template>
        <button class="breadcrumb-seg breadcrumb-current" @click="goToCurrentPage">{{ breadcrumb.title }}</button>
        <template v-for="(seg, i) in elementStore.breadcrumbTrail" :key="i">
          <q-icon name="chevron_right" size="14px" class="breadcrumb-sep" />
          <button
            v-if="i < elementStore.breadcrumbTrail.length - 1"
            class="breadcrumb-seg breadcrumb-dynamic"
            @click="seg.onClick"
          >{{ seg.label }}</button>
          <span v-else class="breadcrumb-dynamic--current" :title="seg.label">{{ seg.label }}</span>
        </template>
      </div>

      <q-space />

      <!-- Session role switcher (Phase E, Step 1) — preliminary, no access
           enforcement. The chosen role is recorded on governance decisions. -->
      <q-btn-dropdown
        flat dense no-caps
        color="white"
        size="sm"
        class="role-switcher q-mr-sm"
        icon="badge"
        :label="roleStore.currentRoleLabel"
      >
        <q-list dense style="min-width: 190px">
          <q-item-label header class="role-switcher-hdr">Acting as</q-item-label>
          <q-item
            v-for="opt in ROLE_OPTIONS"
            :key="opt.value"
            clickable v-close-popup
            :active="roleStore.currentRole === opt.value"
            @click="roleStore.setRole(opt.value)"
          >
            <q-item-section>{{ opt.label }}</q-item-section>
            <q-item-section side v-if="roleStore.currentRole === opt.value">
              <q-icon name="check" size="16px" color="primary" />
            </q-item-section>
          </q-item>
        </q-list>
        <q-tooltip>Session role — no access control yet</q-tooltip>
      </q-btn-dropdown>

      <q-btn
        flat round
        :icon="isFullscreen ? 'fullscreen_exit' : 'fullscreen'"
        color="white"
        class="q-mr-xs"
        size="sm"
        @click="toggleFullscreen"
      >
        <q-tooltip>{{ isFullscreen ? 'Exit full screen' : 'Full screen' }}</q-tooltip>
      </q-btn>

      <q-btn flat round icon="notifications" color="white" class="q-mr-xs" size="sm">
        <q-badge color="negative" floating>0</q-badge>
      </q-btn>

      <q-btn flat round icon="account_circle" color="white" size="sm">
        <q-menu>
          <q-list style="min-width: 150px">
            <q-item clickable>
              <q-item-section>Profile</q-item-section>
            </q-item>
            <q-separator />
            <q-item clickable>
              <q-item-section>Logout</q-item-section>
            </q-item>
          </q-list>
        </q-menu>
      </q-btn>
    </q-toolbar>
  </q-header>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { useRoute, useRouter, type RouteRecordRaw } from 'vue-router';
import { useRoleStore, ROLE_OPTIONS } from 'src/stores/roleStore';
import { useElementStore } from 'src/stores/elementStore';

const roleStore = useRoleStore();
const elementStore = useElementStore();
const route = useRoute();
const router = useRouter();

// Menu branch (meta.group, set per-route in router/index.ts to mirror the
// SideMenu's expansion groups) + current page title, so the header always
// shows the user where they are relative to the left-hand navigation.
const breadcrumb = computed(() => ({
  group: typeof route.meta?.group === 'string' ? route.meta.group : '',
  title: typeof route.meta?.title === 'string' ? route.meta.title : '',
}));

/** First registered route (in router declaration order) belonging to a given
 *  menu group — used so clicking the group segment of the breadcrumb has
 *  somewhere sensible to land, since a group itself isn't a page. */
function firstPathForGroup(group: string): string | null {
  const root = router.options.routes.find((r) => r.path === '/');
  const children = (root?.children ?? []) as RouteRecordRaw[];
  const match = children.find((c) => (c.meta as Record<string, unknown> | undefined)?.group === group);
  return match ? `/${match.path}` : null;
}

function goToGroup(group: string) {
  const path = firstPathForGroup(group);
  if (path && path !== route.path) void router.push(path);
}

function goToCurrentPage() {
  // Re-navigating to the same path (dropping any deep-link query params) is a
  // harmless no-op if nothing changed, but resets state cleanly if the page
  // was opened via a query-string deep link.
  router.push({ path: route.path }).catch(() => { /* ignore duplicate-navigation */ });
}

const isFullscreen = ref(!!document.fullscreenElement);

function handleFullscreenChange() {
  isFullscreen.value = !!document.fullscreenElement;
}

function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen?.();
  } else {
    document.exitFullscreen?.();
  }
}

onMounted(() => document.addEventListener('fullscreenchange', handleFullscreenChange));
onBeforeUnmount(() => document.removeEventListener('fullscreenchange', handleFullscreenChange));
</script>

<style scoped>
.topbar-inner {
  padding: 0 16px;
  height: 50px;
  min-height: 50px;
}

.brand-lockup {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.brand-wordmark {
  display: block;
  height: 28px;
  width: auto;
  flex: 0 0 auto;
  border-bottom: 1px solid #c9a961;
}

.topbar-client {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-left: 18px;
}

.topbar-divider {
  width: 1px;
  height: 28px;
  background: rgba(255,255,255,0.18);
  flex-shrink: 0;
}

.topbar-client-logo {
  height: auto;
  width: 124px;
  object-fit: contain;
  opacity: 0.90;
  filter: brightness(1.1);
}

.topbar-breadcrumb {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-left: 18px;
  min-width: 0;
  overflow: hidden;
}

.topbar-breadcrumb .topbar-divider {
  margin: 0;
}

/* Base for every clickable breadcrumb segment (group / page / dynamic
   source-dataset-column trail) — plain button reset + shared hover affordance
   so every branch in the trail reads and behaves as a link. */
.breadcrumb-seg {
  background: none;
  border: none;
  padding: 0;
  margin: 0;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 220px;
  border-radius: 4px;
  transition: color 0.14s ease, opacity 0.14s ease;
}
.breadcrumb-seg:hover {
  text-decoration: underline;
  opacity: 0.85;
}

.breadcrumb-group {
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.02em;
  color: rgba(226, 240, 255, 0.65);
}

.breadcrumb-sep {
  color: rgba(226, 240, 255, 0.4);
  flex-shrink: 0;
}

.breadcrumb-current {
  font-size: 13px;
  font-weight: 700;
  color: #ffffff;
}

.breadcrumb-dynamic {
  font-size: 13px;
  font-weight: 600;
  color: #7dd3fc;
  background: rgba(125, 211, 252, 0.12);
  border: 1px solid rgba(125, 211, 252, 0.28);
  padding: 2px 9px;
}
.breadcrumb-dynamic:hover {
  color: #e0f2fe;
  background: rgba(125, 211, 252, 0.24);
  text-decoration: none;
  opacity: 1;
}
/* Current drill-down item (the source/dataset/element the user is viewing) —
   highlighted as a filled pill and NOT clickable. */
.breadcrumb-dynamic--current {
  font-size: 13px;
  font-weight: 700;
  color: #06283d;
  background: #7dd3fc;
  border: 1px solid #7dd3fc;
  border-radius: 4px;
  padding: 2px 9px;
  max-width: 220px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  cursor: default;
}
</style>
