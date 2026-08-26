package com.footballprediction.companion

import com.footballprediction.companion.data.repository.InMemoryAuthRepository
import com.footballprediction.companion.domain.repository.UserRole
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class InMemoryAuthRepositoryTest {
    @Test
    fun `access token is memory only and cleared explicitly`() {
        val repository = InMemoryAuthRepository()
        repository.setSessionForDevelopmentOnly(
            accessToken = "test-token",
            expiresAtEpochSeconds = (System.currentTimeMillis() / 1000) + 60,
            role = UserRole.COACH,
        )

        assertEquals("test-token", repository.accessTokenOrNull())
        repository.clearSession()
        assertNull(repository.accessTokenOrNull())
    }

    @Test
    fun `expired token is not returned`() {
        val repository = InMemoryAuthRepository()
        repository.setSessionForDevelopmentOnly(
            accessToken = "expired-token",
            expiresAtEpochSeconds = 0,
            role = UserRole.PLAYER,
        )

        assertNull(repository.accessTokenOrNull())
    }
}
