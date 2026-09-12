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

package com.isaakhanimann.journal.ui.tabs.search.substance

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.GppBad
import androidx.compose.material.icons.filled.Update
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material.icons.outlined.Newspaper
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ElevatedCard
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import com.isaakhanimann.journal.data.room.experiences.entities.CustomUnit
import com.isaakhanimann.journal.data.substances.AdministrationRoute
import com.isaakhanimann.journal.data.substances.classes.Category
import com.isaakhanimann.journal.data.substances.classes.SubstanceWithCategories
import com.isaakhanimann.journal.data.substances.repositories.SubstanceRepository
import com.isaakhanimann.journal.localization.i18n
import com.isaakhanimann.journal.localization.i18nOrDefault
import com.isaakhanimann.journal.ui.tabs.journal.addingestion.dose.ChasingTheDragonText
import com.isaakhanimann.journal.ui.tabs.journal.addingestion.dose.OptionalDosageUnitDisclaimer
import com.isaakhanimann.journal.ui.tabs.journal.addingestion.dose.customunit.CustomUnitRoaDoseView
import com.isaakhanimann.journal.ui.tabs.journal.addingestion.time.TimePickerButton
import com.isaakhanimann.journal.ui.tabs.journal.experience.components.DataForOneEffectLine
import com.isaakhanimann.journal.ui.tabs.journal.experience.components.TimeDisplayOption
import com.isaakhanimann.journal.ui.tabs.journal.experience.timeline.AllTimelines
import com.isaakhanimann.journal.ui.tabs.journal.experience.timeline.AllTimelinesModel
import com.isaakhanimann.journal.ui.tabs.search.substance.roa.ToleranceSection
import com.isaakhanimann.journal.ui.tabs.search.substance.roa.dose.RoaDoseView
import com.isaakhanimann.journal.ui.tabs.search.substance.roa.duration.RoaDurationView
import com.isaakhanimann.journal.ui.tabs.search.substance.roa.toReadableString
import com.isaakhanimann.journal.ui.theme.horizontalPadding
import com.isaakhanimann.journal.ui.theme.verticalPaddingCards
import com.isaakhanimann.journal.ui.utils.administrationRouteKey
import com.isaakhanimann.journal.ui.utils.getInstant
import com.isaakhanimann.journal.ui.utils.getTimeText
import java.time.LocalDateTime
import java.time.temporal.ChronoUnit
import kotlin.math.absoluteValue

@Composable
fun SubstanceScreen(
    navigateToDosageExplanationScreen: () -> Unit,
    navigateToSaferHallucinogensScreen: () -> Unit,
    navigateToSaferStimulantsScreen: () -> Unit,
    navigateToVolumetricDosingScreen: () -> Unit,
    navigateToExplainTimeline: () -> Unit,
    navigateToArticle: (url: String) -> Unit,
    navigateToCategoryScreen: (categoryName: String) -> Unit,
    navigateToSubstanceScreen: (substanceName: String) -> Unit,
    viewModel: SubstanceViewModel = hiltViewModel()
) {
    SubstanceScreen(
        navigateToDosageExplanationScreen = navigateToDosageExplanationScreen,
        navigateToSaferHallucinogensScreen = navigateToSaferHallucinogensScreen,
        navigateToSaferStimulantsScreen = navigateToSaferStimulantsScreen,
        navigateToVolumetricDosingScreen = navigateToVolumetricDosingScreen,
        navigateToCategoryScreen = navigateToCategoryScreen,
        navigateToExplainTimeline = navigateToExplainTimeline,
        navigateToURL = navigateToArticle,
        navigateToSubstanceScreen = navigateToSubstanceScreen,
        substanceWithCategories = viewModel.substanceWithCategories,
        interactionNameLookup = viewModel.interactionNameLookup,
        customUnits = viewModel.customUnitsFlow.collectAsState().value,
        substanceRepo = viewModel.substanceRepo
    )
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun SubstanceScreen(
    navigateToDosageExplanationScreen: () -> Unit,
    navigateToSaferHallucinogensScreen: () -> Unit,
    navigateToSaferStimulantsScreen: () -> Unit,
    navigateToVolumetricDosingScreen: () -> Unit,
    navigateToExplainTimeline: () -> Unit,
    navigateToURL: (url: String) -> Unit,
    navigateToCategoryScreen: (categoryName: String) -> Unit,
    navigateToSubstanceScreen: (substanceName: String) -> Unit,
    substanceWithCategories: SubstanceWithCategories,
    interactionNameLookup: Map<String, String>,
    customUnits: List<CustomUnit>,
    substanceRepo: SubstanceRepository
) {
    val substance = substanceWithCategories.substance
    Scaffold(
        topBar = {
            TopAppBar(title = { Text(substance.displayName) })
        },
        floatingActionButton = {
            ExtendedFloatingActionButton(
                onClick = { navigateToURL(substance.url) },
                icon = {
                    Icon(
                        Icons.Outlined.Newspaper,
                        contentDescription = i18n("substance_open_article")
                    )
                },
                text = { Text(i18n("substance_more_info")) }
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .verticalScroll(rememberScrollState())
                .padding(padding)
        ) {
            if (!substance.isApproved) {
                ElevatedCard(
                    modifier = Modifier
                        .padding(
                            horizontal = horizontalPadding,
                            vertical = verticalPaddingCards
                        )
                        .fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier.padding(
                            vertical = 5.dp,
                            horizontal = horizontalPadding
                        )
                    ) {
                        Icon(
                            imageVector = Icons.Default.GppBad,
                            contentDescription = i18n("verified")
                        )
                        Spacer(Modifier.size(ButtonDefaults.IconSpacing))
                        Text(text = i18n("substance_info_not_approved"))
                    }
                }
            }
            val categories = substanceWithCategories.categories
            if (substance.summary != null || categories.isNotEmpty()) {
                VerticalSpace()
                ElevatedCard(
                    modifier = Modifier.padding(
                        horizontal = horizontalPadding,
                        vertical = verticalPaddingCards
                    )
                ) {
                    Column(
                        modifier = Modifier
                            .padding(
                                horizontal = horizontalPadding,
                                vertical = 10.dp
                            )
                            .fillMaxWidth()
                    ) {
                        if (substance.summary != null) {
                            Text(text = substance.summary)
                            VerticalSpace()
                        }
                        FlowRow(
                            horizontalArrangement = Arrangement.spacedBy(5.dp),
                            verticalArrangement = Arrangement.spacedBy(5.dp)
                        ) {
                            categories.forEach { category ->
                                CategoryChipFromSubstanceScreen(category, navigateToCategoryScreen)
                            }
                        }
                    }
                }
            }
            substance.metabolism?.let { metabolism ->
                SectionWithTitle(title = i18n("substance_metabolism_title")) {
                    Column(Modifier.padding(horizontal = horizontalPadding)) {
                        Text(text = metabolism)
                        substance.metabolismSources.forEachIndexed { index, url ->
                            TextButton(onClick = { navigateToURL(url) }) {
                                Icon(
                                    imageVector = Icons.Outlined.Newspaper,
                                    contentDescription = null,
                                    modifier = Modifier.size(ButtonDefaults.IconSize)
                                )
                                Spacer(Modifier.size(ButtonDefaults.IconSpacing))
                                Text(
                                    i18n(
                                        "substance_metabolism_source",
                                        mapOf("number" to (index + 1).toString())
                                    )
                                )
                            }
                        }
                        VerticalSpace()
                    }
                }
            }
            val roasWithDosesDefined = substance.roas.filter { roa ->
                val roaDose = roa.roaDose
                val isEveryDoseNull =
                    roaDose?.lightMin == null &&
                        roaDose?.commonMin == null &&
                        roaDose?.strongMin == null &&
                        roaDose?.heavyMin == null
                return@filter !isEveryDoseNull
            }
            if (substance.dosageRemark != null || roasWithDosesDefined.isNotEmpty()) {
                SectionWithTitle(title = i18n("substance_dosage_title")) {
                    Column(Modifier.padding(horizontal = horizontalPadding)) {
                        if (substance.dosageRemark != null) {
                            Text(text = substance.dosageRemark)
                            Spacer(modifier = Modifier.height(10.dp))
                            HorizontalDivider()
                        }
                        roasWithDosesDefined.forEach { roa ->
                            Column(
                                modifier = Modifier.padding(vertical = 5.dp)
                            ) {
                                Text(
                                    text = i18nOrDefault(
                                        administrationRouteKey(roa.route),
                                        roa.route.displayText
                                    ),
                                    style = MaterialTheme.typography.titleMedium
                                )
                                if (roa.roaDose == null) {
                                    Text(text = i18n("substance_no_dosage_info"))
                                } else {
                                    RoaDoseView(roaDose = roa.roaDose)
                                }
                                roa.roaDose?.let { roaDose ->
                                    val customUnitsForRoute =
                                        customUnits.filter { it.administrationRoute == roa.route }
                                    customUnitsForRoute.forEach { customUnit ->
                                        Text(
                                            text = customUnit.name,
                                            style = MaterialTheme.typography.titleSmall
                                        )
                                        CustomUnitRoaDoseView(
                                            roaDose = roaDose,
                                            customUnit = customUnit
                                        )
                                    }
                                }
                                val bio = roa.bioavailability
                                if (bio != null) {
                                    val minText = bio.min?.toReadableString() ?: ".."
                                    val maxText = bio.max?.toReadableString() ?: ".."
                                    Text(
                                        text = i18n(
                                            "substance_bioavailability",
                                            mapOf("min" to minText, "max" to maxText)
                                        )
                                    )
                                }
                                if (roa.route == AdministrationRoute.SMOKED &&
                                    substance.name != "Cannabis"
                                ) {
                                    Spacer(modifier = Modifier.height(5.dp))
                                    ChasingTheDragonText(
                                        titleStyle = MaterialTheme.typography.titleMedium
                                    )
                                }
                            }
                            HorizontalDivider()
                        }
                        VerticalSpace()
                        OptionalDosageUnitDisclaimer(substance.name)
                        Text(text = i18n("dose_disclaimer"))
                        VerticalSpace()
                        if (substance.roas.any { it.roaDose?.shouldUseVolumetricDosing == true }) {
                            HorizontalDivider()
                            TextButton(onClick = navigateToVolumetricDosingScreen) {
                                Icon(
                                    Icons.Outlined.Info,
                                    contentDescription = i18n("substance_info"),
                                    modifier = Modifier.size(ButtonDefaults.IconSize)
                                )
                                Spacer(Modifier.size(ButtonDefaults.IconSpacing))
                                Text(i18n("substance_volumetric_dosing"))
                            }
                        }
                        HorizontalDivider()
                        TextButton(onClick = navigateToDosageExplanationScreen) {
                            Icon(
                                Icons.Outlined.Info,
                                contentDescription = i18n("substance_info"),
                                modifier = Modifier.size(ButtonDefaults.IconSize)
                            )
                            Spacer(Modifier.size(ButtonDefaults.IconSpacing))
                            Text(i18n("substance_dosage_classification"))
                        }
                    }
                }
            }
            if (substance.tolerance != null || substance.crossTolerances.isNotEmpty()) {
                SectionWithTitle(title = i18n("substance_tolerance_title")) {
                    Column {
                        val context = androidx.compose.ui.platform.LocalContext.current

                        VerticalSpace()
                        ToleranceSection(

                            tolerance = substance.tolerance,

                            crossTolerances = substance.crossTolerances,

                            modifier = Modifier.padding(horizontal = horizontalPadding),

                            isSubstance = substanceRepo::isSubstance,
                            isCategory = substanceRepo::isCategory,

                            getSubstanceDisplayName = substanceRepo::getSubstanceDisplayName,
                            getCategoryDisplayName = { name ->
                                substanceRepo.getCategory(name)?.getLocalizedName(context) ?: name
                            },
                            navToCategory = navigateToCategoryScreen,
                            navToSubstance = navigateToSubstanceScreen
                        )
                        VerticalSpace()
                    }
                }
            }
            if (substance.toxicities.isNotEmpty()) {
                SectionWithTitle(title = i18n("substance_toxicity_title")) {
                    Column {
                        VerticalSpace()
                        if (substance.toxicities.size == 1) {
                            Text(
                                substance.toxicities.firstOrNull() ?: "",
                                modifier = Modifier.padding(horizontal = horizontalPadding)
                            )
                        } else {
                            BulletPoints(
                                points = substance.toxicities,
                                modifier = Modifier.padding(horizontal = horizontalPadding)
                            )
                        }
                        VerticalSpace()
                    }
                }
            }
            val roasWithDurationsDefined = substance.roas.filter { roa ->
                val roaDuration = roa.roaDuration
                val isEveryDurationNull =
                    roaDuration?.onset == null &&
                        roaDuration?.comeup == null &&
                        roaDuration?.peak == null &&
                        roaDuration?.offset == null &&
                        roaDuration?.total == null
                return@filter !isEveryDurationNull
            }
            if (roasWithDurationsDefined.isNotEmpty()) {
                SectionWithTitle(title = i18n("substance_duration_title")) {
                    Column(Modifier.padding(horizontal = horizontalPadding)) {
                        var ingestionTime by remember { mutableStateOf(LocalDateTime.now()) }
                        Row(
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(i18n("substance_duration_start"))
                            Spacer(modifier = Modifier.width(5.dp))
                            TimePickerButton(
                                localDateTime = ingestionTime,
                                onChange = { ingestionTime = it },
                                timeString = ingestionTime.getTimeText(),
                                hasOutline = false
                            )
                            val isTimeALotDifferentToNow = ChronoUnit.MINUTES.between(
                                ingestionTime,
                                LocalDateTime.now()
                            ).absoluteValue > 5
                            Spacer(modifier = Modifier.width(5.dp))
                            AnimatedVisibility(visible = isTimeALotDifferentToNow) {
                                IconButton(onClick = { ingestionTime = LocalDateTime.now() }) {
                                    Icon(
                                        imageVector = Icons.Default.Update,
                                        contentDescription = i18n("substance_duration_reset")
                                    )
                                }
                            }
                            Spacer(modifier = Modifier.weight(1f))
                            IconButton(onClick = navigateToExplainTimeline) {
                                Icon(
                                    imageVector = Icons.Outlined.Info,
                                    contentDescription = i18n("substance_duration_disclaimer")
                                )
                            }
                        }
                        VerticalSpace()
                        val dataForEffectLines = remember(roasWithDurationsDefined, ingestionTime) {
                            roasWithDurationsDefined.mapIndexed { index, roa ->
                                DataForOneEffectLine(
                                    substanceName = "name$index",
                                    route = roa.route,
                                    roaDuration = roa.roaDuration,
                                    height = 1f,
                                    horizontalWeight = 0.5f,
                                    color = roa.route.color,
                                    startTime = ingestionTime.getInstant(),
                                    endTime = null
                                )
                            }
                        }
                        val timelineModel = remember(dataForEffectLines) {
                            AllTimelinesModel(
                                dataForLines = dataForEffectLines,
                                dataForRatings = emptyList(),
                                timedNotes = emptyList(),
                                areSubstanceHeightsIndependent = false
                            )
                        }
                        AllTimelines(
                            model = timelineModel,
                            isShowingCurrentTime = false,
                            timeDisplayOption = TimeDisplayOption.REGULAR,
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(200.dp),
                            areSubstanceHeightsIndependent = false
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        HorizontalDivider()
                        roasWithDurationsDefined.forEachIndexed { index, roa ->
                            Column(
                                modifier = Modifier.padding(
                                    vertical = 5.dp
                                )
                            ) {
                                Row(
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    RouteColorCircle(roa.route)
                                    Spacer(modifier = Modifier.width(8.dp))
                                    Text(
                                        text = i18nOrDefault(
                                            administrationRouteKey(roa.route),
                                            roa.route.displayText
                                        ),
                                        style = MaterialTheme.typography.titleMedium
                                    )
                                }
                                val roaDuration = roa.roaDuration
                                if (roaDuration == null) {
                                    Text(text = i18n("substance_no_duration_info"))
                                } else {
                                    Spacer(modifier = Modifier.height(3.dp))
                                    RoaDurationView(roaDuration = roaDuration)
                                    if (roa.route == AdministrationRoute.ORAL) {
                                        Text(
                                            text = i18n("FULL_STOMACH_DISCLAIMER"),
                                            style = MaterialTheme.typography.bodySmall
                                        )
                                    }
                                }
                            }
                            if (index < roasWithDurationsDefined.size - 1) {
                                HorizontalDivider()
                            }
                        }
                        VerticalSpace()
                    }
                }
            }
            val interactions = substance.interactions
            if (interactions != null) {
                if (interactions.dangerous.isNotEmpty() ||
                    interactions.unsafe.isNotEmpty() ||
                    interactions.uncertain.isNotEmpty()
                ) {
                    SectionWithTitle(title = i18n("substance_interactions_title")) {
                        InteractionsView(
                            interactions = substance.interactions,
                            substanceURL = substance.url,
                            navigateToURL = navigateToURL,
                            displayNameForSubstance = { name ->
                                interactionNameLookup[name] ?: name
                            },
                            navigateToSubstance = navigateToSubstanceScreen,
                            isSubstance = substanceRepo::isSubstance
                        )
                    }
                }
            }
            if (substance.effectsSummary != null) {
                SectionWithTitle(title = i18n("substance_effects_title")) {
                    Column {
                        Text(
                            text = substance.effectsSummary,
                            modifier = Modifier.padding(horizontal = horizontalPadding)
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                    }
                }
            }
            if (substance.generalRisks != null && substance.longtermRisks != null) {
                SectionWithTitle(title = i18n("substance_risks_title")) {
                    Column {
                        Text(
                            text = substance.generalRisks,
                            modifier = Modifier.padding(horizontal = horizontalPadding)
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                    }
                }
                SectionWithTitle(title = i18n("substance_long_term_title")) {
                    Column {
                        Text(
                            text = substance.longtermRisks,
                            modifier = Modifier.padding(horizontal = horizontalPadding)
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                    }
                }
            }
            if (substance.saferUse.isNotEmpty()) {
                SectionWithTitle(title = i18n("substance_safer_use_title")) {
                    Column {
                        BulletPoints(
                            points = substance.saferUse,
                            modifier = Modifier.padding(horizontal = horizontalPadding)
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                    }
                }
            }
            if (substance.addictionPotential != null) {
                SectionWithTitle(title = i18n("substance_addiction_potential_title")) {
                    Column {
                        Text(
                            substance.addictionPotential,
                            modifier = Modifier.padding(horizontal = horizontalPadding)
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                    }
                }
            }
            val firstRoa = substance.roas.firstOrNull()
            val useVolumetric = firstRoa?.roaDose?.shouldUseVolumetricDosing == true
            if (substance.isHallucinogen || substance.isStimulant || useVolumetric) {
                SectionWithTitle(title = i18n("substance_see_also_title")) {
                    Column {
                        if (substance.isHallucinogen) {
                            TextButton(onClick = navigateToSaferHallucinogensScreen) {
                                Text(
                                    text = i18n("substance_safer_hallucinogen_use"),
                                    modifier = Modifier.padding(horizontal = horizontalPadding)
                                )
                            }
                            HorizontalDivider()
                        }
                        if (substance.isStimulant) {
                            TextButton(onClick = navigateToSaferStimulantsScreen) {
                                Text(
                                    text = i18n("substance_safer_stimulant_use"),
                                    modifier = Modifier.padding(horizontal = horizontalPadding)
                                )
                            }
                            HorizontalDivider()
                        }
                    }
                }
            }
            Spacer(modifier = Modifier.height(70.dp))
        }
    }
}

@Composable
fun RouteColorCircle(administrationRoute: AdministrationRoute) {
    val isDarkTheme = isSystemInDarkTheme()
    Surface(
        shape = CircleShape,
        color = administrationRoute.color.getComposeColor(isDarkTheme),
        modifier = Modifier
            .size(20.dp)
    ) {}
}

@Composable
fun BulletPoints(points: List<String>, modifier: Modifier = Modifier) {
    Column(modifier = modifier) {
        points.forEach {
            Row(verticalAlignment = Alignment.Top) {
                Surface(
                    shape = CircleShape,
                    color = MaterialTheme.colorScheme.onBackground,
                    modifier = Modifier
                        .padding(top = 7.dp)
                        .size(7.dp)
                ) {}
                Spacer(modifier = Modifier.width(6.dp))
                Text(text = it)
            }
        }
    }
}

@Composable
fun VerticalSpace() {
    Spacer(modifier = Modifier.height(5.dp))
}

@Composable
fun CategoryChipFromSubstanceScreen(
    category: Category,
    navigateToCategoryScreen: (categoryName: String) -> Unit
) {
    val context = androidx.compose.ui.platform.LocalContext.current
    val displayName = category.getLocalizedName(context)
    Row(
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .clip(shape = CircleShape)
            .clickable {
                navigateToCategoryScreen(category.name)
            }
            .background(color = category.color.copy(alpha = 0.2f))
            .height(48.dp)
            .padding(horizontal = 12.dp)
    ) {
        Text(text = displayName)
        Spacer(modifier = Modifier.width(3.dp))
        Icon(
            imageVector = Icons.Default.ChevronRight,
            contentDescription = i18n("go_to"),
            modifier = Modifier.size(20.dp)
        )
    }
}
