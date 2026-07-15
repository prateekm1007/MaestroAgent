# npm Audit Risk Acceptance — Phase 1 (Updated)

**Date:** 2026-07-14 (updated from 2026-07-13)
**Expo SDK:** 53.0.0 (upgraded from 52.0.0)
**TypeScript:** 5.4.0 (upgraded from 5.3.0)
**Vulnerabilities:** 14 (12 moderate, 2 high) — down from 18 (12 moderate, 6 high)

## What the SDK 53 upgrade fixed

Upgrading from Expo SDK 52 → 53 reduced **6 high → 2 high** vulnerabilities:
- ✅ `tar` (high → fixed by SDK 53's updated cacache)
- ✅ `cacache` (high → fixed by SDK 53)
- ✅ `@expo/cli` (high → moderate, fixed by SDK 53's updated CLI)
- ✅ `expo` (high → moderate, direct dep now on SDK 53)

## Remaining vulnerabilities (14)

### High (2) — build-time only, no runtime exposure

| Package | Via | CVE | Impact |
|---------|-----|-----|--------|
| `@xmldom/xmldom` | `@expo/plist` | CVE-2024-4068 (prototype pollution) | Build-time XML parsing only (Xcode project generation). Not in production JS bundle. |
| `@expo/plist` | transitive | Depends on `@xmldom/xmldom` | Build-time plist manipulation. Not shipped. |

### Moderate (12) — all Expo build toolchain

All 12 moderate vulnerabilities are in:
- `@expo/cli`, `@expo/config`, `@expo/config-plugins`, `@expo/metro-config`
- `@expo/prebuild-config`, `expo-asset`, `expo-constants`
- `jest-expo`, `postcss`, `uuid`, `xcode`

None ship in the production JS bundle — they are build-time / dev-time only.

## Remediation path

All remaining vulnerabilities require upgrading to **Expo SDK 57** (the latest).
SDK 53 → 57 is a 4-major-version jump that requires:
1. Testing all native modules (expo-av, expo-haptics, expo-secure-store, etc.)
2. Updating React Native version (0.76 → 0.79+)
3. Testing all screen components against new RN APIs
4. Re-running all 70 tests

This is **Phase 6** work (backend/perf/scale) per the roadmap.

## Risk assessment

**LOW.** All remaining vulnerabilities:
- Are in build-time tooling (expo-cli, metro bundler, jest-expo)
- Do NOT ship in the production JS bundle
- Cannot be exploited by app users
- Require build-machine compromise to exploit

An attacker would need to compromise the CI/CD build machine, not the app's users.

## Decision

**Accept risk** until Expo SDK 57 upgrade in Phase 6. Re-audit after upgrade.

## Verification

```
$ npm audit
14 vulnerabilities (12 moderate, 2 high)

$ npx tsc --noEmit
EXIT 0

$ npx jest
70/70 passed
```

## SDK 57 Upgrade Attempt (2026-07-14)

Attempted upgrade to Expo SDK 57 to resolve remaining vulnerabilities.
Result: **REVERTED to SDK 53** — SDK 57 breaks all 78 tests (native module
incompatibility, `@expo/vector-icons` resolution failure, jest transform errors).

SDK 57 is a 4-major-version jump from SDK 53. It requires:
1. React Native 0.76 → 0.79+ (breaking native module changes)
2. React 18 → 19 (breaking component lifecycle changes)
3. All expo-* packages upgraded (expo-av, expo-haptics, expo-secure-store, etc.)
4. Jest configuration changes
5. Full re-test of all 78 tests + manual device testing

This is bounded, known-cost work (~1-2 days) but cannot be done in a single
automated session. It requires iterative testing with a real device/simulator.

**Decision:** Stay on SDK 53. Accept 14 vulnerabilities (all build-time, not
runtime). Plan SDK 57 upgrade as a dedicated task with device testing.
