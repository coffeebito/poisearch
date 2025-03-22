from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, 
    FlexSendMessage, BubbleContainer, BoxComponent,
    TextComponent, ButtonComponent, URIAction,
    CarouselContainer
)
import os
import json
import requests
from bs4 import BeautifulSoup
import logging
import traceback

app = Flask(__name__)

# 環境変数から設定を読み込む（実際のデプロイ時に設定）
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', 'YOUR_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET', 'YOUR_CHANNEL_SECRET')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.route("/callback", methods=['POST'])
def callback():
    """LINE Webhookからのコールバックを処理する"""
    # リクエストヘッダーからX-Line-Signatureを取得
    signature = request.headers.get('X-Line-Signature', '')

    # リクエストボディを取得
    body = request.get_data(as_text=True)
    logger.info("Request body: %s", body)

    # Webhookを処理
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.error("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)
    except Exception as e:
        logger.error(f"Unexpected error in callback: {e}")
        logger.error(traceback.format_exc())
        abort(500)

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    """ユーザーからのメッセージを処理する"""
    # ユーザーからのメッセージを取得
    user_message = event.message.text
    logger.info(f"Received message: {user_message}")

    try:
        # 空のメッセージや長すぎるメッセージをチェック
        if not user_message or len(user_message) > 100:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="検索ワードは1〜100文字で入力してください。")
            )
            return

        # モッピーとハピタスで検索を実行
        moppy_results = search_moppy(user_message)
        hapitas_results = search_hapitas(user_message)

        # 両方の検索結果が空の場合
        if not moppy_results and not hapitas_results:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"「{user_message}」に関する検索結果が見つかりませんでした。別のキーワードで試してみてください。")
            )
            return

        # 検索結果をユーザーに送信
        send_search_results(event.reply_token, user_message, moppy_results, hapitas_results)
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error during search: {e}")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="検索中にネットワークエラーが発生しました。しばらく経ってからもう一度お試しください。")
        )
    except LineBotApiError as e:
        logger.error(f"LINE API error: {e}")
        # LINEのAPIエラーはユーザーに通知しない（通知できない可能性が高い）
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.error(traceback.format_exc())
        try:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="予期せぬエラーが発生しました。しばらく経ってからもう一度お試しください。")
            )
        except Exception:
            pass  # 最後のエラー通知も失敗した場合は無視

def search_moppy(keyword):
    """モッピーサイトで検索を実行し、上位3件の結果を返す"""
    logger.info(f"Searching Moppy for: {keyword}")
    
    url = "https://pc.moppy.jp/search"
    params = {"word": keyword}
    
    try:
        # タイムアウト設定を追加
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        results = []
        
        # 検索結果の広告カードを取得（修正済み）
        # 実際のサイト構造に基づいて、広告カードのセレクタを指定
        ad_cards = []
        
        # 検索結果ページの広告カードを取得
        # 各広告カードは独立した要素として表示されている
        ad_containers = soup.select('.search-result .item-list > div')
        if not ad_containers:
            # 別のセレクタも試す
            ad_containers = soup.select('.search-result-list > div')
        
        if not ad_containers:
            # さらに別のセレクタも試す
            ad_containers = soup.select('[class*="item"]')
        
        # 広告カードから情報を抽出
        for container in ad_containers[:3]:  # 上位3件を取得
            title_elem = None
            link_elem = None
            
            # タイトル要素を探す
            title_candidates = container.select('.item-name, .item-title, h3, [class*="title"]')
            if title_candidates:
                title_elem = title_candidates[0]
            
            # リンク要素を探す
            link_candidates = container.select('a')
            if link_candidates:
                link_elem = link_candidates[0]
            elif container.name == 'a':
                link_elem = container
            
            # タイトルとリンクが見つかった場合、結果に追加
            if title_elem and link_elem:
                title = title_elem.text.strip()
                link = link_elem.get('href')
                
                # タイトルが長すぎる場合は切り詰める
                if len(title) > 40:
                    title = title[:37] + "..."
                
                # 相対URLの場合は絶対URLに変換
                if link and not link.startswith('http'):
                    link = f"https://pc.moppy.jp{link}"
                
                results.append({
                    'title': title,
                    'url': link
                })
            # タイトル要素が見つからない場合でも、リンク要素があればその内容を使用
            elif link_elem:
                title = link_elem.text.strip()
                link = link_elem.get('href')
                
                # 空のタイトルの場合はスキップ
                if not title:
                    continue
                
                # タイトルが長すぎる場合は切り詰める
                if len(title) > 40:
                    title = title[:37] + "..."
                
                # 相対URLの場合は絶対URLに変換
                if link and not link.startswith('http'):
                    link = f"https://pc.moppy.jp{link}"
                
                results.append({
                    'title': title,
                    'url': link
                })
        
        # 結果が3件未満の場合、別の方法でも検索
        if len(results) < 3:
            # 直接広告リンクを探す
            ad_links = soup.select('a[href*="/ad/"]')
            
            for link in ad_links:
                if len(results) >= 3:
                    break
                
                title = link.text.strip()
                url = link.get('href')
                
                # 既に結果に含まれているURLはスキップ
                if any(r['url'] == url for r in results):
                    continue
                
                # 空のタイトルの場合はスキップ
                if not title:
                    continue
                
                # タイトルが長すぎる場合は切り詰める
                if len(title) > 40:
                    title = title[:37] + "..."
                
                # 相対URLの場合は絶対URLに変換
                if url and not url.startswith('http'):
                    url = f"https://pc.moppy.jp{url}"
                
                results.append({
                    'title': title,
                    'url': url
                })
        
        return results[:3]  # 最大3件を返す
    except Exception as e:
        logger.error(f"Error searching Moppy: {e}")
        logger.error(traceback.format_exc())
        # エラーを上位に伝播させる
        raise

def search_hapitas(keyword):
    """ハピタスサイトで検索を実行し、上位3件の結果を返す"""
    logger.info(f"Searching Hapitas for: {keyword}")
    
    url = "https://sp.hapitas.jp/item/search"
    params = {"keyword": keyword}
    
    try:
        # タイムアウト設定を追加
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        results = []
        
        # 検索結果の広告リンクを取得（修正済み）
        # 複数のセレクタを試す
        ad_links = []
        
        # まず、itemDetailへのリンクを探す
        ad_links = soup.select('a[href*="/itemDetail/"]')
        
        # 結果がない場合は別のセレクタを試す
        if not ad_links:
            ad_links = soup.select('.item-list a, .search-result a')
        
        # それでも結果がない場合は、すべてのリンクから広告っぽいものを探す
        if not ad_links:
            all_links = soup.select('a')
            for link in all_links:
                href = link.get('href', '')
                # 広告リンクっぽいものを選択
                if '/item/' in href or '/ad/' in href or '/campaign/' in href:
                    ad_links.append(link)
        
        # 広告リンクから情報を抽出
        for link in ad_links[:3]:  # 上位3件を取得
            # タイトルを取得
            title = link.text.strip()
            # URLを取得
            url = link.get('href')
            
            # 空のタイトルの場合はスキップ
            if not title:
                continue
            
            # タイトルが長すぎる場合は切り詰める
            if len(title) > 40:
                title = title[:37] + "..."
            
            if url:
                # 相対URLの場合は絶対URLに変換
                if not url.startswith('http'):
                    url = f"https://sp.hapitas.jp{url}"
                
                results.append({
                    'title': title,
                    'url': url
                })
        
        return results[:3]  # 最大3件を返す
    except Exception as e:
        logger.error(f"Error searching Hapitas: {e}")
        logger.error(traceback.format_exc())
        # エラーを上位に伝播させる
        raise

def create_flex_message(site_name, results):
    """Flex Messageを作成する"""
    if not results:
        return BubbleContainer(
            body=BoxComponent(
                layout="vertical",
                contents=[
                    TextComponent(text=f"{site_name}", weight="bold", size="xl", color="#1DB446"),
                    TextComponent(text="検索結果がありませんでした。", margin="md")
                ]
            )
        )
    
    contents = [
        TextComponent(text=f"{site_name}", weight="bold", size="xl", color="#1DB446")
    ]
    
    for i, result in enumerate(results, 1):
        contents.extend([
            TextComponent(text=f"{i}. {result['title']}", margin="md", wrap=True),
            ButtonComponent(
                action=URIAction(label="詳細を見る", uri=result['url']),
                style="primary",
                margin="sm",
                height="sm"
            )
        ])
    
    return BubbleContainer(
        body=BoxComponent(
            layout="vertical",
            contents=contents,
            spacing="md",
            paddingAll="20px"
        )
    )

def send_search_results(reply_token, keyword, moppy_results, hapitas_results):
    """検索結果をLINEメッセージとして送信する"""
    try:
        # Flex Messageを作成
        moppy_bubble = create_flex_message("モッピー", moppy_results)
        hapitas_bubble = create_flex_message("ハピタス", hapitas_results)
        
        # カルーセルコンテナにバブルを追加
        carousel = CarouselContainer(contents=[moppy_bubble, hapitas_bubble])
        
        # メッセージを送信
        messages = [
            TextSendMessage(text=f"「{keyword}」の検索結果です。"),
            FlexSendMessage(alt_text=f"「{keyword}」の検索結果", contents=carousel)
        ]
        
        line_bot_api.reply_message(reply_token, messages)
        logger.info(f"Successfully sent search results for: {keyword}")
    except Exception as e:
        logger.error(f"Error sending search results: {e}")
        logger.error(traceback.format_exc())
        # エラーを上位に伝播させる
        raise

if __name__ == "__main__":
    # デバッグモードで実行
    app.run(host='0.0.0.0', port=5000, debug=True)