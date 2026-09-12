# Repository Guidelines

## Project Overview

GPLv3 fork of PsychonautWiki Journal (a substance-use journaling app): single-module Android app, Jetpack Compose UI, Kotlin, Hilt DI, Room, DataStore. The fork's differentiator is multilingual support (en_us / zh_cn / zh_tw) — substance data and UI strings are translated via asset-based overlay systems. Data content derives from PsychonautWiki. Note: README, `gradle/libs.versions.toml`, CI workflows, and some source files carry Chinese comments; app source code comments are otherwise English.

## Architecture & Data Flow

- **Entry**: `MainActivity.kt` (`@AndroidEntryPoint`, splash, edge-to-edge) → `JournalTheme` → `ui/main/MainScreen.kt`: 5-tab NavigationBar (Journal / Statistics / Substances / SaferUse / Settings) + a NavHost; content gated behind a "conditions accepted" DataStore flag.
- **Navigation**: Navigation Compose with per-tab nested graphs in `ui/main/navigation/graphs/` (`journalGraph.kt`, `settingsGraph.kt`, ...), sealed string-route router objects (`navigation/routers/{TabRouter,NoArgumentRouter,ArgumentRouter}.kt`), and shared slide/fade transitions (`navigation/composableWithTransitions.kt`). `addIngestion` and `addCustomUnit` flows are nested graphs under the journal tab.
- **Screens/ViewModels**: one `XScreen.kt` + `XViewModel.kt` pair per feature; screens receive the VM as `viewModel: XViewModel = hiltViewModel()`. VMs combine repository Flows into `StateFlow` via `stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000))`.
- **Data layers**:
  - Room `experiences_db` (v6, 7 entities: Experience, Ingestion, TimedNote, ShulginRating, SubstanceCompanion, CustomUnit, CustomSubstance) via `data/room/AppDatabase.kt`; `ExperienceDao.kt` exposes Flow reads + suspend writes + `@Transaction` multi-entity ops; `ExperienceRepository.kt` wraps it (`flowOn(Dispatchers.IO).conflate()`).
  - Substance catalog: `data/substances/` — org.json parsing (`parse/SubstanceParser.kt`) of `app/src/main/assets/substances/{root,en_us,zh_cn,zh_tw}/`. `root/` is the English master; per-language files are overlays deep-merged by filename (substance name = merge key). `SubstanceRepository.kt` (singleton) loads + merges + caches in memory, reloads lazily on language change, and overlays extension-pack data. Search is pluggable: `search/` with `PinyinSubstanceSearcher` (PinIn library) for zh_cn, `DefaultSubstanceSearcher` otherwise.
  - Preferences: DataStore `user_preferences` (`ui/tabs/settings/combinations/UserPreferences.kt`) — language, owner name, achievements list, display toggles.
  - Localization: `localization/I18n.kt` loads `assets/lang/*.json` (keys like `en_us`, `zh_cn`, `zh_tw`; `supported.json` lists them), en_us fallback + localized overlay, `{placeholder}` replacement; `i18n()`/`i18nOrDefault()` composables; deferred translation via `I18nText(key, params)`. Missing keys render `"missing_key"`.
  - Extension packs: zip (manifest.json + `substances/<lang>/*.json` + language JSON) imported into `filesDir/ext_packs/<registerName>/` (`ui/tabs/settings/ExtensionPackManager.kt`, `ExtensionPackImporter.kt`); data and strings are merged transparently over built-ins; reload is signaled via `SubstanceEvents` + `I18n.markDirty()`.
  - Import/export: kotlinx.serialization DTOs in `ui/tabs/settings/JournalExport.kt` (custom `InstantSerializer` epoch-millis, `ShulginRatingOptionSerializer`), SAF file access; import = delete-all + insert-all.

## Key Directories

| Path | Purpose |
|---|---|
| `app/src/main/java/com/isaakhanimann/journal/ui/` | All Compose UI: `main/` (scaffold, navigation), `tabs/` (journal, search, safer, settings, stats), `theme/`, `utils/` |
| `app/src/main/java/com/isaakhanimann/journal/data/` | `room/` (DB, entities, relations, DAO, repo), `substances/` (classes, parse, repositories, search), `achievements/` |
| `app/src/main/java/com/isaakhanimann/journal/di/` | Hilt modules (`AppModule.kt`, `RepositoryModule.kt`), `JournalApplication.kt` |
| `app/src/main/java/com/isaakhanimann/journal/localization/` | `I18n.kt`, `I18nText.kt` |
| `app/src/main/assets/` | `substances/{root,en_us,zh_cn,zh_tw}/` (per-substance JSON + `_categories.json`), `lang/` (UI strings), `images/achievements/` |
| `app/src/test/` | JVM unit tests |
| `docs/` | `substances-translation-protocol.md`, `substances-pipeline.md`, `substances-pw-extraction.md`, `substances-catalog-sources.md`, `extension-pack-protocol.md`, `scripts/` (Python tooling: pipeline + one fetcher per source), `glossary/` (term tables for `translate`/`convert`), `VC_Demo_Extension/` |
| `Sample Files/` | Example journal export JSONs (import/export fixtures) |
| `app/schemas/` | Room schema exports (KSP `room.schemaLocation`) |

## Development Commands

```bash
# Build (Windows: gradlew.bat; CI uses JDK 21 temurin, compileOptions target Java 17)
./gradlew assembleDebug
./gradlew assembleRelease        # unsigned unless signing env vars set

# Unit tests (JVM; run in CI on every push/PR via build-apk.yml)
./gradlew testDebugUnitTest

# Instrumented tests (needs device/emulator)
./gradlew connectedDebugAndroidTest
```

- Formatting (mirrors `.github/workflows/format.yml`): `ktlint 1.3.1 -F "**/*.kt"` + `prettier --write "**/*.json"`. CI auto-commits "style: format" fixes on manual dispatch — keep changes pre-formatted.
- Release signing: env vars `KEYSTORE_BASE64` (base64 JKS, decoded to `build/release.keystore.jks`), `KEYSTORE_PASSWORD`, `KEY_ALIAS`, `KEY_PASSWORD`. Without them `release.signingConfig` is null → unsigned APK.
- Releases: `.github/workflows/build-release.yml` (manual dispatch) bumps `versionCode`/`versionName` in `app/build.gradle` AND `VERSION_NAME` in `ui/Constants.kt` (keep in sync), tags, and publishes APKs per-ABI.
- Local properties: create `local.properties` with `sdk.dir` as needed; `.gitignore` covers it.

## Code Conventions & Common Patterns

- **DI**: Hilt everywhere. `@HiltViewModel` + constructor injection (`@ApplicationContext` when needed); interfaces bound in `di/RepositoryModule.kt` (`@Binds`); Room/DataStore provided in `di/AppModule.kt`. `ExperienceRepository` is concrete, not interface-bound.
- **State management**: `MutableStateFlow` in VM, exposed via `stateIn`; heavy `combine()` pipelines (e.g. StatsViewModel). UI model data classes are co-located in the VM file. No `State` data-class wrapper, no `Result` types — errors are `try/catch` + snackbar (SettingsViewModel import/export) or silent `runCatching` (parsers/repositories).
- **Room**: Flow reads, suspend writes, `OnConflictStrategy.REPLACE`, `@Transaction` for multi-entity ops, relation classes `ExperienceWith*`/`IngestionWith*`. AutoMigration only (no manual `Migration` objects); `InstantConverter` stores epoch seconds.
- **JSON**: org.json only (except JournalExport). Parser is deliberately lenient/silent-fail — `parseSubstanceFile` returns empty on any exception, missing keys → nulls, never errors. Don't "fix" this into throwing; tests rely on it.
- **Localization**: never hardcode user-facing strings in UI code — use `i18n("key")` or `I18nText`. Key builders in `ui/utils/LocalizationKeys.kt`: `categories.<name>`, `route_<name>`, `route_<name>_desc`, `route_<name>_article`. Substance display name = `localizedName ?: name`. Keep key names as English identifiers; only values are translated.
- **Substance data**: new substance = add `root/<Name>.json` (structure + English text, `name` = merge key) then overlay `<lang>/<Name>.json` with translated text fields only (`summary`, `effectsSummary`, `metabolism`, `dosageRemark`, `generalRisks`, `longtermRisks`, `saferUse`, ...; `metabolismSources` stays in `root`). Objects deep-merge; arrays replace wholesale. See `docs/substances-translation-protocol.md`.
- **Naming**: `XScreen`/`XViewModel`/`XRow` suffixes; preview providers as `*PreviewProvider.kt`; test classes `TestX` or `XKtTest` (extension functions).
- **ktlint**: `.editorconfig` sets `android_studio` style with `function-naming`, `max-line-length`, `no-wildcard-imports`, `filename`, `property-naming` checks disabled.

## Important Files

| File | Why it matters |
|---|---|
| `app/build.gradle` | All build config: signing, minify, splits, versions (Groovy DSL) |
| `gradle/libs.versions.toml` | Version catalog — single source of dependency versions |
| `app/src/main/AndroidManifest.xml` | Entry activity + two launcher aliases (Classic disabled, SpringWind enabled); FileProvider authority `in.kawaiis.journal.fileprovider` |
| `ui/main/MainScreen.kt` | Tab scaffold, nav host, conditions gate, language push to I18n |
| `ui/main/navigation/graphs/*` | Route wiring per tab |
| `data/room/AppDatabase.kt` | Schema v6, AutoMigrations, type converters |
| `data/room/experiences/ExperienceDao.kt` | All journal-data queries/transactions |
| `data/substances/repositories/SubstanceRepository.kt` | Substance load/merge/cache/reload + searcher swap |
| `data/substances/parse/SubstanceParser.kt` | Substance JSON → model parsing (lenient) |
| `localization/I18n.kt` | UI string lookup/fallback/overrides |
| `ui/tabs/settings/JournalExport.kt` | Import/export DTOs + serializers |
| `ui/tabs/settings/ExtensionPackManager.kt` | Extension pack install/update/rollback |
| `ui/tabs/settings/combinations/UserPreferences.kt` | DataStore schema (preference keys) |
| `ui/Constants.kt` | `VERSION_NAME` (must match `app/build.gradle`) |

## Runtime/Tooling Preferences

- **Runtime**: Android 7.0+ (minSdk 26), target/compileSdk 37. No non-Android runtime — pure JVM work only in `app/src/test`.
- **Toolchain**: Gradle 9.6.1 wrapper, JDK 17 compile target (CI builds with temurin 21), AGP 9.3.1, Kotlin 2.4.10, KSP 2.3.10, Compose BOM 2026.06.01, Hilt 2.60.1, Room 2.8.4. Versions live in `gradle/libs.versions.toml` (dependabot updates weekly, target branch `main`).
- **Build quirks**: `buildConfig = false` (no `BuildConfig` class — don't reference it); `android.nonTransitiveRClass=true`; `FAIL_ON_PROJECT_REPOS`; jitpack repo required for `me.towdium:PinIn`. Release minifies + shrinks with proguard (`-dontobfuscate` only). `vcsInfo include=false` is deliberate for F-Droid reproducible builds — don't re-enable. `org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8` (UTF-8 matters: Chinese asset content).
- **CI**: `build-apk.yml` (push/PR), `build-release.yml` (manual release), `format.yml` (manual ktlint+prettier auto-commit), `deepseek-review.yml` (PR review bot, triggered by mentioning `@github-actions`; secret `CHAT_TOKEN`).
- **Substance tooling**: `docs/scripts/` holds one file per tool, sharing helpers from `_common.py` (path/JSON/merge/ledger). `substances_pipeline.py` (Python 3; `translate` needs `requests`) is the local data pipeline — `split`/`scaffold`/`constants`/`translate`/`apply`/`review`/`fix-tolerances`/`convert`, plus `guide`. `convert` does local script conversion (e.g. zh_cn→zh_tw) instead of a second translation pass; it prefers OpenCC (`s2twp`) and falls back to `zhconv` (both optional, clear error when missing). Five fetchers pull from external sources and only fill gaps unless `--overwrite`: `fetch_psychonautwiki.py` (dose/duration/tolerance/interactions via GraphQL), `fetch_tripsit.py` (names/aliases/categories; `--with-doses`), `fetch_atc.py` (ATC classes → name/category/source URL), `fetch_euda.py` (current-year NPS notifications CSV, needs a browser-downloaded file), `fetch_freeodwiki.py` (Chinese PW-derived pages → `zh_cn` overlay, no machine translation). Every fetcher's `--dry-run` is fully read-only and they merge provenance into `docs/substance-catalog-expansion.json`; term glossaries live in `docs/glossary/` (`en_to_zh.json` for `translate --glossary`, `zh_cn_to_zh_tw.json` for `convert --glossary`). Read `docs/substances-translation-protocol.md` (data format), `docs/substances-pipeline.md` (pipeline), `docs/substances-pw-extraction.md` (PW field mapping) and `docs/substances-catalog-sources.md` (ATC/TripSit/EUDA/FreeODwiki + multilingual strategy) before touching bulk translation data.

## Testing & QA

- **Framework**: JUnit4 + `org.junit.Assert` (one file, `DoubleReadableExtensionKtTest.kt`, inconsistently uses `junit.framework.TestCase` — use `org.junit.Assert` in new tests). `testImplementation` includes `org.json:json` because android.jar's org.json stubs throw in JVM tests; `SubstanceParser` needs it.
- **Coverage**: 4 JVM unit tests (`TestRegex.kt`, `TestParse.kt`, `TestDates.kt`, `DoubleReadableExtensionKtTest.kt`) + 1 instrumented smoke test (`ExampleInstrumentedTest.kt`). No Robolectric, no Compose UI tests, no test resources — test data is inline triple-quoted strings. Do not add tests that read `assets/` (impossible without Robolectric).
- **Run**: `./gradlew testDebugUnitTest` (Windows: `gradlew.bat`). CI runs the unit suite on every push/PR (build-apk.yml), so a red test blocks merges.
- **History**: `TestDates.dateDifferences` previously asserted a fractional-string output (`"1,9 days"`) that `getTimeDifferenceText` (whole units like `"45 hours"`) cannot produce; it now asserts `"45 hours"` on fixed instants plus boundary cases. CI runs the suite on every push/PR, so a red test is visible.
- **QA expectations**: keep new tests deterministic and pure-JVM; keep them ktlint-clean (format bot reformats everything). For instrumented behavior, manual device verification; import/export fixtures live in `Sample Files/`.
