package com.footballprediction.companion

import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import com.footballprediction.companion.domain.repository.UserRole
import com.footballprediction.companion.presentation.navigation.NavGraph
import com.footballprediction.companion.presentation.theme.CompanionTheme
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        setContent {
            CompanionTheme {
                Surface(color = MaterialTheme.colorScheme.background) {
                    // Replace with a session-derived role after real OIDC integration.
                    NavGraph(mockedRole = UserRole.COACH)
                }
            }
        }
    }
}
