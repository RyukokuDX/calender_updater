# Google Calendar Updater

入力されたファイルや文章を要約し、指定されたGoogleカレンダーにイベントとして自動登録するPythonアプリケーションです。

## 主な機能

- テキストまたはファイル（例：メール文面や議事録など）をLLM（Gemini API等）で解析し、カレンダーイベント情報を抽出
- Google Calendar APIを利用して、抽出したイベントを指定カレンダーに自動登録
- 設定ファイル（`settings.yml`）による柔軟なカスタマイズ
- ログ出力による動作記録
- `.gitignore`による機密情報の保護

## 技術スタック

- Python 3.x
- Google Calendar API
- Jinja2
- PyYAML
- google-auth-oauthlib, google-api-python-client
- ログ出力: logging

## セットアップ手順

1. 必要なパッケージのインストール
    ```sh
    pip install -r requirements.txt
    ```

2. 必要な環境変数を設定（下記は一例です。ご利用のAPIや環境に応じて適宜変更してください）
    - `GeminiApiKey` : Gemini APIキー
    - `GoogleCalendarCredentialsFile` : Google Calendar API認証情報ファイルのパス
    - `GoogleCalenderDaigakuID` : GoogleカレンダーID

    例（Windows PowerShell）:
    ```sh
    $env:GeminiApiKey = "your-gemini-api-key"
    $env:GoogleCalendarCredentialsFile = "config/client_secret_xxxx.json"
    $env:GoogleCalenderDaigakuID = "your-calendar-id@group.calendar.google.com"
    ```

3. `settings.yml`を編集し、必要に応じて他の設定を調整

4. アプリ実行
    ```sh
    python main.py
    ```

5. 初回実行時は認証フローが開始され、ブラウザでGoogleアカウントの認可が必要です

## 設定ファイル例（settings.yml）

```yaml
google_calendar:
  credentials_file: ${GoogleCalendarCredentialsFile}  # 認証情報ファイルのパス（環境変数）
  token_file: "token.json"
  scopes: ["https://www.googleapis.com/auth/calendar.events"]
  calendars:
    default:
      id: ${GoogleCalenderDaigakuID}  # カレンダーID（環境変数）
      name: "予定表"
      color_id: "1"
      default_duration: 60
  default_calendar: "default"
  output_format:
    type: "json"
    timezone: "Asia/Tokyo"
    date_format: "%Y-%m-%dT%H:%M:%S%z"
    default_duration: 60
    save_to_calendar: true
    save_to_file: true
    output_directory: "./output"
llm:
  providers:
    gemini:
      api_key: ${GeminiApiKey}
      model: "gemini-1.5-flash"
      temperature: 0.7
      max_tokens: 1000
      prompt:
        system: |
          あなたは文章を要約する専門家です。与えられた文章を簡潔に要約し、カレンダーイベントとして適切な形式で出力してください。
          現在は{{ current_year }}年です。
          ...
  default_provider: "gemini"  # デフォルトで使用するプロバイダー
```

> **補足:** `llm.providers`には複数のLLM（例: Gemini, ChatGPT等）を登録可能です。`default_provider`でデフォルトを指定できます。

## 注意事項

- `config/`や`*.json`などの機密ファイルは必ず`.gitignore`で管理対象外にしてください
- 認証情報やトークンファイルは絶対に公開リポジトリに含めないでください
- APIキーやカレンダーIDなどの機密情報は**必ず環境変数で管理**してください

---

## 付録：GoogleカレンダーIDの取得方法

1. [Googleカレンダー](https://calendar.google.com/)を開く
2. 左側の「マイカレンダー」から対象カレンダーの「︙」→「設定と共有」をクリック
3. 「カレンダーの統合」セクションの「カレンダーID」をコピー
4. これをsettings.ymlに設定（サンプルでは環境変数に格納）

## 付録：Google Calendar APIの有効化と認証情報の取得

1. [Google Cloud Console](https://console.cloud.google.com/)にアクセスし、プロジェクトを作成または選択
2. 「APIとサービス」→「ライブラリ」→「Google Calendar API」を検索し有効化
3. 「認証情報」→「認証情報を作成」→「OAuthクライアントID」→「デスクトップアプリ」
4. ダウンロードした`client_secret_xxxx.json`のパスを環境変数`GoogleCalendarCredentialsFile`に設定
5. 初回実行時に認証フローが開始され、`token.json`が自動生成されます

## ライセンス

MIT