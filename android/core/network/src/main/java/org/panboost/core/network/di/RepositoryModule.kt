package org.panboost.core.network.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import org.panboost.core.domain.DriveRepository
import org.panboost.core.network.QuarkDriveRepository
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
}
