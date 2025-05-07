import os
import yaml
import json
import logging
from datetime import datetime
import google.generativeai as genai
from jinja2 import Template
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import re

# --- 設定・ロギング ---
def expand_env_vars(obj):
    if isinstance(obj, dict):
        return {k: expand_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [expand_env_vars(i) for i in obj]
    elif isinstance(obj, str):
        return re.sub(r'\$\{([^}]+)\}', lambda m: os.environ.get(m.group(1), m.group(0)), obj)
    else:
        return obj

def load_settings():
    try:
        settings_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'settings.yml')
        if not os.path.exists(settings_path):
            # サンプル設定ファイルをコピー
            sample_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'settings_sample.yml')
            if os.path.exists(sample_path):
                import shutil
                shutil.copy2(sample_path, settings_path)
                messagebox.showinfo("設定ファイル", "settings.ymlが見つからないため、settings_sample.ymlからコピーしました。")
            else:
                raise FileNotFoundError("settings.ymlとsettings_sample.ymlの両方が見つかりません。")
        
        with open(settings_path, 'r', encoding='utf-8') as f:
            settings = yaml.safe_load(f)
        settings = expand_env_vars(settings)
        return settings
    except Exception as e:
        messagebox.showerror("設定エラー", f"設定ファイルの読み込みに失敗しました: {str(e)}")
        raise

def setup_gemini(settings):
    api_key = os.getenv('GeminiApiKey')
    if not api_key:
        raise ValueError("GeminiApiKey environment variable is not set")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(settings['llm']['providers']['gemini']['model'])
    return model

def prepare_prompt(template_vars, settings):
    system_prompt = settings['llm']['providers']['gemini']['prompt']['system']
    user_template = settings['llm']['providers']['gemini']['prompt']['user_template']
    template_vars = dict(template_vars)
    template_vars['current_year'] = datetime.now().year
    system_template = Template(system_prompt, keep_trailing_newline=True)
    rendered_system = system_template.render(**template_vars)
    template = Template(user_template, keep_trailing_newline=True)
    user_prompt = template.render(**template_vars)
    full_prompt = f"{rendered_system}\n\n{user_prompt}"
    return full_prompt

def call_llm(prompt, settings):
    model = setup_gemini(settings)
    response = model.generate_content(prompt)
    return response

def process_llm_response(response, settings):
    text = response.text.strip()
    try:
        json_start = text.find('{')
        json_end = text.rfind('}') + 1
        if json_start == -1 or json_end == 0:
            raise ValueError("JSON形式のデータが見つかりません")
        json_text = text[json_start:json_end]
        event_data = json.loads(json_text)
        required_fields = ['summary', 'start', 'end']
        for field in required_fields:
            if field not in event_data:
                raise ValueError(f'Missing required field: {field}')
        return event_data
    except json.JSONDecodeError as e:
        raise ValueError(f"レスポンスをJSONとして解析できません: {e}")
    except Exception as e:
        raise

def analyze_text_with_llm(text, instruction, llm_name):
    settings = load_settings()
    # テンプレート変数を準備
    template_vars = {
        'filename': '',
        'filetype': '',
        'creation_time': '',
        'file_content': '',
        'direct_text': text.strip(),
        'additional_instructions': instruction.strip()
    }
    full_prompt = prepare_prompt(template_vars, settings)
    response = call_llm(full_prompt, settings)
    event_data = process_llm_response(response, settings)
    return event_data

def setup_google_calendar(settings):
    creds = None
    # トークンファイルのパスをユーザーのホームディレクトリに変更
    token_file = os.path.join(os.path.expanduser("~"), "calendar_updater_token.json")
    scopes = settings['google_calendar']['scopes']
    if os.path.exists(token_file):
        with open(token_file, 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                settings['google_calendar']['credentials_file'], scopes)
            creds = flow.run_local_server(port=0)
        with open(token_file, 'wb') as token:
            pickle.dump(creds, token)
    service = build('calendar', 'v3', credentials=creds)
    return service

def push_to_google_calendar(event_json):
    settings = load_settings()
    try:
        service = setup_google_calendar(settings)
        calendar_id = settings['google_calendar']['calendars']['default']['id']
        event = service.events().insert(
            calendarId=calendar_id,
            body=event_json
        ).execute()
        return True, event.get('htmlLink', '')
    except Exception as e:
        return False, str(e)

# --- tkinter UI ---
class CalendarUpdaterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Google Calendar Updater")
        self.root.geometry("900x600")
        main_frame = tk.Frame(root)
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)
        left_frame = tk.Frame(main_frame)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        right_frame = tk.Frame(main_frame)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        left_frame.rowconfigure(1, weight=1)
        left_frame.columnconfigure(0, weight=1)
        # 文章入力
        tk.Label(left_frame, text="文章入力").grid(row=0, column=0, sticky="w")
        self.text_input = tk.Text(left_frame)
        self.text_input.grid(row=1, column=0, sticky="nsew", pady=2)
        # ファイル選択
        tk.Label(left_frame, text="ファイル選択").grid(row=2, column=0, sticky="w", pady=(10,0))
        file_frame = tk.Frame(left_frame)
        file_frame.grid(row=3, column=0, sticky="ew")
        self.file_path_var = tk.StringVar()
        tk.Entry(file_frame, textvariable=self.file_path_var, state="readonly").pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(file_frame, text="選択", command=self.select_file).pack(side=tk.LEFT, padx=2)
        # 追加指示
        tk.Label(left_frame, text="追加指示").grid(row=4, column=0, sticky="w", pady=(10,0))
        self.instruction_entry = tk.Entry(left_frame)
        self.instruction_entry.grid(row=5, column=0, sticky="ew", pady=2)
        # 使用LLM
        tk.Label(left_frame, text="使用LLM").grid(row=6, column=0, sticky="w", pady=(10,0))
        self.llm_var = tk.StringVar(value="Gemini")
        self.llm_combo = ttk.Combobox(left_frame, textvariable=self.llm_var, values=["Gemini"], state="readonly")
        self.llm_combo.grid(row=7, column=0, sticky="ew", pady=2)
        tk.Button(left_frame, text="解析", command=self.analyze).grid(row=8, column=0, sticky="ew", pady=(20,0))
        tk.Button(left_frame, text="設定YAML編集", command=self.edit_settings_yml).grid(row=9, column=0, sticky="ew", pady=(5,0))
        tk.Label(right_frame, text="解析結果（JSON, 編集可）").pack(anchor=tk.W)
        self.json_text = tk.Text(right_frame, height=25)
        self.json_text.pack(fill=tk.BOTH, expand=True, pady=2)
        tk.Button(right_frame, text="GoogleカレンダーにPush", command=self.push_event).pack(fill=tk.X, pady=(10,0))

    def select_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if file_path:
            self.file_path_var.set(file_path)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                self.text_input.delete("1.0", tk.END)
                self.text_input.insert(tk.END, content)
            except Exception as e:
                messagebox.showerror("ファイル読み込みエラー", str(e))

    def analyze(self):
        text = self.text_input.get("1.0", tk.END).strip()
        instruction = self.instruction_entry.get().strip()
        llm_name = self.llm_var.get()
        if not text:
            messagebox.showwarning("入力エラー", "文章を入力してください")
            return
        try:
            result = analyze_text_with_llm(text, instruction, llm_name)
            self.json_text.delete("1.0", tk.END)
            self.json_text.insert(tk.END, json.dumps(result, ensure_ascii=False, indent=2))
        except Exception as e:
            messagebox.showerror("解析エラー", str(e))

    def push_event(self):
        try:
            event_json = json.loads(self.json_text.get("1.0", tk.END))
        except Exception as e:
            messagebox.showerror("JSONエラー", f"JSONの形式が正しくありません: {e}")
            return
        ok, url = push_to_google_calendar(event_json)
        if ok:
            messagebox.showinfo("成功", f"Googleカレンダーにイベントを作成しました！\n{url}")
        else:
            messagebox.showerror("エラー", f"Googleカレンダーへの登録に失敗しました\n{url}")

    def edit_settings_yml(self):
        import subprocess
        import platform
        yml_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'settings.yml')
        if not os.path.exists(yml_path):
            messagebox.showerror("エラー", f"settings.ymlが見つかりません: {yml_path}")
            return
        try:
            settings = load_settings()
            editor_cmd = settings.get('app', {}).get('editor_command')
            if not editor_cmd:
                # OSごとのデフォルト
                if platform.system() == "Windows":
                    editor_cmd = "notepad"
                elif platform.system() == "Darwin":
                    editor_cmd = "open"
                else:
                    editor_cmd = "xdg-open"
            subprocess.Popen([editor_cmd, yml_path])
            messagebox.showinfo("情報", f"settings.ymlをエディタ（{editor_cmd}）で開きました。")
        except Exception as e:
            messagebox.showerror("エラー", f"settings.ymlの編集に失敗しました: {e}\nパス: {yml_path}")

if __name__ == "__main__":
    try:
        # アプリケーションのディレクトリを環境変数として設定
        app_dir = os.path.dirname(os.path.abspath(__file__))
        os.environ['APP_DIR'] = app_dir
        
        # 必要な環境変数のチェック
        required_env_vars = ['GeminiApiKey', 'GoogleCalendarCredentialsFile', 'GoogleCalenderDaigakuID']
        missing_vars = [var for var in required_env_vars if not os.getenv(var)]
        if missing_vars:
            messagebox.showwarning(
                "環境変数未設定",
                f"以下の環境変数が設定されていません：\n{', '.join(missing_vars)}\n\n"
                "アプリケーションは起動しますが、一部の機能が動作しない可能性があります。"
            )
        
        root = tk.Tk()
        app = CalendarUpdaterApp(root)
        root.mainloop()
    except Exception as e:
        messagebox.showerror("起動エラー", f"アプリケーションの起動に失敗しました: {str(e)}") 