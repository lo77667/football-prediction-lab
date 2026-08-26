package com.footballprediction.companion.presentation.navigation

import androidx.compose.runtime.Composable
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.footballprediction.companion.domain.repository.UserRole
import com.footballprediction.companion.presentation.coach.CoachHomeScreen
import com.footballprediction.companion.presentation.player.PlayerHomeScreen

@Composable
fun NavGraph(mockedRole: UserRole) {
    val navController = rememberNavController()
    val startDestination = when (mockedRole) {
        UserRole.COACH -> Routes.COACH
        UserRole.PLAYER -> Routes.PLAYER
    }
    NavHost(navController = navController, startDestination = startDestination) {
        composable(Routes.COACH) { CoachHomeScreen() }
        composable(Routes.PLAYER) { PlayerHomeScreen() }
    }
}

private object Routes {
    const val COACH = "coach"
    const val PLAYER = "player"
}
