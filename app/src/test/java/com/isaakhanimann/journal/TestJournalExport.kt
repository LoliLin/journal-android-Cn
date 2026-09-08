package com.isaakhanimann.journal

import com.isaakhanimann.journal.data.room.experiences.entities.Ingestion
import com.isaakhanimann.journal.data.substances.AdministrationRoute
import com.isaakhanimann.journal.data.substances.ReleaseForm
import com.isaakhanimann.journal.ui.tabs.settings.IngestionSerializable
import com.isaakhanimann.journal.ui.tabs.settings.toIngestion
import com.isaakhanimann.journal.ui.tabs.settings.toIngestionSerializable
import java.time.Instant
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Test

class TestJournalExport {
    @Test
    fun journalRoundTripPreservesTheRecordedFormulation() {
        // The null case also exercises backups that omit the new optional field.
        (listOf(null) + ReleaseForm.entries).forEach { form ->
            val original = Ingestion(
                substanceName = "Example medicine",
                time = Instant.parse("2026-01-01T12:00:00Z"),
                creationDate = Instant.parse("2026-01-01T12:01:00Z"),
                administrationRoute = AdministrationRoute.ORAL,
                dose = 50.0,
                isDoseAnEstimate = false,
                estimatedDoseStandardDeviation = null,
                units = "mg",
                experienceId = 7,
                notes = "Product label recorded separately",
                stomachFullness = null,
                consumerName = null,
                customUnitId = null,
                releaseForm = form
            )
            val backup = Json.encodeToString(original.toIngestionSerializable())
            val restored = Json.decodeFromString<IngestionSerializable>(backup)
                .toIngestion(experienceId = original.experienceId)
            assertEquals("Formulation $form must survive export and import", original, restored)
        }
    }
}
