package com.isaakhanimann.journal.ui.utils

import com.isaakhanimann.journal.data.substances.AdministrationRoute
import com.isaakhanimann.journal.data.substances.ReleaseForm

fun categoryNameKey(name: String): String = "categories.$name"

fun releaseFormKey(form: ReleaseForm?): String = when (form) {
    ReleaseForm.IMMEDIATE_RELEASE -> "release_form_immediate"
    ReleaseForm.EXTENDED_RELEASE -> "release_form_extended"
    null -> "release_form_unspecified"
}

fun administrationRouteKey(route: AdministrationRoute): String = "route_${route.name.lowercase()}"

fun administrationRouteDescriptionKey(route: AdministrationRoute): String =
    "route_${route.name.lowercase()}_desc"

fun administrationRouteArticleKey(route: AdministrationRoute): String =
    "route_${route.name.lowercase()}_article"
