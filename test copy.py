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
    
    url = "https://sp.hapitas.jp/item/search"
    params = {"searchWord": keyword}
    
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
    
print(search_hapitas("三井住友"))