package com.footballprediction.companion.domain.repository

interface AuthRepository {
    suspend fun beginPkce(): PkceAuthorizationRequest
    suspend fun completePkce(callbackUri: String): Result<AuthSession>
    fun accessTokenOrNull(): String?
    fun clearSession()
}

data class PkceAuthorizationRequest(
    val authorizationUri: String,
    val state: String,
    val codeVerifier: String,
)

data class AuthSession(
    val accessToken: String,
    val expiresAtEpochSeconds: Long,
    val role: UserRole,
)

enum class UserRole {
    COACH,
    PLAYER,
}
