"""LocalStorage連携ユーティリティモジュール

ブラウザのLocalStorageとStreamlitアプリケーション間でデータを
やり取りするための関数を提供します。
"""

from __future__ import annotations

import json
import os
from typing import Any

import streamlit as st
from streamlit_js_eval import streamlit_js_eval


class LocalStorageManager:
    """LocalStorageとのデータ連携を管理するクラス"""

    def __init__(self, key_prefix: str = "comfyui_"):
        """
        Args:
            key_prefix: LocalStorageのキーに使用するプレフィックス
        """
        self.key_prefix = key_prefix
        self._log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    def _make_key(self, name: str) -> str:
        """LocalStorageのキー名を生成"""
        return f"{self.key_prefix}{name}"

    def get(self, name: str, default: Any = None, use_cache: bool = True) -> Any:
        """LocalStorageから値を取得

        Args:
            name: キー名（プレフィックスは自動付与）
            default: 値が存在しない場合のデフォルト値
            use_cache: 使用されない（互換性のため残す）

        Returns:
            LocalStorageから取得した値（JSON parse済み）
        """
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

        # session_state内のカウンターを使って固定キーを生成
        # sync_from_local_storage()で設定されるカウンターを使用
        if f"_ls_counter_{name}" not in st.session_state:
            st.session_state[f"_ls_counter_{name}"] = 1
        counter = st.session_state[f"_ls_counter_{name}"]
        js_key = f"ls_get_{name}_{counter}"

        json_str = streamlit_js_eval(js_expressions=js_expr, key=js_key)

        # JSONパースをPython側で実行
        if json_str is None or json_str == "":
            return default

        try:
            return json.loads(json_str)
        except (json.JSONDecodeError, TypeError):
            return default

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

        # session_state内のカウンターを使ってユニークキーを生成
        if f"_ls_set_counter_{name}" not in st.session_state:
            st.session_state[f"_ls_set_counter_{name}"] = 0
        st.session_state[f"_ls_set_counter_{name}"] += 1
        counter = st.session_state[f"_ls_set_counter_{name}"]
        js_key = f"ls_set_{name}_{counter}"

        result = streamlit_js_eval(js_expressions=js_expr, key=js_key)

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

        # session_state内のカウンターを使ってユニークキーを生成
        if f"_ls_remove_counter_{name}" not in st.session_state:
            st.session_state[f"_ls_remove_counter_{name}"] = 0
        st.session_state[f"_ls_remove_counter_{name}"] += 1
        counter = st.session_state[f"_ls_remove_counter_{name}"]
        js_key = f"ls_remove_{name}_{counter}"

        result = streamlit_js_eval(js_expressions=js_expr, key=js_key)

        return result is True

# グローバルインスタンス
STORAGE_MANAGER = LocalStorageManager()
