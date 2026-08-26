package com.footballprediction.companion.core.security

import android.content.Context
import android.util.Base64
import java.security.KeyStore
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class SecurityManager @Inject constructor(
    private val context: Context,
) {
    private val preferences by lazy {
        context.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)
    }

    /**
     * Returns the database passphrase, generating and wrapping it on first use.
     * The raw passphrase is never written to disk; only an AES-GCM ciphertext and
     * IV are stored in app-private preferences, with the AES key held by Keystore.
     */
    @Synchronized
    fun databasePassphrase(): ByteArray {
        val storedCiphertext = preferences.getString(CIPHERTEXT_KEY, null)
        val storedIv = preferences.getString(IV_KEY, null)
        if (storedCiphertext == null || storedIv == null) {
            val passphrase = ByteArray(PASSPHRASE_BYTES).also(SecureRandom()::nextBytes)
            val encrypted = encrypt(passphrase)
            preferences.edit()
                .putString(CIPHERTEXT_KEY, Base64.encodeToString(encrypted.ciphertext, Base64.NO_WRAP))
                .putString(IV_KEY, Base64.encodeToString(encrypted.iv, Base64.NO_WRAP))
                .apply()
            return passphrase
        }
        return decrypt(
            ciphertext = Base64.decode(storedCiphertext, Base64.NO_WRAP),
            iv = Base64.decode(storedIv, Base64.NO_WRAP),
        )
    }

    /** Wipes the wrapped database key. Delete the Room database before calling this. */
    fun clearDatabaseKey() {
        preferences.edit().remove(CIPHERTEXT_KEY).remove(IV_KEY).apply()
        keyStore().deleteEntry(KEY_ALIAS)
    }

    private fun encrypt(plaintext: ByteArray): EncryptedValue {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateWrappingKey())
        return EncryptedValue(cipher.doFinal(plaintext), cipher.iv)
    }

    private fun decrypt(ciphertext: ByteArray, iv: ByteArray): ByteArray {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(
            Cipher.DECRYPT_MODE,
            getOrCreateWrappingKey(),
            GCMParameterSpec(GCM_TAG_BITS, iv),
        )
        return cipher.doFinal(ciphertext)
    }

    @Synchronized
    private fun getOrCreateWrappingKey(): SecretKey {
        val store = keyStore()
        val existing = store.getKey(KEY_ALIAS, null) as? SecretKey
        if (existing != null) return existing

        val generator = KeyGenerator.getInstance(KEY_ALGORITHM, ANDROID_KEYSTORE)
        generator.init(
            android.security.keystore.KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                android.security.keystore.KeyProperties.PURPOSE_ENCRYPT or
                    android.security.keystore.KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(android.security.keystore.KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(android.security.keystore.KeyProperties.ENCRYPTION_PADDING_NONE)
                .setUserAuthenticationRequired(false)
                .build(),
        )
        return generator.generateKey()
    }

    private fun keyStore(): KeyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }

    private data class EncryptedValue(val ciphertext: ByteArray, val iv: ByteArray)

    private companion object {
        const val ANDROID_KEYSTORE = "AndroidKeyStore"
        const val KEY_ALGORITHM = "AES"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val KEY_ALIAS = "coach_companion_db_wrap_key_v1"
        const val PREFERENCES_NAME = "coach_companion_wrapped_keys"
        const val CIPHERTEXT_KEY = "database_passphrase_ciphertext"
        const val IV_KEY = "database_passphrase_iv"
        const val PASSPHRASE_BYTES = 32
        const val GCM_TAG_BITS = 128
    }
}
