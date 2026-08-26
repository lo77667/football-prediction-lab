package com.footballprediction.companion.data.local

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Update
import kotlinx.coroutines.flow.Flow

@Dao
interface CachedAlertDao {
    @Query(
        """
        SELECT * FROM cached_alerts
        WHERE alertDate = :date
        ORDER BY CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, alertDate DESC
        """,
    )
    fun observeAlertsForDate(date: String): Flow<List<CachedAlertEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertAll(alerts: List<CachedAlertEntity>)

    @Query(
        "UPDATE cached_alerts SET acknowledgmentStatus = :status WHERE alertId = :alertId",
    )
    suspend fun updateAcknowledgment(alertId: String, status: String): Int

    @Query("DELETE FROM cached_alerts WHERE expiresAtUtc IS NOT NULL AND expiresAtUtc < :nowUtc")
    suspend fun deleteExpired(nowUtc: String): Int
}

@Dao
interface WellnessDraftDao {
    @Query("SELECT * FROM wellness_drafts WHERE playerId = :playerId AND checkInDate = :date LIMIT 1")
    suspend fun get(playerId: String, date: String): WellnessDraftEntity?

    @Query("SELECT * FROM wellness_drafts WHERE playerId = :playerId ORDER BY checkInDate DESC")
    fun observeForPlayer(playerId: String): Flow<List<WellnessDraftEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(draft: WellnessDraftEntity)

    @Query("DELETE FROM wellness_drafts WHERE updatedAtUtc < :beforeUtc")
    suspend fun deleteOlderThan(beforeUtc: String): Int
}

@Dao
interface OutboxDao {
    @Query(
        """
        SELECT * FROM sync_outbox
        WHERE syncState IN ('pending', 'retryable') AND nextAttemptAtUtc <= :nowUtc
        ORDER BY createdAtUtc ASC
        LIMIT :limit
        """,
    )
    suspend fun pending(nowUtc: String, limit: Int): List<OutboxEntity>

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun enqueue(item: OutboxEntity): Long

    @Update
    suspend fun update(item: OutboxEntity)

    @Query("DELETE FROM sync_outbox WHERE clientEventId = :clientEventId")
    suspend fun delete(clientEventId: String): Int

    @Query(
        "UPDATE sync_outbox SET syncState = :state, lastErrorCode = :errorCode, " +
            "attemptCount = :attemptCount, nextAttemptAtUtc = :nextAttemptAtUtc " +
            "WHERE clientEventId = :clientEventId",
    )
    suspend fun markRetry(
        clientEventId: String,
        state: String,
        errorCode: String?,
        attemptCount: Int,
        nextAttemptAtUtc: String,
    ): Int
}
