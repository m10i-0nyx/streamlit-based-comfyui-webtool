"""Danbooruタグ辞書を管理するモジュール

Hugging Faceからdanbooru-tag-csvデータセットを取得し、
プロンプト入力支援に必要なタグ情報を提供する。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from collections.abc import Iterator
import pandas as pd

import streamlit as st
from datasets import load_dataset

class TagDictionary:
    """Danbooruタグ辞書を管理するクラス"""

    def __init__(self, csv_path: Path | None = None) -> None:
        """タグ辞書を初期化

        Args:
            csv_path: CSVファイルのパス。Noneの場合はHugging Faceから取得
        """
        self.csv_path = csv_path
        self._tags: list[dict[str, Any]] = []
        self._tag_map: dict[str, dict[str, Any]] = {}

    def load(self) -> None:
        """タグデータを読み込む"""
        if self.csv_path and self.csv_path.exists():
            self._load_from_file(self.csv_path)
        else:
            self._load_from_huggingface()

    def _load_from_file(self, path: Path) -> None:
        """ローカルCSVファイルからタグデータを読み込む

        Args:
            path: CSVファイルのパス
        """
        try:
            df = pd.read_csv(path)
            self._parse_dataframe(df)
        except Exception as e:
            st.warning(f"ローカルCSVの読み込みに失敗しました: {e}")
            self._load_from_huggingface()

    def _load_from_huggingface(self) -> None:
        """Hugging Faceからタグデータを読み込む"""
        try:
            # メインのタグファイルのみを指定して読み込み
            # 共起データ（cooccurrence）は除外
            dataset = load_dataset(
                "newtextdoc1111/danbooru-tag-csv",
                data_files="danbooru_tags.csv",  # メインのタグファイルを指定
                split="train",
                cache_dir=str(Path.home() / ".cache" / "streamlit-comfyui"),
            )

            # DataFrameに変換
            df_or_iter = dataset.to_pandas()

            # イテレータの場合は最初の要素を取得
            if isinstance(df_or_iter, Iterator):
                df = next(df_or_iter)
            else:
                df = df_or_iter

            # DataFrameであることを確認
            if not isinstance(df, pd.DataFrame):
                raise TypeError(f"Expected DataFrame, got {type(df)}")

            self._parse_dataframe(df)

        except Exception as e:
            st.error(f"Hugging Faceからのタグデータ読み込みに失敗: {e}")
            # フォールバック: 基本的なタグリストを用意
            self._load_fallback_tags()

    def _parse_dataframe(self, df: pd.DataFrame) -> None:
        """DataFrameからタグ情報を解析

        Args:
            df: タグ情報を含むDataFrame
        """
        self._tags = []
        self._tag_map = {}

        for _, row in df.iterrows():
            tag_name = row.iloc[0]  # 1列目: タグ名
            category = row.iloc[1] if len(row) > 1 else 0  # 2列目: カテゴリ
            count = row.iloc[2] if len(row) > 2 else 0  # 3列目: 使用数
            aliases = row.iloc[3] if len(row) > 3 and pd.notna(row.iloc[3]) else ""  # 4列目: エイリアス

            tag_info = {
                "name": tag_name,
                "category": int(category) if pd.notna(category) else 0,
                "count": int(count) if pd.notna(count) else 0,
                "aliases": aliases.split(",") if aliases else [],
            }

            self._tags.append(tag_info)
            self._tag_map[tag_name] = tag_info

        # 使用数でソート（降順）
        self._tags.sort(key=lambda x: x["count"], reverse=True)

    def _load_fallback_tags(self) -> None:
        """基本的なタグリストをフォールバックとして読み込む"""
        fallback_tags = [
            "1girl",
            "solo",
            "long_hair",
            "breasts",
            "looking_at_viewer",
            "blush",
            "smile",
            "open_mouth",
            "short_hair",
            "blue_eyes",
            "skirt",
            "simple_background",
            "white_background",
            "black_hair",
            "brown_hair",
            "blonde_hair",
            "animal_ears",
            "thighhighs",
            "hat",
            "dress",
            "holding",
            "bow",
            "navel",
            "sitting",
            "standing",
            "japanese_clothes",
            "swimsuit",
            "school_uniform",
            "red_eyes",
            "green_eyes",
        ]

        self._tags = [
            {"name": tag, "category": 0, "count": 0, "aliases": []}
            for tag in fallback_tags
        ]
        self._tag_map = {tag["name"]: tag for tag in self._tags}

    def search(self, query: str, limit: int = 50, exclude: list[str] | None = None) -> list[dict[str, Any]]:
        """タグを検索

        Args:
            query: 検索クエリ
            limit: 最大返却数
            exclude: 除外するキーワードのリスト

        Returns:
            マッチしたタグのリスト（除外条件に一致しないもの）
        """
        # 前後の空白を削除
        query = query.strip()

        if not query:
            # クエリが空の場合は人気タグを返す
            return self._tags[:limit]

        query_lower = query.lower()
        exclude_lower = [e.lower().strip() for e in (exclude or []) if e.strip()]
        results: list[dict[str, Any]] = []

        for tag in self._tags:
            tag_name_lower = tag["name"].lower()
            aliases_lower = [alias.lower() for alias in tag["aliases"]]

            # 除外条件のチェック
            if exclude_lower:
                should_exclude = False
                for exclude_query in exclude_lower:
                    if exclude_query in tag_name_lower or any(exclude_query in alias for alias in aliases_lower):
                        should_exclude = True
                        break

                if should_exclude:
                    continue

            # タグ名で検索
            if query_lower in tag_name_lower:
                results.append(tag)
                if len(results) >= limit:
                    break
                continue

            # エイリアス（日本語など）で検索
            for alias in tag["aliases"]:
                if query_lower in alias.lower():
                    results.append(tag)
                    if len(results) >= limit:
                        break
                    break

        return results

    def search_and(self, queries: list[str], limit: int = 50, exclude: list[str] | None = None) -> list[dict[str, Any]]:
        """複数クエリのAND検索（除外条件対応）

        Args:
            queries: 検索クエリのリスト（スペースまたはカンマ区切りを想定）
            limit: 最大返却数
            exclude: 除外するキーワードのリスト

        Returns:
            全てのクエリにマッチし、除外条件に一致しないタグのリスト
        """
        if not queries:
            return self._tags[:limit]

        # クエリを小文字に変換
        queries_lower = [q.lower().strip() for q in queries if q.strip()]
        exclude_lower = [e.lower().strip() for e in (exclude or []) if e.strip()]

        if not queries_lower:
            return self._tags[:limit]

        results: list[dict[str, Any]] = []

        for tag in self._tags:
            tag_name_lower = tag["name"].lower()
            aliases_lower = [alias.lower() for alias in tag["aliases"]]

            # 除外条件のチェック
            if exclude_lower:
                should_exclude = False
                for exclude_query in exclude_lower:
                    # 除外キーワードがタグ名またはエイリアスに含まれているか
                    if exclude_query in tag_name_lower or any(exclude_query in alias for alias in aliases_lower):
                        should_exclude = True
                        break

                if should_exclude:
                    continue

            # 全てのクエリが タグ名 または エイリアス のいずれかに含まれているかチェック
            all_match = True
            for query_lower in queries_lower:
                # このクエリがタグ名かエイリアスのいずれかに含まれているか
                tag_name_match = query_lower in tag_name_lower
                alias_match = any(query_lower in alias for alias in aliases_lower)

                if not (tag_name_match or alias_match):
                    all_match = False
                    break

            if all_match:
                results.append(tag)
                if len(results) >= limit:
                    break

        return results

    def get_popular_tags(self, limit: int = 50) -> list[dict[str, Any]]:
        """人気タグを取得

        Args:
            limit: 最大返却数

        Returns:
            人気タグのリスト（使用数順）
        """
        return self._tags[:limit]

    def get_tag(self, tag_name: str) -> dict[str, Any] | None:
        """タグ情報を取得

        Args:
            tag_name: タグ名

        Returns:
            タグ情報、存在しない場合はNone
        """
        return self._tag_map.get(tag_name)


@st.cache_resource(show_spinner="タグ辞書を読み込み中...")
def get_tag_dictionary(csv_path: Path | None = None) -> TagDictionary:
    """タグ辞書のシングルトンインスタンスを取得

    Args:
        csv_path: CSVファイルのパス（オプション）

    Returns:
        TagDictionaryインスタンス
    """
    dictionary = TagDictionary(csv_path)
    dictionary.load()
    return dictionary
