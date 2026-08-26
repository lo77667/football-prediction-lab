# Coach & Player Companion — Native Android Blueprint

**Product:** Field-ready mobile companion for the youth-soccer hybrid analytics warehouse
**Target:** Android 10+ for managed phones/tablets; signed APK for controlled distribution and AAB for Play distribution
**Primary audience:** Coaches, players, sports-science staff, and safeguarding-authorized reviewers

## 1. Product boundary

The application is a **decision-support client**, not an autonomous selector, medical clearance tool, or psychological diagnostic instrument. It consumes approved aggregates and operational alerts from the existing REST/GraphQL API. The app must not query PostgreSQL or MongoDB directly, and it must not expose raw narrative text to players or unauthorized staff.

The server remains authoritative for identity, consent, alert state, model versions, and audit records. The device is an encrypted, offline-capable working replica for the smallest set of records needed by the signed-in user.

> **Design rule:** A player should see actionable self-care and developmental context, while a coach can see operational risk signals and evidence summaries without receiving unrestricted access to sensitive raw narratives.

## 2. Recommended technology decision

For an Android-first APK, choose **Kotlin with Jetpack Compose** rather than Flutter, React Native, or Kotlin Multiplatform. Kotlin gives the team direct access to Android lifecycle, background work, biometric authentication, Keystore, notification channels, accessibility, and device management APIs without a bridge. Jetpack’s official offline-first guidance recommends a local source of truth, repositories that combine local and network sources, and persistent queued work for synchronization [1].

| Option | Strengths | Trade-offs | Recommendation |
|---|---|---|---|
| Kotlin + Jetpack Compose | Best Android integration, smallest security surface for Android-only deployment, first-class Room/WorkManager/Keystore support, smooth field UI | Separate iOS implementation if the product later expands | **Recommended for this APK** |
| Flutter | Fast cross-platform UI and a large widget ecosystem | Platform integrations, background behavior, and security-sensitive storage still require native plugins; larger runtime surface | Use only if iOS is a near-term requirement and the team already has strong Flutter expertise |
| React Native | Reuse with an existing React organization and broad ecosystem | Bridge/native-module complexity for offline databases, background sync, audio, and cryptographic storage | Not preferred for this security-sensitive, offline-heavy Android client |
| Kotlin Multiplatform | Shares domain, networking, validation, and sync logic across Android/iOS while retaining native UIs | Higher architecture complexity and still requires native platform work | Consider for a second platform after the Android domain contracts stabilize |

### Proposed Android stack

| Layer | Choice |
|---|---|
| UI | Jetpack Compose, Material 3, accessibility semantics, `LazyColumn`, dark/high-contrast theme |
| State | ViewModel + Kotlin Coroutines + `StateFlow`; Hilt for dependency injection |
| API | Retrofit + OkHttp + Kotlin Serialization or Moshi for REST; Apollo Kotlin only if the server standardizes on GraphQL |
| Local database | Room over SQLite; SQLCipher for Android for encrypted database pages where the threat model requires full-database-at-rest encryption |
| Preferences/secrets | Proto DataStore for non-sensitive settings; Android Keystore-wrapped secrets for tokens and database keys |
| Background work | WorkManager with network constraints, exponential backoff, and unique work names |
| Connectivity | `ConnectivityManager` network callbacks plus WorkManager constraints; connectivity is a sync trigger, not a source of truth |
| Voice input | Approved on-device speech recognition where available; otherwise an API-mediated transcription path with encrypted temporary storage and deletion-on-ack |
| Notifications | Android notification channels, server-provided notification eligibility, local dedupe receipts |
| Observability | Crash reporting with PII scrubbing, structured sync metrics, request IDs, and privacy-safe audit events |
| Delivery | Gradle version catalogs, signed release APK/AAB, GitHub Actions build and test pipeline, signing material held outside Git |

## 3. Roles and permission model

Authorization is enforced by the API on every request. The Android client receives a capability document after authentication and uses it to hide unavailable actions, but hidden UI is not a security control.

| Role | Allowed mobile experience | Explicitly prohibited |
|---|---|---|
| Coach | Squad alerts, player operational summaries, acknowledge alerts, quick notes, feedback on recommendations | Bulk export, identity lookup, unrestricted raw safeguarding notes, changing model thresholds |
| Head coach/performance lead | Coach capabilities plus team-level trends and approved model-health summaries | Editing consent or safeguarding records unless separately authorized |
| Sports scientist | Physical/load trends and approved readiness components | Clinical interpretation or unrestricted identity data |
| Player | Own wellness check-in, own simplified trajectory, own resilience trend and explanations | Peer comparisons, coach raw notes, exact risk labels, team alerts, model internals |
| Safeguarding reviewer | Restricted case workflow through a separate capability and screen set | Ordinary dashboard export or use of safeguarding text as an ML feature without approval |

Use server-side scopes such as `alerts:read`, `alerts:ack`, `notes:create`, `feedback:create`, `wellness:self:write`, and `trajectory:self:read`. Every API response should include `request_id`, `as_of_utc`, `feature_set_version`, and `policy_version` where relevant.

## 4. Offline-first architecture

The mobile data layer follows a **local-first repository** pattern. Compose screens observe Room flows; they do not call Retrofit directly. Network responses are mapped into local entities, and local writes are immediately visible in the UI before a queued synchronization attempt. This is consistent with Android’s offline-first design, where the local data source is the canonical source for readers and queued writes are drained by persistent work [1].

```text
Compose screen
    │ observes StateFlow
ViewModel / use case
    │
Repository ───────────────┐
    │                      │
Room encrypted DB      Retrofit/OkHttp API
    │                      │
Outbox + sync cursor   REST/GraphQL gateway
    └──────── WorkManager ┘
```

### Room entities

| Entity | Important fields | Retention/access rule |
|---|---|---|
| `CachedAlertEntity` | `alertId`, `playerId`, `dedupeKey`, severity, reason summary, status, `serverVersion`, `asOfUtc` | Coach-only cache; no raw note text; purge by TTL and logout policy |
| `CachedDailySummaryEntity` | `playerId`, date, load ratio, adaptive threshold, volatility band, readiness band, freshness | Player receives only own rows; coaches receive authorized squad rows |
| `WellnessDraftEntity` | `localId`, `playerId`, date, sleep, soreness, mood, `consentPurpose`, sync state | Self-only; encrypted; delete after server acknowledgment plus short local TTL |
| `CoachNoteDraftEntity` | `localId`, playerId, note type, redacted text or encrypted temporary object reference, sync state | Coach-only; minimize retention; raw audio is never kept after transcription/upload acknowledgment |
| `FeedbackOutboxEntity` | `clientEventId`, `predictionId`, `playerId`, recommendation, rating, action, reason, `createdAtUtc`, retry state | Append-only outbox; no silent overwrite |
| `SyncStateEntity` | resource, server cursor, last successful sync, ETag, error state | Operational metadata only |
| `NotificationReceiptEntity` | `dedupeKey`, `alertId`, notification version, displayed/acted timestamps | Prevents duplicate phone notifications |

The Room database is encrypted with SQLCipher where required by the academy threat model. The SQLCipher passphrase is generated randomly and wrapped by a non-exportable Android Keystore key. Android Keystore is designed to keep key material difficult to extract and can restrict key use to authorized cryptographic operations and user-authenticated sessions [2].

### Sync protocol

Use a hybrid pull/push model. The app performs a pull on login, on coach-dashboard entry, on foreground resume when stale, and after a successful upload. WorkManager performs queued writes under an unmetered or connected-network constraint according to product policy; critical coach acknowledgments may attempt immediate upload and then remain queued if offline.

Each write carries:

```json
{
  "client_event_id": "client-generated-uuid",
  "idempotency_key": "client-generated-uuid",
  "player_id": "opaque-player-uuid",
  "device_id": "rotating-device-install-id",
  "created_at_utc": "2026-08-26T12:00:00Z",
  "base_server_version": 7,
  "payload": {}
}
```

The server returns `accepted`, `duplicate`, `conflict`, `forbidden`, or `retryable_failure`. The client retries only network errors, 408, 425, 429, and 5xx responses with exponential backoff and jitter. It does not retry 400/401/403/404 blindly.

### Feedback conflict resolution

`coach_feedback_log` should be treated as **append-only**. Two coaches submitting feedback for the same prediction are not conflicting edits; they are two observations and must both be retained. If the same device retries the same feedback, `idempotency_key = client_event_id` makes the second request a no-op and the client marks it synchronized.

If a coach corrects a rating, create a new correction event referencing the original `feedback_id`; do not mutate history on the device. If the API returns `409`, fetch the canonical server record, preserve the local event as `conflict_review_required`, and show a non-blocking review state. Never use last-write-wins to erase a coach’s original evaluation.

## 5. Secure API contract

The preferred initial integration is REST because it is easier to cache, troubleshoot, version, and implement offline with resource-specific cursors. GraphQL can be added later for the coach dashboard if the API team needs flexible aggregations; the security and field allow-list rules remain identical.

### Required REST endpoints

| Method and route | Role | Purpose |
|---|---|---|
| `GET /v1/me` | All | Return subject, role, capabilities, consent context, and session metadata; no legal identity payload unless required by the UI |
| `GET /v1/sync/pull?cursor=...` | All | Pull changed authorized records, tombstones, server cursor, and policy versions |
| `POST /v1/sync/push` | All permitted writers | Batch idempotent outbox events with per-event result codes |
| `GET /v1/coach/daily-alerts?date=YYYY-MM-DD` | Coach | Return adaptive alerts, threshold evidence, acknowledgment state, freshness, and reason codes |
| `POST /v1/coach-alerts/{alert_id}/acknowledgment` | Coach | Acknowledge, snooze, resolve, or dismiss with server version and audit metadata |
| `POST /v1/players/{player_id}/coach-notes` | Coach | Submit a short redacted note or approved transcription reference; raw safeguarding content is routed elsewhere |
| `POST /v1/players/me/wellness-checkins` | Player | Submit sleep, soreness, mood, and energy using the active consent purpose |
| `GET /v1/players/me/development?window=12m` | Player | Return a simplified own trajectory and resilience trend |
| `GET /v1/coach/players/{player_id}/summary?date=...` | Coach | Return authorized daily load, adaptive threshold, volatility band, and approved qualitative aggregates |
| `POST /v1/coach-feedback` | Coach | Append prediction accuracy feedback with `client_event_id` and optional outcome reference |
| `GET /v1/monitoring/drift?feature=...` | Analytics/performance lead | Return aggregate drift status; never raw notes or small-cell cohorts |

Every endpoint must apply server-side UUID authorization, consent-purpose checks, role filters, rate limits, audit logging, and response minimization. The API should return `410 Gone` or a structured deletion response when a player has been withdrawn or erased, and the app should purge affected cached records.

### Optional GraphQL operations

```graphql
query CoachDailyAlerts($date: Date!) {
  coachDailyAlerts(date: $date) {
    alertId playerId alertType severity triggerReason
    adaptiveThreshold loadRatio confidenceScore
    acknowledgmentStatus asOfUtc serverVersion
  }
}

mutation SubmitCoachFeedback($input: CoachFeedbackInput!) {
  submitCoachFeedback(input: $input) {
    result clientEventId feedbackId serverVersion
  }
}
```

The GraphQL schema must use persisted operations or an allow-list in production. Do not permit arbitrary field introspection to a player client if it would reveal restricted types or fields.

## 6. Coach and player flows

### Coach flow

The coach opens **Today** and immediately sees three states: `Action required`, `Monitor`, and `No current alert`. Selecting an alert opens a single-screen explanation with the current load, personal adaptive threshold, baseline volatility band, confidence/readiness band, freshness, and a clear action such as “check in,” “review session plan,” or “observe directly.” Acknowledge, snooze, and resolve are large bottom actions with a confirmation only for destructive dismissal.

Quick notes use a 15–30 second capture flow: select context, tap record or dictate, review the redacted transcript, optionally assign a controlled marker, and save. Offline notes show `Queued securely`; they are not shown as synchronized until the server acknowledges them. A coach feedback action is available directly from the alert card and defaults to one tap plus an optional reason.

### Player flow

The player sees **My day**, **Check-in**, and **My progress**. The check-in uses large controls for sleep, soreness, mood, and energy with plain-language anchors. The player receives a receipt showing when the data was last synchronized and can edit the same-day draft before submission.

The progress screen uses a qualitative trend label such as `building`, `steady`, or `needs a conversation`, a simple trajectory line, and an explanation of resilience as “how your performance measures have returned toward your usual range after demanding periods.” It must not show peer rank, exact confidence labels from coaches, raw notes, or a “potential” score.

## 7. Field-ready UX and metric visualization

The interface should be designed for a coach standing beside a pitch in bright sunlight, wearing gloves, and using one hand. Use a minimum 48dp touch target, short labels, one primary action per screen, haptic confirmation sparingly, generous spacing, and no workflow that requires more than three taps for a routine acknowledgment. Support light, dark, and high-contrast themes; never rely on color alone.

| Metric | Mobile visualization | Privacy/safety rule |
|---|---|---|
| Adaptive Load Ratio | Horizontal gauge from `0.8x` to `2.0x+`, with a vertical marker for the player’s adaptive threshold. Label the actual ratio and threshold numerically. | Threshold comes from the server policy version; do not let a client alter it. |
| Baseline Volatility | Three-state chip: `stable`, `variable`, `not enough history`; optional numeric value for authorized staff | Player view receives the band, not the coefficient or cohort comparison. |
| Readiness/confidence | Component cards with `low / typical / strong / not available`, trend arrow, and as-of date | No clinical language, no raw evidence, no forced inference when data is missing. |
| Resilience | 30/90-day trend plus recovered-event count and “not enough history” state | Never present as a fixed psychological trait or selection label. |
| Go/No-Go | `GO`, `REVIEW`, or `NO-GO` with an explanation and human action | `NO-GO` always requires human review; never trigger a silent automatic exclusion. |

Use dynamic color tokens such as green/amber/red only with text and icons. For outdoor use, verify contrast with Android accessibility tools and real-device sunlight testing. Show stale data as `Last updated 3h ago`, not as current truth.

## 8. On-device security and privacy

Authentication should use OIDC Authorization Code with PKCE through the system browser or an approved identity SDK. Store only short-lived access tokens in memory. Store refresh tokens, device-install secrets, and the wrapped database key using Android Keystore-backed storage. Require biometric or device credential re-authentication before revealing coach-only player summaries or exporting any data.

The application should use HTTPS only, reject cleartext traffic, validate certificate chains through the platform network security configuration, and include request IDs for incident investigation. Add certificate pinning only if the operations team can support safe key rotation; brittle pinning that blocks all clients during certificate rotation is worse than managed platform trust.

Never store names, emails, phone numbers, dates of birth, raw identity documents, or direct MongoDB narrative documents locally. Store only opaque UUIDs and the minimum display code required by an authorized coach. Do not place player IDs or health/psychology data in notification titles, lock-screen previews, analytics SDK events, crash logs, clipboard contents, or screenshots. Use `FLAG_SECURE` on sensitive screens where device policy permits.

Voice capture requires special handling. Prefer on-device transcription. If the device lacks an approved on-device recognizer, provide typed entry or upload an encrypted temporary audio object to the approved API. Delete audio after transcription and server acknowledgment, retain only the redacted text permitted by policy, and route safeguarding disclosures outside the ordinary analytics pipeline.

## 9. Alert notification deduplication

The API is the source of truth for alert identity. The client persists a unique `NotificationReceiptEntity` keyed by the server’s `dedupe_key` plus an alert version. When a sync response contains an unacknowledged high-severity alert, the app checks:

```text
if dedupe_key + server_version is absent:
    persist receipt
    schedule one notification
else:
    do not notify again
```

Notification bodies should say “A coaching review is available” rather than naming a player or exposing confidence/load values. When the alert is acknowledged, resolved, dismissed, or deleted by the server, cancel any pending local notification. If severity or trigger reason changes, the server must increment `server_version`; the client may notify once for the new version after applying the user’s notification policy.

## 10. Delivery roadmap and APK strategy

| Phase | Scope | Exit criteria |
|---|---|---|
| 0 — Contract and safeguarding | API OpenAPI/GraphQL schema, role matrix, consent map, threat model, retention rules | Security and safeguarding approval; no direct database access in client |
| 1 — Android shell | Kotlin/Compose navigation, authentication, role routing, themes, device policy | Signed internal APK launches and enforces capabilities |
| 2 — Offline core | Room/SQLCipher, repositories, cached summaries, wellness drafts, sync cursor | Airplane-mode tests pass; local data remains usable and queued writes survive process death |
| 3 — Coach operations | Alerts, acknowledgment, notification dedupe, feedback log, quick notes | Duplicate/retry/conflict tests pass; raw narratives absent from notifications and logs |
| 4 — Player experience | Wellness forms, simplified trajectory, resilience explanation, consent/withdrawal states | Player can access only own records and sees safe missing-data states |
| 5 — Hardening | Accessibility, battery/network tests, API abuse tests, deletion/withdrawal purge, crash/PII review | Internal testing cohort approves field usability and privacy behavior |
| 6 — Release | CI build, signed APK/AAB, staged rollout, rollback and key-rotation runbook | Release artifact hash recorded; Play/internal distribution or managed sideload complete |

The CI pipeline should run unit tests, Room migration tests, API contract tests, offline synchronization tests, Compose screenshot/accessibility checks, static analysis, dependency vulnerability checks, and a release build without exposing signing secrets. Store signing keys in a dedicated secret manager or protected GitHub environment; never commit keystores or passwords.

## 11. Acceptance tests

| Test family | Example acceptance test |
|---|---|
| Offline | Disable connectivity, submit wellness and feedback, kill/restart the app, restore connectivity, verify exactly-once server acceptance |
| Conflict | Submit two coach feedback events for one prediction from two devices; verify both append-only records survive |
| Permissions | Authenticate as player and attempt coach alert/notes endpoints; verify server denial and no cached restricted data |
| Privacy | Inspect notifications, logs, backups, screenshots, and crash payloads; verify no names, raw notes, or psychological text |
| Withdrawal | Revoke processing, sync, verify local purge/tombstones, and verify the app blocks new writes for that purpose |
| Drift/freshness | Serve stale summaries and drift flags; verify visible stale/hold state rather than false current guidance |
| Accessibility | Use large font, TalkBack, high contrast, and sunlight test; verify all actions remain understandable without color |
| Security | Expire access token, rotate refresh token, lock device, attempt database extraction, and verify re-authentication/key protection |

## References

[1]: https://developer.android.com/topic/architecture/data-layer/offline-first "Android Developers: Build an offline-first app"

[2]: https://developer.android.com/privacy-and-security/keystore "Android Developers: Android Keystore system"
