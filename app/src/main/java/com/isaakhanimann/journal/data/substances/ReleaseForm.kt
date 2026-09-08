package com.isaakhanimann.journal.data.substances

import kotlinx.serialization.Serializable

@Serializable
enum class ReleaseForm {
    IMMEDIATE_RELEASE,
    EXTENDED_RELEASE;

    companion object {
        fun fromName(name: String?): ReleaseForm? = entries.firstOrNull { it.name == name }
    }
}
