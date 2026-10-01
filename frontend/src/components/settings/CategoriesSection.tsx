import { useEffect, useState } from "react";

import { getCategories, resetCategories, saveCategories, type CategorySettings } from "../../api";

interface Props {
  idToken: string;
}

// The signed-in user's own fact categories — add/remove chips, each change
// saved immediately, no separate Save button.
function CategoriesSection({ idToken }: Props) {
  const [settings, setSettings] = useState<CategorySettings | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getCategories(idToken)
      .then(setSettings)
      .catch(() => setError("Couldn't load your categories."));
  }, [idToken]);

  // Every change is saved straight away, like connecting an account.
  async function apply(change: () => Promise<CategorySettings>, failure: string) {
    setBusy(true);
    setError(null);
    try {
      setSettings(await change());
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : failure);
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function add(category: string) {
    if (!settings) return;
    const ok = await apply(
      () => saveCategories(idToken, [...settings.categories, category]),
      "Couldn't add it.",
    );
    if (ok) setName("");
  }

  function remove(category: string) {
    if (!settings) return;
    apply(
      () =>
        saveCategories(
          idToken,
          settings.categories.filter((c) => c !== category),
        ),
      "Couldn't remove it.",
    );
  }

  const suggestedToAdd = settings?.suggested.filter((c) => !settings.categories.includes(c)) ?? [];
  const full = settings !== null && settings.categories.length >= settings.max;

  return (
    <div className="settings-field">
      <span className="settings-label">Fact categories</span>
      {settings && (
        <>
          <div className="category-chips">
            {settings.categories.map((c) => (
              <span key={c} className="category-chip">
                {c}
                <button
                  aria-label={`Remove ${c}`}
                  onClick={() => remove(c)}
                  disabled={busy || settings.categories.length <= 1}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
          <div className="category-add">
            <input
              placeholder="New category (e.g. risk)"
              value={name}
              maxLength={30}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && name.trim() && !full && add(name)}
              aria-invalid={!!error}
            />
            <button onClick={() => add(name)} disabled={!name.trim() || full || busy}>
              Add
            </button>
          </div>
          {suggestedToAdd.length > 0 && (
            <div className="category-chips">
              {suggestedToAdd.map((c) => (
                <button
                  key={c}
                  className="category-suggested"
                  onClick={() => add(c)}
                  disabled={full || busy}
                >
                  + {c}
                </button>
              ))}
            </div>
          )}
          <small className={error ? "settings-hint invalid" : "settings-hint"}>
            {error ||
              `Up to ${settings.max}. Removing one keeps its facts; they stay listed under the old name.`}
          </small>
          <button
            onClick={() => apply(() => resetCategories(idToken), "Couldn't reset.")}
            disabled={!settings.customized || busy}
          >
            Reset to suggested
          </button>
        </>
      )}
      {!settings &&
        (error ? (
          <small className="settings-hint invalid">{error}</small>
        ) : (
          <small className="settings-hint">Loading…</small>
        ))}
    </div>
  );
}

export default CategoriesSection;
