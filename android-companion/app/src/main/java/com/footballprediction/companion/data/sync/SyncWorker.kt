package com.footballprediction.companion.data.sync

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.footballprediction.companion.data.local.AppDatabase
import com.footballprediction.companion.data.local.OutboxEntity
import com.footballprediction.companion.data.network.CompanionApi
import com.footballprediction.companion.data.network.OutboxEventDto
import com.footballprediction.companion.data.network.SyncPushRequest
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import java.time.Instant

@HiltWorker
class SyncWorker @AssistedInject constructor(
    @Assisted appContext: Context,
    @Assisted workerParams: WorkerParameters,
    private val database: AppDatabase,
    private val api: CompanionApi,
) : CoroutineWorker(appContext, workerParams) {

    override suspend fun doWork(): Result {
        if (!hasValidatedNetwork()) return Result.retry()

        val now = Instant.now()
        val pending = database.outboxDao().pending(now.toString(), BATCH_SIZE)
        if (pending.isEmpty()) return Result.success()

        val response = runCatching {
            api.push(
                SyncPushRequest(
                    events = pending.map { it.toDto() },
                ),
            )
        }.getOrElse {
            markBatchRetry(pending, "network_error", now)
            return Result.retry()
        }

        val data = response.data
        if (data == null) {
            val error = response.error
            if (error?.retryable == true) {
                markBatchRetry(pending, error.code, now)
                return Result.retry()
            }
            pending.forEach { item ->
                database.outboxDao().markRetry(
                    clientEventId = item.clientEventId,
                    state = "rejected",
                    errorCode = error?.code ?: "empty_response",
                    attemptCount = item.attemptCount + 1,
                    nextAttemptAtUtc = now.toString(),
                )
            }
            return Result.failure()
        }

        val resultsByClientId = data.results.associateBy { it.clientEventId }
        var shouldRetry = false
        pending.forEach { item ->
            when (resultsByClientId[item.clientEventId]?.result) {
                "accepted", "duplicate" -> database.outboxDao().delete(item.clientEventId)
                "retryable_failure" -> {
                    shouldRetry = true
                    markRetry(item, "backend_retryable", now)
                }
                "conflict" -> database.outboxDao().markRetry(
                    clientEventId = item.clientEventId,
                    state = "conflict_review_required",
                    errorCode = "conflict",
                    attemptCount = item.attemptCount + 1,
                    nextAttemptAtUtc = now.toString(),
                )
                else -> database.outboxDao().markRetry(
                    clientEventId = item.clientEventId,
                    state = "rejected",
                    errorCode = "missing_or_forbidden_result",
                    attemptCount = item.attemptCount + 1,
                    nextAttemptAtUtc = now.toString(),
                )
            }
        }
        return if (shouldRetry) Result.retry() else Result.success()
    }

    private suspend fun markBatchRetry(items: List<OutboxEntity>, errorCode: String, now: Instant) {
        items.forEach { markRetry(it, errorCode, now) }
    }

    private suspend fun markRetry(item: OutboxEntity, errorCode: String, now: Instant) {
        val nextAttempt = item.attemptCount + 1
        val delaySeconds = minOf(
            MAX_BACKOFF_SECONDS,
            BASE_BACKOFF_SECONDS * (1L shl minOf(nextAttempt.toInt(), MAX_BACKOFF_POWER)),
        )
        database.outboxDao().markRetry(
            clientEventId = item.clientEventId,
            state = "retryable",
            errorCode = errorCode,
            attemptCount = nextAttempt,
            nextAttemptAtUtc = now.plusSeconds(delaySeconds).toString(),
        )
    }

    private fun hasValidatedNetwork(): Boolean {
        val connectivity = applicationContext.getSystemService(ConnectivityManager::class.java)
        val network = connectivity.activeNetwork ?: return false
        val capabilities = connectivity.getNetworkCapabilities(network) ?: return false
        return capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
            capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
    }

    private fun OutboxEntity.toDto() = OutboxEventDto(
        clientEventId = clientEventId,
        resourceType = resourceType,
        playerId = playerId,
        idempotencyKey = idempotencyKey,
        createdAtUtc = createdAtUtc,
        payloadJson = payloadJson,
    )

    private companion object {
        const val BATCH_SIZE = 50
        const val BASE_BACKOFF_SECONDS = 30L
        const val MAX_BACKOFF_SECONDS = 3_600L
        const val MAX_BACKOFF_POWER = 10
    }
}
