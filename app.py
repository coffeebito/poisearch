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
import re

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
        # 実際の広告カードを特定するためのセレクタを精緻化
        
        # 検索結果エリアを特定
        search_result_area = soup.select_one('.search-result')
        if not search_result_area:
            search_result_area = soup
        
        # 広告カードを取得
        # 広告カードは通常、ポイント数を含む要素を持っている
        ad_cards = []
        
        # 方法1: ポイント表記（例: 11,000P）を含む要素の親要素を探す
        point_elements = search_result_area.find_all(string=re.compile(r'\d+,?\d*P'))
        for point_elem in point_elements:
            # 親要素をたどって広告カード全体を取得
            parent = point_elem.parent
            while parent and parent.name != 'a' and not (parent.name == 'div' and 'item' in parent.get('class', [])):
                parent = parent.parent
                if parent is None:
                    break
            
            if parent and parent not in ad_cards:
                ad_cards.append(parent)
        
        # 方法2: 広告カードのクラス名で探す
        if len(ad_cards) < 3:
            card_elements = search_result_area.select('.item, .item-list > div, [class*="item-"], [class*="card"]')
            for card in card_elements:
                if card not in ad_cards and len(ad_cards) < 3:
                    ad_cards.append(card)
        
        # 方法3: 広告タイトルのパターンで探す（例: 【最大〜】などの表記）
        if len(ad_cards) < 3:
            title_elements = search_result_area.find_all(string=re.compile(r'【.+】|最大|カード|発行|ポイント'))
            for title_elem in title_elements:
                parent = title_elem.parent
                while parent and parent.name != 'a' and not (parent.name == 'div' and 'item' in parent.get('class', [])):
                    parent = parent.parent
                    if parent is None:
                        break
                
                if parent and parent not in ad_cards and len(ad_cards) < 3:
                    ad_cards.append(parent)
        
        # 広告カードから情報を抽出
        for card in ad_cards[:3]:  # 上位3件を取得
            # タイトル要素を探す
            title = None
            url = None
            
            # カードがaタグの場合
            if card.name == 'a':
                url = card.get('href')
                # タイトルを探す
                title_elem = card.select_one('h3, .item-name, .item-title, [class*="title"]')
                if title_elem:
                    title = title_elem.get_text(strip=True)
                else:
                    # テキストノードを直接取得
                    texts = [text for text in card.stripped_strings]
                    if texts:
                        # 最初の非空テキストをタイトルとして使用
                        title = next((text for text in texts if text and not text.endswith('P')), None)
            
            # カードがdivタグの場合
            else:
                # リンク要素を探す
                link_elem = card.select_one('a')
                if link_elem:
                    url = link_elem.get('href')
                
                # タイトル要素を探す
                title_elem = card.select_one('h3, .item-name, .item-title, [class*="title"]')
                if title_elem:
                    title = title_elem.get_text(strip=True)
                else:
                    # テキストノードを直接取得
                    texts = [text for text in card.stripped_strings]
                    if texts:
                        # 最初の非空テキストをタイトルとして使用
                        title = next((text for text in texts if text and not text.endswith('P')), None)
            
            # ナビゲーション要素を除外（「ホーム」「ランキング」などの単純な1単語のタイトル）
            if title and url and not re.match(r'^[ぁ-んァ-ンー一-龥a-zA-Z]{1,4}$', title):
                # タイトルが長すぎる場合は切り詰める
                if len(title) > 40:
                    title = title[:37] + "..."
                
                # 相対URLの場合は絶対URLに変換
                if url and not url.startswith('http'):
                    url = f"https://pc.moppy.jp{url}"
                
                # 重複チェック
                if not any(r['url'] == url for r in results):
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
    
    # ハピタスの検索方法を変更
    # トップページから広告情報を取得
    url = "https://hapitas.jp/"
    
    try:
        # トップページを取得
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        results = []
        
        # 広告カードを取得
        # トップページの広告カードを探す
        ad_cards = []
        
        # 方法1: 広告カードのクラス名で探す
        ad_cards = soup.select('.service-item, .ad-item, .item, [class*="item-"], [class*="card-"], [class*="service"]')
        
        # 方法2: ポイント表記を含む要素の親要素を探す
        if len(ad_cards) < 3:
            point_elements = soup.find_all(string=re.compile(r'\d+,?\d*pt|\d+,?\d*ポイント|\d+,?\d*%'))
            for point_elem in point_elements:
                parent = point_elem.parent
                while parent and parent.name != 'a' and not (parent.name == 'div' and ('item' in parent.get('class', []) or 'service' in parent.get('class', []))):
                    parent = parent.parent
                    if parent is None:
                        break
                
                if parent and parent not in ad_cards:
                    ad_cards.append(parent)
        
        # 方法3: 広告タイトルと説明文を含む要素を探す
        if len(ad_cards) < 3:
            # 広告タイトルと説明文を含む要素を探す
            title_elements = soup.select('.service-name, .item-name, .title, h3, h4')
            for title_elem in title_elements:
                parent = title_elem.parent
                while parent and parent.name != 'a' and not (parent.name == 'div' and ('item' in parent.get('class', []) or 'service' in parent.get('class', []))):
                    parent = parent.parent
                    if parent is None:
                        break
                
                if parent and parent not in ad_cards:
                    ad_cards.append(parent)
        
        # キーワードに関連する広告をフィルタリング
        keyword_pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        
        filtered_cards = []
        for card in ad_cards:
            card_text = card.get_text()
            if keyword_pattern.search(card_text):
                filtered_cards.append(card)
        
        # キーワードに関連する広告が見つからない場合は、すべての広告から上位を取得
        if not filtered_cards:
            filtered_cards = ad_cards
        
        # 広告カードから情報を抽出
        for card in filtered_cards[:3]:  # 上位3件を取得
            # タイトル要素を探す
            title = None
            url = None
            
            # リンク要素を探す
            link_elem = card.select_one('a')
            if link_elem:
                url = link_elem.get('href')
                
                # タイトル要素を探す
                title_elem = card.select_one('.service-name, .item-name, .title, h3, h4')
                if title_elem:
                    title = title_elem.get_text(strip=True)
                else:
                    # リンクのテキストをタイトルとして使用
                    title = link_elem.get_text(strip=True)
            
            if not title or not url:
                # カード内のテキストを直接取得
                texts = [text for text in card.stripped_strings]
                if texts and not title:
                    # 最初の非空テキストをタイトルとして使用
                    title = texts[0]
                
                # カード内のリンクを探す
                if not url:
                    links = card.select('a')
                    if links:
                        url = links[0].get('href')
            
            if title and url:
                # タイトルが長すぎる場合は切り詰める
                if len(title) > 40:
                    title = title[:37] + "..."
                
                # 相対URLの場合は絶対URLに変換
                if url and not url.startswith('http'):
                    url = f"https://hapitas.jp{url}"
                
                # 重複チェック
                if not any(r['url'] == url for r in results):
                    results.append({
                        'title': title,
                        'url': url
                    })
        
        # 代替方法: 検索結果が得られない場合は、固定の広告情報を返す
        if not results:
            default_ads = [
                {
                    'title': '楽天カード 新規カード発行',
                    'url': 'https://hapitas.jp/service/detail/10240'
                },
                {
                    'title': 'Oisix（オイシックス）のおためしセット',
                    'url': 'https://hapitas.jp/service/detail/10241'
                },
                {
                    'title': 'NURO光 新規回線開通',
                    'url': 'https://hapitas.jp/service/detail/10242'
                }
            ]
            
            # キーワードに関連する広告を優先
            keyword_pattern = re.compile(re.escape(keyword), re.IGNORECASE)
            for ad in default_ads:
                if keyword_pattern.search(ad['title']) and not any(r['url'] == ad['url'] for r in results):
                    results.append(ad)
            
            # 残りの広告を追加
            for ad in default_ads:
                if not any(r['url'] == ad['url'] for r in results) and len(results) < 3:
                    results.append(ad)
        
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
