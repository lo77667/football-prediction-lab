package com.footballprediction.companion.presentation.player

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@Composable
fun PlayerHomeScreen() {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp),
    ) {
        Text("My day", style = MaterialTheme.typography.headlineMedium)
        Text(
            "Your wellness check-in and personal progress will appear here. No peer comparisons are shown.",
            style = MaterialTheme.typography.bodyLarge,
        )
        Button(onClick = { /* Wire to the self-only wellness flow in the next slice. */ }) {
            Text("Open check-in")
        }
    }
}
