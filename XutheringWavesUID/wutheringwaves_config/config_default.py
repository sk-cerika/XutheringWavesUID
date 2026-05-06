from typing import Dict

from gsuid_core.utils.plugins_config.models import (
    GSC,
    GsIntConfig,
    GsStrConfig,
    GsBoolConfig,
    GsListStrConfig,
)

CONFIG_DEFAULT: Dict[str, GSC] = {
    "WavesAnnOpen": GsBoolConfig(
        "公告推送总开关",
        "公告推送总开关",
        True,
    ),
    "WavesAnnBBSSub": GsListStrConfig(
        "库洛BBS订阅博主",
        "库洛BBS订阅博主",
        [],
    ),
    "WavesRankUseTokenGroup": GsListStrConfig(
        "有token才能进排行，群管理可设置",
        "有token才能进排行，群管理可设置",
        [],
    ),
    "WavesRankNoLimitGroup": GsListStrConfig(
        "无限制进排行，群管理可设置",
        "无限制进排行，群管理可设置",
        [],
    ),
    "WavesGuide": GsListStrConfig(
        "角色攻略图提供方",
        "使用ww角色攻略时选择的提供方",
        ["all"],
        options=[
            "all",
            "小羊早睡不遭罪",
            "金铃子攻略组",
            "丸子",
            "Moealkyne",
            "小沐XMu",
            "吃我无痕",
            "巡游天国FM",
            "社区攻略",
        ],
    ),
    "WavesGuideMaxSize": GsIntConfig(
        "攻略图片最大大小(M)",
        "发送攻略图片前会自动转为jpg格式，若超过此大小则自动压缩，单位MB",
        2,
        50,
    ),
    "WavesLoginUrl": GsStrConfig(
        "鸣潮登录url",
        "用于设置XutheringWavesUID登录界面的配置",
        "",
    ),
    "WavesLoginUrlSelf": GsBoolConfig(
        "强制【鸣潮登录url】为自己的域名",
        "外置登录服务请关闭；自己穿透或 VPS 反代请打开",
        False,
    ),
    "WavesTencentWord": GsBoolConfig(
        "腾讯文档",
        "腾讯文档",
        False,
    ),
    "WavesQRLogin": GsBoolConfig(
        "开启后，登录链接变成二维码",
        "开启后，登录链接变成二维码",
        False,
    ),
    "WavesLoginForward": GsBoolConfig(
        "开启后，登录链接变为转发消息",
        "开启后，登录链接变为转发消息",
        False,
    ),
    "WavesOnlySelfCk": GsBoolConfig(
        "所有查询使用自己的ck",
        "所有查询使用自己的ck",
        False,
    ),
    "QQPicCache": GsBoolConfig(
        "排行榜qq头像缓存开关",
        "排行榜qq头像缓存开关",
        False,
    ),
    "RankUseToken": GsBoolConfig(
        "有token才能进排行",
        "有token才能进排行",
        True,
    ),
    "GachaRankMin": GsIntConfig(
        "抽卡排行最小抽数阈值", "抽卡排行中只显示总抽数达到此阈值的玩家", 1000
    ),
    "DelInvalidCookie": GsBoolConfig(
        "每天定时删除无效token",
        "每天定时删除无效token",
        False,
    ),
    "ResourceDownloadTime": GsListStrConfig(
        "自动资源更新时间设置 重启生效",
        "每天自动下载全部资源时间设置（时，分），将在该时间点后一小时内随机时间下载资源，注意可能伴随重启，请避开自动签到",
        ["22", "0"],
    ),
    "AnnMinuteCheck": GsIntConfig(
        "公告推送时间检测（单位min）", "公告推送时间检测（单位min）", 10, 60
    ),
    "RefreshInterval": GsIntConfig(
        "刷新全部面板间隔，重启生效（单位秒）",
        "刷新全部面板间隔，重启生效（单位秒）",
        0,
        600,
    ),
    "RefreshSingleCharInterval": GsIntConfig(
        "刷新单角色面板间隔，重启生效（单位秒）",
        "刷新单角色面板间隔，重启生效（单位秒）",
        0,
        600,
    ),
    "RefreshIntervalNotify": GsStrConfig(
        "刷新全部面板间隔通知文案",
        "刷新全部面板间隔通知文案",
        "请等待{}s后尝试刷新面板！",
    ),
    "RefreshSingleCharIntervalNotify": GsStrConfig(
        "刷新单角色面板间隔通知文案",
        "刷新单角色面板间隔通知文案",
        "请等待{}s后尝试刷新角色面板！",
    ),
    "HideUid": GsBoolConfig(
        "隐藏uid",
        "开启后，所有渲染卡片中显示的UID将以 前2位 + **** + 后2位 的形式显示",
        False,
    ),
    "RoleListQuery": GsBoolConfig(
        "是否可以使用uid直接查询练度",
        "是否可以使用uid直接查询练度",
        True,
    ),
    "MaxBindNum": GsIntConfig(
        "绑定特征码限制数量（未登录）", "绑定特征码限制数量（未登录）", 2, 100
    ),
    "WavesToken": GsStrConfig(
        "鸣潮全排行token",
        "鸣潮全排行token",
        "",
    ),
    "AtCheck": GsBoolConfig(
        "开启可以艾特查询",
        "开启可以艾特查询",
        True,
    ),
    "CharCardNum": GsIntConfig(
        "面板图列表一条中图片数量",
        "面板图列表一条中图片数量",
        5,
        30,
    ),
    "KuroUrlProxyUrl": GsStrConfig(
        "库洛域名代理（重启生效）",
        "库洛域名代理（重启生效）",
        "",
    ),
    "LocalProxyUrl": GsStrConfig(
        "本地代理地址",
        "本地代理地址",
        "",
    ),
    "NeedProxyFunc": GsListStrConfig(
        "需要代理的函数",
        "需要代理的函数",
        ["get_role_detail_info"],
        options=[
            "all",
            "get_role_detail_info",
        ],
    ),
    "RefreshCardConcurrency": GsIntConfig(
        "刷新角色面板并发数",
        "刷新角色面板并发数",
        10,
        50,
    ),
    "UseGlobalSemaphore": GsBoolConfig(
        "开启后刷新角色面板并发数为全局共享",
        "开启后刷新角色面板并发数为全局共享",
        False,
    ),
    "CaptchaProvider": GsStrConfig(
        "验证码提供方（重启生效）",
        "验证码提供方（重启生效）",
        "",
        options=["ttorc"],
    ),
    "CaptchaAppKey": GsStrConfig(
        "验证码提供方appkey",
        "验证码提供方appkey",
        "",
    ),
    "CacheEverything": GsBoolConfig(
        "启用数据缓存",
        "启用后，所有API数据（基础信息、角色信息、深渊等）都会被缓存到本地用于网络故障时兜底，每1000用户大约额外占用1GB空间。禁用则每次都从API获取最新数据，但如掉登录等由于实际请求成功，不会生效",
        False,
    ),
    "RefreshSingleCharBehavior": GsStrConfig(
        "刷新单角色面板逻辑",
        "控制刷新单个角色面板后的行为：refresh_only(仅刷新)、refresh_and_send(刷新并合并发送)、refresh_and_send_separately(刷新并分别发送)、concatenate(拼接为一张图发送)",
        "concatenate",
        options=[
            "refresh_only",
            "refresh_and_send",
            "refresh_and_send_separately",
            "concatenate",
        ],
    ),
    "WavesUploadAudit": GsBoolConfig(
        "上传面板图允许审核（需订阅联系主人，建议配合白名单）",
        "开启后, 无权限的用户使用上传面板图指令时, 若附带了图片, 会通过【联系主人】订阅转发给主人, 由主人审核后用上传指令落地",
        False,
    ),
    "AutoSendCharAfterRefresh": GsBoolConfig(
        "刷新面板时自动发送角色面板",
        "全量刷新面板后，自动猜测用户可能想查看的角色面板",
        True,
    ),
    "HelpExtraModules": GsListStrConfig(
        "帮助显示额外模块（重启生效）",
        "在帮助中额外显示的模块：roversign(签到)、todayecho(梭哈)、scoreecho(评分)、roverreminder(体力推送)，需自行安装对应插件",
        [],
        ["roversign", "todayecho", "scoreecho", "roverreminder", "all"],
    ),
    "ActiveUserDays": GsIntConfig(
        "活跃账号认定天数",
        "在此天数内有使用记录的账号被认定为活跃账号",
        42,
        10000,
    ),
    "CacheDaysToKeep": GsIntConfig(
        "保留缓存公告、日历资源天数",
        "自动删除创建时间早于此天数的公告和日历图片缓存，每次启动和每天定时执行",
        45,
        3650,
    ),
    "RankActiveFilterGroup": GsBoolConfig(
        "群排行仅活跃用户",
        "群排行（角色/练度/抽卡）是否仅统计活跃账号",
        True,
    ),
    "UseHtmlRender": GsBoolConfig(
        "使用HTML渲染",
        "开启后将使用HTML渲染公告卡片，关闭后将回退到PIL或纯文本",
        True,
    ),
    "RemoteRenderEnable": GsBoolConfig(
        "外置渲染开关",
        "开启后将使用外置渲染服务进行HTML渲染，失败时自动回退到本地渲染",
        False,
    ),
    "RemoteRenderUrl": GsStrConfig(
        "外置渲染地址",
        "外置渲染服务的API地址，例如：http://127.0.0.1:3000/render",
        "http://127.0.0.1:3000/render",
    ),
    "BotColorMap": GsStrConfig(
        "排行榜Bot名称固定颜色",
        "格式: 名称-(R,G,B)，颜色为RGB值(0-255)，多个用逗号分隔，如: 小维-(234,183,4),千咲-(0,128,255)",
        "",
    ),
    "EnableLocalization": GsBoolConfig(
        "启用多语言本地化",
        "启用后将加载多语言翻译字典到内存，用户可通过【设置语言】切换界面语言。关闭后不加载字典，节省内存",
        False,
    ),
    "FontCssUrl": GsStrConfig(
        "外置渲染字体CSS地址",
        "用于HTML渲染的字体CSS URL，外置渲染时传递，一般保留默认即可，如果在本地，可以填http://127.0.0.1:8765/waves/fonts/fonts.css，如果有自己的登录域名：可以使用 你的登录域名根/waves/fonts/fonts.css",
        "https://fonts.loli.net/css2?family=JetBrains+Mono:wght@500;700&family=Oswald:wght@500;700&family=Noto+Sans+SC:wght@400;700&family=Noto+Sans+JP:wght@400;700&family=Noto+Sans+KR:wght@400;700&family=Noto+Color+Emoji&display=swap",
    ),
    "WavesPanelEditPassword": GsStrConfig(
        "面板图编辑面板密码",
        "为空则关闭网页面板图/背景图编辑工具；设置后通过 HTTP Basic Auth 鉴权（用户名固定 admin），地址 /waves/panel-edit/",
        "",
    ),
    "WavesPanelEditGuestView": GsBoolConfig(
        "面板图编辑访客只读浏览",
        "开启后，未登录用户可浏览图片列表（不渲染预览，不占用服务器资源）；上传/裁剪/删除/覆盖仍需密码",
        False,
    ),
    "WavesGachaWebPage": GsBoolConfig(
        "抽卡网页查看功能",
        "开启后，用户可发送【抽卡页面/抽卡网页/网页抽卡记录】打开网页查看抽卡详细记录。外置登录需外置登录部署时支持此功能",
        False,
    ),
    "WavesAtViewGacha": GsBoolConfig(
        "@他人查看抽卡记录",
        "开启后，群聊中可 @ 已登录用户查询其抽卡记录，要求同群且对方已登录（有 cookie）",
        False,
    ),
    "WavesScheduledRefreshTime": GsListStrConfig(
        "定时刷新面板时间（重启生效）",
        "每天定时为所有已登录用户批量刷新角色面板缓存的时间（时, 分）。"
        "任务无条件注册到 GsCore 调度器，不需要时请在调度页暂停 ww_scheduled_refresh_panel",
        ["4", "0"],
    ),
    "WavesAutoRefreshOnView": GsBoolConfig(
        "查角色面板时自动先刷新",
        "开启后，发送【ww<角色名>面板】查询单角色面板时自动先刷新该角色再渲染。"
        "仅对查自己面板生效，伤害/PK/换装/极限/查别人 等场景跳过；尊重 RefreshSingleCharInterval 冷却",
        False,
    ),
}
