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

package com.isaakhanimann.journal.data.substances.classes

import com.isaakhanimann.journal.data.substances.AdministrationRoute
import com.isaakhanimann.journal.data.substances.ReleaseForm
import com.isaakhanimann.journal.data.substances.classes.roa.Roa
import com.isaakhanimann.journal.ui.utils.getInteractionExplanationURLForSubstance

data class Substance(
    val name: String,
    val localizedName: String?,
    val commonNames: List<String>,
    val url: String,
    val isApproved: Boolean,
    val tolerance: Tolerance?,
    val crossTolerances: List<String>,
    val addictionPotential: String?,
    val toxicities: List<String>,
    val categories: List<String>,
    val summary: String?,
    val effectsSummary: String?,
    val dosageRemark: String?,
    val generalRisks: String?,
    val longtermRisks: String?,
    val saferUse: List<String>,
    val interactions: Interactions?,
    val roas: List<Roa>,
    val metabolism: String? = null,
    val metabolismSources: List<String> = emptyList(),
    val oralReleaseForms: List<ReleaseForm> = emptyList()
) {
    fun getRoa(route: AdministrationRoute, releaseForm: ReleaseForm? = null): Roa? =
        if (releaseForm == ReleaseForm.EXTENDED_RELEASE) {
            // The catalog currently has no formulation-specific dose or duration data.
            null
        } else {
            roas.firstOrNull { it.route == route }
        }

    fun getReleaseForms(route: AdministrationRoute): List<ReleaseForm> =
        if (route == AdministrationRoute.ORAL) oralReleaseForms else emptyList()

    val hasInteractions: Boolean get() {
        return if (interactions == null) {
            false
        } else {
            interactions.uncertain.isNotEmpty() ||
                interactions.unsafe.isNotEmpty() ||
                interactions.dangerous.isNotEmpty()
        }
    }

    val isHallucinogen
        get() = categories.any {
            val hallucinogens = setOf(
                "hallucinogen",
                "psychedelic",
                "dissociative",
                "deliriant"
            )
            hallucinogens.contains(it.lowercase())
        }
    val isStimulant
        get() = categories.any {
            val stimulants = setOf(
                "stimulant"
            )
            stimulants.contains(it.lowercase())
        }

    val interactionExplanationURL get() = getInteractionExplanationURLForSubstance(url)

    val displayName: String
        get() = localizedName ?: name
}
