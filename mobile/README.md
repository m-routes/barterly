# Barterly mobile (talent app)

Flutter app for talent. See [docs/architecture.md](../docs/architecture.md#talent-app-mobile) for how it is put together.

```bash
flutter pub get
flutter run --dart-define-from-file=env/staging.json   # or env/local.json, env/production.json
flutter analyze --fatal-infos && flutter test
```

`env/*.json` hold public build settings (API URL, Firebase app ids, Sentry DSN). Sign-in needs the Firebase values filled in; without them the app says sign-in isn't available.
