package com.footballprediction.companion.presentation.coach

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
fun CoachHomeScreen() {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp),
    ) {
        Text("Coach companion", style = MaterialTheme.typography.headlineMedium)
        Text(
            "Live alerts and authorized player summaries will appear here after API authentication.",
            style = MaterialTheme.typography.bodyLarge,
        )
        Button(onClick = { /* Wire to repository refresh in the next slice. */ }) {
            Text("Refresh when connected")
        }
    }
}
