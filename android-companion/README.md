# Coach & Player Companion — Native Android Module

This directory is a native Kotlin/Jetpack Compose Android module for the existing hybrid soccer analytics warehouse. It is intentionally separate from the Python warehouse package so Android build, signing, and device security can evolve independently.

## Package layout

```text
com.footballprediction.companion/
├── core/security/       Keystore-backed database-key wrapping
├── data/local/          Encrypted Room entities, DAOs, database, preferences
├── data/network/        Retrofit DTOs, API, Hilt network module
├── data/repository/     Auth implementation and repository adapters
├── data/sync/           WorkManager outbox synchronization
├── domain/model/        Stable app-domain types
├── domain/repository/   Auth and future domain contracts
└── presentation/        Compose navigation and role-specific screens
```

## Core dependencies

The version catalog includes Jetpack Compose, Room/KSP, SQLCipher for Android, Hilt, Retrofit/OkHttp, WorkManager, Proto/Preferences DataStore support, Kotlin serialization, and Android test tooling. The app module uses:

```kotlin
implementation(platform(libs.androidx.compose.bom))
implementation(libs.androidx.compose.material3)
implementation(libs.androidx.room.runtime)
implementation(libs.androidx.room.ktx)
ksp(libs.androidx.room.compiler)
implementation(libs.sqlcipher.android)
implementation(libs.hilt.android)
ksp(libs.hilt.compiler)
implementation(libs.retrofit)
implementation(libs.okhttp)
implementation(libs.work.runtime.ktx)
implementation(libs.datastore.preferences)
```

SQLCipher for Android requires `System.loadLibrary("sqlcipher")` before the encrypted Room database is opened. The integration uses `SupportOpenHelperFactory` with a random 32-byte passphrase. The passphrase is wrapped by an AES-GCM key held in Android Keystore; the passphrase and Keystore key material are not committed or logged.

## Build

Open `android-companion` in Android Studio or run `./gradlew assembleDebug`. Configure `BuildConfig.API_BASE_URL` through a release-specific build configuration; the checked-in default is deliberately non-routable. The checked-in wrapper uses Gradle 8.10.2 and the validated module uses Android API 35 with JDK 21. Before release, configure the OIDC issuer/client ID, redirect URI, backend certificate policy, and signing environment through protected build secrets.

The OIDC repository is intentionally a stub. It generates a PKCE verifier/challenge and validates callback state, but it refuses to pretend that token exchange succeeded. Replace the marked server-exchange seam with the approved identity-provider client before enabling production login. Access tokens remain in memory only.

## Privacy invariants

The local database stores only opaque UUIDs, authorized aggregate alert data, wellness drafts, and an encrypted outbox. It does not store names, dates of birth, raw MongoDB notes, safeguarding text, raw audio, or access tokens. Notification text must remain generic. The server is authoritative for authorization, consent, alert state, deletion/tombstones, and audit history.

## Sync invariants

Room is the read source of truth for Compose. WorkManager drains the outbox only on validated connectivity, retries transient failures with bounded exponential backoff, deletes accepted or duplicate events, and preserves conflicts for human review. Coach feedback is append-only; two coaches rating the same prediction are separate observations rather than last-write-wins updates.
