# v4.1.0：R8 full mode 规则（保守起步——保真优先于极致压缩）
# 策略：org.panboost 全包 keep（App 自身代码占比小，收益主要在
# 依赖库裁剪）；依赖库按官方规则。
-keep class org.panboost.** { *; }
-keepclassmembers class org.panboost.** { *; }

# Retrofit（官方规则：接口方法注解反射 + 泛型签名）
-keepattributes Signature, InnerClasses, EnclosingMethod, RuntimeVisibleAnnotations, RuntimeVisibleParameterAnnotations, AnnotationDefault
-keepclassmembers,allowshrinking,allowobfuscation interface * {
    @retrofit2.http.* <methods>;
}
-if interface * { @retrofit2.http.* public *** *(...); }
-keep,allowobfuscation interface <1>
-dontwarn javax.annotation.**
-dontwarn kotlin.Unit
-dontwarn retrofit2.KotlinExtensions
-dontwarn retrofit2.KotlinExtensions$*

# OkHttp（官方 dontwarn 集）
-dontwarn okhttp3.internal.platform.**
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**

# WorkManager Worker（反射实例化——全 keep 构造）
-keep class * extends androidx.work.ListenableWorker {
    public <init>(...);
}

# Coroutines（官方建议）
-dontwarn kotlinx.coroutines.debug.**

# 保留行号/源文件名（崩溃堆栈可读——release 诊断必需）
-keepattributes SourceFile, LineNumberTable
-renamesourcefileattribute SourceFile
