# ai_assistant feature

Everything for the O-Kay financial assistant lives under this folder so it can be dropped into
the main Khalti app later.

Rules:
- No imports from outside this folder except Flutter, Dart and pub packages.
- Repositories talk to the backend through one `ApiClient`.
- The host app is reached only through the `HostAppBridge` interface.
- All design tokens live in one theme file.
- The feature is mounted behind a feature flag.
