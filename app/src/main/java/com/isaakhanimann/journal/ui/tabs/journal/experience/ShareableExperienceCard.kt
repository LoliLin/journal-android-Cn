package com.isaakhanimann.journal.ui.tabs.journal.experience

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.ElevatedCard
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.scale
import androidx.compose.ui.unit.dp
import com.isaakhanimann.journal.data.room.experiences.entities.TimedNote
import com.isaakhanimann.journal.data.room.experiences.relations.ExperienceWithIngestionsCompanionsAndRatings
import com.isaakhanimann.journal.data.substances.AdministrationRoute
import com.isaakhanimann.journal.data.substances.repositories.SubstanceRepository
import com.isaakhanimann.journal.localization.i18n
import com.isaakhanimann.journal.ui.tabs.journal.addingestion.interactions.InteractionChecker
import com.isaakhanimann.journal.ui.tabs.journal.experience.components.CardTitle
import com.isaakhanimann.journal.ui.tabs.journal.experience.components.CardTitleWithAvatar
import com.isaakhanimann.journal.ui.tabs.journal.experience.components.CumulativeDoseRow
import com.isaakhanimann.journal.ui.tabs.journal.experience.components.ExperienceEffectTimelines
import com.isaakhanimann.journal.ui.tabs.journal.experience.components.InteractionRow
import com.isaakhanimann.journal.ui.tabs.journal.experience.components.TimeDisplayOption
import com.isaakhanimann.journal.ui.tabs.journal.experience.components.ingestion.IngestionRow
import com.isaakhanimann.journal.ui.tabs.journal.experience.components.rating.RatingRow
import com.isaakhanimann.journal.ui.tabs.journal.experience.components.timednote.TimedNoteRow
import com.isaakhanimann.journal.ui.tabs.journal.experience.models.ConsumerWithIngestions
import com.isaakhanimann.journal.ui.tabs.journal.experience.models.CumulativeDose
import com.isaakhanimann.journal.ui.tabs.journal.experience.models.CumulativeRouteAndDose
import com.isaakhanimann.journal.ui.tabs.journal.experience.models.IngestionElement
import com.isaakhanimann.journal.ui.tabs.journal.experience.models.InteractionExplanation
import com.isaakhanimann.journal.ui.tabs.journal.experience.models.OneExperienceScreenModel
import com.isaakhanimann.journal.ui.tabs.journal.experience.timeline.DataForOneRating
import com.isaakhanimann.journal.ui.tabs.journal.experience.timeline.DataForOneTimedNote
import com.isaakhanimann.journal.ui.tabs.settings.OwnerProfileCard
import com.isaakhanimann.journal.ui.theme.horizontalPadding
import com.isaakhanimann.journal.ui.utils.getDateWithWeekdayText

@Stable
class SubstanceDisplayNameProvider(val get: (String) -> String)

@Stable
data class ShareableExperienceCardData(
    val oneExperienceScreenModel: OneExperienceScreenModel,
    val ownerUserName: String,
    val achievements: List<String> = emptyList(),
    val substanceDisplayNameProvider: SubstanceDisplayNameProvider,
    val timeDisplayOption: TimeDisplayOption = TimeDisplayOption.RELATIVE_TO_START,
    val areDosageDotsHidden: Boolean = false
)

fun prepareShareableExperienceCardData(
    substanceRepo: SubstanceRepository,
    interactionChecker: InteractionChecker,
    ownerUserName: String,
    getSubstanceDisplayName: (String) -> String,
    timedNotes: List<TimedNote>,
    achievements: List<String> = emptyList(),
    experienceWithIngestionsCompanionsAndRatings: ExperienceWithIngestionsCompanionsAndRatings
): ShareableExperienceCardData {
    val experience = experienceWithIngestionsCompanionsAndRatings.experience
    val ingestionsWithCompanions = experienceWithIngestionsCompanionsAndRatings.ingestionsWithCompanions
    val ratings = experienceWithIngestionsCompanionsAndRatings.ratings
    val sortedIngestions = ingestionsWithCompanions.sortedBy { it.ingestion.time }

    // 1. 同步提取所有需要的本地 Roa 数据
    val allIngestionElements = sortedIngestions.map { oneIngestionWithComp ->
        val ingestion = oneIngestionWithComp.ingestion

        val substance = substanceRepo.getSubstance(ingestion.substanceName)
        val roa = substance?.getRoa(ingestion.administrationRoute, ingestion.releaseForm)

        val numDots = if (oneIngestionWithComp.customUnit != null) {
            roa?.roaDose?.getNumDots(
                ingestionDose = oneIngestionWithComp.customUnitDose?.calculatedDose,
                ingestionUnits = oneIngestionWithComp.customUnit?.originalUnit
            )
        } else {
            roa?.roaDose?.getNumDots(
                oneIngestionWithComp.ingestion.dose,
                ingestionUnits = oneIngestionWithComp.ingestion.units
            )
        }

        Pair(
            IngestionElement(
                ingestionWithCompanionAndCustomUnit = oneIngestionWithComp,
                roaDuration = roa?.roaDuration,
                numDots = numDots
            ),
            roa?.roaDose
        )
    }

    // 2. 剥离出【自己】和【同行伙伴】的数据
    val myElementsWithRoa = allIngestionElements.filter {
        it.first.ingestionWithCompanionAndCustomUnit.ingestion.consumerName ==
            null
    }
    val myIngestionElements = myElementsWithRoa.map { it.first }

    val otherElementsWithRoa = allIngestionElements.filter {
        it.first.ingestionWithCompanionAndCustomUnit.ingestion.consumerName !=
            null
    }
    val consumersWithIngestions = otherElementsWithRoa
        .groupBy { it.first.ingestionWithCompanionAndCustomUnit.ingestion.consumerName }
        .mapNotNull { entry ->
            val consumerName = entry.key ?: return@mapNotNull null
            ConsumerWithIngestions(
                consumerName = consumerName,
                ingestionElements = entry.value.map {
                    it.first
                }.sortedBy { it.ingestionWithCompanionAndCustomUnit.ingestion.time }
            )
        }

    // 3. 纯手写计算累计剂量
    val cumulativeDoses = myElementsWithRoa.map { it.first }
        .groupBy { it.ingestionWithCompanionAndCustomUnit.ingestion.substanceName }
        .map { groupedBySubstanceName ->
            val elements = groupedBySubstanceName.value
            val cumulativeRouteDose = elements.groupBy {
                it.ingestionWithCompanionAndCustomUnit.ingestion.administrationRoute
            }
                .mapNotNull { groupedByRoute ->
                    val groupedElements = groupedByRoute.value
                    if (groupedElements.any {
                            it.ingestionWithCompanionAndCustomUnit.ingestion.dose ==
                                null
                        }
                    ) {
                        return@mapNotNull null
                    }
                    val firstElement = groupedElements.first().ingestionWithCompanionAndCustomUnit
                    val units = firstElement.originalUnit ?: return@mapNotNull null
                    if (groupedElements.any {
                            it.ingestionWithCompanionAndCustomUnit.originalUnit !=
                                units
                        }
                    ) {
                        return@mapNotNull null
                    }

                    val isEstimate = groupedElements.any {
                        it.ingestionWithCompanionAndCustomUnit.ingestion.isDoseAnEstimate ||
                            it.ingestionWithCompanionAndCustomUnit.customUnit?.isEstimate ?: false
                    }
                    val cumulativeDose = groupedElements.mapNotNull {
                        it.ingestionWithCompanionAndCustomUnit.pureDose
                    }.sum()
                    val cumulativeDoseStandardDeviation = groupedElements.mapNotNull {
                        it.ingestionWithCompanionAndCustomUnit.pureDoseStandardDeviation
                    }.sum()

                    val targetRoaDose = myElementsWithRoa.firstOrNull {
                        it.first.ingestionWithCompanionAndCustomUnit.ingestion.substanceName ==
                            firstElement.ingestion.substanceName &&
                            it.first.ingestionWithCompanionAndCustomUnit.ingestion.administrationRoute ==
                            firstElement.ingestion.administrationRoute
                    }?.second
                    val numDots = targetRoaDose?.getNumDots(
                        ingestionDose = cumulativeDose,
                        ingestionUnits = units
                    )

                    CumulativeRouteAndDose(
                        cumulativeDose = cumulativeDose,
                        units = units,
                        isEstimate = isEstimate,
                        cumulativeDoseStandardDeviation = if (cumulativeDoseStandardDeviation >
                            0
                        ) {
                            cumulativeDoseStandardDeviation
                        } else {
                            null
                        },
                        numDots = numDots,
                        route = firstElement.ingestion.administrationRoute,
                        hasMoreThanOneIngestion = groupedElements.size > 1
                    )
                }
            CumulativeDose(
                substanceName = groupedBySubstanceName.key,
                cumulativeRouteAndDose = cumulativeRouteDose
            )
        }
        .filter {
            it.cumulativeRouteAndDose.isNotEmpty() &&
                it.cumulativeRouteAndDose.any { route -> route.hasMoreThanOneIngestion }
        }

    // 4. 计算相互作用机制
    val interactionsToCheck = sortedIngestions.map { it.ingestion.substanceName }.distinct()
    val interactions = interactionsToCheck.flatMapIndexed { index: Int, interaction: String ->
        interactionsToCheck.drop(index + 1).mapNotNull { other ->

            interactionChecker.getInteractionBetween(interaction, other)
        }
    }.sortedByDescending { it.interactionType.dangerCount }

    val interactionExplanations = interactions.flatMap {
        listOf(it.aName, it.bName)
    }.distinct().mapNotNull { name ->
        val substance = substanceRepo.getSubstance(substanceName = name)
        InteractionExplanation(
            name = substance?.name ?: name,
            url = ""
        )
    }

    // 5. 装填 ScreenModel
    val oneExperienceScreenModel = OneExperienceScreenModel(
        isFavorite = experience.isFavorite,
        title = experience.title,
        firstIngestionTime = sortedIngestions.firstOrNull()?.ingestion?.time
            ?: experience.sortDate,
        notes = experience.text,
        locationName = experience.location?.name ?: "",
        isCurrentExperience = false,
        ingestionElements = myIngestionElements,
        cumulativeDoses = cumulativeDoses,
        interactions = interactions,
        interactionExplanations = interactionExplanations,
        ratings = ratings,
        timedNotes = timedNotes,
        consumersWithIngestions = consumersWithIngestions
    )

    return ShareableExperienceCardData(
        oneExperienceScreenModel = oneExperienceScreenModel,
        timeDisplayOption = TimeDisplayOption.RELATIVE_TO_START,
        areDosageDotsHidden = false,
        ownerUserName = ownerUserName,
        achievements = achievements,
        substanceDisplayNameProvider = SubstanceDisplayNameProvider(getSubstanceDisplayName)
    )
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun ShareableExperienceCard(cardData: ShareableExperienceCardData) {
    ShareableExperienceCard(
        oneExperienceScreenModel = cardData.oneExperienceScreenModel,
        timeDisplayOption = cardData.timeDisplayOption,
        areDosageDotsHidden = cardData.areDosageDotsHidden,
        ownerUserName = cardData.ownerUserName,
        achievements = cardData.achievements,
        getSubstanceDisplayName = cardData.substanceDisplayNameProvider.get
    )
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun ShareableExperienceCard(
    oneExperienceScreenModel: OneExperienceScreenModel,
    timeDisplayOption: TimeDisplayOption,
    areDosageDotsHidden: Boolean,
    ownerUserName: String,
    achievements: List<String> = emptyList(),
    getSubstanceDisplayName: (String) -> String
) {
    val verticalCardPadding = 4.dp

    ElevatedCard(
        modifier = Modifier
            .padding(vertical = verticalCardPadding)
            .fillMaxWidth()
    ) {
        OwnerProfileCard(
            ownerUserName = ownerUserName,
            achievements = achievements,
            onUserNameChanged = {}
        )

        CardTitle(title = oneExperienceScreenModel.title)
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = horizontalPadding)
        ) {
            val ingestionElements = oneExperienceScreenModel.ingestionElements
            val dataForRatings = oneExperienceScreenModel.ratings.mapNotNull {
                val ratingTime = it.time
                return@mapNotNull if (ratingTime == null) {
                    null
                } else {
                    DataForOneRating(
                        time = ratingTime,
                        option = it.option
                    )
                }
            }
            val dataForTimedNotes =
                oneExperienceScreenModel.timedNotes.filter { it.isPartOfTimeline }
                    .map {
                        DataForOneTimedNote(time = it.time, color = it.color)
                    }
            val isWorthDrawing =
                ingestionElements.isNotEmpty() &&
                    !(
                        ingestionElements.all { it.roaDuration == null } &&
                            dataForRatings.isEmpty() &&
                            dataForTimedNotes.isEmpty()
                        )
            if (isWorthDrawing) {
                ElevatedCard(modifier = Modifier.padding(vertical = verticalCardPadding)) {
                    Row(
                        horizontalArrangement = Arrangement.SpaceBetween,
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        CardTitleWithAvatar(
                            title = if (ownerUserName ==
                                "You"
                            ) {
                                i18n("effect_timeline")
                            } else {
                                ownerUserName
                            },
                            username = ownerUserName
                        )
                    }
                    Column(
                        modifier = Modifier
                            .padding(horizontal = horizontalPadding)
                            .padding(bottom = 10.dp),
                        verticalArrangement = Arrangement.spacedBy(5.dp)
                    ) {
                        ExperienceEffectTimelines(
                            ingestionElements = oneExperienceScreenModel.ingestionElements,
                            dataForRatings = dataForRatings,
                            dataForTimedNotes = dataForTimedNotes,
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(200.dp)

                        )
                        val hasOralIngestion =
                            oneExperienceScreenModel.ingestionElements.any {
                                it.ingestionWithCompanionAndCustomUnit.ingestion.administrationRoute ==
                                    AdministrationRoute.ORAL
                            }
                    }
                }
            }
            if (oneExperienceScreenModel.ingestionElements.isNotEmpty()) {
                ElevatedCard(modifier = Modifier.padding(vertical = verticalCardPadding)) {
                    CardTitle(
                        title = oneExperienceScreenModel.firstIngestionTime.getDateWithWeekdayText()
                    )
                    if (oneExperienceScreenModel.ingestionElements.isNotEmpty()) {
                        HorizontalDivider()
                    }
                    oneExperienceScreenModel.ingestionElements.forEachIndexed {
                            index,
                            ingestionElement
                        ->
                        IngestionRow(
                            ingestionElement = ingestionElement,
                            timeDisplayOption = timeDisplayOption,
                            startTime = oneExperienceScreenModel.firstIngestionTime,
                            areDosageDotsHidden = areDosageDotsHidden,
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 5.dp, horizontal = horizontalPadding),
                            getSubstanceDisplayName = getSubstanceDisplayName
                        )
                        if (index < oneExperienceScreenModel.ingestionElements.size - 1) {
                            HorizontalDivider()
                        }
                    }
                }
            }
            val cumulativeDoses = oneExperienceScreenModel.cumulativeDoses
            if (cumulativeDoses.isNotEmpty()) {
                ElevatedCard(modifier = Modifier.padding(vertical = verticalCardPadding)) {
                    CardTitle(title = i18n("your_cumulative_doses"))
                    if (cumulativeDoses.isNotEmpty()) {
                        HorizontalDivider()
                    }
                    cumulativeDoses.forEachIndexed { index, cumulativeDose ->
                        CumulativeDoseRow(
                            cumulativeDose = cumulativeDose,
                            areDosageDotsHidden = areDosageDotsHidden,
                            getSubstanceDisplayName = getSubstanceDisplayName,
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 5.dp, horizontal = horizontalPadding)
                        )
                        if (index < cumulativeDoses.size - 1) {
                            HorizontalDivider()
                        }
                    }
                }
            }
            val timedNotes = oneExperienceScreenModel.timedNotes
            if (timedNotes.isNotEmpty()) {
                ElevatedCard(modifier = Modifier.padding(vertical = verticalCardPadding)) {
                    CardTitle(title = i18n("timed_notes"))
                    if (timedNotes.isNotEmpty()) {
                        HorizontalDivider()
                    }
                    timedNotes.forEachIndexed { index, timedNote ->
                        TimedNoteRow(
                            timedNote = timedNote,
                            timeDisplayOption = timeDisplayOption,
                            startTime = oneExperienceScreenModel.firstIngestionTime,
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 5.dp, horizontal = horizontalPadding)
                        )
                        if (index < timedNotes.size - 1) {
                            HorizontalDivider()
                        }
                    }
                }
            }
            if (oneExperienceScreenModel.ratings.isNotEmpty()) {
                ElevatedCard(modifier = Modifier.padding(vertical = verticalCardPadding)) {
                    CardTitle(title = i18n("shulgin_ratings"))
                    HorizontalDivider()
                    val ratingsWithTime =
                        oneExperienceScreenModel.ratings.filter { it.time != null }
                    ratingsWithTime.forEachIndexed { index, rating ->
                        RatingRow(
                            rating = rating,
                            timeDisplayOption = timeDisplayOption,
                            startTime = oneExperienceScreenModel.firstIngestionTime,
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 8.dp, horizontal = horizontalPadding)
                        )
                        if (index < ratingsWithTime.size - 1) {
                            HorizontalDivider()
                        }
                    }
                    val overallRating =
                        oneExperienceScreenModel.ratings.firstOrNull { it.time == null }
                    if (overallRating != null) {
                        if (ratingsWithTime.isNotEmpty()) {
                            HorizontalDivider()
                        }
                        RatingRow(
                            rating = overallRating,
                            timeDisplayOption = timeDisplayOption,
                            startTime = oneExperienceScreenModel.firstIngestionTime,
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 8.dp, horizontal = horizontalPadding)
                        )
                    }
                }
            }
            val notes = oneExperienceScreenModel.notes
            if (notes.isNotBlank()) {
                ElevatedCard(
                    modifier = Modifier
                        .padding(vertical = verticalCardPadding)
                        .fillMaxWidth()
                ) {
                    CardTitle(title = i18n("common_notes"))
                    Column(
                        modifier = Modifier
                            .padding(horizontal = horizontalPadding)
                            .padding(bottom = 10.dp)
                    ) {
                        Text(text = oneExperienceScreenModel.notes)
                        if (oneExperienceScreenModel.locationName.isNotBlank()) {
                            Spacer(modifier = Modifier.height(5.dp))
                            Text(text = "Location: ${oneExperienceScreenModel.locationName}")
                        }
                    }
                }
            }
            oneExperienceScreenModel.consumersWithIngestions.forEach { consumerWithIngestions ->
                ElevatedCard(modifier = Modifier.padding(vertical = verticalCardPadding)) {
                    CardTitleWithAvatar(
                        title = consumerWithIngestions.consumerName,
                        username = consumerWithIngestions.consumerName
                    )
                    Column(
                        modifier = Modifier
                            .padding(horizontal = horizontalPadding)
                            .padding(bottom = 10.dp),
                        verticalArrangement = Arrangement.spacedBy(5.dp)
                    ) {
                        ExperienceEffectTimelines(
                            ingestionElements = consumerWithIngestions.ingestionElements,
                            dataForRatings = emptyList(),
                            dataForTimedNotes = emptyList(),
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(200.dp)

                        )
                    }
                    HorizontalDivider()
                    consumerWithIngestions.ingestionElements.forEachIndexed {
                            index,
                            ingestionElement
                        ->
                        IngestionRow(
                            ingestionElement = ingestionElement,
                            timeDisplayOption = timeDisplayOption,
                            startTime = oneExperienceScreenModel.firstIngestionTime,
                            areDosageDotsHidden = areDosageDotsHidden,
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 5.dp, horizontal = horizontalPadding),
                            getSubstanceDisplayName = getSubstanceDisplayName
                        )
                        if (index < consumerWithIngestions.ingestionElements.size - 1) {
                            HorizontalDivider()
                        }
                    }
                }
            }
            val interactions = oneExperienceScreenModel.interactions
            AnimatedVisibility(visible = interactions.isNotEmpty()) {
                ElevatedCard(
                    modifier = Modifier
                        .padding(vertical = verticalCardPadding)
                ) {
                    CardTitle(title = i18n("substance_interactions_title"))
                    interactions.forEachIndexed { index, interaction ->
                        InteractionRow(
                            interaction = interaction,
                            getSubstanceDisplayName = getSubstanceDisplayName
                        )
                        if (index < interactions.size - 1) {
                            HorizontalDivider()
                        }
                    }
                }
            }
            Spacer(modifier = Modifier.height(60.dp))
            ElevatedCard(
                modifier = Modifier
                    .padding(vertical = verticalCardPadding)
            ) {
                Column(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalAlignment = Alignment.End
                ) {
                    CardTitle(title = "Journal Android Multilingual")
                    Column(modifier = Modifier.scale(0.5f)) {
                        CardTitle(title = com.isaakhanimann.journal.ui.VERSION_NAME)
                    }
                }
            }
        }
    }
}
