"""Plotly 차트 유틸."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def figure_html(fig: go.Figure) -> str:
    return fig.to_html(full_html=False, include_plotlyjs="cdn")


# 막대 1~2개: 빨/초/파 | 3개 이상: 무지개 계열(가시성 높은 톤)
BAR_COLORS_BASIC = ("#e53e3e", "#38a169", "#3182ce")
RAINBOW_BAR_COLORS = (
    "#e53e3e",  # 빨
    "#dd6b20",  # 주
    "#d69e2e",  # 노
    "#38a169",  # 초
    "#3182ce",  # 파
    "#4c51bf",  # 남
    "#805ad5",  # 보
    "#e11d48",  # 진홍
    "#0891b2",  # 청록
    "#c026d3",  # 자홍
)


def _bar_colors(n: int) -> list[str]:
    if n < 3:
        return list(BAR_COLORS_BASIC[:n])
    return [RAINBOW_BAR_COLORS[i % len(RAINBOW_BAR_COLORS)] for i in range(n)]


def top10_bar_figure(
    month_data: pd.DataFrame,
    label_col: str,
    title: str,
    *,
    suffix_col: str | None = None,
) -> go.Figure:
    chart_df = month_data.sort_values("장애건수", ascending=True).copy()
    if suffix_col and suffix_col in chart_df.columns:
        y_vals = chart_df.apply(
            lambda r: (
                f"{r[label_col]} ({r[suffix_col]})"
                if r.get(suffix_col)
                else str(r[label_col])
            ),
            axis=1,
        )
    else:
        y_vals = chart_df[label_col]

    fig = go.Figure(
        go.Bar(
            x=chart_df["장애건수"],
            y=y_vals,
            orientation="h",
            text=chart_df["장애건수"],
            texttemplate="%{text:,}",
            textposition="outside",
            marker_color=_bar_colors(len(chart_df)),
        )
    )
    max_label_len = max((len(str(v)) for v in y_vals), default=10)
    fig.update_layout(
        title=title,
        showlegend=False,
        height=max(320, len(chart_df) * 42),
        margin=dict(l=min(320, max(100, max_label_len * 7)), r=20, t=50, b=20),
        yaxis={"categoryorder": "total ascending"},
        xaxis_title="장애건수",
        yaxis_title=label_col,
    )
    return fig


def multi_month_compare_figure(
    counts: pd.DataFrame,
    label_col: str,
    top_labels: list[str],
    title: str,
) -> go.Figure:
    subset = counts[counts[label_col].isin(top_labels)].copy()
    if subset.empty:
        fig = go.Figure()
        fig.update_layout(title=title, height=360)
        return fig

    fig = px.bar(
        subset,
        x="연월",
        y="장애건수",
        color=label_col,
        barmode="group",
        title=title,
        text="장애건수",
    )
    fig.update_traces(texttemplate="%{text:,}", textposition="outside")
    fig.update_layout(height=420, margin=dict(l=20, r=20, t=50, b=20))
    return fig


def daily_multi_line_figure(
    daily_df: pd.DataFrame,
    label_col: str,
    title: str,
    last_day: int,
) -> go.Figure:
    """선택 TOP 항목별 일별 장애 추이 (1일~말일)."""
    fig = go.Figure()
    if daily_df.empty:
        fig.update_layout(title=title, height=420)
        return fig

    entities = daily_df[label_col].drop_duplicates().tolist()
    colors = _bar_colors(len(entities))
    for i, ent in enumerate(entities):
        sub = daily_df[daily_df[label_col] == ent].sort_values("일")
        fig.add_trace(
            go.Scatter(
                x=sub["일"],
                y=sub["장애건수"],
                mode="lines+markers",
                name=str(ent),
                line=dict(color=colors[i], width=2),
                marker=dict(size=5),
            )
        )

    annotations: list[dict] = []
    totals = (
        daily_df.groupby(label_col, as_index=False)["장애건수"]
        .sum()
        .sort_values("장애건수", ascending=False)
    )
    top3 = totals.head(3)
    if not top3.empty and len(entities) > 1:
        max_y = float(daily_df["장애건수"].max() or 1)
        lines = []
        for i, (_, row) in enumerate(top3.iterrows(), 1):
            lines.append(f"TOP{i} {row[label_col]}  {int(row['장애건수']):,}건")
        annotations.append(
            dict(
                x=last_day * 0.97,
                y=max_y * 0.95,
                xref="x",
                yref="y",
                xanchor="right",
                yanchor="top",
                text="<b>TOP 3</b><br>" + "<br>".join(lines),
                showarrow=False,
                bgcolor="rgba(255,255,255,0.88)",
                bordercolor="#cbd5e0",
                borderwidth=1,
                borderpad=6,
                font=dict(size=11, color="#2d3748"),
                align="left",
            )
        )

    fig.update_layout(
        title=title,
        height=460,
        margin=dict(l=20, r=120, t=50, b=20),
        xaxis=dict(title="일", dtick=1, range=[0.5, last_day + 0.5], tickmode="linear"),
        yaxis_title="장애건수",
        legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02),
        annotations=annotations,
    )
    return fig


def multi_entity_monthly_figure(
    df: pd.DataFrame,
    key_col: str,
    entities: list[str],
    title: str,
) -> go.Figure:
    """여러 기번/지점의 월별 추이를 한 차트에 표시."""
    import analyzer

    fig = go.Figure()
    if not entities:
        fig.update_layout(title=title, height=420)
        return fig

    colors = _bar_colors(len(entities))
    all_months: list[str] = []
    for ent in entities:
        trend = analyzer.get_trend_chart_data(df, key_col, ent)
        if trend.empty:
            continue
        months = trend["연월"].tolist()
        all_months = sorted(set(all_months) | set(months))
        fig.add_trace(
            go.Scatter(
                x=trend["연월"],
                y=trend["장애건수"],
                mode="lines+markers",
                name=str(ent),
                line=dict(color=colors[len(fig.data) % len(colors)], width=2),
                marker=dict(size=6),
            )
        )

    fig.update_layout(
        title=title,
        height=460,
        margin=dict(l=20, r=140, t=50, b=40),
        xaxis_title="연월",
        yaxis_title="장애건수",
        legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02),
    )
    return fig


def five_day_flow_figure(
    bucket_df: pd.DataFrame,
    title: str,
    last_day: int,
) -> go.Figure:
    """5일 구간별 장애건수 — X축 눈금 1/5/10/15/20/25/30."""
    fig = go.Figure()
    if bucket_df.empty:
        fig.update_layout(title=title, height=420)
        return fig

    fig.add_trace(
        go.Bar(
            x=bucket_df["기준일"],
            y=bucket_df["장애건수"],
            text=bucket_df["장애건수"],
            texttemplate="%{text:,}",
            textposition="outside",
            marker_color=_bar_colors(len(bucket_df)),
            width=4,
            hovertext=bucket_df["구간"],
            hoverinfo="text+y",
        )
    )
    tickvals = [1, 5, 10, 15, 20, 25, 30]
    tickvals = [t for t in tickvals if t <= max(30, last_day)]
    fig.update_layout(
        title=title,
        height=420,
        margin=dict(l=20, r=20, t=50, b=20),
        showlegend=False,
        xaxis=dict(
            title="일",
            tickmode="array",
            tickvals=tickvals,
            ticktext=[str(t) for t in tickvals],
            range=[0, max(30, last_day) + 1],
        ),
        yaxis_title="장애건수",
    )
    return fig


def trend_line_figure(chart_data: pd.DataFrame, title: str) -> go.Figure:
    fig = go.Figure()
    if chart_data.empty:
        fig.update_layout(title=title, height=420)
        return fig

    x = chart_data["연월"]
    fig.add_trace(
        go.Scatter(
            x=x,
            y=chart_data["장애건수"],
            mode="lines+markers+text",
            name="장애건수",
            text=chart_data["장애건수"],
            textposition="top center",
            line=dict(color="#1a365d", width=3),
            marker=dict(size=8),
        )
    )

    if "이동평균" in chart_data.columns and chart_data["이동평균"].notna().any():
        fig.add_trace(
            go.Scatter(
                x=x,
                y=chart_data["이동평균"],
                mode="lines",
                name="이동평균(3개월)",
                line=dict(color="#2e75b6", width=2, dash="dash"),
            )
        )

    if "동일기종평균" in chart_data.columns:
        fig.add_trace(
            go.Scatter(
                x=x,
                y=chart_data["동일기종평균"],
                mode="lines",
                name="동일 기종",
                line=dict(color="#38a169", width=2, dash="dot"),
            )
        )

    if "전체평균" in chart_data.columns:
        fig.add_trace(
            go.Scatter(
                x=x,
                y=chart_data["전체평균"],
                mode="lines",
                name="전체 평균(대당)",
                line=dict(color="#718096", width=2, dash="dot"),
            )
        )

    if "이상치여부" in chart_data.columns:
        flagged = chart_data[chart_data["이상치여부"]]
        if not flagged.empty:
            fig.add_trace(
                go.Scatter(
                    x=flagged["연월"],
                    y=flagged["장애건수"],
                    mode="markers",
                    name="이상치",
                    marker=dict(color="#e53e3e", size=14, symbol="x"),
                )
            )

    fig.update_layout(
        title=title,
        height=460,
        margin=dict(l=20, r=20, t=50, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis_title="연월",
        yaxis_title="장애 건수",
    )
    return fig


def distribution_bar_figure(
    counts: pd.DataFrame,
    label_col: str,
    title: str,
    top_n: int | None = 15,
) -> go.Figure:
    chart_df = counts.copy()
    if top_n:
        chart_df = chart_df.head(top_n)
    chart_df = chart_df.sort_values("장애건수", ascending=True)
    fig = go.Figure(
        go.Bar(
            x=chart_df["장애건수"],
            y=chart_df[label_col],
            orientation="h",
            text=chart_df["장애건수"],
            texttemplate="%{text:,}",
            textposition="outside",
            marker_color=_bar_colors(len(chart_df)),
        )
    )
    fig.update_layout(
        title=title,
        showlegend=False,
        height=max(320, len(chart_df) * 36),
        margin=dict(l=20, r=20, t=50, b=20),
        xaxis_title="장애건수",
        yaxis_title=label_col,
    )
    return fig


def daily_line_figure(daily: pd.DataFrame, title: str) -> go.Figure:
    if daily.empty:
        fig = go.Figure()
        fig.update_layout(title=title, height=360)
        return fig
    daily = daily.copy()
    daily["발생일"] = daily["발생일"].astype(str)
    fig = px.line(
        daily,
        x="발생일",
        y="장애건수",
        markers=True,
        title=title,
        text="장애건수",
    )
    fig.update_traces(texttemplate="%{text:,}", textposition="top center")
    fig.update_layout(height=400, margin=dict(l=20, r=20, t=50, b=20))
    return fig
