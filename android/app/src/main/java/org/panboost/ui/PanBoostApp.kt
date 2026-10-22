package org.panboost.ui

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.ManageAccounts
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
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import org.panboost.feature.accounts.AccountsScreen
import org.panboost.feature.download.DownloadScreen
import org.panboost.feature.history.HistoryScreen
import org.panboost.feature.home.HomeScreen
import org.panboost.feature.login.LoginScreen
import org.panboost.feature.logs.LogsScreen
import org.panboost.feature.share.ShareScreen

/**
 * 根导航（v5.0.0：五 Tab 对齐 v3.2.8 五屏——分享/网盘/下载/
 * 历史/账号；日志为账号屏入口路由）。
 *
 * v3.2.8 屏幕映射：首页宫格=账号 Tab（18 网盘卡片）+ 分享 Tab
 * （分享链接解析）合并拆分；下载/历史/日志一一对应。
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
            startDestination = TAB_SHARE,
            modifier = Modifier.padding(innerPadding),
        ) {
            composable(TAB_SHARE) {
                ShareScreen(
                    onOpenDownload = { navController.navigate(TAB_DOWNLOAD) },
                )
            }
            composable(TAB_HOME) {
                HomeScreen(
                    onOpenDownload = { navController.navigate(TAB_DOWNLOAD) },
                    onOpenAccounts = { navController.navigate(TAB_ACCOUNTS) },
                )
            }
            composable(TAB_DOWNLOAD) {
                DownloadScreen()
            }
            composable(TAB_HISTORY) {
                HistoryScreen()
            }
            composable(TAB_ACCOUNTS) {
                AccountsScreen(
                    onLoginPan = { panKey ->
                        navController.navigate("login/$panKey")
                    },
                    onOpenLogs = { navController.navigate("logs") },
                )
            }
            composable(
                route = "login/{panKey}",
                arguments = listOf(
                    navArgument("panKey") { type = NavType.StringType },
                ),
            ) {
                LoginScreen(
                    onLoggedIn = { navController.popBackStack() },
                )
            }
            composable("logs") {
                LogsScreen()
            }
        }
    }
}

private const val TAB_SHARE = "share"
private const val TAB_HOME = "home"
private const val TAB_DOWNLOAD = "download"
private const val TAB_HISTORY = "history"
private const val TAB_ACCOUNTS = "accounts"

private val tabRoutes = setOf(
    TAB_SHARE, TAB_HOME, TAB_DOWNLOAD, TAB_HISTORY, TAB_ACCOUNTS,
)

private data class TabSpec(
    val route: String,
    val label: String,
    val icon: ImageVector,
)

private val tabs = listOf(
    TabSpec(TAB_SHARE, "分享", Icons.Filled.Share),
    TabSpec(TAB_HOME, "网盘", Icons.Filled.VideoLibrary),
    TabSpec(TAB_DOWNLOAD, "下载", Icons.Filled.Download),
    TabSpec(TAB_HISTORY, "历史", Icons.Filled.History),
    TabSpec(TAB_ACCOUNTS, "账号", Icons.Filled.ManageAccounts),
)
