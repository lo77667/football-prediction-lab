package com.footballprediction.companion.data.repository

import android.net.Uri
import com.footballprediction.companion.domain.repository.AuthRepository
import com.footballprediction.companion.domain.repository.AuthSession
import com.footballprediction.companion.domain.repository.PkceAuthorizationRequest
import com.footballprediction.companion.domain.repository.UserRole
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.Base64
import java.util.concurrent.atomic.AtomicReference
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class InMemoryAuthRepository @Inject constructor() : AuthRepository {
    private val session = AtomicReference<AuthSession?>(null)
    private val pendingRequest = AtomicReference<PkceAuthorizationRequest?>(null)

    override suspend fun beginPkce(): PkceAuthorizationRequest {
        val verifier = randomUrlSafe(48)
        val state = randomUrlSafe(24)
        val challenge = Base64.getUrlEncoder().withoutPadding().encodeToString(
            MessageDigest.getInstance("SHA-256").digest(verifier.toByteArray()),
        )
        return PkceAuthorizationRequest(
            authorizationUri = Uri.parse(
                "https://identity.example.invalid/authorize" +
                    "?response_type=code&client_id=coach-companion" +
                    "&redirect_uri=footballcompanion://callback" +
                    "&code_challenge=$challenge&code_challenge_method=S256&state=$state",
            ).toString(),
            state = state,
            codeVerifier = verifier,
        ).also { pendingRequest.set(it) }
    }

    override suspend fun completePkce(callbackUri: String): Result<AuthSession> {
        val request = pendingRequest.get() ?: return Result.failure(
            IllegalStateException("No pending PKCE request"),
        )
        val parsedCallback = Uri.parse(callbackUri)
        val callbackState = parsedCallback.getQueryParameter("state")
        val authorizationCode = parsedCallback.getQueryParameter("code")
        if (callbackState != request.state || authorizationCode.isNullOrBlank()) {
            return Result.failure(IllegalArgumentException("Invalid OIDC callback state or code"))
        }

        // Production seam: exchange authorizationCode + request.codeVerifier on the server.
        // This stub deliberately does not persist a token or pretend a backend exchange succeeded.
        return Result.failure(
            UnsupportedOperationException("Connect the OIDC token exchange endpoint before release"),
        )
    }

    override fun accessTokenOrNull(): String? {
        val current = session.get() ?: return null
        return if (current.expiresAtEpochSeconds > System.currentTimeMillis() / 1000) {
            current.accessToken
        } else {
            session.set(null)
            null
        }
    }

    override fun clearSession() {
        session.set(null)
        pendingRequest.set(null)
    }

    /** Test/development seam; production code should only receive sessions from OIDC exchange. */
    fun setSessionForDevelopmentOnly(accessToken: String, expiresAtEpochSeconds: Long, role: UserRole) {
        require(accessToken.isNotBlank())
        session.set(AuthSession(accessToken, expiresAtEpochSeconds, role))
    }

    private fun randomUrlSafe(bytes: Int): String {
        val value = ByteArray(bytes).also(SecureRandom()::nextBytes)
        return Base64.getUrlEncoder().withoutPadding().encodeToString(value)
    }
}
