import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: () => import('src/layouts/MainLayout.vue'),
    children: [
      { path: '', redirect: '/home' },
      { path: 'home', name: 'assistant-home', meta: { title: 'Home', isAssistantHome: true }, component: () => import('src/pages/AssistantHomePage.vue') },
      { path: 'legacy-home', meta: { title: 'Home' }, component: () => import('src/pages/HomePage.vue') },
      // Promoted out of the legacy /tools/* group to a first-class destination
      // beside Home; the old path still resolves so existing links don't break.
      { path: 'dashboard', name: 'dashboard', meta: { title: 'Dashboard' }, component: () => import('src/pages/DashboardPage.vue') },
      { path: 'tools/dashboard', redirect: { name: 'dashboard' } },
      { path: 'standards/glossary', name: 'business-glossary', meta: { title: 'Business Glossary', group: 'Data Marketspace' }, component: () => import('src/pages/BusinessGlossaryPage.vue') },
      { path: 'standards/reference-data', meta: { title: 'Reference Dataspace', group: 'Data Marketspace' }, component: () => import('src/pages/ReferenceDataspace.vue') },
      { path: 'kb/bird', meta: { title: 'BIRD', group: 'Knowledge Base' }, component: () => import('src/pages/BirdKbPage.vue') },
      { path: 'kb/regulatory', meta: { title: 'Regulatory', group: 'Knowledge Base' }, component: () => import('src/pages/RegulatoryKbPage.vue') },
      { path: 'system/settings', meta: { title: 'Settings', group: 'System' }, component: () => import('src/pages/SettingsPage.vue') },
      { path: 'system/about', meta: { title: 'About', group: 'System' }, component: () => import('src/pages/AboutPage.vue') },
      { path: 'system/audit', meta: { title: 'Audit Log', group: 'System' }, component: () => import('src/pages/AuditPage.vue') },
      { path: 'workspace/onboarding', name: 'data-onboarding', meta: { title: 'Data Onboarding', group: 'Workspace' }, component: () => import('src/pages/DataOnboardingPage.vue') },
      { path: 'workspace', meta: { title: 'Asset Workspace', group: 'Workspace' }, component: () => import('src/pages/AssetWorkspace.vue') },
      { path: 'workspace/mapping', name: 'mapping-workspace', meta: { title: 'Mapping Workspace', group: 'Workspace' }, component: () => import('src/pages/MappingWorkspacePage.vue') },
      { path: 'workspace/review', name: 'review-workspace', meta: { title: 'Review Workspace', group: 'Workspace' }, component: () => import('src/pages/ReviewWorkspacePage.vue') },
    ],
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0, left: 0 }),
});

// Land on the Home chat page only when the app is freshly OPENED after the backend restarted
// (its per-process boot id changed). A page reload/refresh (F5 / Ctrl+F5) always keeps the
// current page — even across a restart — so refreshing never yanks you away from your work.
let restartCheckDone = false;
router.beforeEach(async (to) => {
  if (restartCheckDone) return true;
  restartCheckDone = true;
  if (to.name === 'assistant-home') return true;
  const navType = (performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined)?.type;
  const isReload = navType === 'reload';
  try {
    const res = await fetch('/api/health');
    if (!res.ok) return true;
    const { boot_id } = await res.json() as { boot_id?: string };
    if (!boot_id) return true;
    const key = 'adm_server_boot_id';
    const previous = localStorage.getItem(key);
    localStorage.setItem(key, boot_id);
    // A reload records the new boot id but never redirects; only a fresh open goes Home.
    if (!isReload && previous !== null && previous !== boot_id) return { name: 'assistant-home' };
  } catch {
    // Backend unreachable — honour the requested URL rather than forcing Home.
  }
  return true;
});

export default router;
