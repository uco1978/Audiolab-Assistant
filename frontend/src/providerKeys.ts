import { fetchSettings, Settings, updateSettings } from "./api";

export const KEY_STORAGE_PREFIX = "ppc_provider_key_";

export const API_KEY_FIELD_BY_PROVIDER: Record<string, string> = {
  gemini: "gemini_api_key",
  groq: "groq_api_key",
  openrouter: "openrouter_api_key",
  openai: "openai_api_key",
  anthropic: "anthropic_api_key",
  cohere: "cohere_api_key",
  mistral: "mistral_api_key",
  perplexity: "perplexity_api_key",
  xai: "xai_api_key",
};

export function readStoredProviderKeys(): Record<string, string> {
  const keys: Record<string, string> = {};
  for (const provider of Object.keys(API_KEY_FIELD_BY_PROVIDER)) {
    keys[provider] = (localStorage.getItem(`${KEY_STORAGE_PREFIX}${provider}`) || "").trim();
  }
  return keys;
}

export function writeStoredProviderKey(provider: string, value: string): void {
  localStorage.setItem(`${KEY_STORAGE_PREFIX}${provider}`, value);
}

/**
 * Push browser-stored API keys to the backend when the server is missing them.
 * Returns updated settings when a sync ran, otherwise the current settings (or null).
 */
export async function syncProviderKeysToServer(): Promise<{
  synced: boolean;
  settings: Settings | null;
  providers: string[];
}> {
  const stored = readStoredProviderKeys();
  const localWithKeys = Object.entries(stored).filter(([, v]) => Boolean(v));
  if (localWithKeys.length === 0) {
    return { synced: false, settings: null, providers: [] };
  }

  let settings: Settings;
  try {
    settings = await fetchSettings();
  } catch {
    return { synced: false, settings: null, providers: [] };
  }

  const payload: Record<string, string> = {};
  const providers: string[] = [];
  for (const [provider, keyVal] of localWithKeys) {
    const alreadyOnServer = Boolean(settings.providers?.[provider]);
    if (!alreadyOnServer) {
      payload[API_KEY_FIELD_BY_PROVIDER[provider]] = keyVal;
      providers.push(provider);
    }
  }

  if (providers.length === 0) {
    return { synced: false, settings, providers: [] };
  }

  const updated = await updateSettings(payload);
  return { synced: true, settings: updated, providers };
}
