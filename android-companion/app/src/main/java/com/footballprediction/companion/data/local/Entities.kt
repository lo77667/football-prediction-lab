package com.footballprediction.companion.data.local

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "cached_alerts",
    indices = [
        Index(value = ["dedupeKey", "serverVersion"], unique = true),
        Index(value = ["playerId", "alertDate"]),
        Index(value = ["acknowledgmentStatus"]),
    ],
)
data class CachedAlertEntity(
    @PrimaryKey val alertId: String,
    val playerId: String,
    val dedupeKey: String,
    val alertType: String,
    val severity: String,
    val alertDate: String,
    val triggerReason: String,
    val loadRatio: Double?,
    val adaptiveThreshold: Double?,
    val confidenceScore: Double?,
    val volatilityBand: String?,
    val acknowledgmentStatus: String,
    val serverVersion: Long,
    val asOfUtc: String,
    val expiresAtUtc: String?,
)

@Entity(
    tableName = "wellness_drafts",
    indices = [
        Index(value = ["playerId", "checkInDate"], unique = true),
        Index(value = ["syncState"]),
    ],
)
data class WellnessDraftEntity(
    @PrimaryKey val localId: String,
    val playerId: String,
    val checkInDate: String,
    val sleepHours: Double?,
    val soreness: Int?,
    val mood: Int?,
    val energy: Int?,
    val consentPurpose: String,
    val createdAtUtc: String,
    val updatedAtUtc: String,
    val syncState: String,
)

@Entity(
    tableName = "sync_outbox",
    indices = [
        Index(value = ["idempotencyKey"], unique = true),
        Index(value = ["syncState", "createdAtUtc"]),
    ],
)
data class OutboxEntity(
    @PrimaryKey val clientEventId: String,
    val resourceType: String,
    val playerId: String,
    val idempotencyKey: String,
    val payloadJson: String,
    val createdAtUtc: String,
    val attemptCount: Int,
    val nextAttemptAtUtc: String,
    val syncState: String,
    val lastErrorCode: String?,
)
