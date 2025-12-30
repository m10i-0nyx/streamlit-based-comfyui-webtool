"""LocalStorage連携ユーティリティモジュール

ブラウザのLocalStorageとStreamlitアプリケーション間でデータを
やり取りするための関数を提供します。
"""

from __future__ import annotations

import base64
import json
from typing import Any

from streamlit_js_eval import streamlit_js_eval
from ulid import ULID


class LocalStorageManager:
    """LocalStorageとのデータ連携を管理するクラス"""

    def __init__(self, key_prefix: str = "comfyui_"):
        """
        Args:
            key_prefix: LocalStorageのキーに使用するプレフィックス
        """
        self.key_prefix = key_prefix
        self._cache: dict[str, Any] = {}  # 読み込みキャッシュ

    def _make_key(self, name: str) -> str:
        """LocalStorageのキー名を生成"""
        return f"{self.key_prefix}{name}"

    def get(self, name: str, default: Any = None) -> Any:
        """LocalStorageから値を取得

        Args:
            name: キー名（プレフィックスは自動付与）
            default: 値が存在しない場合のデフォルト値

        Returns:
            LocalStorageから取得した値（JSON parse済み）
        """
        # キャッシュをチェック
        cache_key = self._make_key(name)
        if cache_key in self._cache:
            return self._cache[cache_key]

        key = self._make_key(name)
        js_expr = f"""
        (() => {{
            try {{
                const value = window.localStorage.getItem('{key}');
                return value ? JSON.parse(value) : null;
            }} catch (e) {{
                console.error('LocalStorage get error:', e);
                return null;
            }}
        }})()
        """

        # ユニークなキーを生成してキャッシュを回避
        js_key = f"ls_get_{name}_{ULID()}"
        result = streamlit_js_eval(js_expressions=js_expr, key=js_key)

        # 結果をキャッシュ
        final_result = result if result is not None else default
        self._cache[cache_key] = final_result

        return final_result

    def set(self, name: str, value: Any) -> bool:
        """LocalStorageに値を保存

        Args:
            name: キー名（プレフィックスは自動付与）
            value: 保存する値（JSON serializable）

        Returns:
            保存が成功したかどうか
        """
        key = self._make_key(name)
        json_value = json.dumps(value, ensure_ascii=False)
        # エスケープ処理: シングルクォートとバックスラッシュ
        escaped_value = json_value.replace("\\", "\\\\").replace("'", "\\'")

        js_expr = f"""
        (() => {{
            try {{
                const key = '{key}';
                const value = '{escaped_value}';
                window.localStorage.setItem(key, value);
                return true;
            }} catch (e) {{
                console.error('LocalStorage set error:', e);
                return false;
            }}
        }})()
        """

        js_key = f"ls_set_{name}_{ULID()}"
        result = streamlit_js_eval(js_expressions=js_expr, key=js_key)

        # キャッシュを更新
        if result is True:
            self._cache[key] = value

        return result is True

    def remove(self, name: str) -> bool:
        """LocalStorageから値を削除

        Args:
            name: キー名（プレフィックスは自動付与）

        Returns:
            削除が成功したかどうか
        """
        key = self._make_key(name)
        js_expr = f"""
        (() => {{
            try {{
                window.localStorage.removeItem('{key}');
                return true;
            }} catch (e) {{
                console.error('LocalStorage remove error:', e);
                return false;
            }}
        }})()
        """

        js_key = f"ls_remove_{name}_{ULID()}"
        result = streamlit_js_eval(js_expressions=js_expr, key=js_key)

        # キャッシュから削除
        if result is True and key in self._cache:
            del self._cache[key]

        return result is True

    def encode_image(self, image_bytes: bytes) -> str:
        """画像バイトデータをbase64エンコード

        Args:
            image_bytes: 画像のバイトデータ

        Returns:
            base64エンコードされた文字列
        """
        return base64.b64encode(image_bytes).decode("utf-8")

    def decode_image(self, encoded_str: str) -> bytes:
        """base64エンコードされた画像データをデコード

        Args:
            encoded_str: base64エンコードされた文字列

        Returns:
            画像のバイトデータ
        """
        return base64.b64decode(encoded_str)


# グローバルインスタンス
storage_manager = LocalStorageManager()
