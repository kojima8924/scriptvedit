from scriptvedit import *
# narrate: TTS(モック)+字幕の同時生成・タイムライン同期テスト
# setup_test85 側で scriptvedit.tts の tts / tts_duration をモック化してから実行される
n1 = narrate("こんにちは、世界", speaker=3, subtitle_style={"size": 40})
n2 = narrate("二行目のナレーション", speaker=1, subtitle=False)
