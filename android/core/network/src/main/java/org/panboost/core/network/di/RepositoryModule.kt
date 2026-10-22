package org.panboost.core.network.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import org.panboost.core.domain.AccountRepository
import org.panboost.core.domain.DriveRepository
import org.panboost.core.domain.ShareRepository
import org.panboost.core.network.MultiPanCookieStore
import org.panboost.core.network.QuarkDriveRepository
import org.panboost.core.network.QuarkShareRepository
import javax.inject.Singleton

/** 仓库绑定（第 4 周）：接口→夸克实现。 */
@Module
@InstallIn(SingletonComponent::class)
abstract class RepositoryModule {

    @Binds
    @Singleton
    abstract fun bindDriveRepository(
        impl: QuarkDriveRepository,
    ): DriveRepository

    // v4.2.0：分享链接解析仓库
    @Binds
    @Singleton
    abstract fun bindShareRepository(
        impl: QuarkShareRepository,
    ): ShareRepository

    // v4.3.0：多网盘账号仓库（CookieStore 多网盘化）
    @Binds
    @Singleton
    abstract fun bindAccountRepository(
        impl: MultiPanCookieStore,
    ): AccountRepository
}
