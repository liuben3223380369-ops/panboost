package org.panboost.core.data.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import org.panboost.core.data.DownloadRepositoryImpl
import org.panboost.core.domain.DownloadRepository
import javax.inject.Singleton

/**
 * 数据层绑定（第 2 周）：接口→实现单向依赖（feature 只见 domain）。
 */
@Module
@InstallIn(SingletonComponent::class)
abstract class DataModule {

    @Binds
    @Singleton
    abstract fun bindDownloadRepository(
        impl: DownloadRepositoryImpl,
    ): DownloadRepository
}
