#!/bin/bash

# LINE検索ボットのテスト用スクリプト
echo "LINE検索ボットのテスト開始..."

# 仮想環境をアクティベート
cd /home/ubuntu/line_search_bot
source venv/bin/activate

# 必要なパッケージが全てインストールされているか確認
echo "依存パッケージの確認..."
pip install -r requirements.txt 2>/dev/null || echo "requirements.txtが見つからないため、個別にパッケージをチェックします"

# 個別にパッケージをチェック
for package in line-bot-sdk requests beautifulsoup4 flask; do
    pip show $package >/dev/null 2>&1 || pip install $package
done

# アプリケーションの起動テスト
echo "アプリケーションの起動テスト..."
python -c "import app; print('アプリケーションのインポートに成功しました')"

if [ $? -eq 0 ]; then
    echo "✅ アプリケーションのインポートテスト成功"
else
    echo "❌ アプリケーションのインポートテスト失敗"
    exit 1
fi

# 検索機能のテスト
echo "検索機能のテスト..."
python -c "
import app
import logging

# ロギングを無効化
logging.disable(logging.CRITICAL)

# モッピー検索のテスト
try:
    results = app.search_moppy('ポイント')
    print(f'モッピー検索テスト: {len(results)}件の結果を取得')
    if len(results) > 0:
        print(f'最初の結果: {results[0][\"title\"]}')
        print('✅ モッピー検索テスト成功')
    else:
        print('⚠️ モッピー検索テスト: 結果が0件')
except Exception as e:
    print(f'❌ モッピー検索テスト失敗: {e}')

# ハピタス検索のテスト
try:
    results = app.search_hapitas('ポイント')
    print(f'ハピタス検索テスト: {len(results)}件の結果を取得')
    if len(results) > 0:
        print(f'最初の結果: {results[0][\"title\"]}')
        print('✅ ハピタス検索テスト成功')
    else:
        print('⚠️ ハピタス検索テスト: 結果が0件')
except Exception as e:
    print(f'❌ ハピタス検索テスト失敗: {e}')

# Flexメッセージ作成のテスト
try:
    bubble = app.create_flex_message('テスト', [{'title': 'テストタイトル', 'url': 'https://example.com'}])
    print('✅ Flexメッセージ作成テスト成功')
except Exception as e:
    print(f'❌ Flexメッセージ作成テスト失敗: {e}')
"

echo "テスト完了"
echo "注意: 実際のLINE Botとしての動作確認には、以下が必要です:"
echo "1. LINE Developers ConsoleでのBotの作成とチャネルアクセストークン、チャネルシークレットの取得"
echo "2. 公開されたWebhook URLの設定（ngrokなどのツールを使用）"
echo "3. 環境変数の設定（LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET）"
echo ""
echo "デプロイ手順については、deployment_instructions.mdを参照してください。"
