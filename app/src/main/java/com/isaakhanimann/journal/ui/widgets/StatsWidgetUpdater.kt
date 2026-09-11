package com.isaakhanimann.journal.ui.widgets

import android.appwidget.AppWidgetManager
import android.content.ComponentName
import android.content.Context
import com.isaakhanimann.journal.data.room.experiences.ExperienceRepository
import com.isaakhanimann.journal.data.room.experiences.JournalDataEvents
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.FlowPreview
import kotlinx.coroutines.flow.debounce
import kotlinx.coroutines.launch

/**
 * Pushes fresh summaries into every placed stats widget. Called on journal
 * data changes (JournalDataEvents), app-language changes, and app start, so
 * the desktop never waits for the hourly updatePeriod.
 */
object StatsWidgetUpdater {

    /**
     * Refreshes every placed widget. Safe from the main thread: data reads
     * and preference writes run on Dispatchers.Default, only the RemoteViews
     * push touches the framework. No-op when no stats widget is placed.
     */
    suspend fun refreshAll(context: Context, experienceRepository: ExperienceRepository) {
        val appContext = context.applicationContext
        val manager = AppWidgetManager.getInstance(appContext)
        val ids = manager.getAppWidgetIds(
            ComponentName(appContext, StatsWidgetProvider::class.java)
        )
        if (ids.isEmpty()) return
        ids.forEach { id ->
            StatsWidgetData.refresh(appContext, id, experienceRepository)
            manager.updateAppWidget(id, StatsWidgetProvider.render(appContext, id))
        }
    }

    /**
     * Recomputes whenever journal data changes (insert/edit/delete/import).
     * Debounced so an import or a burst of edits triggers one refresh.
     */
    @OptIn(FlowPreview::class)
    fun observeDataChanges(
        context: Context,
        experienceRepository: ExperienceRepository,
        scope: CoroutineScope
    ) {
        scope.launch {
            JournalDataEvents.journalChangeSignal
                .debounce(500)
                .collect {
                    try {
                        refreshAll(context, experienceRepository)
                    } catch (_: Exception) {
                        // Widget refresh must never crash the app process.
                    }
                }
        }
    }
}
