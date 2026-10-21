package org.panboost.ui

import androidx.compose.runtime.Composable
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import org.panboost.feature.download.DownloadScreen

/**
 * 根导航（第 3 周：单 Activity + NavHost）。
 *
 * 目的地起步只有 "download"（MVI 正式屏）；第 4 周追加
 * login/home 路由。Kivy 时代多屏切换的生命周期/返回栈问题由
 * Navigation 组件统一管理。
 */
@Composable
fun PanBoostApp() {
    val navController = rememberNavController()
    NavHost(
        navController = navController,
        startDestination = "download",
    ) {
        composable("download") {
            DownloadScreen()
        }
    }
}
