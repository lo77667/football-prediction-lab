package com.footballprediction.companion.data.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

interface CompanionApi {
    @GET("v1/coach/daily-alerts")
    suspend fun getDailyAlerts(@Query("date") date: String): ApiResponse<List<AlertDto>>

    @GET("v1/players/{playerId}/development")
    suspend fun getDevelopment(
        @Path("playerId") playerId: String,
        @Query("window") window: String = "12m",
    ): ApiResponse<DevelopmentDto>

    @POST("v1/sync/push")
    suspend fun push(@Body request: SyncPushRequest): ApiResponse<SyncPushResponse>
}

@Serializable
data class ApiResponse<T>(
    val data: T? = null,
    val requestId: String? = null,
    val error: ApiError? = null,
)

@Serializable
data class ApiError(
    val code: String,
    val message: String? = null,
    val retryable: Boolean = false,
)

@Serializable
data class AlertDto(
    val alertId: String,
    val playerId: String,
    val dedupeKey: String,
    val alertType: String,
    val severity: String,
    val alertDate: String,
    val triggerReason: String,
    val loadRatio: Double? = null,
    val adaptiveThreshold: Double? = null,
    val confidenceScore: Double? = null,
    val volatilityBand: String? = null,
    val acknowledgmentStatus: String,
    val serverVersion: Long,
    val asOfUtc: String,
    val expiresAtUtc: String? = null,
)

@Serializable
data class DevelopmentDto(
    val playerId: String,
    val trajectoryBand: String,
    val resilienceBand: String,
    val asOfUtc: String,
    val policyVersion: String,
)

@Serializable
data class SyncPushRequest(
    val events: List<OutboxEventDto>,
)

@Serializable
data class OutboxEventDto(
    val clientEventId: String,
    val resourceType: String,
    val playerId: String,
    val idempotencyKey: String,
    val createdAtUtc: String,
    val payloadJson: String,
)

@Serializable
data class SyncPushResponse(
    val results: List<SyncEventResult>,
)

@Serializable
data class SyncEventResult(
    val clientEventId: String,
    val result: String,
    val serverId: String? = null,
    val serverVersion: Long? = null,
    @SerialName("error_code") val errorCode: String? = null,
)
