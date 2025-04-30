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
import re

# ログ設定
def setup_logging():
    """
    ログ設定を行う関数
    """
    # ログディレクトリの作成
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # ログファイル名の設定（日時を含む）
    log_file = os.path.join(log_dir, f'test_calendar_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    
    # ログ設定
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()  # コンソールにも出力
        ]
    )
    
    return logging.getLogger('test_calendar')

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
    """
    設定ファイルを読み込む関数
    """
    settings_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'settings.yml')
    with open(settings_path, 'r', encoding='utf-8') as f:
        settings = yaml.safe_load(f)
    settings = expand_env_vars(settings)
    return settings

def setup_gemini(settings):
    """
    Gemini APIの設定を行う関数
    """
    api_key = os.getenv('GeminiApiKey')
    if not api_key:
        raise ValueError("GeminiApiKey environment variable is not set")
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(settings['llm']['providers']['gemini']['model'])
    return model

def prepare_prompt(template_vars, settings):
    """
    テンプレート変数と設定を使用してプロンプトを準備する共通関数
    
    Args:
        template_vars (dict): テンプレート変数の辞書
        settings (dict): 設定情報の辞書
    
    Returns:
        str: レンダリングされたプロンプト
    """
    # テンプレートを準備
    system_prompt = settings['llm']['providers']['gemini']['prompt']['system']
    user_template = settings['llm']['providers']['gemini']['prompt']['user_template']
    
    # テンプレートをレンダリング
    template = Template(user_template, keep_trailing_newline=True)
    user_prompt = template.render(
        filename=template_vars['filename'],
        filetype=template_vars['filetype'],
        creation_time=template_vars['creation_time'],
        file_content=template_vars['file_content'],
        direct_text=template_vars['direct_text'],
        additional_instructions=template_vars['additional_instructions']
    )
    
    # システムプロンプトとユーザープロンプトを結合
    full_prompt = f"{system_prompt}\n\n{user_prompt}"
    
    return full_prompt

def call_llm(prompt, settings):
    """
    LLMを呼び出してレスポンスを取得する関数
    
    Args:
        prompt (str): 送信するプロンプト
        settings (dict): 設定情報の辞書
    
    Returns:
        dict: LLMからのレスポンス
    """
    model = setup_gemini(settings)
    response = model.generate_content(prompt)
    return response

def process_llm_response(response, settings, logger):
    """
    LLMからのレスポンスを処理し、カレンダーイベントの形式に変換する関数
    
    Args:
        response (dict): LLMからのレスポンス
        settings (dict): 設定情報の辞書
        logger: ロガーオブジェクト
    
    Returns:
        dict: カレンダーイベントの形式に変換されたデータ
    """
    # レスポンスからテキストを取得
    text = response.text.strip()
    
    # デバッグ出力
    logger.info("LLM Response Text:")
    logger.info(text)
    logger.info("Response Object: %s", response)
    
    try:
        # JSONの開始位置と終了位置を見つける
        json_start = text.find('{')
        json_end = text.rfind('}') + 1
        if json_start == -1 or json_end == 0:
            raise ValueError("JSON形式のデータが見つかりません")
        
        # JSON部分を抽出してパース
        json_text = text[json_start:json_end]
        event_data = json.loads(json_text)
        
        # デバッグ出力
        logger.info("Parsed Event Data: %s", event_data)
        
        # 必須フィールドの確認
        required_fields = ['summary', 'start', 'end']
        for field in required_fields:
            if field not in event_data:
                raise ValueError(f'Missing required field: {field}')
        
        return event_data
    
    except json.JSONDecodeError as e:
        logger.error("JSON解析エラー: %s", e)
        raise ValueError("レスポンスをJSONとして解析できません")
    except Exception as e:
        logger.error("エラー: %s", e)
        raise

def process_text(text, settings, logger):
    """
    テキストを処理してカレンダーイベントの形式に変換する関数
    
    Args:
        text (str): 処理するテキスト
        settings (dict): 設定情報の辞書
        logger: ロガーオブジェクト
    
    Returns:
        dict: カレンダーイベントの形式に変換されたデータ
    """
    # テンプレートの変数を準備
    template_vars = {
        'filename': '',
        'filetype': '',
        'creation_time': '',
        'file_content': '',
        'direct_text': text.strip(),
        'additional_instructions': ''
    }
    
    # プロンプトを準備
    full_prompt = prepare_prompt(template_vars, settings)
    
    # デバッグ出力を追加
    logger.info("Full Prompt:")
    logger.info(full_prompt)
    
    # LLMを呼び出す
    response = call_llm(full_prompt, settings)
    
    # レスポンスを処理
    return process_llm_response(response, settings, logger)

def setup_google_calendar(settings):
    """
    Google Calendar APIの認証設定を行う関数
    
    Args:
        settings (dict): 設定情報の辞書
    
    Returns:
        service: 認証済みのGoogle Calendar APIサービス
    """
    creds = None
    token_file = settings['google_calendar']['token_file']
    scopes = settings['google_calendar']['scopes']

    # トークンファイルが存在する場合は読み込む
    if os.path.exists(token_file):
        with open(token_file, 'rb') as token:
            creds = pickle.load(token)

    # 有効な認証情報がない場合は、ユーザーにログインを要求
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                settings['google_calendar']['credentials_file'], scopes)
            creds = flow.run_local_server(port=0)
        
        # トークンを保存
        with open(token_file, 'wb') as token:
            pickle.dump(creds, token)

    # Google Calendar APIのサービスを構築
    service = build('calendar', 'v3', credentials=creds)
    return service

def create_calendar_event(event_data, settings, logger):
    """
    Google Calendarにイベントを作成する関数
    
    Args:
        event_data (dict): イベントデータ
        settings (dict): 設定情報の辞書
        logger: ロガーオブジェクト
    
    Returns:
        dict: 作成されたイベントの情報
    """
    try:
        service = setup_google_calendar(settings)
        calendar_id = settings['google_calendar']['calendars']['default']['id']
        
        # イベントの作成
        event = service.events().insert(
            calendarId=calendar_id,
            body=event_data
        ).execute()
        
        logger.info("イベントが作成されました: %s", event.get('htmlLink'))
        return event
    
    except Exception as e:
        logger.error("イベント作成中にエラーが発生しました: %s", e, exc_info=True)
        raise

def process_file(file_path, settings, logger):
    """
    ファイルを処理してカレンダーイベントの形式に変換する関数
    
    Args:
        file_path (str): 処理するファイルのパス
        settings (dict): 設定情報の辞書
        logger: ロガーオブジェクト
    
    Returns:
        dict: カレンダーイベントの形式に変換されたデータ
    """
    # ファイル情報の取得
    filename = os.path.basename(file_path)
    filetype = os.path.splitext(filename)[1].lstrip('.')
    creation_time = datetime.fromtimestamp(os.path.getctime(file_path)).isoformat()
    
    # ファイルの内容を読み込む
    with open(file_path, 'r', encoding='utf-8') as f:
        file_content = f.read()
    
    # テンプレートの変数を準備
    template_vars = {
        'filename': filename,
        'filetype': filetype,
        'creation_time': creation_time,
        'file_content': file_content,
        'direct_text': '',
        'additional_instructions': ''
    }
    
    # プロンプトを準備
    full_prompt = prepare_prompt(template_vars, settings)
    
    # デバッグ出力を追加
    logger.info("Full Prompt:")
    logger.info(full_prompt)
    
    # LLMを呼び出す
    response = call_llm(full_prompt, settings)
    
    # レスポンスを処理
    event_data = process_llm_response(response, settings, logger)
    
    # Google Calendarにイベントを作成
    if settings['google_calendar']['output_format']['save_to_calendar']:
        created_event = create_calendar_event(event_data, settings, logger)
        logger.info("カレンダーイベントが作成されました: %s", created_event.get('htmlLink'))
    
    return event_data

def main():
    # ログ設定
    logger = setup_logging()
    logger.info("テストを開始します")
    
    try:
        # 設定の読み込み
        settings = load_settings()
        logger.info("設定を読み込みました")
        
        # ファイル処理のテスト
        logger.info("ファイル処理のテストを開始します")
        test_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample.txt")
        
        try:
            result = process_file(test_file, settings, logger)
            logger.info("ファイル処理の結果: %s", result)
        except Exception as e:
            logger.error("ファイル処理中にエラーが発生しました: %s", e, exc_info=True)
            raise
        
        logger.info("テストが正常に完了しました")
    
    except Exception as e:
        logger.error("テスト中にエラーが発生しました: %s", e, exc_info=True)
        raise

if __name__ == "__main__":
    main() 