"""장애 다발 기기 분석 PoC — Flask 웹 앱 (Streamlit 대체)."""
from __future__ import annotations

import io
import logging
import os
from typing import Any

import api_settings
import pandas as pd
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

import ai_classifier
import analyzer
import cloud_bootstrap
import data_loader
import db
import drilldown
from app_common import (
    allow_c_unconfirmed,
    clear_grouping_draft,
    get_fault_content_filter,
    get_grouping_draft,
    get_home_selected_month,
    get_incidents_df,
    get_nav_target,
    get_nav_to_c,
    get_pending_uploads,
    set_allow_c_unconfirmed,
    set_fault_content_filter,
    set_grouping_draft,
    set_home_selected_month,
    set_nav_target,
    set_nav_to_c,
    set_pending_uploads,
)
from chart_utils import (
    daily_line_figure,
    daily_multi_line_figure,
    distribution_bar_figure,
    figure_html,
    five_day_flow_figure,
    top10_bar_figure,
    trend_line_figure,
    multi_entity_monthly_figure,
)
from config import (
    BASE_DIR,
    FAULT_TYPES,
    LOCAL_APP_URL,
    MAPPING_FILE,
    MAX_UPLOAD_FILES,
    PORT,
    PRIORITY_TOP_N,
    TOP_N,
)

api_settings.load_env()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "atm-fault-poc-local-dev-key")

cloud_bootstrap.ensure_runtime_data()


class _SkipStreamlitPollFilter(logging.Filter):
    """예전 Streamlit 탭의 /_stcore 폴링 404 로그 숨김."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "/_stcore/" not in record.getMessage()


logging.getLogger("werkzeug").addFilter(_SkipStreamlitPollFilter())


@app.after_request
def _cors_for_live_server(response):
    """index.html(Live Server 5500)에서 API 상태 확인용."""
    if request.path.startswith("/_stcore/"):
        response.headers["Access-Control-Allow-Origin"] = "*"
    return response


@app.route("/_stcore/health")
def stcore_health():
    return "ok", 200


@app.route("/_stcore/host-config")
def stcore_host_config():
    return jsonify({"allowedOrigins": [], "useExternalAuthToken": False})


@app.route("/_stcore/<path:subpath>")
def stcore_fallback(subpath: str):
    return "", 204

TAB_CONFIG = {
    "지점": {"column": "지점명", "nav_type": "지점", "all_items": False},
    "기번": {"column": "기번", "nav_type": "기번", "all_items": False},
    "기종": {"column": "기종", "nav_type": "기종", "all_items": True},
}

ANALYSIS_MODES = {
    "기번 (개별 ATM)": "기번",
    "지점": "지점명",
    "기종 (모델 전체)": "기종",
}


def table_html(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return '<p class="muted">표시할 데이터가 없습니다.</p>'
    return df.to_html(index=False, classes="data-table", border=0)


def _current_app_url() -> str:
    try:
        return request.url_root.rstrip("/")
    except RuntimeError:
        return LOCAL_APP_URL.rstrip("/")


def _is_local_host() -> bool:
    try:
        host = request.host.split(":")[0].lower()
        return host in ("localhost", "127.0.0.1")
    except RuntimeError:
        return True


@app.context_processor
def inject_globals() -> dict[str, Any]:
    key = api_settings.get_api_key()
    app_url = _current_app_url()
    return {
        "app_url": app_url,
        "app_mode": "로컬 실행" if _is_local_host() else "웹 서비스",
        "api_key_set": bool(key),
        "api_key_masked": api_settings.mask_api_key(key),
        "nav_items": [
            {"endpoint": "a_compare", "label": "전체비교", "tone": "blue"},
            {"endpoint": "flow", "label": "장애다발기기분석", "tone": "orange"},
            {"endpoint": "code_analysis", "label": "모듈별장애분석", "tone": "purple"},
            {"endpoint": "priority", "label": "중점장애관리", "tone": "red"},
            {"endpoint": "data_manage", "label": "데이터관리", "tone": "green"},
        ],
    }


@app.route("/api-key", methods=["POST"])
def save_api_key():
    action = request.form.get("action", "save")
    if action == "delete":
        api_settings.delete_api_key()
        flash("API 키를 삭제했습니다.", "warning")
    else:
        try:
            api_settings.save_api_key(request.form.get("api_key", ""))
            flash("API 키가 .env 파일에 저장되었습니다.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
    return redirect(request.referrer or url_for("a_compare"))


@app.route("/")
def index():
    return redirect(url_for("a_compare"))


@app.route("/compare")
def a_compare():
    df = get_incidents_df()
    if df.empty:
        return render_template("a_compare.html", empty=True, df=df)

    months = sorted(df["연월"].unique())
    selected_month = request.args.get("month") or months[-1]
    if selected_month not in months:
        selected_month = months[-1]

    tab = request.args.get("tab", "지점")
    if tab not in TAB_CONFIG:
        tab = "지점"

    daily_entity = request.args.get("daily_entity", "")
    if tab != "지점":
        daily_entity = ""

    aggregates = analyzer.aggregate_monthly(df)
    sections: dict[str, dict[str, Any]] = {}

    for tab_key, cfg in TAB_CONFIG.items():
        col_name = cfg["column"]
        counts = aggregates[tab_key if tab_key != "지점" else "지점"]
        if cfg["all_items"]:
            month_data = counts[counts["연월"] == selected_month].copy()
            title_suffix = f"{selected_month} — {tab_key}별 전체"
        else:
            top10_all = analyzer.top_n_by_month(counts, col_name, n=TOP_N)
            month_data = top10_all[top10_all["연월"] == selected_month].copy()
            title_suffix = f"{selected_month} — {tab_key}별 TOP{TOP_N}"

        daily_html = ""
        daily_options: list[dict[str, str | int]] = []
        selected_daily = ""
        last_day = 31
        if not month_data.empty:
            month_data = month_data.sort_values("장애건수", ascending=False).reset_index(drop=True)
            month_data.insert(0, "순위", range(1, len(month_data) + 1))
            if tab_key == "기번":
                month_data = analyzer.attach_branch_name(
                    df, month_data, selected_month=selected_month
                )
            chart_html = figure_html(
                top10_bar_figure(
                    month_data,
                    col_name,
                    title_suffix,
                    suffix_col="지점이름" if tab_key == "기번" else None,
                )
            )
            labels = month_data[col_name].tolist()

            if tab_key == "지점":
                daily_options = [
                    {
                        "value": str(row[col_name]),
                        "label": f"{row[col_name]} ({int(row['장애건수']):,}건)",
                        "count": int(row["장애건수"]),
                    }
                    for _, row in month_data.iterrows()
                ]
                if daily_entity in labels:
                    selected_daily = daily_entity

            daily_df, last_day = analyzer.daily_trend_by_entities(
                df, selected_month, col_name, labels
            )
            plot_label_col = col_name
            if tab_key == "기번" and "지점이름" in month_data.columns:
                name_map = {
                    row[col_name]: f"{row[col_name]} ({row['지점이름']})"
                    for _, row in month_data.iterrows()
                    if row.get("지점이름")
                }
                daily_df = daily_df.copy()
                daily_df["표시명"] = daily_df[col_name].map(name_map).fillna(daily_df[col_name])
                plot_label_col = "표시명"

            chart_daily_df = daily_df
            if tab_key == "지점" and selected_daily:
                chart_daily_df = daily_df[daily_df[col_name] == selected_daily].copy()
                daily_title = (
                    f"{selected_month} — {selected_daily} 일별 장애 추이 (1~{last_day}일)"
                )
            else:
                daily_title = (
                    f"{selected_month} — {tab_key}별 일별 장애 추이 (1~{last_day}일)"
                )

            daily_html = figure_html(
                daily_multi_line_figure(
                    chart_daily_df,
                    plot_label_col,
                    daily_title,
                    last_day,
                )
            )
        else:
            chart_html = ""
            labels = []

        sections[tab_key] = {
            "month_data": month_data if not month_data.empty else pd.DataFrame(),
            "table_html": table_html(month_data) if not month_data.empty else "",
            "chart_html": chart_html,
            "daily_html": daily_html,
            "daily_options": daily_options,
            "selected_daily": selected_daily,
            "last_day": last_day,
            "labels": labels,
            "nav_type": cfg["nav_type"],
            "title_suffix": title_suffix,
        }

    return render_template(
        "a_compare.html",
        empty=False,
        df=df,
        months=months,
        selected_month=selected_month,
        tab=tab,
        sections=sections,
        top_n=TOP_N,
    )


@app.route("/goto-flow", methods=["POST"])
def goto_flow():
    set_nav_target(
        request.form["nav_type"],
        request.form["nav_value"],
        request.form["selected_month"],
    )
    flash(
        f"선택: {request.form['nav_type']}={request.form['nav_value']} → 장애다발기기분석",
        "success",
    )
    return redirect(url_for("flow"))


@app.route("/goto-code-nav", methods=["POST"])
def goto_code_nav():
    nav_type = request.form["nav_type"]
    nav_value = request.form["nav_value"]
    month = request.form["selected_month"]
    df = get_incidents_df()
    key_map = {"기번": "기번", "지점": "지점명", "기종": "기종"}
    key_col = key_map.get(nav_type, "기번")
    subset = df[(df["연월"] == month) & (df[key_col].astype(str) == str(nav_value))]
    top_fault = None
    if not subset.empty:
        top_fault = subset["세부장애"].value_counts().index[0]
    set_nav_to_c(month, top_fault)
    params: dict[str, str] = {"month": month}
    if nav_type == "지점":
        params["branch"] = nav_value
    elif nav_type == "기번":
        params["device"] = nav_value
        if top_fault:
            params["fault"] = top_fault
    flash(f"선택: {nav_type}={nav_value} → 모듈별장애분석", "success")
    return redirect(url_for("code_analysis", **params))


@app.route("/data", methods=["GET", "POST"])
def data_manage():
    df = get_incidents_df()
    selected_month = get_home_selected_month(df)

    if request.method == "POST":
        action = request.form.get("action")
        if action == "upload":
            files = request.files.getlist("files")
            if not files or not files[0].filename:
                flash("업로드할 파일을 선택하세요.", "error")
            else:
                if len(files) > MAX_UPLOAD_FILES:
                    flash(
                        f"최대 {MAX_UPLOAD_FILES}개까지만 처리합니다. "
                        f"초과 {len(files) - MAX_UPLOAD_FILES}개는 무시됩니다.",
                        "warning",
                    )
                    files = files[:MAX_UPLOAD_FILES]
                _process_uploads(files)
        elif action == "delete_month":
            month = request.form.get("month")
            if month:
                db.delete_month(month)
                flash(f"{month} 데이터를 삭제했습니다.", "success")
        elif action == "save_pending":
            _save_pending_uploads()
        elif action == "set_month":
            set_home_selected_month(request.form.get("month", ""))
        elif action == "filter_all":
            month = request.form.get("month")
            if month and not df.empty:
                month_df = df[df["연월"] == month]
                opts = sorted(month_df["장애내용"].dropna().astype(str).unique().tolist())
                set_fault_content_filter(month, opts)
        elif action == "filter_none":
            month = request.form.get("month")
            if month:
                set_fault_content_filter(month, [])
        elif action == "filter_apply":
            month = request.form.get("month")
            selected = request.form.getlist("fault_content")
            if month:
                set_fault_content_filter(month, selected)
        elif action == "grouping_run":
            if df.empty:
                flash("데이터가 없습니다.", "error")
            else:
                draft, _message = ai_classifier.run_classification(df)
                draft["confirmed_type"] = draft["ai_type"]
                set_grouping_draft(draft)
                db.save_grouping_rules(draft, confirmed=False)
        elif action == "grouping_confirm":
            draft = get_grouping_draft()
            if draft.empty:
                flash("그룹핑 초안이 없습니다.", "error")
            else:
                editable = draft.copy()
                if not df.empty:
                    editable = ai_classifier.attach_detail_lists(df, editable)
                for _, row in editable.iterrows():
                    code = row["장애코드2"]
                    val = request.form.get(f"type_{code}", row["confirmed_type"])
                    editable.loc[editable["장애코드2"] == code, "confirmed_type"] = val
                    details = row.get("세부장애목록")
                    if isinstance(details, list) and details:
                        editable.loc[
                            editable["장애코드2"] == code, "세부장애"
                        ] = ", ".join(details)
                editable = editable.drop(columns=["세부장애목록"], errors="ignore")
                db.save_grouping_rules(editable, confirmed=True)
                set_grouping_draft(editable)
                flash("장애코드 변경 내용이 저장되었습니다.", "success")
        return redirect(url_for("data_manage"))

    pending = get_pending_uploads()
    meta = db.list_uploaded_months()
    analysis = _build_analysis_context(df, selected_month)
    grouping_draft = get_grouping_draft()
    if not grouping_draft.empty and not df.empty:
        grouping_draft = ai_classifier.attach_detail_lists(df, grouping_draft)
    preview = _build_preview(df, selected_month)
    pending_rows = []
    for result in pending:
        existing = meta[meta["연월"] == result.연월]
        pending_rows.append(
            {
                "filename": result.filename,
                "연월": result.연월,
                "upload_count": len(result.df),
                "existing_filename": existing.iloc[0]["source_filename"] if not existing.empty else None,
                "existing_count": int(existing.iloc[0]["건수"]) if not existing.empty else None,
            }
        )

    return render_template(
        "data_manage.html",
        df=df,
        meta=meta,
        meta_html=table_html(meta),
        pending_rows=pending_rows,
        selected_month=selected_month,
        analysis=analysis,
        preview=preview,
        grouping_records=grouping_draft.to_dict("records") if not grouping_draft.empty else [],
        fault_types=FAULT_TYPES,
        mapping_exists=MAPPING_FILE.exists(),
        max_upload_files=MAX_UPLOAD_FILES,
    )


def _build_preview(df: pd.DataFrame, selected_month: str | None) -> dict[str, Any]:
    if df.empty or not selected_month:
        return {"empty": True}
    month_df = df[df["연월"] == selected_month]
    preview_cols = [
        "연월", "점번", "지점명", "기번", "기종", "발생일자", "세부장애", "장애내용", "장애코드2",
    ]
    return {
        "empty": False,
        "month_count": len(month_df),
        "total_count": len(df),
        "branch_count": month_df["지점명"].nunique(),
        "device_count": month_df["기번"].nunique(),
        "table_html": table_html(month_df[preview_cols].head(20)),
    }


def _build_analysis_context(df: pd.DataFrame, selected_month: str | None) -> dict[str, Any]:
    if df.empty or not selected_month:
        return {"empty": True}

    months = sorted(df["연월"].unique())
    if selected_month not in months:
        selected_month = months[-1]

    month_df = df[df["연월"] == selected_month]
    all_options = sorted(month_df["장애내용"].dropna().astype(str).unique().tolist())
    selected_contents = get_fault_content_filter(selected_month, month_df)
    if not selected_contents:
        return {
            "empty": False,
            "months": months,
            "selected_month": selected_month,
            "all_options": all_options,
            "selected_contents": [],
            "no_filter": True,
        }

    filtered_df = df[df["장애내용"].isin(selected_contents)]
    aggregates = analyzer.aggregate_monthly(filtered_df)
    anomalies, anomaly_message = analyzer.detect_anomalies_for_devices(filtered_df)

    def tab_data(key: str, col: str, all_items: bool) -> dict[str, Any]:
        data = aggregates[key]
        if all_items:
            md = data[data["연월"] == selected_month]
        else:
            top10 = analyzer.top_n_by_month(data, col)
            md = top10[top10["연월"] == selected_month]
        return {"table_html": table_html(md), "empty": md.empty}

    return {
        "empty": False,
        "months": months,
        "selected_month": selected_month,
        "all_options": all_options,
        "selected_contents": selected_contents,
        "no_filter": False,
        "tabs": {
            "기종": tab_data("기종", "기종", True),
            "지점": tab_data("지점", "지점명", False),
            "기번": tab_data("기번", "기번", False),
        },
        "anomalies_html": table_html(anomalies),
        "anomaly_message": anomaly_message,
        "anomalies_empty": anomalies.empty,
    }


def _process_uploads(uploaded_files) -> None:
    results = data_loader.parse_uploaded_files(uploaded_files)
    ready: list = []
    success_count = 0

    for result in results:
        if not result.ok:
            flash(f"[{result.filename}] {', '.join(result.errors)}", "error")
            continue
        if db.month_exists(result.연월):
            ready.append(result)
        else:
            success_count += _save_result(result, "replace")

    if ready:
        set_pending_uploads(ready)
        flash(
            f"동일 연월 파일 {len(ready)}건 — 교체/추가 선택 후 저장하세요.",
            "warning",
        )
    elif success_count:
        clear_grouping_draft()
        flash(f"{success_count}개 파일 저장 완료.", "success")


def _save_result(result, mode: str) -> int:
    saved = db.save_month_data(result.df, result.연월, result.filename, mode=mode)
    flash(f"[{result.filename}] {result.연월} — {saved:,}건 저장 ({mode})", "success")
    for warning in result.warnings:
        flash(warning, "warning")
    if result.unmapped_codes:
        flash(f"매핑되지 않은 세부장애: {', '.join(result.unmapped_codes[:10])}", "warning")
    return 1


def _save_pending_uploads() -> None:
    pending = get_pending_uploads()
    to_save = []
    for result in pending:
        choice = request.form.get(f"pending_{result.filename}", "cancel")
        if choice == "replace":
            to_save.append((result, "replace"))
        elif choice == "append":
            to_save.append((result, "append"))
    for result, mode in to_save:
        _save_result(result, mode)
    set_pending_uploads([])
    clear_grouping_draft()
    if to_save:
        set_home_selected_month(to_save[0][0].연월)


@app.route("/flow", methods=["GET", "POST"])
def flow():
    df = get_incidents_df()
    if df.empty:
        return render_template("flow.html", empty=True)

    nav_type, nav_value, nav_month = get_nav_target()
    mode_labels = list(ANALYSIS_MODES.keys())

    if request.method == "POST":
        action = request.form.get("action")
        if action == "save_note":
            db.save_anomaly_note(
                request.form["target_type"],
                request.form["key_value"],
                request.form["month"],
                "confirmed" in request.form,
                request.form.get("memo", ""),
            )
            flash(f"{request.form['month']} 메모 저장 완료", "success")
            return redirect(
                url_for(
                    "flow",
                    mode=request.form.get("mode"),
                    value=request.form.get("key_value"),
                    flow_month=request.form.get("flow_month"),
                    view=request.form.get("view", "daily"),
                )
            )
        elif action == "goto_code":
            fault = request.form.get("link_fault")
            set_nav_to_c(request.form["link_month"], None if fault in ("", "(전체)") else fault)
            flash("모듈별장애분석 조건을 전달했습니다.", "success")
            return redirect(url_for("code_analysis"))

    selected_mode = request.args.get("mode") or _resolve_default_mode(nav_type)
    if selected_mode not in mode_labels:
        selected_mode = mode_labels[0]
    key_col = ANALYSIS_MODES[selected_mode]
    target_type = key_col if key_col != "지점명" else "지점"

    all_months = sorted(df["연월"].unique().tolist())
    flow_month = request.args.get("flow_month")
    if flow_month not in all_months:
        flow_month = (
            nav_month if nav_month in all_months else (all_months[-1] if all_months else None)
        )

    show_count = key_col in ("기번", "지점명")

    def load_options(month: str | None) -> list[dict[str, str | int]]:
        items = analyzer.entity_select_options(
            df, key_col, month, show_count=show_count
        )
        if items:
            return items
        if month:
            return analyzer.entity_select_options(
                df, key_col, None, show_count=show_count
            )
        return []

    option_items = load_options(flow_month)
    options = [str(item["value"]) for item in option_items]

    multi_select = key_col in ("기번", "지점명")
    default_value = (
        nav_value
        if nav_type == target_type and nav_value in options
        else (options[0] if options else "")
    )

    if multi_select:
        selected_values = request.args.getlist("value")
        if not selected_values:
            legacy = request.args.get("value", "")
            if legacy:
                selected_values = [v.strip() for v in legacy.split(",") if v.strip()]
        selected_values = [v for v in selected_values if v in options]
        if not selected_values and default_value:
            selected_values = [default_value]
    else:
        single = request.args.get("value") or default_value
        if single not in options:
            single = default_value
        selected_values = [single] if single else []

    selected_value = selected_values[0] if selected_values else ""

    display_values = [
        analyzer.format_device_label(v, analyzer.primary_branch_for_device(df, v))
        if key_col == "기번"
        else v
        for v in selected_values
    ]
    label_short = ", ".join(display_values[:3])
    if len(selected_values) > 3:
        label_short += f" 외 {len(selected_values) - 3}개"

    chart_data = (
        analyzer.get_trend_chart_data(df, key_col, selected_value) if selected_value else pd.DataFrame()
    )
    month_count = len(chart_data)

    if len(selected_values) == 1:
        entity_months = analyzer.available_months_for_entity(df, key_col, selected_value)
    else:
        entity_months = sorted(
            {
                month
                for val in selected_values
                for month in analyzer.available_months_for_entity(df, key_col, val)
            }
        )
    if not entity_months:
        entity_months = all_months

    if flow_month not in entity_months:
        flow_month = entity_months[-1]
        option_items = load_options(flow_month) or option_items
        options = [str(item["value"]) for item in option_items]
        selected_values = [v for v in selected_values if v in options] or (
            [options[0]] if options else []
        )
        selected_value = selected_values[0] if selected_values else ""

    view = request.args.get("view", "daily")
    if view not in ("daily", "monthly"):
        view = "daily"

    bucket_df = pd.DataFrame()
    daily_df = pd.DataFrame()
    last_day = 30
    flow_html = ""
    flow_table_html = ""
    chart_title = ""
    if flow_month and selected_values:
        if view == "monthly":
            chart_title = f"{label_short} — 월별 추이"
            if len(selected_values) == 1:
                monthly_data = analyzer.get_trend_chart_data(df, key_col, selected_value)
                flow_html = figure_html(trend_line_figure(monthly_data, chart_title))
                flow_table_html = table_html(monthly_data) if not monthly_data.empty else ""
            else:
                name_map = (
                    dict(zip(selected_values, display_values)) if key_col == "기번" else None
                )
                flow_html = figure_html(
                    multi_entity_monthly_figure(
                        df, key_col, selected_values, chart_title, display_names=name_map
                    )
                )
                flow_table_html = ""
            month_total = int(
                df[(df["연월"] == flow_month) & (df[key_col].isin(selected_values))].shape[0]
            )
        else:
            daily_raw, last_day = analyzer.daily_trend_by_entities(
                df, flow_month, key_col, selected_values
            )
            chart_title = f"{label_short} — {flow_month} 일별 장애 추이"
            if len(selected_values) == 1:
                daily_df = daily_raw[daily_raw[key_col] == selected_value].copy()
                daily_df["발생일"] = daily_df["일"].apply(
                    lambda d: f"{flow_month}-{int(d):02d}"
                )
                flow_html = figure_html(
                    daily_line_figure(daily_df[["발생일", "장애건수"]], chart_title)
                )
                flow_table_html = table_html(daily_df[["일", "장애건수"]])
            else:
                plot_df = daily_raw.copy()
                if key_col == "기번":
                    plot_df[key_col] = plot_df[key_col].map(
                        lambda x: analyzer.format_device_label(
                            x, analyzer.primary_branch_for_device(df, x)
                        )
                    )
                flow_html = figure_html(
                    daily_multi_line_figure(plot_df, key_col, chart_title, last_day)
                )
                flow_table_html = ""
            month_total = int(daily_raw["장애건수"].sum()) if not daily_raw.empty else 0
            daily_df = daily_raw
            bucket_df = daily_df

    if view == "monthly" and not flow_html:
        month_total = 0
    elif view == "daily" and not flow_html:
        month_total = 0

    anomalies, anomaly_message = analyzer.get_entity_anomalies(df, key_col, selected_value)
    saved_notes = db.load_anomaly_notes(target_type, selected_value)
    note_map = {row["연월"]: row for _, row in saved_notes.iterrows()} if not saved_notes.empty else {}

    subset = df[df[key_col] == selected_value]
    link_months = chart_data["연월"].tolist() if not chart_data.empty else []
    link_faults = sorted(subset["세부장애"].dropna().unique().tolist())

    return render_template(
        "flow.html",
        empty=False,
        nav_type=nav_type,
        nav_value=nav_value,
        nav_month=nav_month,
        mode_labels=mode_labels,
        selected_mode=selected_mode,
        selected_value=selected_value,
        selected_values=selected_values,
        multi_select=multi_select,
        option_items=option_items,
        options=options,
        target_type=target_type,
        key_col=key_col,
        chart_data=chart_data,
        chart_table_html=table_html(chart_data) if month_count > 1 else "",
        flow_html=flow_html,
        flow_table_html=flow_table_html,
        chart_title=chart_title,
        label_short=label_short,
        bucket_table_html=flow_table_html,
        view=view,
        flow_month=flow_month,
        entity_months=entity_months,
        last_day=last_day,
        month_total=month_total,
        month_count=month_count,
        anomaly_records=anomalies.to_dict("records") if not anomalies.empty else [],
        anomalies_html=table_html(anomalies[["연월", "대상", "장애건수", "이동평균", "평소대비증가율"]])
        if not anomalies.empty
        else "",
        anomaly_message=anomaly_message,
        note_map=note_map,
        link_months=link_months,
        link_faults=link_faults,
    )


def _with_detail_labels(scope: pd.DataFrame, counts: pd.DataFrame) -> pd.DataFrame:
    out = counts.copy()
    if out.empty:
        return out
    out["표시"] = analyzer.detail_chart_labels(scope, out)
    return out


def _resolve_default_mode(nav_type: str | None) -> str:
    if nav_type == "기번":
        return "기번 (개별 ATM)"
    if nav_type == "기종":
        return "기종 (모델 전체)"
    if nav_type == "지점":
        return "지점"
    return "기번 (개별 ATM)"


@app.route("/code", methods=["GET", "POST"])
def code_analysis():
    df = get_incidents_df()
    if df.empty:
        return render_template("code_analysis.html", empty=True)

    if not db.is_grouping_confirmed() and not allow_c_unconfirmed():
        return render_template("code_analysis.html", empty=False, need_grouping=True)

    if request.method == "POST" and request.form.get("action") == "allow_unconfirmed":
        set_allow_c_unconfirmed(True)
        return redirect(url_for("code_analysis"))

    grouped = drilldown.attach_grouping(df, confirmed_only=db.is_grouping_confirmed())
    link_month, link_fault = get_nav_to_c()
    months = sorted(grouped["연월"].unique())
    selected_month = request.args.get("month") or (
        link_month if link_month in months else months[-1]
    )
    if selected_month not in months:
        selected_month = months[-1]

    scope = drilldown.filter_scope(grouped, 연월=selected_month)
    if link_fault and link_month == selected_month:
        scope = drilldown.filter_scope(scope, 세부장애=link_fault)

    ai_types = list(FAULT_TYPES)
    if scope.empty:
        return render_template(
            "code_analysis.html",
            empty=False,
            need_grouping=False,
            no_data=True,
            selected_month=selected_month,
            months=months,
        )

    selected_type = request.args.get("ai_type") or ai_types[0]
    if selected_type not in ai_types:
        selected_type = ai_types[0]
    type_scope = drilldown.filter_scope(scope, ai_type=selected_type)

    scope_branch = request.args.get("scope_branch", "")
    scope_device = request.args.get("scope_device", "")

    branch_filter_list = drilldown.distribution(type_scope, "지점명", top_n=50)
    branch_filter_rows = (
        branch_filter_list.to_dict("records") if not branch_filter_list.empty else []
    )
    branch_filter_options = (
        branch_filter_list["지점명"].tolist() if not branch_filter_list.empty else []
    )
    device_filter_scope = type_scope
    if scope_branch:
        device_filter_scope = drilldown.filter_scope(type_scope, 지점명=scope_branch)
    device_filter_items = analyzer.entity_select_options(
        device_filter_scope, "기번", selected_month, show_count=True
    )
    device_filter_values = [str(item["value"]) for item in device_filter_items]

    if scope_branch and scope_branch not in branch_filter_options:
        scope_branch = ""
    if scope_device and scope_device not in device_filter_values:
        scope_device = ""

    analysis_scope = type_scope
    if scope_branch:
        analysis_scope = drilldown.filter_scope(analysis_scope, 지점명=scope_branch)
    if scope_device:
        analysis_scope = drilldown.filter_scope(analysis_scope, 기번=scope_device)

    scope = analysis_scope

    fault_list = analyzer.enrich_fault_distribution(scope, drilldown.distribution(scope, "세부장애"))
    fault_options = fault_list["세부장애"].tolist() if not fault_list.empty else []
    selected_fault = request.args.get("fault") or (
        link_fault if link_fault in fault_options else (fault_options[0] if fault_options else "")
    )
    if selected_fault not in fault_options and fault_options:
        selected_fault = fault_options[0]
    if selected_fault:
        scope = drilldown.filter_scope(scope, 세부장애=selected_fault)

    code2_list = drilldown.distribution(scope, "장애코드2")
    code2_options = code2_list["장애코드2"].tolist() if not code2_list.empty else []
    selected_code2 = request.args.get("code2") or (code2_options[0] if code2_options else "")
    if selected_code2 not in code2_options and code2_options:
        selected_code2 = code2_options[0]
    if selected_code2:
        scope = drilldown.filter_scope(scope, 장애코드2=selected_code2)

    branch_list = drilldown.distribution(scope, "지점명", top_n=20)
    branch_options = branch_list["지점명"].tolist() if not branch_list.empty else []
    selected_branch = request.args.get("branch", "")
    if selected_branch and selected_branch not in branch_options:
        selected_branch = ""

    device_list = pd.DataFrame()
    branch_scope_count = 0
    selected_device = request.args.get("device", "")
    if selected_branch:
        branch_scope = drilldown.filter_scope(scope, 지점명=selected_branch)
        branch_scope_count = len(branch_scope)
        device_list = drilldown.distribution(branch_scope, "기번", top_n=20)
        device_options = device_list["기번"].tolist() if not device_list.empty else []
        if selected_device and selected_device not in device_options:
            selected_device = ""
        if selected_device:
            scope = drilldown.filter_scope(branch_scope, 기번=selected_device)
        else:
            scope = branch_scope
    else:
        selected_device = ""

    daily = drilldown.daily_trend(scope) if selected_device else pd.DataFrame()

    def build_url(**kwargs):
        params = {
            "month": selected_month,
            "ai_type": selected_type,
            "scope_branch": scope_branch,
            "scope_device": scope_device,
            "fault": selected_fault,
            "code2": selected_code2,
            "branch": selected_branch,
            "device": selected_device,
        }
        params.update(kwargs)
        return url_for("code_analysis", **{k: v for k, v in params.items() if v})

    return render_template(
        "code_analysis.html",
        empty=False,
        need_grouping=False,
        no_data=False,
        link_month=link_month,
        link_fault=link_fault,
        months=months,
        selected_month=selected_month,
        ai_types=ai_types,
        selected_type=selected_type,
        scope_branch=scope_branch,
        scope_device=scope_device,
        branch_filter_rows=branch_filter_rows,
        branch_filter_options=branch_filter_options,
        device_filter_items=device_filter_items,
        scope_count=len(scope),
        fault_list=fault_list,
        fault_chart=figure_html(
            distribution_bar_figure(
                _with_detail_labels(scope, fault_list),
                "세부장애",
                f"{selected_type} — 세부장애 분포 (건수)",
                top_n=15,
                display_col="표시",
            )
        )
        if not fault_list.empty
        else "",
        selected_fault=selected_fault,
        code2_list=code2_list,
        code2_chart=figure_html(
            distribution_bar_figure(code2_list, "장애코드2", f"{selected_fault} — 장애코드2 분포")
        )
        if not code2_list.empty
        else "",
        selected_code2=selected_code2,
        branch_list=branch_list,
        branch_chart=figure_html(
            distribution_bar_figure(branch_list, "지점명", f"{selected_code2} — 지점별 TOP20", top_n=20)
        )
        if not branch_list.empty
        else "",
        selected_branch=selected_branch,
        device_list=device_list,
        device_chart=figure_html(
            distribution_bar_figure(
                device_list, "기번", f"{selected_branch} — 지점별 분포", top_n=20
            )
        )
        if not device_list.empty
        else "",
        selected_device=selected_device,
        branch_scope_count=branch_scope_count,
        daily=daily,
        daily_chart=figure_html(
            daily_line_figure(daily, f"{selected_device} — {selected_month} 일별 추이")
        )
        if not daily.empty
        else "",
        build_url=build_url,
        summary={
            "연월": selected_month,
            "AI유형": selected_type,
            "필터_지점": scope_branch or "(전체)",
            "필터_기번": scope_device or "(전체)",
            "세부장애": selected_fault,
            "장애코드2": selected_code2,
            "지점명": selected_branch,
            "기번": selected_device,
            "잔여건수": len(scope),
        },
    )


@app.route("/priority", methods=["GET", "POST"])
def priority():
    df = get_incidents_df()
    if df.empty:
        return render_template("priority.html", empty=True)

    top_n = int(request.args.get("top_n", PRIORITY_TOP_N))
    top_n = max(5, min(50, top_n))
    ranked = analyzer.compute_priority_ranking(df, top_n=top_n)

    if request.method == "POST":
        action = request.form.get("action")
        selected = request.form.get("device")
        latest_month = sorted(df["연월"].unique())[-1]
        if action == "goto_flow" and selected:
            set_nav_target("기번", selected, latest_month)
            flash(f"기번 {selected} → 장애다발기기분석으로 이동합니다.", "success")
            return redirect(url_for("flow"))
        if action == "goto_code" and selected:
            subset = df[(df["기번"] == selected) & (df["연월"] == latest_month)]
            top_fault = subset["세부장애"].value_counts().index[0] if len(subset) > 0 else None
            set_nav_to_c(latest_month, top_fault)
            flash(f"연월={latest_month}, 세부장애={top_fault or '전체'} → 모듈별장애분석으로 이동합니다.", "success")
            return redirect(url_for("code_analysis"))

    chart_html = ""
    if not ranked.empty:
        chart_df = ranked.copy()
        chart_df["장애건수"] = chart_df["위험도점수"]
        chart_html = figure_html(
            top10_bar_figure(
                chart_df,
                "기번",
                f"위험도 TOP{len(ranked)} (기번 · 지점)",
                suffix_col="지점명",
            )
        )

    return render_template(
        "priority.html",
        empty=False,
        ranked_records=ranked.to_dict("records"),
        ranked_html=table_html(ranked),
        chart_html=chart_html,
        top_n=top_n,
        latest_month=sorted(df["연월"].unique())[-1],
    )


if __name__ == "__main__":
    import threading
    import webbrowser

    print(f"장애 다발 기기 분석 - {LOCAL_APP_URL}")
    if not os.environ.get("PORT") and not os.environ.get("RENDER"):
        threading.Timer(1.0, lambda: webbrowser.open(LOCAL_APP_URL)).start()
    app.run(host="0.0.0.0", port=PORT, debug=False)
