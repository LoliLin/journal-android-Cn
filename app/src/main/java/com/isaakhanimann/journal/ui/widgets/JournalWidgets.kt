package com.isaakhanimann.journal.ui.widgets

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.widget.RemoteViews
import com.isaakhanimann.journal.MainActivity
import com.isaakhanimann.journal.R
import com.isaakhanimann.journal.ui.notifications.EXTRA_NAVIGATE_TO
import com.isaakhanimann.journal.ui.notifications.EXTRA_SUBSTANCE_NAME
import com.isaakhanimann.journal.ui.notifications.NAV_ADD_INGESTION
import com.isaakhanimann.journal.ui.notifications.NAV_STATS
import com.isaakhanimann.journal.ui.notifications.NAV_CHOOSE_ROUTE
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

private fun pendingActivity(
    context: Context,
    navTarget: String,
    requestCode: Int,
    substanceName: String? = null
): PendingIntent =
    PendingIntent.getActivity(
        context,
        requestCode,
        Intent(context, MainActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            putExtra(EXTRA_NAVIGATE_TO, navTarget)
            substanceName?.let { putExtra(EXTRA_SUBSTANCE_NAME, it) }
        },
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
    )

private fun pendingConfigure(context: Context, appWidgetId: Int): PendingIntent =
    PendingIntent.getActivity(
        context,
        // Distinct request-code space: PendingIntent collisions silently replace
        // one another, which made the gear button open the wrong screen.
        200_000 + appWidgetId,
        Intent(context, StatsWidgetConfigActivity::class.java).apply {
            putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, appWidgetId)
        },
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
    )

class StatsWidgetProvider : AppWidgetProvider() {

    override fun onUpdate(
        context: Context,
        appWidgetManager: AppWidgetManager,
        appWidgetIds: IntArray
    ) {
        val pending = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val app = context.applicationContext as? com.isaakhanimann.journal.di.JournalApplication
                appWidgetIds.forEach { appWidgetId ->
                    if (app != null) {
                        StatsWidgetData.refresh(context, appWidgetId, app.experienceRepository)
                    }
                    appWidgetManager.updateAppWidget(appWidgetId, render(context, appWidgetId))
                }
            } finally {
                pending.finish()
            }
        }
    }

    override fun onDeleted(context: Context, appWidgetIds: IntArray) {
        StatsWidgetData.deleteConfig(context, appWidgetIds)
    }

    companion object {

        /**
         * Asks the framework to re-run [onUpdate] for every placed stats widget.
         * Rendering lives only in the provider, so callers (data changes, app
         * start, language changes, config save) just poke AppWidgetManager and
         * never build RemoteViews themselves. No-op when no widget is placed.
         */
        fun requestUpdate(context: Context) {
            val appContext = context.applicationContext
            val provider = ComponentName(appContext, StatsWidgetProvider::class.java)
            val ids = AppWidgetManager.getInstance(appContext).getAppWidgetIds(provider)
            if (ids.isEmpty()) return
            appContext.sendBroadcast(
                Intent(appContext, StatsWidgetProvider::class.java).apply {
                    action = AppWidgetManager.ACTION_APPWIDGET_UPDATE
                    putExtra(AppWidgetManager.EXTRA_APPWIDGET_IDS, ids)
                }
            )
        }

        fun render(context: Context, appWidgetId: Int): RemoteViews {
            val summary = StatsWidgetData.readSummary(context, appWidgetId)
            val app = context.applicationContext as? com.isaakhanimann.journal.di.JournalApplication
            val localized = { key: String -> com.isaakhanimann.journal.localization.I18n.translate(context, key) }
            val title = if (summary.substanceName != null) {
                val display = app?.substanceRepo?.getDisplayName(summary.substanceName)
                    ?: summary.substanceName
                "$display · ${summary.days}d"
            } else {
                "${localized("widget_config_all_substances")} · ${summary.days}d"
            }
            // Tapping the card opens the "choose administration route" page for
            // the bound substance (the ingestion flow); All opens the Stats tab.
            val bodyNavTarget =
                summary.substanceName?.let { NAV_CHOOSE_ROUTE } ?: NAV_STATS
            return RemoteViews(context.packageName, R.layout.widget_stats).apply {
                setTextViewText(R.id.widget_stats_title, title)
                setTextViewText(
                    R.id.widget_stats_ingestions,
                    localized("widget_stat_ingestions")
                )
                setTextViewText(
                    R.id.widget_stats_experiences,
                    localized("widget_stat_experiences")
                )
                setTextViewText(
                    R.id.widget_stats_substances,
                    localized("widget_stat_substances")
                )
                // Numbers as separate views so labels localize without string templates.
                setTextViewText(R.id.widget_stats_ingestions_count, summary.ingestionCount.toString())
                setTextViewText(
                    R.id.widget_stats_experiences_count,
                    summary.experienceCount.toString()
                )
                // Substance count is meaningless when one substance is bound.
                setViewVisibility(
                    R.id.widget_stats_substances_column,
                    if (summary.substanceName == null) android.view.View.VISIBLE
                    else android.view.View.GONE
                )
                setTextViewText(
                    R.id.widget_stats_substances_count,
                    summary.substanceCount.toString()
                )
                setOnClickPendingIntent(
                    R.id.widget_stats_root,
                    pendingActivity(
                        context,
                        bodyNavTarget,
                        appWidgetId,
                        summary.substanceName
                    )
                )
                setOnClickPendingIntent(
                    R.id.widget_stats_settings,
                    pendingConfigure(context, appWidgetId)
                )
            }
        }
    }
}
