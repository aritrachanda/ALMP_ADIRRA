import { onMounted, ref } from 'vue';

const THEME_KEY = 'adm-theme';
const dark = ref(false);
let initialized = false;

function applyThemeClass(nextDark: boolean) {
  if (typeof document === 'undefined') return;
  document.body.classList.toggle('dark', nextDark);
}

function initTheme() {
  if (initialized || typeof window === 'undefined') return;
  // Dark mode dropped — always light; clear any stale stored preference
  window.localStorage.removeItem(THEME_KEY);
  dark.value = false;
  applyThemeClass(false);
  initialized = true;
}

export function useTheme() {
  onMounted(() => {
    initTheme();
  });

  const toggleTheme = () => {
    dark.value = !dark.value;
    applyThemeClass(dark.value);
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(THEME_KEY, dark.value ? 'dark' : 'light');
    }
  };

  return { dark, toggleTheme };
}
