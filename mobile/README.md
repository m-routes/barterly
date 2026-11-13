# Barterly mobile (talent app)

Flutter app for talent. See [docs/architecture.md](../docs/architecture.md#talent-app-mobile) for how it is put together.

```bash
flutter pub get
cp env/firebase-keys.example.json env/firebase-keys.json   # once; fill in the keys
flutter run --dart-define-from-file=env/staging.json --dart-define-from-file=env/firebase-keys.json
flutter analyze --fatal-infos && flutter test
```

`env/{local,staging,production}.json` hold build settings (API URL, Firebase project and app ids, Sentry DSN). The Firebase API keys live in `env/firebase-keys.json`, which is not committed: copy them from the Firebase console (Project settings → Your apps) or from `GoogleService-Info.plist` / `google-services.json`. Without the keys the app says sign-in isn't available.
