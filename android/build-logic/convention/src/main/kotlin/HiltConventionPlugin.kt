import org.gradle.api.Plugin
import org.gradle.api.Project
import org.gradle.api.artifacts.VersionCatalogsExtension
import org.gradle.kotlin.dsl.dependencies
import org.gradle.kotlin.dsl.getByType

/**
 * Hilt 约定（第 1 周：纯 KSP 路径）。
 *
 * Hilt 2.5x 在 KSP 模式下无需 dagger.hilt.android.plugin（该
 * gradle plugin 只提供聚合任务转换），挂 KSP + hilt-android/
 * hilt-compiler 依赖即可完成 @HiltAndroidApp/@AndroidEntryPoint/
 * @Inject 的完整编译链——少一个 classpath 依赖即少一个版本坑。
 */
class HiltConventionPlugin : Plugin<Project> {
    override fun apply(target: Project) {
        with(target) {
            val libs = extensions.getByType<VersionCatalogsExtension>()
                .named("libs")
            pluginManager.apply("com.google.devtools.ksp")

            dependencies {
                add("implementation", libs.findLibrary("hilt-android").get())
                add("ksp", libs.findLibrary("hilt-compiler").get())
                add("kspTest", libs.findLibrary("hilt-compiler").get())
            }
        }
    }
}
