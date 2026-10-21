package org.panboost.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview

/**
 * 根 Composable（第 1 周骨架：空页面）。
 *
 * 第 3 周接 :feature:download 的 NavHost；第 4 周接 login/home。
 * 品牌主色对齐 Kivy 版（Material 蓝 0x2563EB≈#1D6FE8）。
 */
@Composable
fun PanBoostApp() {
    Scaffold { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Text(
                text = "PanBoost",
                style = MaterialTheme.typography.displayMedium,
            )
            Text(
                text = "原生重构进行中 · 第 1 周",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun PanBoostAppPreview() {
    PanBoostApp()
}
