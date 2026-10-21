package org.panboost.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/**
 * 字体规格（第 1 周骨架：默认字体 + 品牌标题加重）。
 *
 * CJK 字体后续周按需打包（对齐 Kivy 版 fonts/cjk.ttf 的思路），
 * 第 1 周先用系统字体保证骨架可跑。
 */
val PanBoostTypography = Typography(
    displayMedium = TextStyle(
        fontWeight = FontWeight.Bold,
        fontSize = 45.sp,
        lineHeight = 52.sp,
    ),
)
