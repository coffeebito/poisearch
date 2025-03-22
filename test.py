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

logger = logging.getLogger(__name__)

def search_hapitas(keyword):
    """ハピタスサイトで検索を実行し、上位3件の結果を返す"""
    logger.info(f"Searching Hapitas for: {keyword}")
    
    url = "https://sp.hapitas.jp/item/search?apn=search_by_point_from_global_navigation&"
    params = {
    "searchWord": keyword,
    "sort": "point",
    "parentCategory": 0,
    "childCategory": 0
}
    
    try:
        # タイムアウト設定を追加
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        results = []
        # 検索結果の広告リンクを取得
        ad_links = soup.select('a[href*="/itemDetail/"]')[:3]  # 上位3件を取得
        
        for link in ad_links:
            # タイトルを取得
            title = link.text.strip()
            # URLを取得
            url = link.get('href')
            
            if title and url:
                # タイトルが長すぎる場合は切り詰める
                if len(title) > 40:
                    title = title[:37] + "..."
                
                # 相対URLの場合は絶対URLに変換
                if url and not url.startswith('http'):
                    url = f"https://sp.hapitas.jp{url}"
                
                results.append({
                    'title': title,
                    'url': url
                })
        
        return results
    except Exception as e:
        print("Error searching Hapitas: ", e)
        logger.error(f"Error searching Hapitas: {e}")
        logger.error(traceback.format_exc())
        # エラーを上位に伝播させる
        raise
    
print(search_hapitas("三井住友"))