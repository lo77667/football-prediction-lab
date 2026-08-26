package com.footballprediction.companion.data.local

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

private val Context.preferencesDataStore by preferencesDataStore(name = "companion_preferences")

@Singleton
class AppPreferences @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    val highContrastEnabled: Flow<Boolean> = context.preferencesDataStore.data.map { preferences ->
        preferences[HIGH_CONTRAST_KEY] ?: false
    }

    suspend fun setHighContrastEnabled(enabled: Boolean) {
        context.preferencesDataStore.edit { preferences ->
            preferences[HIGH_CONTRAST_KEY] = enabled
        }
    }

    private companion object {
        val HIGH_CONTRAST_KEY = booleanPreferencesKey("high_contrast_enabled")
    }
}
