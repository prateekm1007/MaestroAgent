import { useState, useEffect } from "react";
import { useAppStore } from "../store/appStore";
import { api, checkAuthStatus, loginWithApiKey } from "../lib/api";
import { X, KeyRound, LogIn, ShieldCheck, AlertCircle } from "lucide-react";

/**
 * LoginModal — shown when auth is enabled and the user isn't authenticated.
 *
 * Flow:
 *   1. On app load, call /api/auth/status.
 *   2. If auth is enabled and not authenticated, show this modal.
 *   3. User pastes their API key (from api_key.txt or keyring).
 *   4. On success, store the key in localStorage + close modal.
 *
 * For OAuth (v1.1): a "Sign in with Supabase/Auth0" button will appear
 * when an OAuth provider is configured.
 */
export default function LoginModal() {
  const [open, setOpen] = useState(false);
  const [authEnabled, setAuthEnabled] = useState(false);
  const [oauthProvider, setOauthProvider] = useState<string | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const checkHealth = useAppStore((s) => s.checkHealth);

  useEffect(() => {
    // Check auth status on mount.
    checkAuthStatus().then((status) => {
      setAuthEnabled(status.enabled);
      setOauthProvider(status.oauth_provider || null);
      if (status.enabled && !status.authenticated) {
        setOpen(true);
      }
    });
  }, []);

  const handleLogin = async () => {
    if (!apiKey.trim()) {
      setError("Please enter your API key.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const ok = await loginWithApiKey(apiKey.trim());
      if (ok) {
        setOpen(false);
        setApiKey("");
        await checkHealth();
      } else {
        setError("Invalid API key. Check api_key.txt or your keyring.");
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="bg-surface-1 border border-surface-3 rounded-lg w-full max-w-md shadow-2xl">
        <div className="flex items-center justify-between px-6 py-4 border-b border-surface-3">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-maestro-400" />
            <h2 className="text-sm font-semibold">Authentication Required</h2>
          </div>
        </div>
        <div className="p-6 space-y-4">
          <div className="bg-surface-2 border border-surface-3 rounded-md p-3 text-xs text-ink-mid space-y-1">
            <p className="font-semibold text-ink-high">This MaestroAgent instance requires an API key.</p>
            <p>Your key was generated on first startup and saved to:</p>
            <code className="block bg-surface-3 rounded px-2 py-1 text-[10px] text-maestro-300 mt-1">
              /data/api_key.txt
            </code>
            <p className="mt-2">Or set <code className="text-maestro-300">MAESTRO_API_KEY</code> env var.</p>
          </div>

          <div>
            <label className="block text-xs text-ink-low uppercase tracking-wide mb-1.5">
              <KeyRound className="w-3 h-3 inline mr-1" />
              API Key
            </label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleLogin()}
              placeholder="ma_..."
              className="input w-full font-mono text-xs"
              autoFocus
            />
          </div>

          {oauthProvider && (
            <div className="text-center">
              <div className="text-xs text-ink-low mb-2">— or —</div>
              <button className="btn-ghost w-full">
                <LogIn className="w-3.5 h-3.5" />
                Sign in with {oauthProvider}
              </button>
              <p className="text-[10px] text-ink-low mt-1">OAuth coming in v1.1</p>
            </div>
          )}

          {error && (
            <div className="text-xs text-accent-err p-2 bg-accent-err/10 rounded font-mono flex items-start gap-2">
              <AlertCircle className="w-3 h-3 flex-shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}
        </div>
        <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-surface-3">
          <button onClick={handleLogin} disabled={loading} className="btn-primary">
            <KeyRound className="w-3.5 h-3.5" />
            {loading ? "Verifying..." : "Unlock"}
          </button>
        </div>
      </div>
    </div>
  );
}
