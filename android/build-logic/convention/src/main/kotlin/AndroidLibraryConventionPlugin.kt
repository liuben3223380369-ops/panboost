import org.gradle.api.JavaVersion
import org.gradle.api.Plugin
import org.gradle.api.Project
import org.gradle.kotlin.dsl.configure
import org.jetbrains.kotlin.gradle.dsl.JvmTarget
import org.jetbrains.kotlin.gradle.dsl.KotlinAndroidProjectExtension

/**
 * library 模块通用约定（第 1 周）。
 *
 * 与 application 约定保持同一 Java/Kotlin 17 + compileSdk 35；
 * 消费 proguard 配置由各模块自带 consumer-rules（后续周按需）。
 */
class AndroidLibraryConventionPlugin : Plugin<Project> {
    override fun apply(target: Project) {
        with(target) {
            pluginManager.apply("com.android.library")
            pluginManager.apply("org.jetbrains.kotlin.android")

            extensions.configure<com.android.build.api.dsl.LibraryExtension> {
                compileSdk = 36
                defaultConfig {
                    minSdk = 26
                    testInstrumentationRunner =
                        "androidx.test.runner.AndroidJUnitRunner"
                }
                // v5.4.0：NIA 对照——测试选项对齐目标 SDK
                testOptions.targetSdk = 36
                compileOptions {
                    sourceCompatibility = JavaVersion.VERSION_17
                    targetCompatibility = JavaVersion.VERSION_17
                }
            }
            extensions.configure<KotlinAndroidProjectExtension> {
                compilerOptions {
                    jvmTarget.set(JvmTarget.JVM_17)
                }
            }
        }
    }
}
