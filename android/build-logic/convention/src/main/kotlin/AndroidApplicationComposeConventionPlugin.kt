import org.gradle.api.Plugin
import org.gradle.api.Project
import org.gradle.api.artifacts.VersionCatalogsExtension
import org.gradle.kotlin.dsl.configure
import org.gradle.kotlin.dsl.dependencies
import org.gradle.kotlin.dsl.getByType

/**
 * Compose 约定（application 形态，第 1 周）。
 *
 * Kotlin 2.x 起 Compose 编译器随 Kotlin 版本发布，本插件只做：
 * - 挂 org.jetbrains.kotlin.plugin.compose（版本与 Kotlin 绑定）
 * - buildFeatures.compose = true
 * - 引入 Compose BOM + 基础依赖（material3/ui/foundation/
 *   tooling-preview，debugImplementation tooling）
 */
class AndroidApplicationComposeConventionPlugin : Plugin<Project> {
    override fun apply(target: Project) {
        with(target) {
            val libs = extensions.getByType<VersionCatalogsExtension>()
                .named("libs")
            pluginManager.apply("org.jetbrains.kotlin.plugin.compose")

            extensions.configure<com.android.build.gradle.BaseAppModuleExtension> {
                buildFeatures {
                    compose = true
                }
            }

            dependencies {
                val bom = libs.findLibrary("compose-bom").get()
                add("implementation", platform(bom))
                add("androidTestImplementation", platform(bom))
                add("implementation", libs.findLibrary("compose-ui").get())
                add("implementation", libs.findLibrary("compose-foundation").get())
                add("implementation", libs.findLibrary("compose-material3").get())
                add("implementation", libs.findLibrary("compose-ui-tooling-preview").get())
                add("debugImplementation", libs.findLibrary("compose-ui-tooling").get())
            }
        }
    }
}
