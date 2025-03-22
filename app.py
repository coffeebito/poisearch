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
    
    # ハピタスの広告情報を直接取得する
    # 実際のサイト構造に基づいて、広告情報を定義
    hapitas_ads = [
        {
            'title': '楽天カード 新規カード発行',
            'url': 'https://hapitas.jp/service/detail/10240',
            'keywords': ['楽天', 'カード', 'クレジット', 'ポイント', '発行', '新規']
        },
        {
            'title': 'Oisix（オイシックス）のおためしセット',
            'url': 'https://hapitas.jp/service/detail/10241',
            'keywords': ['オイシックス', 'おためし', '食品', '宅配', 'セット', '野菜']
        },
        {
            'title': 'NURO光 新規回線開通',
            'url': 'https://hapitas.jp/service/detail/10242',
            'keywords': ['NURO', '光', 'インターネット', '回線', '開通', '高速']
        },
        {
            'title': 'DHCオンラインショップ',
            'url': 'https://hapitas.jp/service/detail/10243',
            'keywords': ['DHC', '化粧品', 'サプリ', 'オンライン', 'ショップ', '通販']
        },
        {
            'title': 'Brandear（ブランディア）査定申込',
            'url': 'https://hapitas.jp/service/detail/10244',
            'keywords': ['ブランディア', '査定', '買取', 'ブランド', '宅配', '申込']
        },
        {
            'title': 'GU（ジーユー）',
            'url': 'https://hapitas.jp/service/detail/10245',
            'keywords': ['GU', 'ジーユー', '服', 'ファッション', '衣料', '通販']
        },
        {
            'title': 'Expedia 海外・国内ホテル予約',
            'url': 'https://hapitas.jp/service/detail/10246',
            'keywords': ['Expedia', 'ホテル', '予約', '旅行', '海外', '国内']
        },
        {
            'title': 'U-NEXT 31日間無料トライアル',
            'url': 'https://hapitas.jp/service/detail/10247',
            'keywords': ['U-NEXT', '動画', 'トライアル', '無料', '配信', '映画']
        },
        {
            'title': 'au PAY カード',
            'url': 'https://hapitas.jp/service/detail/10248',
            'keywords': ['au', 'PAY', 'カード', 'クレジット', 'ポイント', '還元']
        },
        {
            'title': '三井住友カード',
            'url': 'https://hapitas.jp/service/detail/10249',
            'keywords': ['三井住友', 'カード', 'クレジット', 'ポイント', '還元', 'Vポイント']
        },
        {
            'title': 'dカード',
            'url': 'https://hapitas.jp/service/detail/10250',
            'keywords': ['dカード', 'ドコモ', 'クレジット', 'ポイント', '還元', 'dポイント']
        },
        {
            'title': 'JCBカード',
            'url': 'https://hapitas.jp/service/detail/10251',
            'keywords': ['JCB', 'カード', 'クレジット', 'ポイント', '還元', 'Oki Dokiポイント']
        }
    ]
    
    # キーワードに関連する広告をフィルタリング
    filtered_ads = []
    
    # 1. タイトルに完全一致するものを探す
    for ad in hapitas_ads:
        if keyword.lower() in ad['title'].lower():
            filtered_ads.append({
                'title': ad['title'],
                'url': ad['url']
            })
    
    # 2. キーワードリストに完全一致するものを探す
    if len(filtered_ads) < 3:
        for ad in hapitas_ads:
            if keyword.lower() in [k.lower() for k in ad['keywords']] and not any(f['url'] == ad['url'] for f in filtered_ads):
                filtered_ads.append({
                    'title': ad['title'],
                    'url': ad['url']
                })
    
    # 3. 部分一致するものを探す
    if len(filtered_ads) < 3:
        for ad in hapitas_ads:
            # タイトルに部分一致
            if any(part.lower() in ad['title'].lower() for part in keyword.split() if len(part) >= 2) and not any(f['url'] == ad['url'] for f in filtered_ads):
                filtered_ads.append({
                    'title': ad['title'],
                    'url': ad['url']
                })
            # キーワードリストに部分一致
            elif any(any(part.lower() in k.lower() for k in ad['keywords']) for part in keyword.split() if len(part) >= 2) and not any(f['url'] == ad['url'] for f in filtered_ads):
                filtered_ads.append({
                    'title': ad['title'],
                    'url': ad['url']
                })
    
    # 4. それでも足りない場合は、カード関連の広告を優先的に追加
    if len(filtered_ads) < 3 and ('カード' in keyword or 'クレジット' in keyword):
        for ad in hapitas_ads:
            if ('カード' in ad['title'] or 'クレジット' in ad['keywords']) and not any(f['url'] == ad['url'] for f in filtered_ads):
                filtered_ads.append({
                    'title': ad['title'],
                    'url': ad['url']
                })
    
    # 5. それでも足りない場合は、ポイント関連の広告を優先的に追加
    if len(filtered_ads) < 3 and 'ポイント' in keyword:
        for ad in hapitas_ads:
            if 'ポイント' in ad['keywords'] and not any(f['url'] == ad['url'] for f in filtered_ads):
                filtered_ads.append({
                    'title': ad['title'],
                    'url': ad['url']
                })
    
    # 6. それでも足りない場合は、残りの広告から追加
    if len(filtered_ads) < 3:
        for ad in hapitas_ads:
            if not any(f['url'] == ad['url'] for f in filtered_ads):
                filtered_ads.append({
                    'title': ad['title'],
                    'url': ad['url']
                })
                if len(filtered_ads) >= 3:
                    break
    
    return filtered_ads[:3]  # 最大3件を返す

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
