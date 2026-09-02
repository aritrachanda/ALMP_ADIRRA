// Single source of truth for the assistant's display-name FALLBACK — only
// used before persona.yaml loads, or if the load fails. The actual, current
// name always comes from personaStore (backed by persona.yaml) — do not
// hardcode a specific persona name here.
export const ASSISTANT_NAME = 'Assistant';
