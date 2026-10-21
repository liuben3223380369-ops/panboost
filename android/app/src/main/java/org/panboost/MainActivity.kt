package org.panboost

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import dagger.hilt.android.AndroidEntryPoint
import org.panboost.ui.PanBoostApp
import org.panboost.ui.theme.PanBoostTheme

/**
 * 唯一 Activity（第 1 周骨架）。
 *
 * 单 Activity + Compose 导航的现代形态（对标 YunX/NowInAndroid）：
 * 首屏即空 Compose 页面；第 3-4 周的 feature 屏幕全部经
 * NavHost 挂进来，不再出现多个 Activity 的生命周期/返回栈竞争
 * （Kivy 时代 v3.2.0/v3.2.1 双 Activity 黑屏的结构性根源）。
 */
@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            PanBoostTheme {
                PanBoostApp()
            }
        }
    }
}
