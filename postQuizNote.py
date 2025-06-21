from dotenv import load_dotenv
from notion_client import Client
import requests
import random
import tempfile
import os
import http.client
import json
import urllib.parse
import hmac
import hashlib
import base64
import time
import uuid

# 環境変数を読み込み
load_dotenv()

# Notion API設定
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

# X(Twitter) API設定
TWITTER_CONSUMER_KEY = os.getenv("TWITTER_CONSUMER_KEY")
TWITTER_CONSUMER_SECRET = os.getenv("TWITTER_CONSUMER_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")


def check_environment_variables():
    """必要な環境変数がセットされているかチェック"""
    required_vars = {
        "NOTION_TOKEN": NOTION_TOKEN,
        "NOTION_DATABASE_ID": NOTION_DATABASE_ID,
        "TWITTER_CONSUMER_KEY": TWITTER_CONSUMER_KEY,
        "TWITTER_CONSUMER_SECRET": TWITTER_CONSUMER_SECRET,
        "TWITTER_ACCESS_TOKEN": TWITTER_ACCESS_TOKEN,
        "TWITTER_ACCESS_TOKEN_SECRET": TWITTER_ACCESS_TOKEN_SECRET,
    }

    missing_vars = []
    for var_name, var_value in required_vars.items():
        if not var_value:
            missing_vars.append(var_name)

    if missing_vars:
        print("❌ 以下の環境変数が設定されていません:")
        for var in missing_vars:
            print(f"   - {var}")
        print("\n.envファイルを確認してください。")
        return False

    print("✅ 環境変数の設定を確認しました")
    return True


def get_random_record(notion):
    """全件取得してランダムに1つ選択"""
    try:
        print("📥 全レコードを取得中...")

        all_pages = []
        start_cursor = None

        while True:
            response = notion.databases.query(
                database_id=NOTION_DATABASE_ID, page_size=100, start_cursor=start_cursor
            )

            pages = response["results"]
            all_pages.extend(pages)

            print(f"取得済み: {len(all_pages)}件")

            if not response["has_more"]:
                break

            start_cursor = response["next_cursor"]

        if all_pages:
            random_page = random.choice(all_pages)
            print(f"✅ 総レコード数: {len(all_pages)}件からランダム選択")
            return random_page
        else:
            print("❌ レコードが見つかりません")
            return None

    except Exception as e:
        print(f"レコード取得エラー: {e}")
        return None


def extract_needed_data(page):
    """必要なデータ（タイトル、テキスト、画像URL）を抽出"""
    if not page:
        return None

    properties = page.get("properties", {})

    # タイトルを取得
    title = ""
    title_prop = properties.get("タイトル", {})
    if title_prop.get("type") == "title":
        title_texts = title_prop.get("title", [])
        title = "".join(
            [text.get("text", {}).get("content", "") for text in title_texts]
        )

    # テキストを取得
    text_content = ""
    text_prop = properties.get("テキスト", {})
    if text_prop.get("type") == "rich_text":
        rich_texts = text_prop.get("rich_text", [])
        text_content = "".join(
            [
                text.get("text", {}).get("content", "")
                for text in rich_texts
                if text.get("type") == "text"
            ]
        )

    # 画像URLを取得
    image_urls = []
    image_prop = properties.get("画像", {})
    if image_prop.get("type") == "files":
        files = image_prop.get("files", [])
        for file_data in files:
            if file_data.get("type") == "file":
                # Notion内部ファイル
                file_url = file_data.get("file", {}).get("url", "")
                if file_url:
                    image_urls.append(file_url)
            elif file_data.get("type") == "external":
                # 外部ファイル
                external_url = file_data.get("external", {}).get("url", "")
                if external_url:
                    image_urls.append(external_url)

    return {
        "title": title,
        "text": text_content,
        "image_urls": image_urls,
    }


def display_extracted_data(data):
    """抽出したデータを見やすく表示"""
    if not data:
        print("❌ 表示するデータがありません")
        return

    print("\n" + "=" * 60)
    print("📄 抽出されたデータ")
    print("=" * 60)

    print(f"\n📝 タイトル:")
    print(f"   {data['title'] if data['title'] else '(タイトルなし)'}")

    print(f"\n📄 テキスト:")
    if data["text"]:
        text_lines = data["text"].split("\n")
        for line in text_lines:
            print(f"   {line}")
    else:
        print("   (テキストなし)")

    print(f"\n🖼️  画像URL:")
    if data["image_urls"]:
        for i, url in enumerate(data["image_urls"], 1):
            print(f"   {i}. {url}")
    else:
        print("   (画像なし)")

    print("\n" + "=" * 60)

    return data


def create_post_content(data):
    """投稿用のコンテンツを作成"""
    if not data:
        return ""

    content_parts = []

    # タイトルを墨付きカッコで囲んで追加
    if data["title"]:
        content_parts.append(f"【{data['title']}】")

    # テキストを追加
    if data["text"]:
        content_parts.append(data["text"])

    post_content = "\n".join(content_parts)

    # X(Twitter)の文字数制限を考慮（画像URLがある場合は短縮URLが追加されるため少し余裕を持つ）
    max_length = 270 if data.get("image_urls") else 280

    if len(post_content) > max_length:
        # 制限文字数以内に収まるよう調整
        truncate_length = max_length - 3  # "..." の分を除く
        post_content = post_content[:truncate_length] + "..."

    return post_content


class TwitterAPIv2:
    def __init__(
        self, consumer_key, consumer_secret, access_token, access_token_secret
    ):
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.access_token = access_token
        self.access_token_secret = access_token_secret
        self.host = "upload.twitter.com"  # メディアアップロード用
        self.api_host = "api.twitter.com"  # API用

    def _percent_encode(self, s):
        """OAuth 1.0a仕様に従ってエンコード"""
        return urllib.parse.quote(str(s), safe="~")

    def _generate_oauth_signature(self, method, url, params):
        """OAuth 1.0a署名を生成"""
        # パラメータをアルファベット順にソート
        sorted_params = sorted(params.items())

        # パラメータを文字列に変換
        param_string = "&".join(
            [
                f"{self._percent_encode(k)}={self._percent_encode(v)}"
                for k, v in sorted_params
            ]
        )

        # 署名のベース文字列を作成
        base_string = f"{method.upper()}&{self._percent_encode(url)}&{self._percent_encode(param_string)}"

        # 署名キーを作成
        signing_key = f"{self._percent_encode(self.consumer_secret)}&{self._percent_encode(self.access_token_secret)}"

        # HMACでSHA-1署名を生成
        signature = hmac.new(
            signing_key.encode("utf-8"), base_string.encode("utf-8"), hashlib.sha1
        )
        return base64.b64encode(signature.digest()).decode("utf-8")

    def _generate_oauth_header(self, method, url, additional_params=None):
        """OAuth認証ヘッダーを生成"""
        oauth_params = {
            "oauth_consumer_key": self.consumer_key,
            "oauth_token": self.access_token,
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": str(int(time.time())),
            "oauth_nonce": str(uuid.uuid4()),
            "oauth_version": "1.0",
        }

        # 追加パラメータがある場合は署名計算に含める
        if additional_params:
            all_params = {**oauth_params, **additional_params}
        else:
            all_params = oauth_params

        oauth_params["oauth_signature"] = self._generate_oauth_signature(
            method, url, all_params
        )

        auth_header = "OAuth " + ", ".join(
            [
                f'{self._percent_encode(k)}="{self._percent_encode(v)}"'
                for k, v in oauth_params.items()
            ]
        )

        return auth_header

    def upload_media(self, image_path):
        """画像をTwitterにアップロード"""
        try:
            print(f"📤 Twitterに画像をアップロード中: {image_path}")

            # ファイルサイズとMIMEタイプを取得
            file_size = os.path.getsize(image_path)

            # INIT - アップロード開始
            init_url = "https://upload.twitter.com/1.1/media/upload.json"
            init_params = {
                "command": "INIT",
                "media_type": "image/jpeg",
                "total_bytes": str(file_size),
            }

            auth_header = self._generate_oauth_header("POST", init_url, init_params)

            conn = http.client.HTTPSConnection("upload.twitter.com")
            headers = {
                "Authorization": auth_header,
                "Content-Type": "application/x-www-form-urlencoded",
            }

            body = urllib.parse.urlencode(init_params)
            conn.request("POST", "/1.1/media/upload.json", body=body, headers=headers)
            response = conn.getresponse()
            init_response = json.loads(response.read().decode("utf-8"))
            conn.close()

            if response.status != 200:
                print(f"❌ INIT failed: {init_response}")
                return None

            media_id = init_response["media_id_string"]
            print(f"✅ INIT成功, Media ID: {media_id}")

            # APPEND - 画像データをアップロード
            with open(image_path, "rb") as f:
                image_data = f.read()

            append_url = "https://upload.twitter.com/1.1/media/upload.json"

            # マルチパートフォームデータを手動で作成
            boundary = f"----formdata-{uuid.uuid4()}"
            form_data = []

            # command パラメータ
            form_data.append(f"--{boundary}")
            form_data.append('Content-Disposition: form-data; name="command"')
            form_data.append("")
            form_data.append("APPEND")

            # media_id パラメータ
            form_data.append(f"--{boundary}")
            form_data.append('Content-Disposition: form-data; name="media_id"')
            form_data.append("")
            form_data.append(media_id)

            # segment_index パラメータ
            form_data.append(f"--{boundary}")
            form_data.append('Content-Disposition: form-data; name="segment_index"')
            form_data.append("")
            form_data.append("0")

            # media ファイル
            form_data.append(f"--{boundary}")
            form_data.append(
                'Content-Disposition: form-data; name="media"; filename="image.jpg"'
            )
            form_data.append("Content-Type: image/jpeg")
            form_data.append("")

            # テキスト部分を結合
            text_part = "\r\n".join(form_data) + "\r\n"

            # 終了境界
            end_boundary = f"\r\n--{boundary}--\r\n"

            # 完全なボディを作成
            body_bytes = (
                text_part.encode("utf-8") + image_data + end_boundary.encode("utf-8")
            )

            # OAuth署名用のパラメータ（ファイルデータは含めない）
            append_params = {
                "command": "APPEND",
                "media_id": media_id,
                "segment_index": "0",
            }

            auth_header = self._generate_oauth_header("POST", append_url, append_params)

            conn = http.client.HTTPSConnection("upload.twitter.com")
            headers = {
                "Authorization": auth_header,
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(body_bytes)),
            }

            conn.request(
                "POST", "/1.1/media/upload.json", body=body_bytes, headers=headers
            )
            response = conn.getresponse()
            append_response = response.read().decode("utf-8")
            conn.close()

            if response.status != 204:  # APPENDは204 No Contentを返す
                print(
                    f"❌ APPEND failed: Status {response.status}, Response: {append_response}"
                )
                return None

            print("✅ APPEND成功")

            # FINALIZE - アップロード完了
            finalize_url = "https://upload.twitter.com/1.1/media/upload.json"
            finalize_params = {"command": "FINALIZE", "media_id": media_id}

            auth_header = self._generate_oauth_header(
                "POST", finalize_url, finalize_params
            )

            conn = http.client.HTTPSConnection("upload.twitter.com")
            headers = {
                "Authorization": auth_header,
                "Content-Type": "application/x-www-form-urlencoded",
            }

            body = urllib.parse.urlencode(finalize_params)
            conn.request("POST", "/1.1/media/upload.json", body=body, headers=headers)
            response = conn.getresponse()
            finalize_response = json.loads(response.read().decode("utf-8"))
            conn.close()

            if response.status != 200:
                print(f"❌ FINALIZE failed: {finalize_response}")
                return None

            print(f"✅ 画像アップロード完了: {media_id}")
            return media_id

        except Exception as e:
            print(f"❌ 画像アップロードエラー: {e}")
            return None

    def post_tweet(self, text, media_id=None):
        """ツイートを投稿"""
        method = "POST"
        url = "https://api.twitter.com/2/tweets"

        # ペイロードを作成
        payload_data = {"text": text}
        if media_id:
            payload_data["media"] = {"media_ids": [media_id]}

        payload = json.dumps(payload_data)

        auth_header = self._generate_oauth_header(method, url)

        conn = http.client.HTTPSConnection(self.api_host)
        headers = {"Content-Type": "application/json", "Authorization": auth_header}

        try:
            conn.request(method, "/2/tweets", body=payload, headers=headers)
            response = conn.getresponse()
            response_body = response.read().decode("utf-8")

            return {"status_code": response.status, "body": json.loads(response_body)}
        except Exception as e:
            print(f"❌ ツイート投稿エラー: {e}")
            return None
        finally:
            conn.close()


def download_image(image_url):
    """画像をダウンロードして一時ファイルとして保存"""
    try:
        print(f"📥 画像をダウンロード中: {image_url}")

        response = requests.get(image_url, timeout=30)
        response.raise_for_status()

        # 一時ファイルに保存
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
            tmp_file.write(response.content)
            tmp_file_path = tmp_file.name

        print(f"✅ 画像ダウンロード完了: {tmp_file_path}")
        return tmp_file_path

    except Exception as e:
        print(f"❌ 画像ダウンロードエラー: {e}")
        return None


def post_tweet(extracted_data):
    """extracted_dataを使ってツイートを投稿"""
    if not extracted_data:
        print("❌ 投稿するデータがありません")
        return False

    # Twitter APIを初期化
    try:
        twitter_api = TwitterAPIv2(
            consumer_key=TWITTER_CONSUMER_KEY,
            consumer_secret=TWITTER_CONSUMER_SECRET,
            access_token=TWITTER_ACCESS_TOKEN,
            access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
        )
        print("✅ Twitter API初期化成功")
    except Exception as e:
        print(f"❌ Twitter API初期化エラー: {e}")
        return False

    # 投稿コンテンツを作成
    post_content = create_post_content(extracted_data)
    if not post_content:
        print("❌ 投稿可能なコンテンツがありません")
        return False

    print(f"\n📱 投稿予定のコンテンツ:")
    print("-" * 40)
    print(post_content)
    print(f"文字数: {len(post_content)}")
    print("-" * 40)

    try:
        media_id = None
        temp_file_path = None

        # 画像がある場合は1枚目をアップロード
        if extracted_data.get("image_urls"):
            image_url = extracted_data["image_urls"][0]
            print(f"🖼️  画像を含めて投稿します: {image_url}")

            # 画像をダウンロード
            temp_file_path = download_image(image_url)

            if temp_file_path:
                # 画像をTwitterにアップロード
                media_id = twitter_api.upload_media(temp_file_path)
                if not media_id:
                    print("❌ 画像アップロードに失敗しました")
                    return False

        # ツイートを投稿
        print("📤 ツイートを投稿中...")
        result = twitter_api.post_tweet(post_content, media_id)

        if result and result["status_code"] == 201:
            tweet_data = result["body"].get("data", {})
            tweet_id = tweet_data.get("id", "unknown")

            print(f"✅ 投稿成功!")
            # print(f"🔗 ツイートURL: https://twitter.com/user/status/{tweet_id}")
            # print(f"📊 ツイートID: {tweet_id}")

            # 一時ファイルを削除
            if temp_file_path and os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
                print("🗑️  一時ファイルを削除しました")

            return True
        else:
            print(f"❌ 投稿失敗:")
            print(f"ステータスコード: {result['status_code'] if result else 'None'}")
            print(f"レスポンス: {result['body'] if result else 'None'}")
            return False

    except Exception as e:
        print(f"❌ 投稿エラー: {e}")

        # エラー時も一時ファイルを削除
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)

        return False


def main():
    # 環境変数をチェック
    if not check_environment_variables():
        return

    # Notion クライアントを初期化
    try:
        notion = Client(auth=NOTION_TOKEN)
        print("✅ Notion クライアント初期化成功")
    except Exception as e:
        print(f"❌ Notion クライアント初期化エラー: {e}")
        return

    # ランダムレコードを取得
    page = get_random_record(notion)

    if not page:
        print("❌ レコードの取得に失敗しました")
        return

    # 必要なデータを抽出
    extracted_data = extract_needed_data(page)

    # 結果を表示
    display_extracted_data(extracted_data)

    success = post_tweet(extracted_data)

    if success:
        print("\n🎉 投稿が完了しました！")
    else:
        print("\n😞 投稿に失敗しました")


if __name__ == "__main__":
    main()
