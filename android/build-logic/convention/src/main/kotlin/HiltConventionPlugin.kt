import org.gradle.api.Plugin
import org.gradle.api.Project
import org.gradle.api.artifacts.VersionCatalogsExtension
import org.gradle.kotlin.dsl.dependencies
import org.gradle.kotlin.dsl.getByType

/**
 * Hilt 约定（第 1 周）。
 *
 * CI 实锤：@AndroidEntryPoint/@HiltAndroidApp 必须挂 Hilt Gradle
 * Plugin（com.google.dagger.hilt.android——对注解做字节码变换
 * 补 value），纯 KSP 路径只适用于部分 Dagger SPI 场景；本插件
 * 挂 plugin + KSP + hilt-android/hilt-compiler 依赖的完整链。
 */
class HiltConventionPlugin : Plugin<Project> {
    override fun apply(target: Project) {
        with(target) {
            val libs = extensions.getByType<VersionCatalogsExtension>()
                .named("libs")
            pluginManager.apply("com.google.dagger.hilt.android")
            pluginManager.apply("com.google.devtools.ksp")

            dependencies {
                add("implementation", libs.findLibrary("hilt-android").get())
                add("ksp", libs.findLibrary("hilt-compiler").get())
                add("kspTest", libs.findLibrary("hilt-compiler").get())
            }
        }
    }
}
