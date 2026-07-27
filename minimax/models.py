"""Minimax 系统音色参考字典与常量。

运行时应以 /v1/get_voice 接口返回为准，本文件仅用于 UI 展示与默认值。
"""

# 中文系统音色（name, voice_id）
SYSTEM_VOICES_ZH = [
    ("青涩青年", "male-qn-qingse"),
    ("精英青年", "male-qn-jingying"),
    ("霸道青年", "male-qn-badao"),
    ("青年大学生", "male-qn-daxuesheng"),
    ("少女", "female-shaonv"),
    ("御姐", "female-yujie"),
    ("成熟女性", "female-chengshu"),
    ("甜美女性", "female-tianmei"),
    ("男性主持人", "presenter_male"),
    ("女性主持人", "presenter_female"),
    ("男性有声书1", "audiobook_male_1"),
    ("男性有声书2", "audiobook_male_2"),
    ("女性有声书1", "audiobook_female_1"),
    ("女性有声书2", "audiobook_female_2"),
    # Beta 版
    ("青涩青年-beta", "male-qn-qingse-jingpin"),
    ("精英青年-beta", "male-qn-jingying-jingpin"),
    ("霸道青年-beta", "male-qn-badao-jingpin"),
    ("青年大学生-beta", "male-qn-daxuesheng-jingpin"),
    ("少女-beta", "female-shaonv-jingpin"),
    ("御姐-beta", "female-yujie-jingpin"),
    ("成熟女性-beta", "female-chengshu-jingpin"),
    ("甜美女性-beta", "female-tianmei-jingpin"),
    # 特色角色
    ("聪明男童", "clever_boy"),
    ("可爱男童", "cute_boy"),
    ("萌萌女童", "lovely_girl"),
    ("卡通猪小琪", "cartoon_pig"),
    ("病娇弟弟", "bingjiao_didi"),
    ("俊朗男友", "junlang_nanyou"),
    ("纯真学弟", "chunzhen_xuedi"),
    ("冷淡学长", "lengdan_xiongzhang"),
    ("霸道少爷", "badao_shaoye"),
    ("甜心小玲", "tianxin_xiaoling"),
    ("俏皮萌妹", "qiaopi_mengmei"),
    ("妩媚御姐", "wumei_yujie"),
    ("嗲嗲学妹", "diadia_xuemei"),
    ("淡雅学姐", "danya_xuejie"),
]

# 英文系统音色
SYSTEM_VOICES_EN = [
    ("Santa Claus", "Santa_Claus"),
    ("Grinch", "Grinch"),
    ("Rudolph", "Rudolph"),
    ("Arnold", "Arnold"),
    ("Charming Santa", "Charming_Santa"),
    ("Charming Lady", "Charming_Lady"),
    ("Sweet Girl", "Sweet_Girl"),
    ("Cute Elf", "Cute_Elf"),
    ("Attractive Girl", "Attractive_Girl"),
    ("Serene Woman", "Serene_Woman"),
]

ALL_SYSTEM_VOICES = SYSTEM_VOICES_ZH + SYSTEM_VOICES_EN

# speech-2.8 系列支持的语气词标签（可内嵌于 text 中）
INTERJECTION_TAGS = [
    "(laughs)", "(chuckle)", "(coughs)", "(clear-throat)", "(groans)",
    "(breath)", "(pant)", "(inhale)", "(exhale)", "(gasps)", "(sniffs)",
    "(sighs)", "(snorts)", "(burps)", "(lip-smacking)", "(humming)",
    "(hissing)", "(emm)", "(whistles)", "(sneezes)", "(crying)", "(applause)",
]

# 可选模型
SUPPORTED_MODELS = [
    ("speech-2.8-hd (最新HD，支持语气词)", "speech-2.8-hd"),
    ("speech-2.8-turbo (最新Turbo，速度快)", "speech-2.8-turbo"),
    ("speech-2.6-hd (HD韵律好)", "speech-2.6-hd"),
    ("speech-2.6-turbo (40语种)", "speech-2.6-turbo"),
    ("speech-02-hd (稳定)", "speech-02-hd"),
    ("speech-02-turbo (小语种强)", "speech-02-turbo"),
]

# 情绪可选值
EMOTION_OPTIONS = ["", "happy", "sad", "angry", "fearful", "disgusted", "surprised", "calm"]

# 语言增强可选值（部分常用）
LANGUAGE_BOOST_OPTIONS = [
    "auto", "Chinese", "Chinese,Yue", "English", "Japanese", "Korean",
    "French", "German", "Spanish", "Russian", "Arabic", "Portuguese",
    "Italian", "Thai", "Vietnamese", "Indonesian", "Hindi", "",
]

# 音效可选值
SOUND_EFFECTS_OPTIONS = [
    "", "spacious_echo", "auditorium_echo", "lofi_telephone", "robotic",
]

# 采样率可选值
SAMPLE_RATE_OPTIONS = [8000, 16000, 22050, 24000, 32000, 44100]

# 比特率可选值
BITRATE_OPTIONS = [32000, 64000, 128000, 256000]

# 音频格式可选值
AUDIO_FORMAT_OPTIONS = ["mp3", "wav", "flac", "pcm"]
