/*
 * Fork feature: build timeline data outside ViewModels so it can be reused by
 * the notification (rendered to a bitmap at ingestion-save time).
 */
package com.isaakhanimann.journal.ui.tabs.journal.experience.components

import android.content.Context
import android.graphics.Bitmap
import android.util.Log
import android.view.View
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.isaakhanimann.journal.data.room.experiences.entities.ShulginRating
import com.isaakhanimann.journal.data.room.experiences.entities.TimedNote
import com.isaakhanimann.journal.data.room.experiences.relations.IngestionWithCompanionAndCustomUnit
import com.isaakhanimann.journal.data.substances.repositories.SubstanceRepository
import com.isaakhanimann.journal.ui.tabs.journal.experience.models.IngestionElement
import com.isaakhanimann.journal.ui.tabs.journal.experience.timeline.DataForOneRating
import com.isaakhanimann.journal.ui.tabs.journal.experience.timeline.DataForOneTimedNote
import com.isaakhanimann.journal.ui.theme.JournalTheme
import com.isaakhanimann.journal.ui.utils.renderComposeViewToBitmap

/**
 * Pure mapping from stored ingestions + substance data to the model the
 * timeline canvas draws. Mirrors TimelineScreenViewModel/ExperienceEffectTimelines
 * logic so all callers render identically.
 */
fun buildIngestionElements(
    ingestions: List<IngestionWithCompanionAndCustomUnit>,
    substanceRepo: SubstanceRepository
): List<IngestionElement> = ingestions
    .sortedBy { it.ingestion.time }
    .map { oneIngestionWithComp ->
        val ingestion = oneIngestionWithComp.ingestion
        val roa = substanceRepo.getSubstance(ingestion.substanceName)
            ?.getRoa(ingestion.administrationRoute, ingestion.releaseForm)
        // Custom-unit doses must resolve through the unit conversion; mirroring
        // ExperienceViewModel.getIngestionElements.
        val numDots = if (oneIngestionWithComp.customUnit != null) {
            roa?.roaDose?.getNumDots(
                ingestionDose = oneIngestionWithComp.customUnitDose?.calculatedDose,
                ingestionUnits = oneIngestionWithComp.customUnit?.originalUnit
            )
        } else {
            roa?.roaDose?.getNumDots(
                ingestionDose = ingestion.dose,
                ingestionUnits = ingestion.units
            )
        }
        IngestionElement(
            ingestionWithCompanionAndCustomUnit = oneIngestionWithComp,
            roaDuration = roa?.roaDuration,
            numDots = numDots
        )
    }

fun timedNotesForTimeline(timedNotes: List<TimedNote>): List<DataForOneTimedNote> =
    timedNotes.filter { it.isPartOfTimeline }.map { DataForOneTimedNote(it.time, it.color) }

/**
 * Renders the effect timeline for the given ingestions to a bitmap, suitable
 * for a notification BigPictureStyle. Must be called while an Activity view
 * tree is available (the save flow runs before dismissal). Returns null when
 * nothing is drawable or rendering fails; callers fall back to the plain text
 * notification.
 */
suspend fun renderTimelineBitmapForNotification(
    context: Context,
    ingestions: List<IngestionWithCompanionAndCustomUnit>,
    ratings: List<ShulginRating>,
    timedNotes: List<TimedNote>,
    substanceRepo: SubstanceRepository,
    lifecycleView: View,
    widthPx: Int
): Bitmap? {
    val ingestionElements = buildIngestionElements(ingestions, substanceRepo)
    if (ingestionElements.isEmpty()) return null
    if (ingestionElements.all { it.roaDuration == null }) return null
    val dataForRatings = ratings.mapNotNull {
        it.time?.let { time -> DataForOneRating(time, it.option) }
    }
    // OneExperienceScreen shrinks the canvas when the substance data lacks a
    // full onset/comeup/peak/offset; do the same so the picture is not mostly
    // empty space.
    val hasFullDuration = ingestionElements.any {
        it.roaDuration?.onset != null &&
            it.roaDuration.comeup != null &&
            it.roaDuration.peak != null &&
            it.roaDuration.offset != null
    }
    val timelineHeight = if (hasFullDuration) 200.dp else 110.dp
    return try {
        renderComposeViewToBitmap(
            context = context,
            widthPx = widthPx,
            lifecycleView = lifecycleView,
            // The timeline canvas needs one full frame after layout before
            // its draw pass has content; the other offscreen call sites
            // (TimelineScreen, ExperienceRow) use the same delay.
            postLayoutDelayMs = 400L,
            // Draw on the software canvas: hardware layers are not readable
            // into the bitmap on some devices, producing a blank picture.
            drawOnSoftwareCanvas = true,
            content = {
                JournalTheme {
                    ExperienceEffectTimelines(
                        ingestionElements = ingestionElements,
                        dataForRatings = dataForRatings,
                        dataForTimedNotes = timedNotesForTimeline(timedNotes),
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(timelineHeight),
                        areSubstanceHeightsIndependent = false
                    )
                }
            }
        )
    } catch (e: Exception) {
        Log.w(TAG, "Timeline notification bitmap failed", e)
        null
    }
}

private const val TAG = "NotifTimeline"
