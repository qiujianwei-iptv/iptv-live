.class public Lcom/github/catvod/spider/QfUpdate;
.super Lcom/github/catvod/crawler/Spider;
.source "QfUpdate.java"


# static fields
.field private static final DIR:Ljava/lang/String; = "/storage/emulated/0/Download/"

.field private static final LOCAL:Ljava/lang/String; = "/storage/emulated/0/Download/tvbox.json"

.field private static final LOG:Ljava/lang/String; = "/storage/emulated/0/Download/qf_update_log.txt"

.field private static final M1:Ljava/lang/String; = "https://raw.githubusercontent.com/qiujianwei-iptv/iptv-live/main/tvbox_local.json?t="

.field private static final M2:Ljava/lang/String; = "https://gh-proxy.com/https://raw.githubusercontent.com/qiujianwei-iptv/iptv-live/main/tvbox_local.json?t="

.field private static final M3:Ljava/lang/String; = "https://aka.doubaocdn.com/s/RjoAOdilcc"

.field private static final RESULT:Ljava/lang/String; = "/storage/emulated/0/Download/qf_result.txt"

.field private static final SHADOW:Ljava/lang/String; = "/storage/emulated/0/Download/qf_applied.json"


# direct methods
.method public constructor <init>()V
    .registers 1

    .line 17
    invoke-direct {p0}, Lcom/github/catvod/crawler/Spider;-><init>()V

    return-void
.end method

.method private static fetch(Ljava/lang/String;)Ljava/lang/String;
    .registers 6

    .line 51
    const-string v0, ""

    :try_start_2
    new-instance v1, Lokhttp3/OkHttpClient$Builder;

    invoke-direct {v1}, Lokhttp3/OkHttpClient$Builder;-><init>()V

    sget-object v2, Ljava/util/concurrent/TimeUnit;->SECONDS:Ljava/util/concurrent/TimeUnit;

    .line 52
    const-wide/16 v3, 0x4

    invoke-virtual {v1, v3, v4, v2}, Lokhttp3/OkHttpClient$Builder;->connectTimeout(JLjava/util/concurrent/TimeUnit;)Lokhttp3/OkHttpClient$Builder;

    move-result-object v1

    sget-object v2, Ljava/util/concurrent/TimeUnit;->SECONDS:Ljava/util/concurrent/TimeUnit;

    .line 53
    const-wide/16 v3, 0x6

    invoke-virtual {v1, v3, v4, v2}, Lokhttp3/OkHttpClient$Builder;->readTimeout(JLjava/util/concurrent/TimeUnit;)Lokhttp3/OkHttpClient$Builder;

    move-result-object v1

    .line 54
    invoke-virtual {v1}, Lokhttp3/OkHttpClient$Builder;->build()Lokhttp3/OkHttpClient;

    move-result-object v1

    .line 55
    new-instance v2, Lokhttp3/Request$Builder;

    invoke-direct {v2}, Lokhttp3/Request$Builder;-><init>()V

    invoke-virtual {v2, p0}, Lokhttp3/Request$Builder;->url(Ljava/lang/String;)Lokhttp3/Request$Builder;

    move-result-object p0

    invoke-virtual {p0}, Lokhttp3/Request$Builder;->build()Lokhttp3/Request;

    move-result-object p0

    .line 56
    invoke-virtual {v1, p0}, Lokhttp3/OkHttpClient;->newCall(Lokhttp3/Request;)Lokhttp3/Call;

    move-result-object p0

    invoke-interface {p0}, Lokhttp3/Call;->execute()Lokhttp3/Response;

    move-result-object p0

    .line 57
    invoke-virtual {p0}, Lokhttp3/Response;->body()Lokhttp3/ResponseBody;

    move-result-object p0

    .line 58
    if-nez p0, :cond_37

    return-object v0

    .line 59
    :cond_37
    invoke-virtual {p0}, Lokhttp3/ResponseBody;->string()Ljava/lang/String;

    move-result-object p0
    :try_end_3b
    .catchall {:try_start_2 .. :try_end_3b} :catchall_3c

    return-object p0

    .line 60
    :catchall_3c
    move-exception p0

    .line 61
    return-object v0
.end method

.method private static flat(Ljava/lang/String;)Ljava/lang/String;
    .registers 3

    .line 45
    const-string v0, ""

    if-nez p0, :cond_5

    return-object v0

    .line 46
    :cond_5
    const-string v1, " "

    invoke-virtual {p0, v1, v0}, Ljava/lang/String;->replace(Ljava/lang/CharSequence;Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object p0

    const-string v1, "\n"

    invoke-virtual {p0, v1, v0}, Ljava/lang/String;->replace(Ljava/lang/CharSequence;Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object p0

    const-string v1, "\r"

    invoke-virtual {p0, v1, v0}, Ljava/lang/String;->replace(Ljava/lang/CharSequence;Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object p0

    const-string v1, "\t"

    invoke-virtual {p0, v1, v0}, Ljava/lang/String;->replace(Ljava/lang/CharSequence;Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object p0

    return-object p0
.end method

.method private static read(Ljava/lang/String;)Ljava/lang/String;
    .registers 2

    .line 38
    :try_start_0
    new-instance v0, Ljava/io/File;

    invoke-direct {v0, p0}, Ljava/io/File;-><init>(Ljava/lang/String;)V

    invoke-static {v0}, Lcom/github/catvod/spider/merge/m/k;->a(Ljava/io/File;)Ljava/lang/String;

    move-result-object p0
    :try_end_9
    .catchall {:try_start_0 .. :try_end_9} :catchall_a

    return-object p0

    .line 39
    :catchall_a
    move-exception p0

    .line 40
    const-string p0, ""

    return-object p0
.end method

.method private static usable(Ljava/lang/String;)Z
    .registers 3

    .line 66
    if-eqz p0, :cond_14

    invoke-virtual {p0}, Ljava/lang/String;->length()I

    move-result v0

    const/16 v1, 0xb8

    if-le v0, v1, :cond_14

    const-string v0, "LOCALJAR"

    invoke-virtual {p0, v0}, Ljava/lang/String;->indexOf(Ljava/lang/String;)I

    move-result p0

    if-ltz p0, :cond_14

    const/4 p0, 0x1

    goto :goto_15

    :cond_14
    const/4 p0, 0x0

    :goto_15
    return p0
.end method

.method private static write(Ljava/lang/String;Ljava/lang/String;)V
    .registers 3

    .line 31
    :try_start_0
    new-instance v0, Ljava/io/File;

    invoke-direct {v0, p0}, Ljava/io/File;-><init>(Ljava/lang/String;)V

    invoke-static {v0, p1}, Lcom/github/catvod/spider/merge/m/k;->c(Ljava/io/File;Ljava/lang/String;)V
    :try_end_8
    .catchall {:try_start_0 .. :try_end_8} :catchall_9

    .line 33
    goto :goto_a

    .line 32
    :catchall_9
    move-exception p0

    .line 34
    :goto_a
    return-void
.end method


# virtual methods
.method public homeContent(Z)Ljava/lang/String;
    .registers 13

    .line 73
    const-string p1, "/storage/emulated/0/Download/qf_applied.json"

    const-string v0, "/storage/emulated/0/Download/tvbox.json"

    const-string v1, "/storage/emulated/0/Download/qf_update_log.txt"

    :try_start_6
    const-string v2, "[v47] start"

    invoke-static {v1, v2}, Lcom/github/catvod/spider/QfUpdate;->write(Ljava/lang/String;Ljava/lang/String;)V

    .line 74
    invoke-static {v0}, Lcom/github/catvod/spider/QfUpdate;->read(Ljava/lang/String;)Ljava/lang/String;

    move-result-object v2

    .line 75
    invoke-static {p1}, Lcom/github/catvod/spider/QfUpdate;->read(Ljava/lang/String;)Ljava/lang/String;

    move-result-object v3

    .line 76
    invoke-virtual {v3}, Ljava/lang/String;->length()I

    move-result v4

    if-lez v4, :cond_1a

    move-object v2, v3

    :cond_1a
    invoke-static {v2}, Lcom/github/catvod/spider/QfUpdate;->flat(Ljava/lang/String;)Ljava/lang/String;

    move-result-object v2

    .line 78
    const/4 v3, 0x3

    new-array v4, v3, [Ljava/lang/String;

    new-instance v5, Ljava/lang/StringBuilder;

    invoke-direct {v5}, Ljava/lang/StringBuilder;-><init>()V

    const-string v6, "https://raw.githubusercontent.com/qiujianwei-iptv/iptv-live/main/tvbox_local.json?t="

    invoke-virtual {v5, v6}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v5

    .line 79
    invoke-static {}, Ljava/lang/System;->currentTimeMillis()J

    move-result-wide v6

    invoke-virtual {v5, v6, v7}, Ljava/lang/StringBuilder;->append(J)Ljava/lang/StringBuilder;

    move-result-object v5

    invoke-virtual {v5}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v5

    const/4 v6, 0x0

    aput-object v5, v4, v6

    new-instance v5, Ljava/lang/StringBuilder;

    invoke-direct {v5}, Ljava/lang/StringBuilder;-><init>()V

    const-string v7, "https://gh-proxy.com/https://raw.githubusercontent.com/qiujianwei-iptv/iptv-live/main/tvbox_local.json?t="

    invoke-virtual {v5, v7}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v5

    .line 80
    invoke-static {}, Ljava/lang/System;->currentTimeMillis()J

    move-result-wide v7

    invoke-virtual {v5, v7, v8}, Ljava/lang/StringBuilder;->append(J)Ljava/lang/StringBuilder;

    move-result-object v5

    invoke-virtual {v5}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v5

    const/4 v7, 0x1

    aput-object v5, v4, v7

    const-string v5, "https://aka.doubaocdn.com/s/RjoAOdilcc"

    const/4 v7, 0x2

    aput-object v5, v4, v7

    .line 84
    const-string v5, ""

    .line 85
    nop

    .line 86
    nop

    .line 88
    const/4 v7, 0x0

    :goto_5f
    if-ge v6, v3, :cond_a9

    .line 89
    new-instance v8, Ljava/lang/StringBuilder;

    invoke-direct {v8}, Ljava/lang/StringBuilder;-><init>()V

    const-string v9, "[v47] fetch \u7b2c"

    invoke-virtual {v8, v9}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v8

    invoke-virtual {v8, v6}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    move-result-object v8

    const-string v9, "\u4e2a\u6e90"

    invoke-virtual {v8, v9}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v8

    invoke-virtual {v8}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v8

    invoke-static {v1, v8}, Lcom/github/catvod/spider/QfUpdate;->write(Ljava/lang/String;Ljava/lang/String;)V

    .line 90
    aget-object v8, v4, v6

    invoke-static {v8}, Lcom/github/catvod/spider/QfUpdate;->fetch(Ljava/lang/String;)Ljava/lang/String;

    move-result-object v8

    .line 91
    invoke-static {v8}, Lcom/github/catvod/spider/QfUpdate;->usable(Ljava/lang/String;)Z

    move-result v9

    if-nez v9, :cond_8a

    goto :goto_a6

    .line 92
    :cond_8a
    const-string v9, "LOCALJAR"

    const-string v10, "clan://localhost/Download/qf.jar"

    invoke-virtual {v8, v9, v10}, Ljava/lang/String;->replace(Ljava/lang/CharSequence;Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object v8

    invoke-static {v8}, Lcom/github/catvod/spider/QfUpdate;->flat(Ljava/lang/String;)Ljava/lang/String;

    move-result-object v8

    .line 93
    if-nez v7, :cond_9d

    .line 94
    nop

    .line 95
    invoke-virtual {v8}, Ljava/lang/String;->length()I

    move-result v7

    .line 97
    :cond_9d
    invoke-virtual {v8, v2}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v9

    if-nez v9, :cond_a6

    .line 98
    nop

    .line 99
    move-object v5, v8

    goto :goto_a9

    .line 88
    :cond_a6
    :goto_a6
    add-int/lit8 v6, v6, 0x1

    goto :goto_5f

    .line 103
    :cond_a9
    :goto_a9
    invoke-virtual {v5}, Ljava/lang/String;->length()I

    move-result v2

    if-lez v2, :cond_fd

    .line 104
    invoke-static {v0, v5}, Lcom/github/catvod/spider/QfUpdate;->write(Ljava/lang/String;Ljava/lang/String;)V

    .line 105
    invoke-static {p1, v5}, Lcom/github/catvod/spider/QfUpdate;->write(Ljava/lang/String;Ljava/lang/String;)V

    .line 106
    invoke-static {v0}, Lcom/github/catvod/spider/QfUpdate;->read(Ljava/lang/String;)Ljava/lang/String;

    move-result-object p1

    .line 107
    invoke-virtual {p1, v5}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v0

    if-eqz v0, :cond_d7

    .line 108
    new-instance p1, Ljava/lang/StringBuilder;

    invoke-direct {p1}, Ljava/lang/StringBuilder;-><init>()V

    const-string v0, "OK \u5df2\u66f4\u65b0\u5e76\u6821\u9a8c \u8fdc\u7aef="

    invoke-virtual {p1, v0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object p1

    invoke-virtual {v5}, Ljava/lang/String;->length()I

    move-result v0

    invoke-virtual {p1, v0}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    move-result-object p1

    invoke-virtual {p1}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object p1

    goto :goto_fc

    .line 110
    :cond_d7
    new-instance v0, Ljava/lang/StringBuilder;

    invoke-direct {v0}, Ljava/lang/StringBuilder;-><init>()V

    const-string v2, "ERR \u5199\u5165\u672a\u751f\u6548 \u8bfb\u56de="

    invoke-virtual {v0, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v0

    invoke-virtual {p1}, Ljava/lang/String;->length()I

    move-result p1

    invoke-virtual {v0, p1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    move-result-object p1

    const-string v0, " \u5e94\u4e3a="

    invoke-virtual {p1, v0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object p1

    invoke-virtual {v5}, Ljava/lang/String;->length()I

    move-result v0

    invoke-virtual {p1, v0}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    move-result-object p1

    invoke-virtual {p1}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object p1

    .line 112
    :goto_fc
    goto :goto_115

    :cond_fd
    if-lez v7, :cond_113

    .line 113
    new-instance p1, Ljava/lang/StringBuilder;

    invoke-direct {p1}, Ljava/lang/StringBuilder;-><init>()V

    const-string v0, "\u5df2\u662f\u6700\u65b0 \u8fdc\u7aef="

    invoke-virtual {p1, v0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object p1

    invoke-virtual {p1, v7}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    move-result-object p1

    invoke-virtual {p1}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object p1

    goto :goto_115

    .line 115
    :cond_113
    const-string p1, "\u6ca1\u62ff\u5230\u53ef\u7528\u7684\u672c\u5730\u7ebf\u8def\u5305\u6a21\u677f"
    :try_end_115
    .catchall {:try_start_6 .. :try_end_115} :catchall_116

    .line 119
    :goto_115
    goto :goto_132

    .line 117
    :catchall_116
    move-exception p1

    .line 118
    new-instance v0, Ljava/lang/StringBuilder;

    invoke-direct {v0}, Ljava/lang/StringBuilder;-><init>()V

    const-string v2, "ERR \u5185\u90e8\u5f02\u5e38 "

    invoke-virtual {v0, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v0

    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    move-result-object p1

    invoke-virtual {p1}, Ljava/lang/Class;->getSimpleName()Ljava/lang/String;

    move-result-object p1

    invoke-virtual {v0, p1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object p1

    invoke-virtual {p1}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object p1

    .line 121
    :goto_132
    invoke-static {v1, p1}, Lcom/github/catvod/spider/QfUpdate;->write(Ljava/lang/String;Ljava/lang/String;)V

    .line 122
    const-string v0, "/storage/emulated/0/Download/qf_result.txt"

    invoke-static {v0, p1}, Lcom/github/catvod/spider/QfUpdate;->write(Ljava/lang/String;Ljava/lang/String;)V

    .line 123
    sput-object p1, Lcom/github/catvod/spider/QfToast;->a:Ljava/lang/String;

    .line 125
    :try_start_13c
    new-instance v0, Landroid/os/Handler;

    invoke-static {}, Landroid/os/Looper;->getMainLooper()Landroid/os/Looper;

    move-result-object v1

    invoke-direct {v0, v1}, Landroid/os/Handler;-><init>(Landroid/os/Looper;)V

    new-instance v1, Lcom/github/catvod/spider/QfToast;

    invoke-direct {v1}, Lcom/github/catvod/spider/QfToast;-><init>()V

    invoke-virtual {v0, v1}, Landroid/os/Handler;->post(Ljava/lang/Runnable;)Z
    :try_end_14d
    .catchall {:try_start_13c .. :try_end_14d} :catchall_14e

    .line 127
    goto :goto_14f

    .line 126
    :catchall_14e
    move-exception v0

    .line 129
    :goto_14f
    nop

    .line 130
    nop

    .line 131
    nop

    .line 132
    new-instance v0, Ljava/lang/StringBuilder;

    invoke-direct {v0}, Ljava/lang/StringBuilder;-><init>()V

    const-string v1, "{\"class\":[{\"type_id\":\"upd\",\"type_name\":\""

    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v0

    invoke-virtual {v0, p1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v0

    const-string v1, "\"}],\"list\":[{\"vod_id\":\"0\",\"vod_name\":\"[v47] "

    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v0

    invoke-virtual {v0, p1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object p1

    const-string v0, "\",\"vod_pic\":\"\",\"vod_remarks\":\"\"}],\"filters\":[]}"

    invoke-virtual {p1, v0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object p1

    invoke-virtual {p1}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object p1

    return-object p1
.end method
