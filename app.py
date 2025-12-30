from __future__ import annotations

import asyncio
import secrets
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import streamlit as st
from ulid import ULID

from app.comfy_client import ComfyUIClient, GenerationResult
from app.config import load_config
from app.session import session_manager
from app.storage import storage_manager
from app.workflow import WorkflowTemplateError, load_workflow, render_workflow

st.set_page_config(
    page_title="ComfyUI Web Tool",
    layout="wide",
    initial_sidebar_state="collapsed",
)

CONFIGS = load_config()
TZ = ZoneInfo(CONFIGS.time_zone)


def _sanitize_error_message(message: str) -> str:
    """Redact sensitive endpoints from user-facing error messages."""

    redacted = message or ""
    secrets = {CONFIGS.api_base.rstrip("/"), CONFIGS.ws_url.rstrip("/")}
    for secret in secrets:
        if not secret:
            continue
        redacted = redacted.replace(secret, "[REDACTED]")
    return redacted

@st.cache_resource(show_spinner=False)
def _user_counters() -> tuple[dict[str, int], threading.Lock]:
    """Shared running-counter per client_id across sessions."""
    return {}, threading.Lock()


@st.cache_resource(show_spinner=False)
def _global_state() -> tuple[dict[str, int], threading.Lock]:
    return {"queued": 0, "running": 0}, threading.Lock()



@st.cache_data(show_spinner=False)
def _load_template(path: Path) -> dict[str, Any]:
    return load_workflow(path)


def _get_client_id() -> str:
    """SessionManager経由でクライアントIDを取得"""
    return session_manager.get_client_id()


def _get_jobs() -> list[dict[str, Any]]:
    """ジョブキューを取得（session_stateから）"""
    if "jobs" not in st.session_state:
        st.session_state["jobs"] = []
    return st.session_state["jobs"]


def _set_jobs(jobs: list[dict[str, Any]]) -> None:
    """ジョブキューを保存（バッチ処理用フラグで制御）"""
    st.session_state["jobs"] = jobs
    # 保存フラグを立てる（実際の保存はsync_to_local_storage()で行う）
    st.session_state["jobs_dirty"] = True


def _running_jobs_count() -> int:
    counters, lock = _user_counters()
    client_id = _get_client_id()
    with lock:
        return counters.get(client_id, 0)


def _add_job(job: dict[str, Any]) -> None:
    jobs = _get_jobs()
    jobs.append(job)
    _set_jobs(jobs)
    counters, lock = _global_state()
    with lock:
        counters["queued"] += 1


def _update_job(job_id: str, **kwargs: Any) -> None:
    jobs = _get_jobs()
    for job in jobs:
        if job["id"] == job_id:
            job.update(kwargs)
            break
    _set_jobs(jobs)


def _remove_job(job_id: str) -> None:
    jobs = _get_jobs()
    remaining: list[dict[str, Any]] = []
    removed: dict[str, Any] | None = None
    for job in jobs:
        if job["id"] == job_id:
            removed = job
        else:
            remaining.append(job)
    _set_jobs(remaining)

    if removed:
        counters, lock = _global_state()
        with lock:
            status = removed.get("status")
            if status == "running":
                counters["running"] = max(0, counters["running"] - 1)
                user_counters, user_lock = _user_counters()
                with user_lock:
                    client_id = _get_client_id()
                    user_counters[client_id] = max(
                        0, user_counters.get(client_id, 0) - 1
                    )
            elif status == "queued":
                counters["queued"] = max(0, counters["queued"] - 1)


def _release_running_slot() -> None:
    """Decrease running counters for the current user and global state."""

    counters, lock = _global_state()
    with lock:
        counters["running"] = max(0, counters["running"] - 1)

    user_counters, user_lock = _user_counters()
    with user_lock:
        client_id = _get_client_id()
        user_counters[client_id] = max(0, user_counters.get(client_id, 0) - 1)


def _get_history() -> list[dict[str, Any]]:
    """履歴を取得（session_stateから）"""
    if "history" not in st.session_state:
        st.session_state["history"] = []
    return st.session_state["history"]


def _save_history() -> None:
    """履歴をLocalStorageに保存（バッチ処理用フラグで制御）"""
    # 保存フラグを立てる（実際の保存はsync_to_local_storage()で行う）
    st.session_state["history_dirty"] = True


def _append_history(entry: dict[str, Any]) -> None:
    """履歴に新しいエントリを追加"""
    history = _get_history()
    history.append(entry)
    _save_history()


def _upsert_history(job_id: str, data: dict[str, Any]) -> None:
    """履歴エントリを挿入または更新"""
    history = _get_history()
    for entry in history:
        if entry.get("job_id") == job_id:
            entry.update(data)
            _save_history()
            return
    data_with_id = {**data, "job_id": job_id}
    history.append(data_with_id)
    _save_history()


def _apply_theme(mode: str) -> None:
    if mode == "dark":
        base_bg = "#0b1221"
        card_bg = "#151f33"
        text_color = "#e9f0ff"
        accent = "#6dd3ff"
        border_color = "#1f2a44"
    else:
        base_bg = "#eef2ff"
        card_bg = "#ffffff"
        text_color = "#0b1221"
        accent = "#2563eb"
        border_color = "#cbd5e1"
    st.markdown(
        f"""
        <style>
        body {{ background: radial-gradient(circle at 20% 20%, {accent}1a, transparent 25%),
                        radial-gradient(circle at 80% 10%, #ff9d6f1a, transparent 25%),
                        {base_bg}; color: {text_color}; }}
        .stApp {{ background: transparent; color: {text_color}; }}
        .stTextArea textarea, .stNumberInput input {{
            background: {card_bg};
            color: {text_color};
            border: 1px solid {border_color};
        }}
        .stSelectbox div, .stRadio div, label {{ color: {text_color}; }}
        .stButton button {{
            background: linear-gradient(135deg, {accent}, #8de1ff);
            color: #0b1221;
            border: 1px solid {border_color};
        }}
        .stButton button:hover {{ transform: translateY(-1px); box-shadow: 0 6px 18px #00000033; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _random_seed() -> int:
    return secrets.randbelow(2**31)


def _current_timestamp() -> str:
    return datetime.now(tz=TZ).strftime("%Y-%m-%d %H:%M:%S %Z")


def _render_sidebar(theme_mode: str) -> None:
    st.sidebar.header("設定")
    if CONFIGS.log_level in ["TRACE"]:
        st.sidebar.write(f"API: {CONFIGS.api_base}")
        st.sidebar.write(f"WebSocket: {CONFIGS.ws_url}")
    st.sidebar.write(f"ワークフロー: {CONFIGS.workflow_path}")
    st.sidebar.write(f"画像サイズ: {CONFIGS.width} x {CONFIGS.height}")
    st.sidebar.write("1ユーザ・1セッション同時リクエスト数: 1 件")
    if CONFIGS.global_max_active_requests > 0:
        st.sidebar.write(
            f"システム全体同時上限: {CONFIGS.global_max_active_requests} 件"
        )

    counters, _ = _global_state()
    st.sidebar.write(
        f"実行中: {counters['running']} 件 / キュー: {counters['queued']} 件"
    )

    st.sidebar.divider()
    #st.sidebar.caption(
    #    "ワークフロー内の {{positive_prompt}} / {{negative_prompt}} / {{seed}} / {{width}} / {{height}} "
    #    "をユーザ入力で置換します。"
    #)
    #st.sidebar.caption(
    #    "プレースホルダが存在しない場合はエラーになります。ワークフローを差し替えてご利用ください。"
    #)
    #st.sidebar.caption(f"テーマ: {theme_mode}")

    st.sidebar.caption(f"ログレベル: {CONFIGS.log_level}")


def _display_results(result: GenerationResult) -> None:
    st.success(f"生成完了 (prompt_id: {result.prompt_id})")
    for idx, image in enumerate(result.images, start=1):
        st.image(image.data, caption=f"出力 {idx}: {image.file_name}")


def _display_history() -> None:
    history = list(reversed(_get_history()))
    st.caption("過去の生成結果")
    if not history:
        st.info("まだ履歴がありません。生成するとここに表示されます。")
        return
    for idx, entry in enumerate(history, start=1):
        status = entry.get("status", "running")
        header = f"#{idx} [{status}]"
        with st.expander(header, expanded=True if status == "success" else False):
            if entry.get("prompt_id"):
                st.caption(f"prompt_id: {entry['prompt_id']}")
            if entry.get("completed_at"):
                st.caption(f"完了日時: {entry['completed_at']}")

            if status == "success":
                for img_idx, img_data in enumerate(entry.get("images", []), start=1):
                    col_img, col_meta = st.columns([3, 2])
                    # base64エンコードされた画像データをデコード
                    if isinstance(img_data, str):
                        img_bytes = storage_manager.decode_image(img_data)
                    else:
                        img_bytes = img_data
                    col_img.image(img_bytes, caption=f"出力 {img_idx}")

                    if img_idx == 1:
                        col_meta.markdown("**Positive Prompt**")
                        col_meta.code(
                            entry.get("positive_prompt", ""), language="text"
                        )
                        col_meta.markdown("**Negative Prompt**")
                        col_meta.code(
                            entry.get("negative_prompt", ""), language="text"
                        )
                        col_meta.markdown("**Seed**")
                        col_meta.code(str(entry.get("seed")), language="text")

                    col_meta.download_button(
                        label="画像をダウンロード",
                        data=img_bytes,
                        file_name=f"result_{entry.get('prompt_id','unknown')}_{img_idx}.png",
                        mime="image/png",
                        key=f"download_{entry.get('prompt_id','unknown')}_{img_idx}",
                    )

            elif status == "running":
                st.info("生成中... 履歴に画像が反映されるまでお待ちください")
                st.text(f"Positive: {entry.get('positive_prompt','')}")
                st.text(f"Negative: {entry.get('negative_prompt','')}")
                st.text(f"Seed: {entry.get('seed')}")

            else:
                st.error(entry.get("error", "不明なエラー"))


def _recover_running_job_history() -> None:
    """On reload, reconcile running entries by fetching results from ComfyUI."""

    if st.session_state.get("running_recovered"):
        return
    st.session_state["running_recovered"] = True

    history = list(_get_history())
    running_entries: list[dict[str, Any]] = []
    cleaned = False
    stale_running = 0
    for h in history:
        if h.get("status") != "running":
            continue
        prompt_id = h.get("prompt_id")
        if prompt_id:
            running_entries.append(h)
        else:
            # If reload happened before prompt_id acquisition, drop the stale entry
            cleaned = True
            stale_running += 1
    if cleaned:
        st.session_state["history"] = [h for h in history if not (h.get("status") == "running" and not h.get("prompt_id"))]
        _save_history()
        for _ in range(stale_running):
            _release_running_slot()
    if not running_entries:
        return

    for entry in running_entries:
        prompt_id = entry.get("prompt_id")
        if not isinstance(prompt_id, str) or not prompt_id:
            continue
        job_id = entry.get("job_id") or prompt_id
        try:
            result = asyncio.run(_fetch_existing_result(prompt_id, timeout=1.5, fast=True))
            _upsert_history(
                job_id,
                {
                    "positive_prompt": entry.get("positive_prompt", ""),
                    "negative_prompt": entry.get("negative_prompt", ""),
                    "seed": entry.get("seed"),
                    "images": [storage_manager.encode_image(img.data) for img in result.images],
                    "prompt_id": result.prompt_id,
                    "status": "success",
                    "completed_at": _current_timestamp(),
                },
            )
            _release_running_slot()
        except RuntimeError as exc:
            message = str(exc)
            transient_markers = [
                "did not populate",
                "history not ready",
                "history was empty",
            ]
            if any(marker in message for marker in transient_markers):
                # ComfyUI側でまだ履歴が固まっていない可能性が高いので、このラウンドでは待たずに継続
                continue
            sanitized_error = _sanitize_error_message(message)
            _upsert_history(
                job_id,
                {
                    "positive_prompt": entry.get("positive_prompt", ""),
                    "negative_prompt": entry.get("negative_prompt", ""),
                    "seed": entry.get("seed"),
                    "prompt_id": prompt_id,
                    "status": "failed",
                    "completed_at": _current_timestamp(),
                    "error": f"結果取得に失敗しました: {sanitized_error}",
                },
            )
            _release_running_slot()
        except Exception as exc:
            sanitized_error = _sanitize_error_message(str(exc))
            _upsert_history(
                job_id,
                {
                    "positive_prompt": entry.get("positive_prompt", ""),
                    "negative_prompt": entry.get("negative_prompt", ""),
                    "seed": entry.get("seed"),
                    "prompt_id": prompt_id,
                    "status": "failed",
                    "completed_at": _current_timestamp(),
                    "error": f"結果取得に失敗しました: {sanitized_error}",
                },
            )
            _release_running_slot()


def _process_job_queue() -> None:
    jobs = _get_jobs()
    running = _running_jobs_count()
    per_user_available = 0 if running >= 1 else 1

    global_available = None
    if CONFIGS.global_max_active_requests > 0:
        counters, lock = _global_state()
        with lock:
            global_available = max(0, CONFIGS.global_max_active_requests - counters["running"])
    if global_available is None:
        available = per_user_available
    else:
        available = min(per_user_available, global_available)
    if available <= 0:
        return

    for job in list(jobs):
        if available <= 0:
            break
        if job.get("status") != "queued":
            continue

        client_id = _get_client_id()
        counters, lock = _global_state()
        with lock:
            if CONFIGS.global_max_active_requests > 0 and counters["running"] >= CONFIGS.global_max_active_requests:
                continue
            _upsert_history(
                job["id"],
                {
                    "status": "running",
                    "positive_prompt": job["positive_prompt"],
                    "negative_prompt": job["negative_prompt"],
                    "seed": job["seed"],
                    "prompt_id": job.get("prompt_id"),
                },
            )
            _update_job(job["id"], status="running")
            user_counters, user_lock = _user_counters()
            with user_lock:
                user_counters[client_id] = user_counters.get(client_id, 0) + 1
            counters["queued"] = max(0, counters["queued"] - 1)
            counters["running"] += 1
        available -= 1

        try:
            template = _load_template(CONFIGS.workflow_path)
            workflow = render_workflow(
                template,
                positive_prompt=job["positive_prompt"],
                negative_prompt=job["negative_prompt"],
                seed=job["seed"],
                width=CONFIGS.width,
                height=CONFIGS.height,
            )
            placeholder = st.empty()
            placeholder.info(
                f"生成中... PromptID={job.get('prompt_id') or '取得中'} seed={job['seed']}"
            )

            def _set_prompt_id(pid: str) -> None:
                job["prompt_id"] = pid
                _upsert_history(job["id"], {"prompt_id": pid})
                placeholder.info(
                    f"生成中... PromptID={pid} seed={job['seed']}"
                )

            with st.spinner("ComfyUIで生成中..."):
                result = asyncio.run(
                    _run_generation(
                        workflow,
                        client_id,
                        on_prompt_id=_set_prompt_id,
                    )
                )

            _display_results(result)

            _upsert_history(
                job["id"],
                {
                    "positive_prompt": job["positive_prompt"],
                    "negative_prompt": job["negative_prompt"],
                    "seed": job["seed"],
                    "images": [storage_manager.encode_image(img.data) for img in result.images],
                    "prompt_id": result.prompt_id,
                    "status": "success",
                    "completed_at": _current_timestamp(),
                },
            )

        except WorkflowTemplateError as exc:
            sanitized_error = _sanitize_error_message(str(exc))
            st.error(sanitized_error)
            _upsert_history(
                job["id"],
                {
                    "positive_prompt": job["positive_prompt"],
                    "negative_prompt": job["negative_prompt"],
                    "seed": job["seed"],
                    "images": [],
                    "prompt_id": job.get("prompt_id"),
                    "status": "failed",
                    "error": sanitized_error,
                },
            )
        except Exception as exc:
            sanitized_error = _sanitize_error_message(str(exc))
            st.error(f"生成に失敗しました: {sanitized_error}")
            st.caption(
                "エラー詳細は上記メッセージを参照してください。/prompt 400 の場合は ComfyUI 側で"
                "ワークフロー JSON が受理されていない可能性があります。"
            )
            _append_history(
                {
                    "positive_prompt": job["positive_prompt"],
                    "negative_prompt": job["negative_prompt"],
                    "seed": job["seed"],
                    "images": [],
                    "prompt_id": job.get("prompt_id"),
                    "status": "failed",
                    "error": sanitized_error,
                }
            )
        finally:
            _remove_job(job["id"])
            st.rerun()


async def _run_generation(
    workflow: dict[str, Any], client_id: str, on_prompt_id: Callable[[str], None] | None = None
) -> GenerationResult:
    client = ComfyUIClient(
        api_base=CONFIGS.api_base,
        ws_url=CONFIGS.ws_url,
        timeout=CONFIGS.request_timeout,
        log_level=CONFIGS.log_level,
    )
    return await client.generate(workflow, client_id, on_prompt_id=on_prompt_id)


async def _fetch_existing_result(prompt_id: str, *, timeout: float | None = None, fast: bool = False) -> GenerationResult:
    client = ComfyUIClient(
        api_base=CONFIGS.api_base,
        ws_url=CONFIGS.ws_url,
        timeout=timeout or CONFIGS.request_timeout,
        log_level=CONFIGS.log_level,
    )
    return await client.fetch_existing(prompt_id, fast=fast)


def main() -> None:
    # セッション初期化
    session_manager.initialize()
    session_manager.sync_from_local_storage()

    theme_mode = "dark"
    _apply_theme(theme_mode)

    st.title("Streamlit Based ComfyUI Web Tool")

    _render_sidebar(theme_mode)

    _recover_running_job_history()

    # Auto-refresh every 10s while there are running entries with prompt_id to pick up completions.
    history_snapshot = _get_history()
    if any(h.get("status") == "running" and h.get("prompt_id") for h in history_snapshot):
        st.markdown(
            "<meta http-equiv='refresh' content='10'>",
            unsafe_allow_html=True,
        )

    col_left, col_right = st.columns(2)

    with col_left:
        st.caption("プロンプト/ネガティブ/シードのみ編集可能なComfyUIクライアント")

        positive_prompt = st.text_area(
            "プロンプト(描画したい内容を入力)",
            height=160,
            placeholder="描画したい内容を入力",
            value="Pikachu",
        )
        negative_prompt = st.text_area(
            "ネガティブプロンプト(除外したい内容を入力)",
            height=120,
            placeholder="除外したい内容を入力",
            value="lowres, bad anatomy, error, missing fingers",
        )

        seed_value = st.number_input(
            "シード値 (-1 の場合はランダム)", min_value=-1, step=1, value=-1, max_value=2**31 - 1
        )

        if st.button("画像を生成する", type="primary"):
            if _running_jobs_count() >= 1:
                st.error("1ユーザあたりの同時リクエスト上限に達しました。完了をお待ちください。")
            else:
                if CONFIGS.global_max_active_requests > 0:
                    counters, lock = _global_state()
                    with lock:
                        if counters["running"] >= CONFIGS.global_max_active_requests:
                            st.error("システム全体の同時実行上限に達しています。完了をお待ちください。")
                            st.stop()

                job_id = str(ULID())
                chosen_seed = _random_seed() if int(seed_value) < 0 else int(seed_value)
                _add_job(
                    {
                        "id": job_id,
                        "status": "queued",
                        "positive_prompt": positive_prompt,
                        "negative_prompt": negative_prompt,
                        "seed": chosen_seed,
                        "prompt_id": None,
                    }
                )
                st.rerun()

        _process_job_queue()

    with col_right:
        _display_history()

    # セッション終了時にLocalStorageに保存
    session_manager.sync_to_local_storage()

if __name__ == "__main__":
    main()
