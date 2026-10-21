package org.panboost.ui

import androidx.compose.runtime.Composable
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import org.panboost.feature.home.HomeScreen
import org.panboost.feature.login.LoginScreen
import org.panboost.feature.download.DownloadScreen

/**
 * 根导航（第 4 周：完整链路 login → home → download）。
 *
 * - login 为起点：LoginScreen 检测已存 Cookie 自动跳 home
 *   （登录屏本体为原生 WebView——Compose AndroidView 嵌入，
 *   官方成熟路径，无 Kivy 时代的桥接坑）
 * - home（网盘列表）点文件 → 取直链 → enqueue 真实下载任务
 * - download（MVI 进度屏）实时展示；Snackbar 引导跳转
 * 单 Activity + Navigation 组件管理返回栈。
 */
@Composable
fun PanBoostApp() {
    val navController = rememberNavController()
    NavHost(
        navController = navController,
        startDestination = "login",
    ) {
        composable("login") {
            LoginScreen(
                onLoggedIn = {
                    navController.navigate("home") {
                        popUpTo("login") { inclusive = true }
                    }
                },
            )
        }
        composable("home") {
            HomeScreen(
                onOpenDownload = {
                    navController.navigate("download")
                },
            )
        }
        composable("download") {
            DownloadScreen()
        }
    }
}
