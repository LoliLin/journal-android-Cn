/*
 * Copyright (c) 2026. Journal Multilingual fork.
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

package com.isaakhanimann.journal.ui.tabs.stats

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.isaakhanimann.journal.data.room.experiences.ExperienceRepository
import com.isaakhanimann.journal.data.room.experiences.entities.AdaptiveColor
import com.isaakhanimann.journal.data.room.experiences.relations.IngestionWithCompanionAndCustomUnit
import com.isaakhanimann.journal.data.substances.classes.roa.DoseClass
import com.isaakhanimann.journal.data.substances.repositories.SubstanceRepository
import com.isaakhanimann.journal.ui.tabs.search.substance.roa.toReadableString
import com.isaakhanimann.journal.ui.tabs.settings.combinations.UserPreferences
import dagger.hilt.android.lifecycle.HiltViewModel
import java.time.LocalDate
import java.time.ZoneId
import javax.inject.Inject
import kotlin.math.floor
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn

enum class AnalysisPeriodPreset { ALL_TIME, LAST_30_DAYS, LAST_90_DAYS, THIS_YEAR, LAST_YEAR, CUSTOM }

// null-consumer ingestions belong to the owner; All aggregates everyone
sealed interface ConsumerSelection {
    data object All : ConsumerSelection
    data object Owner : ConsumerSelection
    data class Specific(val name: String) : ConsumerSelection
}

data class TotalDoseLine(
    val substanceName: String,
    val units: String,
    val color: AdaptiveColor?,
    val absoluteTotal: Double,
    val relativeTotal: Double?
)

data class SubstanceChartData(
    val substanceName: String,
    val color: AdaptiveColor?,
    // dose distribution: values are relative doses (x common dose) when relativeDoseData exists,
    // otherwise raw doses in the substance's unit; labels are derived via bucketLabel
    val doseBuckets: List<Pair<Double, Int>>,
    val bucketLabel: (Double) -> String,
    val doseClassCounts: List<Pair<DoseClass, Int>>,
    val perDayCumulativeRelative: List<Pair<LocalDate, Double>>,
    val absoluteTotal: Double,
    val relativeTotal: Double?,
    val units: String?,
    val unknownDoseCount: Int
)

data class StatsAnalysisModel(
    val selectedSubstances: Set<String>,
    val selectedConsumer: ConsumerSelection,
    val selectedPreset: AnalysisPeriodPreset,
    val startDate: LocalDate?,
    val endDate: LocalDate?,
    val effectiveStart: LocalDate?,
    val effectiveEnd: LocalDate?,
    val ingestionCount: Int,
    val totalDoseBySubstance: List<TotalDoseLine>,
    val perSubstanceCharts: List<SubstanceChartData>,
    val ingestions: List<IngestionWithCompanionAndCustomUnit>
)

/**
 * The reference dose for relative measurements: the midpoint of the common dose range
 * [commonMin, strongMin), falling back to commonMin when the range has no upper bound.
 */
internal fun commonDoseReference(commonMin: Double?, strongMin: Double?): Double? =
    when {
        commonMin == null -> null
        strongMin != null -> (commonMin + strongMin) / 2
        else -> commonMin
    }

/**
 * Relative dose of one ingestion: the pure dose divided by the common dose reference of the
 * substance's ROA, defined only when the entry is expressed in the ROA's units.
 */
internal fun relativeDoseOfIngestion(
    substanceRepo: SubstanceRepository,
    ingestionWith: IngestionWithCompanionAndCustomUnit
): Double? {
    val ingestion = ingestionWith.ingestion
    val substance = substanceRepo.getSubstance(ingestion.substanceName) ?: return null
    val roaDose = substance.getRoa(ingestion.administrationRoute, ingestion.releaseForm)
        ?.roaDose
        ?: return null
    val reference = commonDoseReference(roaDose.commonMin, roaDose.strongMin) ?: return null
    if (reference <= 0) return null
    // relative dose is only defined when the entry is expressed in the ROA's units
    val unit = ingestionWith.originalUnit
    if (unit != null && roaDose.units != unit) return null
    val pureDose = ingestionWith.pureDose ?: return null
    return pureDose / reference
}

@HiltViewModel
class StatsAnalysisViewModel @Inject constructor(
    experienceRepository: ExperienceRepository,
    val substanceRepo: SubstanceRepository,
    private val userPreferences: UserPreferences
) : ViewModel() {

    private val ingestionsFlow =
        experienceRepository.getSortedIngestionsWithSubstanceCompanionsFlow(limit = 100000)

    val usedSubstancesFlow: StateFlow<List<String>> = ingestionsFlow.map { list ->
        list.map { it.ingestion.substanceName }.distinct().sorted()
    }.stateIn(
        initialValue = emptyList(),
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5000)
    )

    val consumerNamesFlow: StateFlow<List<String>> = ingestionsFlow.map { list ->
        list.mapNotNull { it.ingestion.consumerName }.distinct().sorted()
    }.stateIn(
        initialValue = emptyList(),
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5000)
    )

    val ownerUserNameFlow: StateFlow<String?> = userPreferences.ownerUserNameFlow.stateIn(
        initialValue = "You",
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5000)
    )

    private val _selectedConsumer = MutableStateFlow<ConsumerSelection>(ConsumerSelection.All)
    val selectedConsumerFlow: StateFlow<ConsumerSelection> = _selectedConsumer.asStateFlow()

    fun selectAllConsumers() {
        _selectedConsumer.value = ConsumerSelection.All
    }

    fun selectOwner() {
        _selectedConsumer.value = ConsumerSelection.Owner
    }

    fun selectConsumer(name: String) {
        _selectedConsumer.value = ConsumerSelection.Specific(name)
    }

    private val _selectedSubstances = MutableStateFlow<Set<String>>(emptySet())
    val selectedSubstancesFlow: StateFlow<Set<String>> = _selectedSubstances.asStateFlow()

    fun toggleSubstance(substanceName: String) {
        _selectedSubstances.value = _selectedSubstances.value.let { current ->
            if (substanceName in current) {
                current - substanceName
            } else {
                current + substanceName
            }
        }
    }

    fun clearSubstances() {
        _selectedSubstances.value = emptySet()
    }

    private val _selectedPreset = MutableStateFlow(AnalysisPeriodPreset.ALL_TIME)
    val selectedPresetFlow: StateFlow<AnalysisPeriodPreset> = _selectedPreset.asStateFlow()

    fun setPreset(preset: AnalysisPeriodPreset) {
        _selectedPreset.value = preset
        if (preset != AnalysisPeriodPreset.CUSTOM) {
            _startDate.value = null
            _endDate.value = null
        }
    }

    private val _startDate = MutableStateFlow<LocalDate?>(null)
    val startDateFlow: StateFlow<LocalDate?> = _startDate.asStateFlow()

    fun setStartDate(date: LocalDate?) {
        _startDate.value = date
        if (date != null) {
            _selectedPreset.value = AnalysisPeriodPreset.CUSTOM
        }
    }

    private val _endDate = MutableStateFlow<LocalDate?>(null)
    val endDateFlow: StateFlow<LocalDate?> = _endDate.asStateFlow()

    fun setEndDate(date: LocalDate?) {
        _endDate.value = date
        if (date != null) {
            _selectedPreset.value = AnalysisPeriodPreset.CUSTOM
        }
    }

    fun clearTimeRange() {
        _startDate.value = null
        _endDate.value = null
        _selectedPreset.value = AnalysisPeriodPreset.ALL_TIME
    }

    private fun relativeDoseOf(ingestionWith: IngestionWithCompanionAndCustomUnit): Double? =
        relativeDoseOfIngestion(substanceRepo, ingestionWith)

    private fun doseClassOf(ingestionWith: IngestionWithCompanionAndCustomUnit): DoseClass? {
        val ingestion = ingestionWith.ingestion
        val substance = substanceRepo.getSubstance(ingestion.substanceName) ?: return null
        val roaDose = substance.getRoa(ingestion.administrationRoute, ingestion.releaseForm)
            ?.roaDose
            ?: return null
        return roaDose.getDoseClass(ingestionWith.pureDose, ingestionWith.originalUnit)
    }

    private data class AnalysisFilters(
        val selectedSubstances: Set<String>,
        val consumer: ConsumerSelection,
        val preset: AnalysisPeriodPreset,
        val start: LocalDate?,
        val end: LocalDate?
    )

    private val filtersFlow: Flow<AnalysisFilters> = combine(
        _selectedSubstances,
        _selectedConsumer,
        _selectedPreset,
        _startDate,
        _endDate
    ) { selected, consumer, preset, start, end ->
        AnalysisFilters(selected, consumer, preset, start, end)
    }

    val modelFlow: StateFlow<StatsAnalysisModel> = combine(
        ingestionsFlow,
        filtersFlow
    ) { ingestions, filters ->
        val selected = filters.selectedSubstances
        val consumerSelection = filters.consumer
        val preset = filters.preset
        val start = filters.start
        val end = filters.end
        val consumerMatches: (String?) -> Boolean = when (consumerSelection) {
            ConsumerSelection.All -> { _ -> true }
            ConsumerSelection.Owner -> { consumer -> consumer == null }
            is ConsumerSelection.Specific -> { consumer -> consumer == consumerSelection.name }
        }
        val zone = ZoneId.systemDefault()
        val today = LocalDate.now()
        val (effectiveStart, effectiveEnd) = when (preset) {
            AnalysisPeriodPreset.ALL_TIME -> null to null
            AnalysisPeriodPreset.LAST_30_DAYS -> today.minusDays(30) to today
            AnalysisPeriodPreset.LAST_90_DAYS -> today.minusDays(90) to today
            AnalysisPeriodPreset.THIS_YEAR -> LocalDate.of(today.year, 1, 1) to today
            AnalysisPeriodPreset.LAST_YEAR ->
                LocalDate.of(today.year - 1, 1, 1) to LocalDate.of(today.year - 1, 12, 31)
            AnalysisPeriodPreset.CUSTOM -> start to end
        }
        val filtered = ingestions.filter { ingestionWith ->
            if (ingestionWith.ingestion.substanceName !in selected) {
                return@filter false
            }
            if (!consumerMatches(ingestionWith.ingestion.consumerName)) {
                return@filter false
            }
            val date = ingestionWith.ingestion.time.atZone(zone).toLocalDate()
            val isAfterStart = effectiveStart == null || !date.isBefore(effectiveStart)
            val isBeforeEnd = effectiveEnd == null || !date.isAfter(effectiveEnd)
            isAfterStart && isBeforeEnd
        }
        val totalDoseBySubstance = filtered
            .groupBy { it.ingestion.substanceName to (it.ingestion.units ?: "") }
            .map { (key, list) ->
                val absoluteTotal = list.sumOf { it.pureDose ?: 0.0 }
                val relativeValues = list.mapNotNull { relativeDoseOf(it) }
                TotalDoseLine(
                    substanceName = key.first,
                    units = key.second,
                    color = list.firstOrNull()?.substanceCompanion?.color,
                    absoluteTotal = absoluteTotal,
                    relativeTotal = relativeValues.sum().takeIf { relativeValues.isNotEmpty() }
                )
            }
            .sortedBy { it.substanceName }
        val perSubstanceCharts = filtered
            .groupBy { it.ingestion.substanceName }
            .map { (name, list) ->
                val relativeValues = list.mapNotNull { relativeDoseOf(it) }
                val hasRelativeData = relativeValues.isNotEmpty()
                val buckets: List<Pair<Double, Int>> = if (hasRelativeData) {
                    // bucket relative doses in 0.5 steps of the common dose
                    relativeValues
                        .groupBy { floor(it * 2) / 2 }
                        .map { (bucket, bucketList) -> bucket to bucketList.size }
                        .sortedBy { it.first }
                } else {
                    list
                        .mapNotNull { it.pureDose }
                        .groupBy { floor(it * 2) / 2 }
                        .map { (bucket, bucketList) -> bucket to bucketList.size }
                        .sortedBy { it.first }
                }
                val bucketLabel: (Double) -> String = if (hasRelativeData) {
                    { bucket -> "${bucket.toReadableString()}×" }
                } else {
                    { bucket -> bucket.toReadableString() }
                }
                val doseClassCounts = list
                    .mapNotNull { doseClassOf(it) }
                    .groupBy { it }
                    .map { (doseClass, classList) -> doseClass to classList.size }
                    .sortedBy { it.first.ordinal }
                val cumulativeByDay = list
                    .groupBy { it.ingestion.time.atZone(zone).toLocalDate() }
                    .toSortedMap()
                    .map { (date, dateList) ->
                        date to dateList.mapNotNull { relativeDoseOf(it) }.sum()
                    }
                var runningTotal = 0.0
                val perDayCumulativeRelative = cumulativeByDay.map { (date, dayRelative) ->
                    runningTotal += dayRelative
                    date to runningTotal
                }
                SubstanceChartData(
                    substanceName = name,
                    color = list.firstOrNull()?.substanceCompanion?.color,
                    doseBuckets = buckets,
                    bucketLabel = bucketLabel,
                    doseClassCounts = doseClassCounts,
                    perDayCumulativeRelative = perDayCumulativeRelative,
                    absoluteTotal = list.sumOf { it.pureDose ?: 0.0 },
                    relativeTotal = relativeValues.sum().takeIf { hasRelativeData },
                    units = list.mapNotNull { it.originalUnit }.firstOrNull(),
                    unknownDoseCount = list.count { it.pureDose == null }
                )
            }
            .sortedBy { it.substanceName }
        StatsAnalysisModel(
            selectedSubstances = selected,
            selectedConsumer = consumerSelection,
            selectedPreset = preset,
            startDate = start,
            endDate = end,
            effectiveStart = effectiveStart,
            effectiveEnd = effectiveEnd,
            ingestionCount = filtered.size,
            totalDoseBySubstance = totalDoseBySubstance,
            perSubstanceCharts = perSubstanceCharts,
            ingestions = filtered
        )
    }.stateIn(
        initialValue = StatsAnalysisModel(
            selectedSubstances = emptySet(),
            selectedConsumer = ConsumerSelection.All,
            selectedPreset = AnalysisPeriodPreset.ALL_TIME,
            startDate = null,
            endDate = null,
            effectiveStart = null,
            effectiveEnd = null,
            ingestionCount = 0,
            totalDoseBySubstance = emptyList(),
            perSubstanceCharts = emptyList(),
            ingestions = emptyList()
        ),
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5000)
    )
}
