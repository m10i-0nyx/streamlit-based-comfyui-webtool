"""セッション状態管理モジュール

st.session_stateとLocalStorageの連携を管理し、
ユーザーセッションのライフサイクルを制御します。
"""

from __future__ import annotations

import streamlit as st
from ulid import ULID
from streamlit_js_eval import streamlit_js_eval

from app.storage import STORAGE_MANAGER


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
        # 既に確認済みの場合は即座に返す（JavaScriptを再実行しない）
        if st.session_state.get("client_id_confirmed") and st.session_state.get("client_id"):
            return st.session_state["client_id"]

        # 候補IDを用意
        candidate_id = st.session_state.get("client_id_seed") or str(ULID())
        st.session_state["client_id_seed"] = candidate_id

        # LocalStorageからIDを取得または設定（初回のみ）
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
        st.session_state["client_id_confirmed"] = True  # 確実にフラグを立てる

        return final_id

    @classmethod
    def initialize(cls) -> None:
        """セッション状態の初期化

        アプリケーション起動時に一度だけ実行され、
        必要なセッション変数を初期化します。
        """
        if st.session_state.get("session_initialized"):
            return

        # running_recoveredフラグのみここで初期化
        if "running_recovered" not in st.session_state:
            st.session_state["running_recovered"] = False

        # 初期化完了フラグ
        st.session_state["session_initialized"] = True

    @classmethod
    def sync_from_local_storage(cls) -> None:
        """LocalStorageからセッション状態に同期

        ブラウザリロード時などに、LocalStorageに保存された
        ジョブキューと履歴をセッション状態に読み込みます。
        一度だけ実行されます。
        """
        # 既に読み込み成功している場合はスキップ
        if st.session_state.get("localstorage_loaded"):
            return

        # カウンターをインクリメントして、新しい読み込みを実行
        if "_ls_sync_attempt" not in st.session_state:
            st.session_state["_ls_sync_attempt"] = 0
        st.session_state["_ls_sync_attempt"] += 1

        # カウンターを更新（STORAGE_MANAGERが使用）
        for key in ["jobs", "history"]:
            st.session_state[f"_ls_counter_{key}"] = st.session_state["_ls_sync_attempt"]

        # ジョブキューを読み込み（強制上書き、キャッシュバイパス）
        jobs = STORAGE_MANAGER.get("jobs", default=None, use_cache=False)

        # 履歴を読み込み（強制上書き、キャッシュバイパス）
        history = STORAGE_MANAGER.get("history", default=None, use_cache=False)

        # streamlit_js_evalが初回レンダリング時にNoneを返すため、
        # データが取得できるまで読み込み完了フラグを立てない
        if jobs is not None and history is not None:
            st.session_state["jobs"] = jobs if isinstance(jobs, list) else []
            st.session_state["history"] = history if isinstance(history, list) else []
            # 読み込み完了フラグ
            st.session_state["localstorage_loaded"] = True
        else:
            # データ取得失敗時は初期値を設定
            if "jobs" not in st.session_state:
                st.session_state["jobs"] = []
            if "history" not in st.session_state:
                st.session_state["history"] = []
            # 3回試行してもダメなら諦めて空配列として扱う
            if st.session_state["_ls_sync_attempt"] >= 3:
                st.session_state["localstorage_loaded"] = True

    @classmethod
    def sync_to_local_storage(cls) -> None:
        """セッション状態からLocalStorageに同期

        現在のジョブキューと履歴をLocalStorageに保存します。
        """
        client_id = cls.get_client_id()

        # ジョブキューを保存
        jobs = st.session_state.get("jobs", [])
        STORAGE_MANAGER.set(f"jobs", jobs)

        # 履歴を保存
        history = st.session_state.get("history", [])
        STORAGE_MANAGER.set(f"history", history)

    @classmethod
    def clear_local_storage(cls) -> None:
        """LocalStorageのデータをクリア

        デバッグやテスト用に、ユーザーのLocalStorageを
        クリアします。
        """
        client_id = cls.get_client_id()
        STORAGE_MANAGER.remove(f"jobs")
        STORAGE_MANAGER.remove(f"history")

        # セッション状態もクリア
        st.session_state["jobs"] = []
        st.session_state["history"] = []


# グローバルインスタンス
SESSION_MANAGER = SessionManager()
