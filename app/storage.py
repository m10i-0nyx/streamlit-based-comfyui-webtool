"""LocalStorage連携ユーティリティモジュール

ブラウザのLocalStorageとStreamlitアプリケーション間でデータを
やり取りするための関数を提供します。
"""

from __future__ import annotations

import json
from typing import Any

from streamlit_js_eval import streamlit_js_eval


class LocalStorageManager:
    """LocalStorageとのデータ連携を管理するクラス"""

    def __init__(self, key_prefix: str = "comfyui_"):
        """
        Args:
            key_prefix: LocalStorageのキーに使用するプレフィックス
            use_compression: zstd圧縮を使用するか
        """
        self.key_prefix = key_prefix
        self._cache: dict[str, Any] = {}  # 読み込みキャッシュ

    def _make_key(self, name: str) -> str:
        """LocalStorageのキー名を生成"""
        return f"{self.key_prefix}{name}"

    def get(self, name: str, default: Any = None, use_cache: bool = True) -> Any:
        """LocalStorageから値を取得

        Args:
            name: キー名（プレフィックスは自動付与）
            default: 値が存在しない場合のデフォルト値
            use_cache: キャッシュを使用するか

        Returns:
            LocalStorageから取得した値（JSON parse済み）
        """
        cache_key = self._make_key(name)

        # キャッシュをチェック（use_cache=Trueの場合のみ）
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]

        key = self._make_key(name)
        js_expr = f"""
        (() => {{
            try {{
                const value = window.localStorage.getItem('{key}');
                return value;
            }} catch (e) {{
                console.error('LocalStorage get error:', e);
                return null;
            }}
        }})()
        """

        # ユニークなキーを生成してキャッシュを回避
        js_key = f"ls_get_{name}"
        json_str = streamlit_js_eval(js_expressions=js_expr, key=js_key)

        # JSONパースをPython側で実行
        if json_str is None or json_str == "":
            final_result = default
        else:
            try:
                final_result = json.loads(json_str)
            except (json.JSONDecodeError, TypeError):
                final_result = default

        # 結果をキャッシュ
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
                window.localStorage.setItem('{key}', '{escaped_value}');
                return true;
            }} catch (e) {{
                console.error('LocalStorage set error:', e);
                return false;
            }}
        }})()
        """

        js_key = f"ls_set_{name}"
        result = streamlit_js_eval(js_expressions=js_expr, key=js_key)

        # JSが成功した場合のみキャッシュを更新
        if result is True:
            self._cache[key] = value
            return True

        return False

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

        js_key = f"ls_remove_{name}"
        result = streamlit_js_eval(js_expressions=js_expr, key=js_key)

        # キャッシュから削除
        if result is True and key in self._cache:
            del self._cache[key]

        return result is True

# グローバルインスタンス
STORAGE_MANAGER = LocalStorageManager()
