package org.panboost.core.network

import org.panboost.core.domain.ShareFile
import org.panboost.core.domain.ShareRepository
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 分享链接解析分发器（v5.0.0：v3.2.8 RESOLVERS/RESOLVE_HINTS
 * 原生等价——夸克/123/蓝奏三网盘）。
 *
 * 按 URL 域名特征路由到对应实现；未识别的链接给出支持清单
 * 提示（v3.2.8 find_resolver 语义）。
 */
@Singleton
class CompositeShareRepository @Inject constructor(
    private val quark: QuarkShareRepository,
    private val pan123: Pan123ShareRepository,
    private val lanzou: LanzouShareResolver,
) : ShareRepository {

    override suspend fun resolve(shareUrl: String, passcode: String): List<ShareFile> {
        return when {
            Regex("quark\\.cn/s/[A-Za-z0-9]+").containsMatchIn(shareUrl) ->
                quark.resolve(shareUrl, passcode)

            Regex("123pan\\.com/s/[A-Za-z0-9]+").containsMatchIn(shareUrl) ->
                pan123.resolve(shareUrl, passcode)

            Regex("""lanzou[a-z]*\.(?:com|cn)|lanzn\.com""").containsMatchIn(shareUrl) ->
                lanzou.resolve(shareUrl, passcode)

            else -> throw IllegalArgumentException(
                "暂不支持该分享链接。当前支持：夸克网盘、123云盘、蓝奏云" +
                        "（更多网盘按 ROADMAP 逐步接入）"
            )
        }
    }
}
