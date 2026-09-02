import { defineStore } from 'pinia';
import { ref, computed } from 'vue';

/**
 * Session role model (Phase E, Step 1).
 *
 * A lightweight, non-enforced "who am I acting as" selector — a preliminary step
 * toward role-based access control. The chosen role is recorded on governance
 * actions (definition approve/reject, semantic-type accept/reject) via the
 * `*_by_role` fields, so the audit trail and the two review lanes can attribute
 * decisions. There is NO access enforcement yet.
 */
export type UserRole = 'data_analyst' | 'data_architect' | 'data_steward' | 'business_user';

export const ROLE_OPTIONS: { value: UserRole; label: string }[] = [
  { value: 'data_analyst', label: 'Data Analyst' },
  { value: 'data_architect', label: 'Data Architect' },
  { value: 'data_steward', label: 'Data Steward' },
  { value: 'business_user', label: 'Business User' },
];

const STORAGE_KEY = 'adm.currentRole';
const DEFAULT_ROLE: UserRole = 'data_analyst';

function loadInitialRole(): UserRole {
  try {
    const stored = localStorage.getItem(STORAGE_KEY) as UserRole | null;
    if (stored && ROLE_OPTIONS.some((r) => r.value === stored)) return stored;
  } catch {
    /* localStorage unavailable — fall back to default */
  }
  return DEFAULT_ROLE;
}

export const useRoleStore = defineStore('role', () => {
  const currentRole = ref<UserRole>(loadInitialRole());

  const currentRoleLabel = computed(
    () => ROLE_OPTIONS.find((r) => r.value === currentRole.value)?.label ?? 'Data Analyst',
  );

  function setRole(role: UserRole) {
    currentRole.value = role;
    try {
      localStorage.setItem(STORAGE_KEY, role);
    } catch {
      /* ignore persistence failure */
    }
  }

  return { currentRole, currentRoleLabel, setRole };
});
