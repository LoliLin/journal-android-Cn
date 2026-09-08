package com.isaakhanimann.journal.ui.tabs.journal.addingestion

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.isaakhanimann.journal.data.substances.ReleaseForm
import com.isaakhanimann.journal.localization.i18n
import com.isaakhanimann.journal.ui.tabs.journal.experience.components.CardWithTitle
import com.isaakhanimann.journal.ui.utils.releaseFormKey

@Composable
fun ReleaseFormPicker(
    availableForms: List<ReleaseForm>,
    selectedForm: ReleaseForm?,
    onSelect: (ReleaseForm?) -> Unit
) {
    if (availableForms.isEmpty() && selectedForm == null) return
    CardWithTitle(title = i18n("release_form_title"), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.selectableGroup()) {
            val options = (listOf(null) + availableForms + listOfNotNull(selectedForm)).distinct()
            options.forEach { form ->
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .selectable(
                            selected = form == selectedForm,
                            onClick = { onSelect(form) },
                            role = Role.RadioButton
                        )
                        .padding(vertical = 4.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    RadioButton(selected = form == selectedForm, onClick = null)
                    Text(i18n(releaseFormKey(form)))
                }
            }
            Text(i18n("release_form_hint"), style = MaterialTheme.typography.bodySmall)
            if (selectedForm == ReleaseForm.EXTENDED_RELEASE) {
                Text(
                    i18n("release_form_no_reference"),
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(top = 8.dp)
                )
            }
        }
    }
}
