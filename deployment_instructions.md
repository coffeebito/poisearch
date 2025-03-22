# LINE検索ボット デプロイ手順

このドキュメントでは、LINE Messaging APIを使用して、モッピーとハピタスのサイトで広告を検索するボットのデプロイ方法について説明します。

## 前提条件

- Pythonがインストールされているサーバー環境（Python 3.6以上推奨）
- LINEビジネスアカウント
- LINE Developersアカウント
- 公開されたWebサーバー（HerokuやAWS、Google Cloud Platformなど）

## 1. LINE Developersでの設定

1. [LINE Developers Console](https://developers.line.biz/console/)にアクセスし、ログインします。
2. 新しいプロバイダーを作成するか、既存のプロバイダーを選択します。
3. 「新規チャネル作成」をクリックし、「Messaging API」を選択します。
4. 必要な情報を入力してチャネルを作成します：
   - チャネル名：「広告検索ボット」など
   - チャネル説明：適切な説明を入力
   - 大業種・小業種：適切なものを選択
   - メールアドレス：連絡先のメールアドレス
5. 利用規約に同意して「作成」をクリックします。
6. チャネル基本設定ページで以下の情報を確認し、メモしておきます：
   - チャネルシークレット（Channel Secret）
   - チャネルアクセストークン（Channel Access Token）
     - 「Messaging API設定」タブで「チャネルアクセストークン」の「発行」ボタンをクリックして取得

## 2. サーバー環境の準備

### Herokuを使用する場合

1. [Heroku](https://www.heroku.com/)にアカウント登録し、ログインします。
2. 新しいアプリケーションを作成します。
3. デプロイ方法を選択します（GitHubやHeroku CLI、コンテナレジストリなど）。

### 他のサーバー環境の場合

1. サーバーにSSH接続します。
2. Pythonと必要なパッケージをインストールします：
   ```bash
   sudo apt update
   sudo apt install python3 python3-pip python3-venv
   ```

## 3. アプリケーションのデプロイ

### ファイルの準備

1. 以下のファイルをサーバーにアップロードまたはクローンします：
   - `app.py`：メインアプリケーションファイル
   - `requirements.txt`：依存パッケージリスト（以下の内容で作成）

```
line-bot-sdk==3.16.2
Flask==3.1.0
requests==2.32.3
beautifulsoup4==4.13.3
gunicorn==21.2.0
```

### 環境変数の設定

#### Herokuの場合

1. Herokuダッシュボードで、アプリケーションの「Settings」タブを開きます。
2. 「Config Vars」セクションで「Reveal Config Vars」をクリックします。
3. 以下の環境変数を追加します：
   - `LINE_CHANNEL_SECRET`：LINE Developersで取得したチャネルシークレット
   - `LINE_CHANNEL_ACCESS_TOKEN`：LINE Developersで取得したチャネルアクセストークン

#### 他のサーバー環境の場合

1. 環境変数を設定します：
   ```bash
   export LINE_CHANNEL_SECRET='your_channel_secret'
   export LINE_CHANNEL_ACCESS_TOKEN='your_channel_access_token'
   ```
2. これらの環境変数を永続化するには、`.bashrc`や`.profile`ファイルに追加します。

### アプリケーションの起動

#### Herokuの場合

1. `Procfile`を作成し、以下の内容を記述します：
   ```
   web: gunicorn app:app
   ```
2. Heroku CLIを使用してデプロイします：
   ```bash
   git add .
   git commit -m "Initial commit"
   git push heroku master
   ```
3. または、Herokuダッシュボードの「Deploy」タブからデプロイします。

#### 他のサーバー環境の場合

1. 仮想環境を作成し、アクティベートします：
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
2. 依存パッケージをインストールします：
   ```bash
   pip install -r requirements.txt
   ```
3. Gunicornを使用してアプリケーションを起動します：
   ```bash
   gunicorn app:app
   ```
4. または、systemdサービスとして設定して自動起動させることもできます。

## 4. Webhookの設定

1. LINE Developers Consoleで、作成したチャネルの「Messaging API設定」タブを開きます。
2. 「Webhook URL」に、デプロイしたアプリケーションのURLに`/callback`を追加したものを入力します：
   - 例：`https://your-app-name.herokuapp.com/callback`
3. 「Webhookの利用」を「有効」に設定します。
4. 「Webhook送信」を「有効」に設定します。
5. 「検証」ボタンをクリックして、Webhookが正しく設定されていることを確認します。

## 5. ボットの友だち追加

1. LINE Developers Consoleの「Messaging API設定」タブで、QRコードを確認します。
2. スマートフォンのLINEアプリでQRコードをスキャンし、ボットを友だちに追加します。

## 6. 動作確認

1. LINEアプリでボットにメッセージを送信します（例：「ポイント」）。
2. ボットがモッピーとハピタスの検索結果を返すことを確認します。

## トラブルシューティング

### Webhookの検証に失敗する場合

- サーバーのファイアウォール設定を確認します。
- アプリケーションが正常に起動しているか確認します。
- ログを確認して、エラーメッセージを特定します。

### ボットが応答しない場合

- LINE Developers Consoleで「Webhookの利用」と「Webhook送信」が有効になっているか確認します。
- 環境変数が正しく設定されているか確認します。
- サーバーのログを確認して、エラーメッセージを特定します。

## セキュリティ上の注意

- チャネルシークレットとチャネルアクセストークンは秘密情報です。公開リポジトリにコミットしないでください。
- 本番環境では、HTTPSを使用してください。
- 定期的にチャネルアクセストークンをローテーションすることをお勧めします。

## 参考リンク

- [LINE Messaging API ドキュメント](https://developers.line.biz/ja/docs/messaging-api/)
- [Heroku ドキュメント](https://devcenter.heroku.com/)
- [Flask ドキュメント](https://flask.palletsprojects.com/)
