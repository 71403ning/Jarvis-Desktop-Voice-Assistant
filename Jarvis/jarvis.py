"""Jarvis 桌面語音助理。

可在 macOS、Windows、Linux 上執行。不屬於內建指令的問題，會交給本機 Ollama
(https://ollama.com) 上的大型語言模型回答，不需要任何 API 金鑰。

設定（環境變數）：
    JARVIS_LANG        語音辨識與發音的語言，例如 "zh-TW" 或 "en-US"（預設 en-US）
    JARVIS_MODEL       Ollama 模型名稱（預設 breeze；見 scripts/pull_tw_models.sh）
    JARVIS_OLLAMA_URL  Ollama 伺服器網址（預設 http://localhost:11434）
    JARVIS_DATA_DIR    設定檔存放位置（預設 ~/.jarvis）
    JARVIS_ALLOW_POWER 設為 1 才允許用語音關機/重開機（預設關閉）
    JARVIS_MUTE        設為 1 時只印出回覆、不發出聲音

加上 --text 參數可改用鍵盤輸入，不需要麥克風（透過 SSH 使用時很方便）。
"""
import datetime
import json
import os
import platform
import random
import re
import subprocess
import sys
import urllib.error
import urllib.request
import webbrowser as wb
from pathlib import Path

SYSTEM = platform.system()  # "Darwin"（macOS）、"Windows" 或 "Linux"
LANG = os.environ.get("JARVIS_LANG", "en-US")
IS_ZH = LANG.lower().startswith("zh")
OLLAMA_URL = os.environ.get("JARVIS_OLLAMA_URL", "http://localhost:11434").rstrip("/")
DATA_DIR = Path(os.environ.get("JARVIS_DATA_DIR", Path.home() / ".jarvis"))
ALLOW_POWER = os.environ.get("JARVIS_ALLOW_POWER") == "1"
DEFAULT_MODEL = "breeze"

# 口說名稱 -> Ollama 模型名稱。短名稱由 scripts/pull_tw_models.sh 建立；
# 其他已安裝的 Ollama 模型也可以直接使用。
MODEL_ALIASES = {
    "taide": "taide", "台德": "taide", "泰德": "taide",
    "breeze": "breeze", "微風": "breeze", "布利茲": "breeze",
    "bailong": "bailong", "百龍": "bailong", "白龍": "bailong",
    "qwen": "qwen2.5:7b", "通義": "qwen2.5:7b",
}
MUTE = os.environ.get("JARVIS_MUTE") == "1"
AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".aiff"}

MESSAGES = {
    "welcome": ("Welcome back, sir!", "歡迎回來！"),
    "morning": ("Good morning!", "早安！"),
    "afternoon": ("Good afternoon!", "午安！"),
    "evening": ("Good evening!", "晚安！"),
    "night": ("It's late, remember to rest.", "很晚了，記得休息。"),
    "service": ("{name} at your service. How may I assist you?", "{name} 為您服務，請問需要什麼幫忙？"),
    "time": ("The current time is {t}", "現在時間 {t}"),
    "date": ("Today is {d}", "今天是 {d}"),
    "not_understood": ("Sorry, I did not understand that.", "抱歉，我沒聽清楚。"),
    "stt_down": ("Speech recognition service is unavailable.", "語音辨識服務無法連線。"),
    "wiki_search": ("Searching Wikipedia...", "正在搜尋維基百科…"),
    "wiki_multi": ("Multiple results found. Please be more specific.", "找到多個結果，請說得更具體一點。"),
    "wiki_none": ("I couldn't find anything on Wikipedia.", "維基百科上找不到相關資料。"),
    "playing": ("Playing {song}.", "正在播放 {song}。"),
    "no_song": ("No song found.", "找不到歌曲。"),
    "ask_name": ("What would you like to name me?", "你想幫我取什麼名字？"),
    "named": ("Alright, I will be called {name} from now on.", "好的，從現在起我叫 {name}。"),
    "no_name": ("Sorry, I couldn't catch that.", "抱歉，我沒聽清楚。"),
    "screenshot": ("Screenshot saved as {path}.", "截圖已存到 {path}。"),
    "screenshot_fail": ("I couldn't take a screenshot: {err}", "截圖失敗：{err}"),
    "power_off": ("Voice power control is disabled.", "語音關機功能目前停用。"),
    "confirm": ("Are you sure? Say yes to confirm.", "確定嗎？請說「確定」。"),
    "cancelled": ("Cancelled.", "已取消。"),
    "shutdown": ("Shutting down the system, goodbye!", "正在關機，再見！"),
    "restart": ("Restarting the system, please wait!", "正在重新開機，請稍候！"),
    "bye": ("Going offline. Have a good day!", "離線了，祝你有美好的一天！"),
    "no_llm": ("Sorry, I can't do that yet.", "抱歉，這個我還不會。"),
    "opening": ("Opening {site}.", "正在開啟 {site}。"),
    "model_now": ("I'm using {model}. Options: taide, breeze, bailong.", "目前使用 {model}，可選 TAIDE、Breeze、百龍。"),
    "model_set": ("Switched to {model}.", "已切換到 {model}。"),
    "model_missing": ("{model} is not installed. Run scripts/pull_tw_models.sh first.",
                      "{model} 還沒下載，請先執行 scripts/pull_tw_models.sh。"),
}

# (動作, 關鍵字)。順序有意義：第一個符合的動作優先，所以帶參數的指令
# （例如維基百科）要排在 "time" 這類短關鍵字之前。
COMMANDS = [
    ("model", ["switch model", "change model", "use model", "which model",
               "切換模型", "換模型", "模型換成", "用什麼模型", "哪個模型", "目前模型"]),
    ("wikipedia", ["wikipedia", "維基百科", "維基"]),
    ("music", ["play music", "播放音樂", "放音樂", "放歌"]),
    ("youtube", ["open youtube", "打開youtube", "開啟youtube"]),
    ("google", ["open google", "打開google", "開啟google"]),
    ("rename", ["change your name", "改名", "換名字"]),
    ("screenshot", ["screenshot", "screen shot", "截圖"]),
    ("joke", ["tell me a joke", "joke", "笑話"]),
    ("shutdown", ["shutdown", "shut down", "關機"]),
    ("restart", ["restart", "reboot", "重新開機", "重開機"]),
    ("exit", ["exit", "offline", "goodbye", "離線", "再見", "結束"]),
    ("time", ["time", "幾點", "時間"]),
    ("date", ["date", "日期", "幾號", "星期幾"]),
]
YES_WORDS = ["yes", "confirm", "確定", "是", "對"]
NO_WORDS = ["no", "not", "cancel", "不", "取消", "別"]


def msg(key: str, **kwargs) -> str:
    text = MESSAGES[key][1 if IS_ZH else 0]
    return text.format(**kwargs)


def normalize(text: str) -> str:
    return text.lower().strip()


def _matches(keyword: str, query: str) -> bool:
    if keyword.isascii():
        return re.search(rf"\b{re.escape(keyword)}\b", query) is not None
    # 中文語音辨識結果可能有空格也可能沒有，所以比對前先去掉空格。
    return keyword in query.replace(" ", "")


def route(query: str):
    """回傳查詢對應的動作名稱；沒有符合的指令則回傳 None。"""
    query = normalize(query)
    for action, keywords in COMMANDS:
        if any(_matches(k, query) for k in keywords):
            return action
    return None


def strip_keywords(query: str, action: str) -> str:
    """從查詢中移除該動作的關鍵字，留下參數（例如歌名、搜尋詞）。"""
    query = normalize(query)
    for action_name, keywords in COMMANDS:
        if action_name != action:
            continue
        for k in sorted(keywords, key=len, reverse=True):
            if k.isascii():
                query = re.sub(rf"\b{re.escape(k)}\b", " ", query)
            else:
                query = query.replace(k, " ")
    return " ".join(query.split())


# ---------------------------------------------------------------- 語音輸出
_engine = None


def _voice_languages(voice):
    langs = []
    for lang in getattr(voice, "languages", None) or []:
        if isinstance(lang, bytes):
            lang = lang.decode("utf-8", "ignore")
        lang = "".join(ch for ch in str(lang) if ch.isprintable())
        langs.append(lang.lower().replace("-", "_"))
    return langs


def pick_voice(voices, lang: str):
    """挑選最符合語言標籤（例如 "zh-TW"）的系統語音。"""
    wanted = lang.lower().replace("-", "_")
    prefix = wanted.split("_")[0]
    for v in voices:
        if wanted in _voice_languages(v):
            return v
    for v in voices:
        if any(l.split("_")[0] == prefix for l in _voice_languages(v)):
            return v
    return None


def get_engine():
    global _engine
    if _engine is None:
        import pyttsx3

        _engine = pyttsx3.init()
        voice = pick_voice(_engine.getProperty("voices"), LANG)
        if voice is not None:
            _engine.setProperty("voice", voice.id)
        _engine.setProperty("rate", 175)
        _engine.setProperty("volume", 1.0)
    return _engine


def speak(text: str) -> None:
    print(f"Jarvis: {text}")
    if MUTE:
        return
    try:
        engine = get_engine()
        engine.say(text)
        engine.runAndWait()
    except Exception as e:  # 音訊出問題時不能讓助理整個當掉
        print(f"(speech output failed: {e})")


# ----------------------------------------------------------------- 語音輸入
def takecommand(text_mode: bool = False):
    """回傳使用者說的內容（轉小寫）；沒有內容時回傳 None。"""
    if text_mode:
        try:
            line = input("You: ")
        except EOFError:
            return "exit"
        return normalize(line) or None

    import speech_recognition as sr

    r = sr.Recognizer()
    r.pause_threshold = 1
    with sr.Microphone() as source:
        print("Listening...")
        try:
            audio = r.listen(source, timeout=5, phrase_time_limit=15)
        except sr.WaitTimeoutError:
            return None  # 沒人說話是正常的，安靜地繼續聽

    try:
        print("Recognizing...")
        query = r.recognize_google(audio, language=LANG)
        print(f"You: {query}")
        return normalize(query)
    except sr.UnknownValueError:
        speak(msg("not_understood"))
    except sr.RequestError:
        speak(msg("stt_down"))
    return None


# ------------------------------------------------------------------- 功能
def tell_time() -> None:
    speak(msg("time", t=datetime.datetime.now().strftime("%H:%M")))


def tell_date() -> None:
    now = datetime.datetime.now()
    if IS_ZH:
        weekday = "一二三四五六日"[now.weekday()]
        d = f"{now.year}年{now.month}月{now.day}日 星期{weekday}"
    else:
        d = now.strftime("%A, %d %B %Y")
    speak(msg("date", d=d))


def load_name() -> str:
    try:
        return (DATA_DIR / "assistant_name.txt").read_text(encoding="utf-8").strip() or "Jarvis"
    except FileNotFoundError:
        return "Jarvis"


def save_name(name: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "assistant_name.txt").write_text(name, encoding="utf-8")


def wishme() -> None:
    speak(msg("welcome"))
    hour = datetime.datetime.now().hour
    if 4 <= hour < 12:
        speak(msg("morning"))
    elif 12 <= hour < 18:
        speak(msg("afternoon"))
    elif 18 <= hour < 24:
        speak(msg("evening"))
    else:
        speak(msg("night"))
    speak(msg("service", name=load_name()))


def open_path(path: Path) -> None:
    if SYSTEM == "Windows":
        os.startfile(path)  # type: ignore[attr-defined]
    elif SYSTEM == "Darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def screenshot() -> None:
    folder = Path.home() / "Pictures"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"jarvis-{datetime.datetime.now():%Y%m%d-%H%M%S}.png"
    try:
        import pyautogui

        pyautogui.screenshot().save(path)
        speak(msg("screenshot", path=path))
    except Exception as e:
        speak(msg("screenshot_fail", err=e))


def find_songs(music_dir: Path, name: str = "", limit: int = 5000):
    songs = []
    if not music_dir.is_dir():
        return songs
    for root, _dirs, files in os.walk(music_dir):
        for f in files:
            if Path(f).suffix.lower() in AUDIO_EXTS and name.lower() in f.lower():
                songs.append(Path(root) / f)
                if len(songs) >= limit:
                    return songs
    return songs


def play_music(song_name: str = "") -> None:
    songs = find_songs(Path.home() / "Music", song_name)
    if songs:
        song = random.choice(songs)
        open_path(song)
        speak(msg("playing", song=song.stem))
    else:
        speak(msg("no_song"))


def search_wikipedia(query: str) -> None:
    import wikipedia

    wikipedia.set_lang("zh" if IS_ZH else "en")
    try:
        speak(msg("wiki_search"))
        speak(wikipedia.summary(query, sentences=2))
    except wikipedia.exceptions.DisambiguationError:
        speak(msg("wiki_multi"))
    except Exception:
        speak(msg("wiki_none"))


def current_model() -> str:
    env = os.environ.get("JARVIS_MODEL")
    if env:
        return env
    try:
        return (DATA_DIR / "model.txt").read_text(encoding="utf-8").strip() or DEFAULT_MODEL
    except FileNotFoundError:
        return DEFAULT_MODEL


def find_model_alias(query: str):
    compact = normalize(query).replace(" ", "")
    for spoken, model in MODEL_ALIASES.items():
        if spoken in compact:
            return model
    return None


def _ollama(path: str, payload=None, timeout: float = 10):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(f"{OLLAMA_URL}{path}", data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def installed_models():
    """已安裝的 Ollama 模型名稱（含與不含 ':latest' 兩種寫法）；Ollama 沒在執行時回傳 None。"""
    try:
        names = [m["name"] for m in _ollama("/api/tags").get("models", [])]
    except (urllib.error.URLError, OSError, KeyError, ValueError):
        return None
    return set(names) | {n.removesuffix(":latest") for n in names}


def switch_model(query: str) -> None:
    """依名稱切換模型，並釋放舊模型佔用的記憶體（16GB 的 Mac 一次只適合載入一個）。"""
    old = current_model()
    new = find_model_alias(query)
    if new is None:
        speak(msg("model_now", model=old))
        return
    installed = installed_models()
    if installed is not None and new not in installed:
        speak(msg("model_missing", model=new))
        return
    if os.environ.get("JARVIS_MODEL"):
        os.environ["JARVIS_MODEL"] = new  # 只影響這次執行；環境變數的優先順序高於存檔的選擇
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "model.txt").write_text(new, encoding="utf-8")
    if old != new:
        try:  # keep_alive 設為 0 會立即卸載上一個模型
            _ollama("/api/generate", {"model": old, "keep_alive": 0})
        except (urllib.error.URLError, OSError, ValueError):
            pass
    speak(msg("model_set", model=new))


def ask_llm(question: str, history: list, timeout: float = 120):
    """詢問本機 Ollama 模型。回傳答案；無法連線時回傳 None。"""
    system = (
        "You are Jarvis, a concise voice assistant running on the user's Mac mini. "
        "Answer in 1-3 short spoken sentences, without markdown or lists. "
        + ("Always reply in Traditional Chinese (Taiwan)." if IS_ZH else "Reply in the user's language.")
    )
    messages = [{"role": "system", "content": system}] + history[-6:]
    messages.append({"role": "user", "content": question})
    # think=False：讓具有推理模式的模型（qwen3、gemma-3 衍生模型等）直接回答，
    # 語音回覆才夠快；沒有推理模式的模型會忽略這個參數。
    body = json.dumps(
        {"model": current_model(), "messages": messages, "stream": False, "think": False}
    ).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat", data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            answer = json.load(resp)["message"]["content"].strip()
    except (urllib.error.URLError, OSError, KeyError, ValueError) as e:
        print(f"(LLM unavailable: {e})")
        return None
    history += [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]
    return answer


def tell_joke(history: list) -> None:
    if IS_ZH:
        joke = ask_llm("講一個簡短、適合大家的笑話。", history)
        if joke:
            speak(joke)
            return
    import pyjokes

    speak(pyjokes.get_joke())


def power(action: str, text_mode: bool) -> bool:
    """經使用者確認後關機或重開機。有執行時回傳 True。"""
    if not ALLOW_POWER:
        speak(msg("power_off"))
        return False
    speak(msg("confirm"))
    answer = takecommand(text_mode) or ""
    said_no = any(_matches(w, answer) for w in NO_WORDS)
    if said_no or not any(_matches(w, answer) for w in YES_WORDS):
        speak(msg("cancelled"))
        return False
    speak(msg(action))
    if SYSTEM == "Windows":
        os.system("shutdown /s /t 1" if action == "shutdown" else "shutdown /r /t 1")
    elif SYSTEM == "Darwin":
        verb = "shut down" if action == "shutdown" else "restart"
        subprocess.run(["osascript", "-e", f'tell application "System Events" to {verb}'])
    else:
        subprocess.run(["systemctl", "poweroff" if action == "shutdown" else "reboot"])
    return True


def handle(query: str, history: list, text_mode: bool = False) -> bool:
    """執行一個指令。助理應該結束時回傳 False。"""
    action = route(query)
    if action == "model":
        switch_model(query)
    elif action == "time":
        tell_time()
    elif action == "date":
        tell_date()
    elif action == "wikipedia":
        search_wikipedia(strip_keywords(query, "wikipedia"))
    elif action == "music":
        play_music(strip_keywords(query, "music"))
    elif action == "youtube":
        speak(msg("opening", site="YouTube"))
        wb.open("https://www.youtube.com")
    elif action == "google":
        speak(msg("opening", site="Google"))
        wb.open("https://www.google.com")
    elif action == "rename":
        speak(msg("ask_name"))
        name = takecommand(text_mode)
        if name:
            save_name(name)
            speak(msg("named", name=name))
        else:
            speak(msg("no_name"))
    elif action == "screenshot":
        screenshot()
    elif action == "joke":
        tell_joke(history)
    elif action in ("shutdown", "restart"):
        return not power(action, text_mode)
    elif action == "exit":
        speak(msg("bye"))
        return False
    else:
        speak(ask_llm(query, history) or msg("no_llm"))
    return True


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    text_mode = "--text" in argv
    history: list = []
    wishme()
    while True:
        query = takecommand(text_mode)
        if query and not handle(query, history, text_mode):
            break


if __name__ == "__main__":
    main()
