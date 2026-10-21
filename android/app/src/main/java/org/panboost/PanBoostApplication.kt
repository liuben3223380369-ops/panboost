package org.panboost

import android.app.Application
import dagger.hilt.android.HiltAndroidApp

/**
 * 应用入口（第 1 周骨架）。
 *
 * @HiltAndroidApp 触发 Hilt 依赖图的生成——第 2 周起所有
 * 仓库/Worker/ViewModel 的注入都挂在这棵树上。
 */
@HiltAndroidApp
class PanBoostApplication : Application()
