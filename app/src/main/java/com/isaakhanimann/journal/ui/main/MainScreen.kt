/*
 * Copyright (c) 2022-2023. Isaak Hanimann.
 * This file is part of PsychonautWiki Journal.
 *
 * PsychonautWiki Journal is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or (at
 * your option) any later version.
 *
 * PsychonautWiki Journal is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with PsychonautWiki Journal.  If not, see https://www.gnu.org/licenses/gpl-3.0.en.html.
 */

package com.isaakhanimann.journal.ui.main

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.shrinkVertically
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.offset
import androidx.compose.material3.BottomAppBarDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.input.nestedscroll.NestedScrollConnection
import androidx.compose.ui.input.nestedscroll.NestedScrollSource
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.IntOffset
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.isaakhanimann.journal.localization.I18n
import com.isaakhanimann.journal.localization.i18n
import com.isaakhanimann.journal.ui.main.navigation.graphs.journalGraph
import com.isaakhanimann.journal.ui.main.navigation.graphs.navigateToAddIngestion
import com.isaakhanimann.journal.ui.main.navigation.routers.navigateToChooseRouteOfAddIngestion
import com.isaakhanimann.journal.ui.main.navigation.routers.navigateToQuickTimedNote
import com.isaakhanimann.journal.ui.main.navigation.routers.navigateToSubstanceCompanionScreen
import com.isaakhanimann.journal.ui.main.navigation.routers.navigateToSubstanceScreen
import com.isaakhanimann.journal.ui.main.navigation.routers.navigateToTimeCapsule
import com.isaakhanimann.journal.ui.notifications.EXTRA_EXPERIENCE_ID
import com.isaakhanimann.journal.ui.notifications.EXTRA_NAVIGATE_TO
import com.isaakhanimann.journal.ui.notifications.EXTRA_SUBSTANCE_NAME
import com.isaakhanimann.journal.ui.notifications.NAV_QUICK_NOTE
import com.isaakhanimann.journal.ui.notifications.NAV_ADD_INGESTION
import com.isaakhanimann.journal.ui.notifications.NAV_STATS
import com.isaakhanimann.journal.ui.notifications.NAV_SUBSTANCE
import com.isaakhanimann.journal.ui.notifications.NAV_CHOOSE_ROUTE
import com.isaakhanimann.journal.ui.notifications.NAV_SUBSTANCE_COMPANION
import com.isaakhanimann.journal.ui.notifications.NAV_TIME_CAPSULE
import com.isaakhanimann.journal.ui.main.navigation.graphs.saferGraph
import com.isaakhanimann.journal.ui.main.navigation.graphs.searchGraph
import com.isaakhanimann.journal.ui.main.navigation.graphs.settingsGraph
import com.isaakhanimann.journal.ui.main.navigation.graphs.statsGraph
import com.isaakhanimann.journal.ui.main.navigation.routers.TabRouter
import com.isaakhanimann.journal.ui.main.navigation.routers.isMainTabRootRoute
import com.isaakhanimann.journal.ui.utils.keyboard.isKeyboardOpen

private fun parseNavIntent(intent: android.content.Intent?): Triple<String, Int, String?>? {
    val target = intent?.getStringExtra(EXTRA_NAVIGATE_TO) ?: return null
    val experienceId = intent.getIntExtra(EXTRA_EXPERIENCE_ID, -1)
    val substanceName = intent.getStringExtra(EXTRA_SUBSTANCE_NAME)
    return Triple(target, experienceId, substanceName)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainScreen(viewModel: MainScreenViewModel = hiltViewModel()) {
    val selectedLanguageKey by viewModel.selectedLanguageFlow.collectAsState()
    LaunchedEffect(selectedLanguageKey) {
        I18n.setPreferredLanguageKey(selectedLanguageKey)
    }
    val isAccepted = viewModel.isAcceptedFlow.collectAsState().value
    val isBottomBarPinned = viewModel.isBottomBarPinnedFlow.collectAsState().value

    // Notification taps can steer the app to a target screen (quick note / time capsule).
    // Tracked above the gate so the intent survives the accept/lock screens and is
    // consumed by the content branch once it composes.
    var pendingNav by remember { mutableStateOf<Triple<String, Int, String?>?>(null) }
    val activity = LocalContext.current as? androidx.activity.ComponentActivity
    DisposableEffect(activity) {
        val listener = { intent: android.content.Intent ->
            parseNavIntent(intent)?.let { pendingNav = it }
            Unit
        }
        activity?.addOnNewIntentListener(listener)
        onDispose { activity?.removeOnNewIntentListener(listener) }
    }
    LaunchedEffect(Unit) {
        parseNavIntent(activity?.intent)?.let { pendingNav = it }
    }

    if (isAccepted == null) {
        // DataStore value not read yet: show nothing instead of flashing content.
        Box(modifier = Modifier.fillMaxSize())
    } else if (!isAccepted) {
        AcceptConditionsScreen(onTapAccept = viewModel::accept)
    } else if (viewModel.isAppLockEnabledFlow.collectAsState().value &&
        !viewModel.isUnlockedFlow.collectAsState().value
    ) {
        AppLockScreen(onUnlocked = viewModel::markUnlocked)
    } else {
        val navController = rememberNavController()
        val navBackStackEntry by navController.currentBackStackEntryAsState()
        val currentDestination = navBackStackEntry?.destination

        LaunchedEffect(pendingNav) {
            pendingNav?.let { (target, experienceId, substanceName) ->
                when (target) {
                    NAV_QUICK_NOTE -> if (experienceId > 0) {
                        navController.navigateToQuickTimedNote(experienceId)
                    }
                    NAV_TIME_CAPSULE -> navController.navigateToTimeCapsule()
                    NAV_ADD_INGESTION -> navController.navigateToAddIngestion()
                    NAV_STATS -> navController.navigate(TabRouter.Statistics.route) {
                        popUpTo(navController.graph.findStartDestination().id) {
                            saveState = true
                        }
                        launchSingleTop = true
                        restoreState = true
                    }
                    NAV_SUBSTANCE -> if (!substanceName.isNullOrBlank()) {
                        navController.navigateToSubstanceScreen(substanceName)
                    }
                    NAV_SUBSTANCE_COMPANION -> if (!substanceName.isNullOrBlank()) {
                        navController.navigateToSubstanceCompanionScreen(substanceName, null)
                    }
                    NAV_CHOOSE_ROUTE -> if (!substanceName.isNullOrBlank()) {
                        navController.navigateToChooseRouteOfAddIngestion(substanceName)
                    }
                }
                pendingNav = null
            }
        }

        val isKeyboardOpenNow = isKeyboardOpen().value
        val isOnMainTabRoot = isMainTabRootRoute(currentDestination?.route)
        val isBottomBarShown = isOnMainTabRoot && !isKeyboardOpenNow
        // Official Material3 hide-on-scroll connection, plus onPreScroll so an
        // upward swipe at the list top (consumed.y == 0) still reveals the bar.
        // When the user pins the bar (issue #144) no connection is provided at
        // all: lists scroll normally and the bar never moves.
        val bottomBarScrollBehavior = BottomAppBarDefaults.exitAlwaysScrollBehavior(
            canScroll = { isOnMainTabRoot && !isKeyboardOpenNow }
        )
        val nestedScrollConnection = if (isBottomBarPinned) {
            null
        } else {
            remember(bottomBarScrollBehavior) {
                val official = bottomBarScrollBehavior.nestedScrollConnection
                object : NestedScrollConnection {
                    override fun onPreScroll(
                        available: Offset,
                        source: NestedScrollSource
                    ): Offset {
                        if (available.y > 0f &&
                            bottomBarScrollBehavior.state.heightOffset < 0f
                        ) {
                            val state = bottomBarScrollBehavior.state
                            val next = (state.heightOffset + available.y)
                                .coerceIn(state.heightOffsetLimit, 0f)
                            val consumedY = next - state.heightOffset
                            state.heightOffset = next
                            return Offset(0f, consumedY)
                        }
                        return Offset.Zero
                    }

                    override fun onPostScroll(
                        consumed: Offset,
                        available: Offset,
                        source: NestedScrollSource
                    ): Offset = official.onPostScroll(consumed, available, source)
                }
            }
        }
        LaunchedEffect(isOnMainTabRoot, isKeyboardOpenNow, isBottomBarPinned) {
            if (!isOnMainTabRoot || isKeyboardOpenNow || isBottomBarPinned) {
                bottomBarScrollBehavior.state.heightOffset = 0f
            }
        }

        Box(modifier = Modifier.fillMaxSize()) {
            val barHeightPx = remember { mutableIntStateOf(0) }
            val heightOffset = if (isBottomBarPinned) {
                0f
            } else {
                bottomBarScrollBehavior.state.heightOffset
            }
            val visibleBarPx = if (isBottomBarShown) {
                (barHeightPx.intValue + heightOffset.toInt()).coerceAtLeast(0)
            } else {
                0
            }
            CompositionLocalProvider(
                LocalBottomBarNestedScrollConnection provides nestedScrollConnection,
                LocalBottomBarOverlayInsetPx provides visibleBarPx
            ) {
                NavHost(
                    navController,
                    startDestination = TabRouter.Journal.route,
                    modifier = Modifier.fillMaxSize()
                ) {
                    journalGraph(navController)
                    statsGraph(navController)
                    searchGraph(navController)
                    saferGraph(navController)
                    settingsGraph(navController)
                }
            }
            AnimatedVisibility(
                visible = isBottomBarShown,
                modifier = Modifier.align(Alignment.BottomCenter),
                enter = slideInVertically(tween(durationMillis = 250)) { it } +
                    expandVertically(tween(durationMillis = 250), expandFrom = Alignment.Bottom),
                exit = slideOutVertically(tween(durationMillis = 250)) { it } +
                    shrinkVertically(tween(durationMillis = 250), shrinkTowards = Alignment.Bottom)
            ) {
                NavigationBar(
                    modifier = Modifier
                        .onSizeChanged { size ->
                            barHeightPx.intValue = size.height
                            bottomBarScrollBehavior.state.heightOffsetLimit =
                                -size.height.toFloat()
                        }
                        .offset {
                            IntOffset(
                                x = 0,
                                y = if (isBottomBarPinned) {
                                    0
                                } else {
                                    -bottomBarScrollBehavior.state.heightOffset.toInt()
                                }
                            )
                        }
                ) {
                    val tabs = listOf(
                        TabRouter.Statistics,
                        TabRouter.Journal,
                        TabRouter.Substances,
                        TabRouter.SaferUse,
                        TabRouter.Settings
                    )
                    tabs.forEach { tab ->
                        val isSelected =
                            currentDestination?.hierarchy?.any { it.route == tab.route } == true
                        NavigationBarItem(
                            icon = {
                                if (isSelected) {
                                    Icon(tab.iconSelected, contentDescription = null)
                                } else {
                                    Icon(tab.icon, contentDescription = null)
                                }
                            },
                            label = { Text(i18n(tab.labelKey)) },
                            selected = isSelected,
                            onClick = {
                                if (isSelected) {
                                    val isAlreadyOnTopOfTab = tabs.any {
                                        it.childRoute ==
                                            currentDestination.route
                                    }
                                    if (!isAlreadyOnTopOfTab) {
                                        navController.popBackStack()
                                    }
                                } else {
                                    navController.navigate(tab.route) {
                                        popUpTo(navController.graph.findStartDestination().id) {
                                            saveState = true
                                        }
                                        launchSingleTop = true
                                        restoreState = true
                                    }
                                }
                            }
                        )
                    }
                }
            }
        }
    }
}
