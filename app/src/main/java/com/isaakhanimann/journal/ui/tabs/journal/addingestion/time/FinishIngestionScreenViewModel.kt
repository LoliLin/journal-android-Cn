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

package com.isaakhanimann.journal.ui.tabs.journal.addingestion.time

import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.isaakhanimann.journal.data.room.experiences.ExperienceRepository
import com.isaakhanimann.journal.data.room.experiences.entities.AdaptiveColor
import com.isaakhanimann.journal.data.room.experiences.entities.Experience
import com.isaakhanimann.journal.data.room.experiences.entities.Ingestion
import com.isaakhanimann.journal.data.room.experiences.entities.SubstanceCompanion
import com.isaakhanimann.journal.data.room.experiences.relations.ExperienceWithIngestions
import com.isaakhanimann.journal.data.substances.AdministrationRoute
import com.isaakhanimann.journal.data.substances.ReleaseForm
import com.isaakhanimann.journal.data.substances.repositories.SubstanceRepository
import com.isaakhanimann.journal.ui.main.navigation.routers.ADMINISTRATION_ROUTE_KEY
import com.isaakhanimann.journal.ui.main.navigation.routers.CUSTOM_UNIT_ID_KEY
import com.isaakhanimann.journal.ui.main.navigation.routers.DOSE_KEY
import com.isaakhanimann.journal.ui.main.navigation.routers.ESTIMATED_DOSE_STANDARD_DEVIATION_KEY
import com.isaakhanimann.journal.ui.main.navigation.routers.IS_ESTIMATE_KEY
import com.isaakhanimann.journal.ui.main.navigation.routers.RELEASE_FORM_KEY
import com.isaakhanimann.journal.ui.main.navigation.routers.SUBSTANCE_NAME_KEY
import com.isaakhanimann.journal.ui.main.navigation.routers.UNITS_KEY
import com.isaakhanimann.journal.ui.notifications.Notifications
import com.isaakhanimann.journal.ui.tabs.settings.combinations.UserPreferences
import com.isaakhanimann.journal.ui.utils.getInstant
import com.isaakhanimann.journal.ui.utils.getLocalDateTime
import com.isaakhanimann.journal.ui.utils.getLongDateText
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import java.time.Duration
import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.temporal.ChronoUnit
import javax.inject.Inject
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.firstOrNull
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

const val hourLimitToSeparateIngestions: Long = 12

enum class IngestionTimePickerOption {
    POINT_IN_TIME,
    TIME_RANGE
}

@HiltViewModel
class FinishIngestionScreenViewModel @Inject constructor(
    private val experienceRepo: ExperienceRepository,
    private val userPreferences: UserPreferences,
    val substanceRepo: SubstanceRepository,
    @ApplicationContext private val appContext: Context,
    private val state: SavedStateHandle
) : ViewModel() {
    var substanceName by mutableStateOf("")
    var releaseForm by mutableStateOf(ReleaseForm.fromName(state.get<String>(RELEASE_FORM_KEY)))
        private set
    val availableReleaseForms: List<ReleaseForm>
        get() = substanceRepo.getSubstance(
            substanceName
        )?.getReleaseForms(administrationRoute).orEmpty()

    fun changeReleaseForm(form: ReleaseForm?) {
        releaseForm = form
        state[RELEASE_FORM_KEY] = form?.name
    }
    val localDateTimeStartFlow = MutableStateFlow(LocalDateTime.now())
    val localDateTimeEndFlow = MutableStateFlow(LocalDateTime.now().plusMinutes(30))
    val ingestionTimePickerOptionFlow = MutableStateFlow(IngestionTimePickerOption.POINT_IN_TIME)
    val experiencesInRangeFlow = MutableStateFlow<List<ExperienceWithIngestions>>(emptyList())
    val selectedExperienceFlow = MutableStateFlow<ExperienceWithIngestions?>(null)

    // Once the user picks an experience (or "new experience") from the dropdown, time changes
    // must not silently re-select a different experience.
    private var hasMadeExplicitExperienceSelection = false
    var enteredTitle by mutableStateOf(LocalDateTime.now().getLongDateText())
    val isEnteredTitleOk get() = enteredTitle.isNotEmpty()
    var consumerName by mutableStateOf("")

    fun onChangeTimePickerOption(ingestionTimePickerOption: IngestionTimePickerOption) =
        viewModelScope.launch {
            ingestionTimePickerOptionFlow.emit(ingestionTimePickerOption)
            if (ingestionTimePickerOption == IngestionTimePickerOption.TIME_RANGE) {
                applySavedDurationPresetIfAny()
            }
        }

    fun onSelectDurationPreset(minutes: Long) = viewModelScope.launch {
        userPreferences.saveRoaDurationPreset(administrationRoute, minutes)
        val startTime = localDateTimeStartFlow.first()
        localDateTimeEndFlow.emit(startTime.plusMinutes(minutes))
    }

    private suspend fun applySavedDurationPresetIfAny() {
        val savedMinutes = userPreferences.getRoaDurationPreset(administrationRoute)
        if (savedMinutes != null) {
            val startTime = localDateTimeStartFlow.first()
            localDateTimeEndFlow.emit(startTime.plusMinutes(savedMinutes))
        }
    }

    private val sortedExperiencesFlow = experienceRepo.getSortedExperiencesWithIngestionsFlow()

    val sortedConsumerNamesFlow =
        experienceRepo.getSortedIngestions(limit = 200).map { ingestions ->
            return@map ingestions.mapNotNull { it.consumerName }.distinct()
        }.stateIn(
            initialValue = emptyList(),
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5000)
        )

    var isLoadingColor by mutableStateOf(true)
    var isShowingColorPicker by mutableStateOf(false)
    var selectedColor by mutableStateOf(AdaptiveColor.BLUE)
    var note by mutableStateOf("")
    private var hasTitleBeenChanged = false

    fun changeTitle(newTitle: String) {
        enteredTitle = newTitle
        hasTitleBeenChanged = true
    }

    fun changeConsumerName(newName: String) {
        consumerName = newName
    }

    val previousNotesFlow: StateFlow<List<String>> =
        experienceRepo.getSortedIngestionsFlow(substanceName, limit = 10).map { list ->
            list.mapNotNull { it.notes }.filter { it.isNotBlank() }.distinct()
        }.stateIn(
            initialValue = emptyList(),
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5000)
        )

    private val administrationRoute: AdministrationRoute
    private val dose: Double?
    private val units: String?
    private val isEstimate: Boolean
    private val estimatedDoseStandardDeviation: Double?
    private val customUnitId: Int?
    private var substanceCompanion: SubstanceCompanion? = null

    private val companionFlow = experienceRepo.getAllSubstanceCompanionsFlow()

    val alreadyUsedColorsFlow: StateFlow<List<AdaptiveColor>> =
        companionFlow.map { companions ->
            companions.map { it.color }.distinct()
        }.stateIn(
            initialValue = emptyList(),
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5000)
        )

    val otherColorsFlow: StateFlow<List<AdaptiveColor>> =
        alreadyUsedColorsFlow.map { alreadyUsedColors ->
            AdaptiveColor.entries.filter {
                !alreadyUsedColors.contains(it)
            }
        }.stateIn(
            initialValue = emptyList(),
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5000)
        )

    private val newExperienceIdToUseFlow: Flow<Int> = sortedExperiencesFlow.map { experiences ->
        val previousMax = experiences.maxOfOrNull { it.experience.id } ?: 1
        return@map previousMax + 1
    }

    init {
        // Fork navigation passes string-route arguments via SavedStateHandle (no type-safe routes).
        substanceName = state.get<String>(SUBSTANCE_NAME_KEY) ?: ""
        administrationRoute = AdministrationRoute.valueOf(
            state.get<String>(ADMINISTRATION_ROUTE_KEY)!!
        )
        dose = state.get<String>(DOSE_KEY)?.toDoubleOrNull()
        estimatedDoseStandardDeviation =
            state.get<String>(ESTIMATED_DOSE_STANDARD_DEVIATION_KEY)?.toDoubleOrNull()
        customUnitId = state.get<String>(CUSTOM_UNIT_ID_KEY)?.toIntOrNull()
        units = state.get<String>(UNITS_KEY)?.let {
            if (it == "null") {
                null
            } else {
                it
            }
        }
        isEstimate = state.get<Boolean>(IS_ESTIMATE_KEY)!!
        viewModelScope.launch {
            val lastIngestionTimeOfExperience =
                userPreferences.lastIngestionTimeOfExperienceFlow.first()
            val clonedIngestionTime = userPreferences.clonedIngestionTimeFlow.first()
            if (clonedIngestionTime != null) {
                localDateTimeStartFlow.emit(clonedIngestionTime.getLocalDateTime())
                localDateTimeEndFlow.emit(
                    clonedIngestionTime.plus(30, ChronoUnit.MINUTES).getLocalDateTime()
                )
                updateTitleBasedOnTime(clonedIngestionTime)
            } else if (lastIngestionTimeOfExperience != null) {
                val wasLastIngestionOfExperienceMoreThan20HoursAgo =
                    lastIngestionTimeOfExperience < Instant.now().minus(20, ChronoUnit.HOURS)
                if (wasLastIngestionOfExperienceMoreThan20HoursAgo) {
                    localDateTimeStartFlow.emit(lastIngestionTimeOfExperience.getLocalDateTime())
                    localDateTimeEndFlow.emit(
                        lastIngestionTimeOfExperience.plus(
                            30,
                            ChronoUnit.MINUTES
                        ).getLocalDateTime()
                    )
                    updateTitleBasedOnTime(lastIngestionTimeOfExperience)
                }
            }
            updateExperiencesBasedOnSelectedTime()
            val allCompanions = experienceRepo.getAllSubstanceCompanionsFlow().first()
            val thisCompanion = allCompanions.firstOrNull { it.substanceName == substanceName }
            substanceCompanion = thisCompanion
            if (thisCompanion == null) {
                isShowingColorPicker = true
                val alreadyUsedColors = allCompanions.map { it.color }
                val otherColors = AdaptiveColor.entries.filter { !alreadyUsedColors.contains(it) }
                selectedColor = otherColors.filter { it.isPreferred }.randomOrNull()
                    ?: otherColors.randomOrNull() ?: AdaptiveColor.entries.random()
            } else {
                selectedColor = thisCompanion.color
            }
            isLoadingColor = false
        }
    }

    fun onChangeOfSelectedExperience(experienceWithIngestions: ExperienceWithIngestions?) =
        viewModelScope.launch {
            hasMadeExplicitExperienceSelection = true
            selectedExperienceFlow.emit(experienceWithIngestions)
        }

    fun onChangeStartDateOrTime(newLocalDateTime: LocalDateTime) = viewModelScope.launch {
        localDateTimeStartFlow.emit(newLocalDateTime)
        updateExperiencesBasedOnSelectedTime()
        val startTime = newLocalDateTime.atZone(ZoneId.systemDefault()).toInstant()
        if (!hasTitleBeenChanged) {
            updateTitleBasedOnTime(startTime)
        }
        val endTime = localDateTimeEndFlow.first().atZone(ZoneId.systemDefault()).toInstant()
        if (startTime > endTime || Duration.between(startTime, endTime).toHours() > 24) {
            val newEndTime = startTime.plus(30, ChronoUnit.MINUTES)
            localDateTimeEndFlow.emit(newEndTime.getLocalDateTime())
        }
    }

    fun onChangeEndDateOrTime(newLocalDateTime: LocalDateTime) = viewModelScope.launch {
        localDateTimeEndFlow.emit(newLocalDateTime)
        val endTime = newLocalDateTime.atZone(ZoneId.systemDefault()).toInstant()
        val startTime =
            localDateTimeStartFlow.first().atZone(ZoneId.systemDefault()).toInstant()
        if (startTime > endTime) {
            val newStartTime = endTime.minus(30, ChronoUnit.MINUTES)
            localDateTimeStartFlow.emit(newStartTime.getLocalDateTime())
        }
    }

    private fun updateTitleBasedOnTime(time: Instant) {
        enteredTitle = time.getLongDateText()
    }

    private suspend fun updateExperiencesBasedOnSelectedTime() {
        val selectedInstant = localDateTimeStartFlow.value.getInstant()
        val fromInstant = selectedInstant.minus(3, ChronoUnit.DAYS)
        val toInstant = selectedInstant.plus(1, ChronoUnit.DAYS)
        val experiencesInRange =
            experienceRepo.getSortedExperiencesWithIngestionsWithSortDateBetween(
                fromInstant = fromInstant,
                toInstant = toInstant
            )
        experiencesInRangeFlow.emit(experiencesInRange)
        val explicitlySelectedExperienceId = selectedExperienceFlow.value?.experience?.id
        val isExplicitlySelectedExperienceStillInRange =
            explicitlySelectedExperienceId != null &&
                experiencesInRange.any { it.experience.id == explicitlySelectedExperienceId }
        // Re-run auto selection unless the user chose explicitly and that choice is still in
        // range; an explicit "new experience" choice is always kept.
        val shouldReRunAutoSelection = !hasMadeExplicitExperienceSelection ||
            (explicitlySelectedExperienceId != null && !isExplicitlySelectedExperienceStillInRange)
        if (shouldReRunAutoSelection) {
            val enforceDayBoundary = userPreferences.isMidnightCutoffEnabledFlow.first()
            val closestExperience = findClosestExperience(
                experiences = experiencesInRange,
                selectedInstant = selectedInstant,
                zone = ZoneId.systemDefault(),
                enforceDayBoundary = enforceDayBoundary
            )
            selectedExperienceFlow.emit(closestExperience)
        }
    }

    fun createSaveAndDismissAfter(dismiss: () -> Unit, lifecycleView: android.view.View? = null) {
        viewModelScope.launch {
            createAndSaveIngestion(lifecycleView)
            withContext(Dispatchers.Main) {
                dismiss()
            }
        }
    }

    private suspend fun createAndSaveIngestion(lifecycleView: android.view.View?) {
        val substanceCompanion = SubstanceCompanion(
            substanceName,
            color = selectedColor
        )
        val oldIdToUse = selectedExperienceFlow.firstOrNull()?.experience?.id
        val ingestionTime =
            localDateTimeStartFlow.first().atZone(ZoneId.systemDefault()).toInstant()
        val savedExperienceId: Int
        if (oldIdToUse == null) {
            val newIdToUse = newExperienceIdToUseFlow.firstOrNull() ?: 1
            val newExperience = Experience(
                id = newIdToUse,
                title = enteredTitle,
                text = "",
                creationDate = Instant.now(),
                sortDate = ingestionTime,
                location = null // todo: allow to add real location
            )
            val newIngestion = createNewIngestion(newExperience.id)
            experienceRepo.insertIngestionExperienceAndCompanion(
                ingestion = newIngestion,
                experience = newExperience,
                substanceCompanion = substanceCompanion
            )
            savedExperienceId = newExperience.id
        } else {
            val newIngestion = createNewIngestion(oldIdToUse)
            experienceRepo.insertIngestionAndCompanion(
                ingestion = newIngestion,
                substanceCompanion = substanceCompanion
            )
            savedExperienceId = oldIdToUse
        }
        // Fork feature: keep an "effects in progress" notification with quick-note access.
        if (userPreferences.isEffectNotificationEnabledFlow.first()) {
            // Attach the effect timeline as the notification picture when a view
            // tree is available (save always runs on-screen, before dismissal).
            val timelineBitmap = lifecycleView?.let { view ->
                val experienceId = savedExperienceId
                val ingestions = experienceRepo
                    .getIngestionsWithCompanionsFlow(experienceId).first()
                val ratings = experienceRepo.getRatingsFlow(experienceId).first()
                val timedNotes = experienceRepo.getTimedNotes(experienceId)
                com.isaakhanimann.journal.ui.tabs.journal.experience.components
                    .renderTimelineBitmapForNotification(
                        context = appContext,
                        ingestions = ingestions,
                        ratings = ratings,
                        timedNotes = timedNotes,
                        substanceRepo = substanceRepo,
                        lifecycleView = view,
                        widthPx = appContext.resources.displayMetrics.widthPixels
                    )
            }
            // Longest plausible effect window for this substance+route: feeds the
            // screen-on refresh cadence (total-duration / 30).
            val totalDuration = substanceRepo.getSubstance(substanceName)
                ?.getRoa(administrationRoute, releaseForm)?.roaDuration?.total
                ?.interpolateAtValueInSeconds(1f)?.let { java.time.Duration.ofSeconds(it.toLong()) }
            Notifications.showEffectNotification(
                context = appContext,
                experienceId = savedExperienceId,
                substanceName = substanceName,
                ingestionTime = ingestionTime,
                timelineBitmap = timelineBitmap
            )
            if (timelineBitmap != null) {
                com.isaakhanimann.journal.ui.notifications.EffectNotificationRefresher
                    .onNotificationRendered(
                        savedExperienceId,
                        ingestionTime,
                        substanceName,
                        totalDuration
                    )
            }
        }
    }

    private suspend fun createNewIngestion(experienceId: Int): Ingestion {
        val time = localDateTimeStartFlow.first().atZone(ZoneId.systemDefault()).toInstant()
        val ingestionTimePickerOption = ingestionTimePickerOptionFlow.first()
        val endTime = when (ingestionTimePickerOption) {
            IngestionTimePickerOption.POINT_IN_TIME -> null
            IngestionTimePickerOption.TIME_RANGE -> localDateTimeEndFlow.first()
                .atZone(ZoneId.systemDefault()).toInstant()
        }
        return Ingestion(
            substanceName = substanceName,
            time = time,
            endTime = endTime,
            administrationRoute = administrationRoute,
            dose = dose,
            isDoseAnEstimate = isEstimate,
            estimatedDoseStandardDeviation = estimatedDoseStandardDeviation,
            units = units,
            experienceId = experienceId,
            notes = note,
            stomachFullness = null, // todo: allow to add real stomach fullness
            consumerName = consumerName.ifBlank {
                null
            },
            customUnitId = customUnitId,
            releaseForm = releaseForm.takeIf { administrationRoute == AdministrationRoute.ORAL }
        )
    }
}

/**
 * Picks the experience a new ingestion at [selectedInstant] should join, or null if it should
 * start a new one.
 *
 * An experience matches when [selectedInstant] lies within its session window
 * (first ingestion - 3h .. max(first ingestion + 15h, last ingestion + 3h)). When
 * [enforceDayBoundary] is enabled, the instant must additionally fall on one of the calendar
 * days the experience's own ingestions span, so an ingestion shortly after midnight starts a
 * new experience instead of joining the previous day's: a session only continues into the next
 * calendar day if it demonstrably crossed midnight. The day span is treated as a contiguous
 * range: an experience with ingestions on non-adjacent days also matches a selected day in between.
 */
internal fun findClosestExperience(
    experiences: List<ExperienceWithIngestions>,
    selectedInstant: Instant,
    zone: ZoneId,
    enforceDayBoundary: Boolean
): ExperienceWithIngestions? {
    return experiences.firstOrNull { experience ->
        val sortedIngestions = experience.ingestions.sortedBy { it.time }
        val firstIngestionTime = sortedIngestions.firstOrNull()?.time ?: return@firstOrNull false
        val upperBoundBasedOnFirstIngestion = firstIngestionTime.plus(15, ChronoUnit.HOURS)
        val lastIngestionTime = sortedIngestions.lastOrNull()?.time ?: return@firstOrNull false
        val upperBoundBasedOnLastIngestion = lastIngestionTime.plus(3, ChronoUnit.HOURS)
        val finalUpperBound =
            maxOf(upperBoundBasedOnFirstIngestion, upperBoundBasedOnLastIngestion)
        val lowerBound = firstIngestionTime.minus(3, ChronoUnit.HOURS)
        val isWithinSessionWindow = selectedInstant in lowerBound..finalUpperBound
        if (!enforceDayBoundary) {
            return@firstOrNull isWithinSessionWindow
        }
        val selectedDay = selectedInstant.atZone(zone).toLocalDate()
        val firstIngestedDay = firstIngestionTime.atZone(zone).toLocalDate()
        val lastIngestedDay = lastIngestionTime.atZone(zone).toLocalDate()
        val isWithinIngestedDays = selectedDay in firstIngestedDay..lastIngestedDay
        isWithinSessionWindow && isWithinIngestedDays
    }
}
