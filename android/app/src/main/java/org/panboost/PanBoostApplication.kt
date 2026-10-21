package org.panboost

import android.app.Application
import androidx.hilt.work.HiltWorkerFactory
import androidx.work.Configuration
import dagger.hilt.android.HiltAndroidApp
import javax.inject.Inject

/**
 * 应用入口（第 2 周：WorkManager 接线）。
 *
 * @HiltAndroidApp 生成依赖图；实现 Configuration.Provider 把
 * HiltWorkerFactory 交给 WorkManager——@HiltWorker 构造注入
 * （MockDownloadWorker ← MediaStoreDownloadsWriter）的接线点。
 * Manifest 已移除 WorkManagerInitializer 默认初始化避免冲突。
 */
@HiltAndroidApp
class PanBoostApplication : Application(), Configuration.Provider {

    @Inject
    lateinit var workerFactory: HiltWorkerFactory

    override val workManagerConfiguration: Configuration
        get() = Configuration.Builder()
            .setWorkerFactory(workerFactory)
            .build()
}
