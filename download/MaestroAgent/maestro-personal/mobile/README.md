# Maestro Personal Mobile App

React Native + Expo app for Maestro Personal v1.

## Setup

```bash
cd maestro-personal/mobile
npm install --legacy-peer-deps
```

**Note:** `--legacy-peer-deps` is required because `@testing-library/react-native`
has peer dependency conflicts with Expo SDK 52's React version. This is a known
Expo ecosystem issue, not a Maestro bug. The app works correctly with this flag.

## Running

### Start the API server first

```bash
cd maestro-personal/src/maestro_personal_shell
python api.py
# Starts on http://localhost:8766
# Prints the auth token to stdout
```

### Start the mobile app

```bash
cd maestro-personal/mobile
npx expo start
# Opens Metro bundler
# Scan QR with Expo Go (iOS/Android) to test on physical device
```

### Run tests

```bash
cd maestro-personal/mobile
npx jest
# 25 structure tests
```

## Screens

| Screen | Purpose |
|--------|---------|
| Login | Obtains bearer token from API |
| Home | Situations + What Changed overview |
| Ask | Question-answering via Core |
| Commitments | Active commitments (promise/proposal tracking) |
| Prepare | Meeting/situation preparation |
| Add Signal | Manual signal entry (v1 — Gmail/Calendar in v2) |

## Architecture

```
Mobile app (React Native + Expo)
  → HTTP API (FastAPI :8766, bearer auth, SQLite)
    → PersonalShell (thin wrapper)
      → Core (maestro_cognitive_council, 354 tests)
```

No intelligence in the mobile or API layers. All cognition flows through
the shell to Core. The AST-based no-dilution guard enforces this.
