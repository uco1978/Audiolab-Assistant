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

/** One-time migration from legacy browser-stored keys into the encrypted DB store. */
export async function migrateLegacyBrowserKeysOnce(): Promise<{
  migrated: boolean;
  providers: string[];
  settings: Settings | null;
}> {
  const flag = "ppc_provider_keys_migrated_v1";
  if (localStorage.getItem(flag) === "1") {
    return { migrated: false, providers: [], settings: null };
  }

  const payload: Record<string, string> = {};
  const providers: string[] = [];
  for (const [provider, field] of Object.entries(API_KEY_FIELD_BY_PROVIDER)) {
    const keyVal = (localStorage.getItem(`${KEY_STORAGE_PREFIX}${provider}`) || "").trim();
    if (keyVal) {
      payload[field] = keyVal;
      providers.push(provider);
    }
  }

  if (providers.length === 0) {
    localStorage.setItem(flag, "1");
    return { migrated: false, providers: [], settings: null };
  }

  let settings: Settings;
  try {
    settings = await fetchSettings();
  } catch {
    return { migrated: false, providers: [], settings: null };
  }

  const missing = providers.filter((p) => !settings.providers?.[p]);
  if (missing.length === 0) {
    // Server already has keys — clear legacy browser copies.
    for (const provider of Object.keys(API_KEY_FIELD_BY_PROVIDER)) {
      localStorage.removeItem(`${KEY_STORAGE_PREFIX}${provider}`);
    }
    localStorage.setItem(flag, "1");
    return { migrated: false, providers: [], settings };
  }

  const toSave: Record<string, string> = {};
  for (const provider of missing) {
    const field = API_KEY_FIELD_BY_PROVIDER[provider];
    const keyVal = (localStorage.getItem(`${KEY_STORAGE_PREFIX}${provider}`) || "").trim();
    if (keyVal) toSave[field] = keyVal;
  }

  const updated = await updateSettings(toSave);
  for (const provider of Object.keys(API_KEY_FIELD_BY_PROVIDER)) {
    localStorage.removeItem(`${KEY_STORAGE_PREFIX}${provider}`);
  }
  localStorage.setItem(flag, "1");
  return { migrated: true, providers: missing, settings: updated };
}
