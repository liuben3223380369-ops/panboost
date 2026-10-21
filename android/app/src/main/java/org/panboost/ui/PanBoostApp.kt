package org.panboost.ui

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.Share
import androidx.compose.material.icons.filled.VideoLibrary
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import org.panboost.feature.download.DownloadScreen
import org.panboost.feature.home.HomeScreen
import org.panboost.feature.login.LoginScreen
import org.panboost.feature.share.ShareScreen

/**
 * 根导航（v4.2.0：login → 底部导航三 Tab [分享/网盘/下载]）。
 *
 * - login 为前置屏（检测 Cookie 自动跳 Tab 区）
 * - 分享 Tab（P0 回补）：粘贴分享链接→勾选→批量下载
 * - 网盘 Tab：我的网盘浏览下载；下载 Tab：进度/取消/重试
 * 底部 NavigationBar（M3）+ NavHost 返回栈由 Navigation 管理。
 */
@Composable
fun PanBoostApp() {
    val navController = rememberNavController()
    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentDestination = backStackEntry?.destination

    Scaffold(
        bottomBar = {
            if (currentDestination?.hierarchy?.any { it.route in tabRoutes } == true) {
                NavigationBar {
                    tabs.forEach { tab ->
                        val selected = currentDestination?.hierarchy
                            ?.any { it.route == tab.route } == true
                        NavigationBarItem(
                            selected = selected,
                            onClick = {
                                navController.navigate(tab.route) {
                                    popUpTo(tabRoutes.first()) { saveState = true }
                                    launchSingleTop = true
                                    restoreState = true
                                }
                            },
                            icon = { Icon(tab.icon, contentDescription = tab.label) },
                            label = { Text(tab.label) },
                        )
                    }
                }
            }
        },
    ) { innerPadding ->
        NavHost(
            navController = navController,
            startDestination = "login",
            modifier = Modifier.padding(innerPadding),
        ) {
            composable("login") {
                LoginScreen(
                    onLoggedIn = {
                        navController.navigate(TAB_SHARE) {
                            popUpTo("login") { inclusive = true }
                        }
                    },
                )
            }
            composable(TAB_SHARE) {
                ShareScreen(
                    onOpenDownload = { navController.navigate(TAB_DOWNLOAD) },
                )
            }
            composable(TAB_HOME) {
                HomeScreen(
                    onOpenDownload = { navController.navigate(TAB_DOWNLOAD) },
                )
            }
            composable(TAB_DOWNLOAD) {
                DownloadScreen()
            }
        }
    }
}

private const val TAB_SHARE = "share"
private const val TAB_HOME = "home"
private const val TAB_DOWNLOAD = "download"

private val tabRoutes = setOf(TAB_SHARE, TAB_HOME, TAB_DOWNLOAD)

private data class TabSpec(
    val route: String,
    val label: String,
    val icon: ImageVector,
)

private val tabs = listOf(
    TabSpec(TAB_SHARE, "分享", Icons.Filled.Share),
    TabSpec(TAB_HOME, "网盘", Icons.Filled.VideoLibrary),
    TabSpec(TAB_DOWNLOAD, "下载", Icons.Filled.Download),
)
