/*
 * Copyright (c) 2022. Isaak Hanimann.
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

package com.isaakhanimann.journal

import com.isaakhanimann.journal.data.substances.ReleaseForm
import com.isaakhanimann.journal.data.substances.parse.SubstanceParser
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TestParse {

    private val parser = SubstanceParser()

    @Test
    fun noCrash() {
        val substances = parser.parseSubstanceFile(string = "error")
        assertTrue(substances.substances.isEmpty())
    }

    @Test
    fun noCrashExtract() {
        val result = parser.extractSubstanceString(string = "error")
        assertTrue(result == null)
    }

    @Test
    fun testExtractSubstancesString() {
        val text = """
{
  "data": {
    "substances": [
      {
        "name": "Armodafinil",
        "roas": [
          {
            "name": "oral"
          }
        ]
      }
    ]
  }
}"""
        val result = parser.extractSubstanceString(string = text)
        assertTrue(result == "[{\"name\":\"Armodafinil\",\"roas\":[{\"name\":\"oral\"}]}]")
    }

    @Test
    fun parseSingleSubstance() {
        val substance = parser.parseSubstance(
            string = """
                {
                  "name": "Armodafinil",
                  "url": "https://example.com/armodafinil",
                  "metabolism": "Amide hydrolysis and oxidation.",
                  "metabolismSources": ["https://example.com/metabolism"],
                  "oralReleaseForms": ["IMMEDIATE_RELEASE", "EXTENDED_RELEASE", "future_form"],
                  "categories": ["stimulant"],
                  "roas": [
                    {
                      "name": "oral"
                    }
                  ]
                }
            """.trimIndent()
        )
        assertTrue(substance?.name == "Armodafinil")
        assertEquals("Amide hydrolysis and oxidation.", substance?.metabolism)
        assertEquals(listOf("https://example.com/metabolism"), substance?.metabolismSources)
        assertEquals(
            listOf(ReleaseForm.IMMEDIATE_RELEASE, ReleaseForm.EXTENDED_RELEASE),
            substance?.oralReleaseForms
        )
    }

    @Test
    fun parseCategoriesArray() {
        val categories = parser.parseCategories(
            """
                [
                  {
                    "name": "test",
                    "description": "desc",
                    "color": 1234
                  }
                ]
            """.trimIndent()
        )
        assertTrue(categories.size == 1)
        assertTrue(categories.first().name == "test")
    }
}
