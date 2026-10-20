package org.panboost;

/**
 * PanBoost 主入口 Activity（v3.2.2）。
 *
 * 经 p4a --android-entrypoint 注册进 AndroidManifest（buildozer.spec
 * 的 p4a.extra_args 透传），继承 org.kivy.android.PythonActivity
 * （Python 启动链/SDL 桥接全部继承，行为与默认入口完全一致）。
 *
 * 唯一职责：接管返回键/手势——登录层（LoginLayer，addContentView
 * 叠加在 SDL surface 之上的全屏 View 层）打开时：
 * - WebView 可后退 → 先退网页（handleBack 内部处理）
 * - 否则 → 按取消关闭登录层
 * 层未打开 → 走 super（SDLActivity 默认行为，与历史版本一致）。
 *
 * 这是 v1.8.3 遗留问题的钥匙：当年 View 层方案因 SDL trap 吞掉
 * 手势返回（Android 10+ 手势不产生键盘事件，Kivy/OnKeyListener
 * 全收不到）被迫改用 Dialog 弹窗；如今重写主 Activity 的
 * onBackPressed，手势返回走系统标准路径直达本层——View 层方案
 * 的最后一块拼图补齐，Dialog 弹窗（真机"不能展示信息"）与独立
 * Activity（真机"返回后黑屏卡住"）两条已证死路都不再需要。
 */
public class PanMainActivity extends org.kivy.android.PythonActivity {

    @Override
    public void onBackPressed() {
        if (org.panboost.login.LoginLayer.handleBack(this)) {
            return;
        }
        super.onBackPressed();
    }
}
