# npm Audit Risk Acceptance — Phase 1

**Date:** 2026-07-13
**Expo SDK:** 52.0.0
**Vulnerabilities:** 18 (12 moderate, 6 high) — ALL in Expo build-time transitive deps

## Analysis

All 18 vulnerabilities are in Expo SDK 52's transitive dependencies:
- `@expo/cli`, `@expo/config`, `@expo/config-plugins`, `@expo/metro-config`
- `expo-asset`, `expo-constants`, `jest-expo`
- `tar`, `cacache`, `@xmldom/xmldom`, `@expo/plist`
- `uuid`, `xcode`, `postcss`, `@expo/bunyan`, `@expo/rudder-sdk-node`

None of these ship in the production JS bundle — they are build-time / dev-time only (used by `expo-cli` for building, not by the app at runtime).

## Risk

**LOW.** These vulnerabilities affect:
- Build tooling (expo-cli, metro bundler) — not the app's runtime code
- Test runner (jest-expo) — not production
- Xcode project generation — build-time only

An attacker would need to compromise the build machine, not the app's users.

## Remediation

Upgrade to **Expo SDK 53+** when it's stable (requires testing all plugins + native modules). This is Phase 6 work (backend/perf/scale).

## CVEs

- `tar` (high): CVE-2024-28863 (DoS via crafted tar archive)
- `@xmldom/xmldom` (high): CVE-2024-4068 (prototype pollution)
- `cacache` (high): depends on vulnerable `tar`

All are build-time only. No runtime exposure.

## Decision

**Accept risk** until Expo SDK 53 upgrade in Phase 6. Re-audit after upgrade.
