"""プロンプト入力支援UIコンポーネント

Danbooruタグ辞書を使用した高度なプロンプト入力支援機能を提供する。
オートコンプリート風のUIで、タイピング中にタグ候補を表示・選択できる。
"""

from __future__ import annotations

import streamlit as st

from app.tag_dictionary import get_tag_dictionary


def render_prompt_input_with_tags(
    label: str,
    key: str,
    default_value: str = "",
    height: int = 150,
    help_text: str | None = None,
) -> str:
    """タグ支援付きプロンプト入力欄（オートコンプリート風）

    Args:
        label: ラベル
        key: セッションステートのキー
        default_value: デフォルト値
        height: テキストエリアの高さ
        help_text: ヘルプテキスト

    Returns:
        入力されたプロンプトテキスト
    """
    # タグ辞書を取得
    tag_dict = get_tag_dictionary()

    # セッションステートのキー
    textarea_key = f"{key}_textarea"
    search_key = f"{key}_search"
    clear_search_flag = f"{key}_clear_search_flag"
    insert_tag_key = f"{key}_insert_tag"

    # 検索クリアフラグの処理（ウィジェット作成前に実行）
    if st.session_state.get(clear_search_flag, False):
        st.session_state[search_key] = ""  # 空文字列を設定
        st.session_state[clear_search_flag] = False

    # タグ挿入処理（ウィジェット作成前に実行）
    if insert_tag_key in st.session_state:
        tag_to_insert = st.session_state[insert_tag_key]
        current_prompt = st.session_state.get(textarea_key, "").strip()

        if current_prompt:
            # 既存のプロンプトの末尾にカンマで追加
            if not current_prompt.endswith(","):
                st.session_state[textarea_key] = f"{current_prompt}, {tag_to_insert}"
            else:
                st.session_state[textarea_key] = f"{current_prompt} {tag_to_insert}"
        else:
            st.session_state[textarea_key] = tag_to_insert

        # 挿入完了後、一時キーを削除
        del st.session_state[insert_tag_key]

    # 初期値の設定
    if textarea_key not in st.session_state:
        st.session_state[textarea_key] = default_value

    # プロンプト入力欄
    prompt = st.text_area(
        label,
        key=textarea_key,
        height=height,
        help=help_text or "カンマ区切りでタグを入力してください。下の検索ボックスでタグ候補を表示できます。",
    )

    # タグ検索入力ボックスと候補表示
    cols = st.columns([3, 1])
    with cols[0]:
        search_query = st.text_input(
            "🔍 タグを検索（英語・日本語対応）",
            key=search_key,
            placeholder="例: smile, 笑顔, blue_eyes... (スペース/カンマでAND, -XXXで除外)",
            help="タグ名または日本語でタグを検索できます。複数キーワードをスペースまたはカンマで区切るとAND検索。-を付けると除外します。",
        )
    with cols[1]:
        st.write("")  # 高さ調整用
        st.write("")  # 高さ調整用
        if st.button("🗑️ クリア", key=f"{key}_clear_search_btn"):
            st.session_state[clear_search_flag] = True
            st.rerun()

    # 検索結果を表示
    if search_query:
        # スペースまたはカンマで分割してAND検索を判定
        import re
        search_query = search_query.strip()  # 前後の空白を削除
        queries = re.split(r'[,\s]+', search_query)
        queries = [q for q in queries if q]  # 空文字を除去

        # NOT条件（-で始まるもの）を分離
        include_queries = [q for q in queries if not q.startswith('-')]
        exclude_queries = [q[1:] for q in queries if q.startswith('-') and len(q) > 1]

        # 検索モードの表示用文字列を作成
        search_mode_parts = []
        if len(include_queries) > 1:
            search_mode_parts.append(f"AND検索: {' + '.join(include_queries)}")
        elif len(include_queries) == 1:
            search_mode_parts.append(f"検索: {include_queries[0]}")

        if exclude_queries:
            search_mode_parts.append(f"除外: {', '.join(exclude_queries)}")

        if search_mode_parts:
            st.caption(f"🔍 {' | '.join(search_mode_parts)}")

        # 検索実行
        if len(include_queries) > 1:
            # AND検索
            results = tag_dict.search_and(include_queries, limit=20, exclude=exclude_queries)
        elif len(include_queries) == 1:
            # 通常検索
            results = tag_dict.search(include_queries[0], limit=20, exclude=exclude_queries)
        elif exclude_queries:
            # 除外のみ（人気タグから除外）
            results = tag_dict.search("", limit=20, exclude=exclude_queries)
        else:
            # 条件なし
            results = tag_dict.search("", limit=20)

        if results:
            st.markdown("**タグ候補（クリックでプロンプトに追加）**")

            # カテゴリ別の色アイコン
            category_colors = {
                0: "🔵",  # 一般タグ
                1: "🟡",  # アーティスト
                3: "🟢",  # 著作権
                4: "🟣",  # キャラクター
                5: "🔴",  # メタタグ
            }

            # 候補をコンパクトに表示（5列）
            cols_per_row = 5
            for i in range(0, len(results), cols_per_row):
                cols = st.columns(cols_per_row)
                for j, col in enumerate(cols):
                    idx = i + j
                    if idx < len(results):
                        tag = results[idx]
                        tag_name = tag["name"]
                        category = tag.get("category", 0)
                        count = tag.get("count", 0)
                        icon = category_colors.get(category, "⚪")

                        with col:
                            tooltip = f"使用数: {count:,}" if count > 0 else "タグ"
                            button_key = f"{key}_insert_{tag_name}_{idx}"

                            if st.button(
                                f"{icon} {tag_name}",
                                key=button_key,
                                help=tooltip,
                                use_container_width=True,
                            ):
                                # タグを一時キーに保存（次の実行で挿入される）
                                st.session_state[insert_tag_key] = tag_name
                                # 検索をクリア（フラグを立てる）
                                st.session_state[clear_search_flag] = True
                                st.rerun()
        else:
            st.info("該当するタグが見つかりませんでした")

    return st.session_state[textarea_key]


def render_negative_prompt_presets(key: str = "negative_preset") -> str | None:
    """ネガティブプロンプトのプリセット選択

    Args:
        key: セッションステートのキー

    Returns:
        選択されたプリセットテキスト
    """
    presets = {
        "なし": "",
        "基本": "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry",
        "高品質重視": "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry, artist name, multiple views, extra limbs, deformed, disfigured, mutation, mutated, ugly, out of frame",
        "カスタム": None,
    }

    preset_name = st.selectbox(
        "ネガティブプロンプト プリセット",
        options=list(presets.keys()),
        index=1,  # 初期値: 基本（インデックス1）
        key=key,
        help="よく使うネガティブプロンプトのテンプレート",
    )

    return presets[preset_name]
