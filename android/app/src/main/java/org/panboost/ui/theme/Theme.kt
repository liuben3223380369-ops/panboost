package org.panboost.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable

// 品牌色对齐 Kivy 版视觉（主蓝 #1D6FE8、浅色底 #F4F7FA）
private val LightColors = lightColorScheme(
    primary = PrimaryBlue,
    onPrimary = OnPrimaryLight,
    primaryContainer = PrimaryBlueDim,
    onPrimaryContainer = OnPrimaryContainerLight,
    secondary = SlateDark,
    background = BgLight,
    onBackground = SlateDark,
    surface = BgLight,
    onSurface = SlateDark,
    onSurfaceVariant = SlateMid,
)

private val DarkColors = darkColorScheme(
    primary = PrimaryBlueBright,
    onPrimary = OnPrimaryDark,
    background = BgDark,
    onBackground = TextLight,
    surface = BgDark,
    onSurface = TextLight,
    onSurfaceVariant = SlateLight,
)

/**
 * 应用主题（第 1 周骨架）。
 *
 * Material3 动态取色暂不启用——保持品牌色稳定（网盘工具类
 * 应用对辨识度优先于系统融合）。
 */
@Composable
fun PanBoostTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkColors else LightColors,
        content = content,
    )
}
