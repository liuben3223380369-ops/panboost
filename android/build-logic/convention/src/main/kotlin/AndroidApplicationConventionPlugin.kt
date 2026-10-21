import org.gradle.api.JavaVersion
import org.gradle.api.Plugin
import org.gradle.api.Project
import org.gradle.api.artifacts.VersionCatalogsExtension
import org.gradle.kotlin.dsl.configure
import org.gradle.kotlin.dsl.getByType
import org.jetbrains.kotlin.gradle.dsl.JvmTarget
import org.jetbrains.kotlin.gradle.dsl.KotlinAndroidProjectExtension

/**
 * application 模块通用约定（第 1 周）。
 *
 * compileSdk 35 / targetSdk 35（第 5 周按计划升 36 并移除
 * MANAGE_EXTERNAL_STORAGE）；minSdk 26 覆盖 97%+ 设备且
 * WorkManager / MediaStore 无兼容负担。Java/Kotlin 统一 17。
 */
class AndroidApplicationConventionPlugin : Plugin<Project> {
    override fun apply(target: Project) {
        with(target) {
            pluginManager.apply("com.android.application")
            pluginManager.apply("org.jetbrains.kotlin.android")

            extensions.configure<com.android.build.gradle.BaseAppModuleExtension> {
                compileSdk = 35
                defaultConfig {
                    minSdk = 26
                    targetSdk = 35
                    testInstrumentationRunner =
                        "androidx.test.runner.AndroidJUnitRunner"
                }
                compileOptions {
                    sourceCompatibility = JavaVersion.VERSION_17
                    targetCompatibility = JavaVersion.VERSION_17
                }
                buildTypes {
                    release {
                        isMinifyEnabled = false
                    }
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
