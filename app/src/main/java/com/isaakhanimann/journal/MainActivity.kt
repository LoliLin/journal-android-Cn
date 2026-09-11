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

package com.isaakhanimann.journal

import android.os.Bundle
import androidx.fragment.app.FragmentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import com.isaakhanimann.journal.ui.main.MainScreen
import com.isaakhanimann.journal.ui.theme.JournalTheme
import com.isaakhanimann.journal.ui.widgets.StatsWidgetUpdater
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch

@AndroidEntryPoint
class MainActivity : FragmentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        installSplashScreen()
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        // Screen-on refreshes for the effect-notification timeline register once
        // here; actual re-renders run through the activity's view tree below.
        val app = application as com.isaakhanimann.journal.di.JournalApplication
        com.isaakhanimann.journal.ui.notifications.EffectNotificationRefresher.register(
            this,
            app.applicationScope
        )
        setContent {
            JournalTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    MainScreen()
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        // Foregrounded again: the activity view tree is available, so any
        // pending (dirty or overdue) timeline refresh can render now.
        val root = findViewById<android.view.View>(android.R.id.content)
        com.isaakhanimann.journal.ui.notifications.EffectNotificationRefresher.flushIfDue(
            this,
            root,
            force = false
        )
        // Keep the stats widget in sync after any journal change made while
        // the app was closed or in the background. The updater computes on
        // Dispatchers.Default; only the RemoteViews push runs here.
        val app = application as com.isaakhanimann.journal.di.JournalApplication
        app.applicationScope.launch {
            try {
                StatsWidgetUpdater.refreshAll(this@MainActivity, app.experienceRepository)
            } catch (_: Exception) {
                // Widget refresh must never crash the app process.
            }
        }
    }
}
