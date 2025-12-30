"""セッション状態管理モジュール

st.session_stateとLocalStorageの連携を管理し、
ユーザーセッションのライフサイクルを制御します。
"""

from __future__ import annotations

import streamlit as st
from ulid import ULID
from streamlit_js_eval import streamlit_js_eval

from app.storage import storage_manager


class SessionManager:
    """セッション状態の初期化と管理を行うクラス"""

    LOCAL_STORAGE_CLIENT_KEY = "comfyui_client_id"

    @classmethod
    def get_client_id(cls) -> str:
        """ブラウザ固定のクライアントIDを取得

        LocalStorageに保存されたクライアントIDを取得し、
        存在しない場合は新規にULIDを生成して保存します。

        Returns:
            クライアントID（ULID形式）
        """
        # 既に確認済みの場合は即座に返す
        if st.session_state.get("client_id_confirmed"):
            return st.session_state["client_id"]

        # 候補IDを用意
        candidate_id = st.session_state.get("client_id_seed") or str(ULID())
        st.session_state["client_id_seed"] = candidate_id

        # LocalStorageからIDを取得または設定
        js_expr = f"""
        (() => {{
            const key = '{cls.LOCAL_STORAGE_CLIENT_KEY}';
            let cid = window.localStorage.getItem(key);
            if (!cid) {{
                cid = '{candidate_id}';
                window.localStorage.setItem(key, cid);
            }}
            return cid;
        }})()
        """

        js_key = f"get_or_set_client_id_{ULID()}"
        stored_id = streamlit_js_eval(
            js_expressions=js_expr,
            key=js_key,
        )

        final_id = str(stored_id or candidate_id)
        st.session_state["client_id"] = final_id
        st.session_state["client_id_confirmed"] = stored_id is not None

        return final_id

    @classmethod
    def initialize(cls) -> None:
        """セッション状態の初期化

        アプリケーション起動時に一度だけ実行され、
        必要なセッション変数を初期化します。
        """
        if st.session_state.get("session_initialized"):
            return

        # クライアントIDを確保
        client_id = cls.get_client_id()

        # セッション変数の初期化
        if "jobs" not in st.session_state:
            st.session_state["jobs"] = []

        if "history" not in st.session_state:
            st.session_state["history"] = []

        if "running_recovered" not in st.session_state:
            st.session_state["running_recovered"] = False

        # 初期化完了フラグ
        st.session_state["session_initialized"] = True

    @classmethod
    def sync_from_local_storage(cls) -> None:
        """LocalStorageからセッション状態に同期

        ブラウザリロード時などに、LocalStorageに保存された
        ジョブキューと履歴をセッション状態に読み込みます。
        """
        client_id = cls.get_client_id()

        # ジョブキューを読み込み
        if "jobs" not in st.session_state or not st.session_state["jobs"]:
            jobs = storage_manager.get(f"jobs_{client_id}", default=[])
            st.session_state["jobs"] = jobs

        # 履歴を読み込み
        if "history" not in st.session_state or not st.session_state["history"]:
            history = storage_manager.get(f"history_{client_id}", default=[])
            st.session_state["history"] = history

    @classmethod
    def sync_to_local_storage(cls) -> None:
        """セッション状態からLocalStorageに同期

        現在のジョブキューと履歴をLocalStorageに保存します。
        """
        client_id = cls.get_client_id()

        # ジョブキューを保存
        jobs = st.session_state.get("jobs", [])
        storage_manager.set(f"jobs_{client_id}", jobs)

        # 履歴を保存
        history = st.session_state.get("history", [])
        storage_manager.set(f"history_{client_id}", history)

    @classmethod
    def clear_local_storage(cls) -> None:
        """LocalStorageのデータをクリア

        デバッグやテスト用に、ユーザーのLocalStorageを
        クリアします。
        """
        client_id = cls.get_client_id()
        storage_manager.remove(f"jobs_{client_id}")
        storage_manager.remove(f"history_{client_id}")

        # セッション状態もクリア
        st.session_state["jobs"] = []
        st.session_state["history"] = []


# グローバルインスタンス
session_manager = SessionManager()
