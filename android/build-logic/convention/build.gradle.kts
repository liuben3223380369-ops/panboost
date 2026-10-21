// convention 插件实现模块：依赖 AGP/Kotlin/KSP 的 Gradle API
plugins {
    `kotlin-dsl`
}
kotlin {
    jvmToolchain(17)
}
dependencies {
    compileOnly(libs.android.gradlePlugin)
    compileOnly(libs.kotlin.gradlePlugin)
    compileOnly(libs.ksp.gradlePlugin)
    compileOnly(libs.hilt.gradlePlugin)
}
gradlePlugin {
    plugins {
        register("androidApplication") {
            id = "panboost.android.application"
            implementationClass = "AndroidApplicationConventionPlugin"
        }
        register("androidLibrary") {
            id = "panboost.android.library"
            implementationClass = "AndroidLibraryConventionPlugin"
        }
        register("androidApplicationCompose") {
            id = "panboost.android.application.compose"
            implementationClass = "AndroidApplicationComposeConventionPlugin"
        }
        register("androidLibraryCompose") {
            id = "panboost.android.library.compose"
            implementationClass = "AndroidLibraryComposeConventionPlugin"
        }
        register("hilt") {
            id = "panboost.hilt"
            implementationClass = "HiltConventionPlugin"
        }
    }
}
