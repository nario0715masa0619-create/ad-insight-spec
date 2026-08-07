"""
MetaAdsCsvService - Meta Ads Manager CSVエクスポートの取り込み（Phase 1）

目的:
Meta Ads Manager からユーザーがそのままエクスポートした CSV
（列の並べ替え・リネームなし）を受け取り、
- 日本語/英語の主要列名ゆれを吸収した列マッピング
- キャンペーン/広告セット/広告のいずれの粒度かの判定
- 分析に使う KPI（impressions/clicks/spend/conversions）への正規化
- 分析期間（analysis_period）の抽出
を行う。既存の手入力KPI（JSON）フローとは独立しており、
AnalysisOrchestrator._step_load_kpi がファイル拡張子で振り分ける。

非目的（Phase 1 スコープ外）:
- Meta Marketing API 連携
- 全列・全指標の完全対応（未対応列は unmapped_columns として無視するのみ）
- CTR/CPA/CVR の CSV 値そのままの採用
  （複数行（日別内訳等）の合算時に元のレシオ値をそのまま使うと不整合が
  生じるため、ここでは impressions/clicks/spend/conversions の合算値のみを
  返し、CTR/CPA/CVR は既存の Performance モデル（app/schemas/ad_insight.py）
  の root_validator に再計算させる。既存の手入力KPI(JSON)フローと同じ
  計算ロジックに揃うため、二重実装によるドリフトを避けられる）
"""

import csv
import io
import re
from datetime import datetime
from typing import Any, Dict, List, Optional


class MetaAdsCsvError(Exception):
    """
    CSVを解析できない/主要指標が不足している場合に送出する。

    user_message: そのままUI/APIレスポンスに出せる、次のアクションが分かる文言。
    missing_fields: 不足している内部フィールド名のリスト（machine-readable）。
    details: 追加のデバッグ情報（unmapped_columns等）。
    """

    def __init__(
        self,
        user_message: str,
        error_code: str = "META_ADS_CSV_INVALID",
        missing_fields: Optional[List[str]] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(user_message)
        self.user_message = user_message
        self.error_code = error_code
        self.missing_fields = missing_fields or []
        self.details = details or {}


# ===== 列名マッピング =====
# key: 内部フィールド名, value: Meta Ads Manager がエクスポートに使う代表的な
# 列名のバリエーション（日本語/英語）。マッチングは正規化後（後述）の
# 完全一致で行う。

COLUMN_ALIASES: Dict[str, List[str]] = {
    "campaign_name": ["キャンペーン名", "campaign name", "campaign"],
    "adset_name": ["広告セット名", "セット名", "ad set name", "adset name"],
    "ad_name": ["広告名", "ad name"],
    "impressions": ["インプレッション", "impressions"],
    "clicks": [
        "クリック（すべて）",
        "クリック(すべて)",
        "クリック数",
        "リンクのクリック数",
        "リンククリック数",
        "clicks (all)",
        "clicks(all)",
        "link clicks",
        "clicks",
    ],
    "ctr": [
        "ctr（すべて）",
        "ctr(すべて)",
        "ctr（リンクのクリック率）",
        "ctr(リンクのクリック率)",
        "ctr",
        "ctr (all)",
        "ctr (link click-through rate)",
    ],
    "spend": [
        "消化金額 (jpy)",
        "消化金額(jpy)",
        "消化金額",
        "amount spent (jpy)",
        "amount spent (usd)",
        "amount spent",
    ],
    "conversions": ["結果", "コンバージョン", "results", "conversions", "result"],
    "cpa": [
        "result当たりのコスト",
        "resultあたりのコスト",
        "コンバージョン単価",
        "cost per result",
        "cost per conversion",
        "cpa",
    ],
    "cvr": ["cvr", "コンバージョン率"],
    "date_start": ["レポート開始日", "reporting starts"],
    "date_end": ["レポート終了日", "reporting ends"],
    "date_single": ["日付", "day", "date"],
}

# 分析に最低限必要な指標（これが揃わない場合は分析自体を開始できない）
REQUIRED_FIELDS = ("impressions", "clicks")
REQUIRED_FIELD_LABELS = {
    "impressions": "インプレッション",
    "clicks": "クリック（すべて / リンククリック）",
}

# あると分析の質が上がる指標（無くても分析は継続できる）
RECOMMENDED_FIELDS = ("spend", "conversions")
RECOMMENDED_FIELD_LABELS = {
    "spend": "消化金額",
    "conversions": "結果（コンバージョン）",
}

NAME_FIELDS = ("campaign_name", "adset_name", "ad_name")
NAME_FIELD_LABELS = {
    "campaign_name": "キャンペーン名",
    "adset_name": "広告セット名",
    "ad_name": "広告名",
}

_ENCODINGS = ("utf-8-sig", "utf-8", "cp932", "shift_jis")
_FULLWIDTH_TO_HALFWIDTH = str.maketrans({"（": "(", "）": ")", "　": " "})
_CURRENCY_RE = re.compile(r"[¥$€,]")
_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%Y.%m.%d")


def _normalize_header(header: str) -> str:
    h = (header or "").translate(_FULLWIDTH_TO_HALFWIDTH)
    h = h.strip().lower()
    h = re.sub(r"\s+", "", h)
    return h


_ALIAS_TO_FIELD: Dict[str, str] = {}
for _field, _aliases in COLUMN_ALIASES.items():
    for _alias in _aliases:
        _ALIAS_TO_FIELD.setdefault(_normalize_header(_alias), _field)


def _match_alias(header: str) -> Optional[str]:
    return _ALIAS_TO_FIELD.get(_normalize_header(header))


def _parse_number(raw: Optional[str]) -> Optional[float]:
    if raw is None:
        return None
    s = raw.strip()
    if s in ("", "-", "—", "N/A", "n/a", "NA"):
        return None
    is_percent = s.endswith("%")
    if is_percent:
        s = s[:-1]
    s = _CURRENCY_RE.sub("", s).strip()
    if s == "":
        return None
    try:
        value = float(s)
    except ValueError:
        return None
    return value / 100.0 if is_percent else value


def _parse_date(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    s = raw.strip()
    if not s:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _sum_field(
    data_rows: List[List[str]],
    field: str,
    cell_getter,
) -> Optional[float]:
    total = 0.0
    found = False
    for row in data_rows:
        value = _parse_number(cell_getter(row, field))
        if value is not None:
            total += value
            found = True
    return total if found else None


def _extract_analysis_period(
    data_rows: List[List[str]],
    column_index: Dict[str, int],
    cell_getter,
    warnings: List[str],
) -> Dict[str, Optional[str]]:
    starts: List[str] = []
    ends: List[str] = []
    has_date_columns = any(f in column_index for f in ("date_start", "date_end", "date_single"))

    if "date_start" in column_index or "date_end" in column_index:
        for row in data_rows:
            s = _parse_date(cell_getter(row, "date_start"))
            e = _parse_date(cell_getter(row, "date_end"))
            if s:
                starts.append(s)
            if e:
                ends.append(e)
    elif "date_single" in column_index:
        for row in data_rows:
            d = _parse_date(cell_getter(row, "date_single"))
            if d:
                starts.append(d)
                ends.append(d)

    start = min(starts) if starts else None
    end = max(ends) if ends else None

    if not has_date_columns:
        warnings.append("日付列が見つからなかったため、分析期間（analysis_period）は未設定のままです。")
    elif start is None and end is None:
        warnings.append("日付列は見つかりましたが、値を日付として解釈できませんでした。分析期間は未設定のままです。")

    return {"start": start, "end": end}


class MetaAdsCsvService:
    """Meta Ads Manager CSVエクスポートを解析するサービス（Phase 1: Meta特化）。"""

    @staticmethod
    def _decode_bytes(data: bytes) -> str:
        for encoding in _ENCODINGS:
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise MetaAdsCsvError(
            "CSVファイルの文字コードを判定できませんでした。UTF-8 または Shift_JIS(CP932) で"
            "保存し直してから、もう一度アップロードしてください。",
            error_code="META_ADS_CSV_ENCODING_ERROR",
        )

    @staticmethod
    def parse_bytes(data: bytes) -> Dict[str, Any]:
        return MetaAdsCsvService.parse_text(MetaAdsCsvService._decode_bytes(data))

    @staticmethod
    def parse_file(file_path: str) -> Dict[str, Any]:
        with open(file_path, "rb") as f:
            data = f.read()
        return MetaAdsCsvService.parse_bytes(data)

    @staticmethod
    def parse_text(csv_text: str) -> Dict[str, Any]:
        """
        Returns:
            {
                "granularity": "ad" | "adset" | "campaign" | "unknown",
                "row_count": int,
                "column_mapping": {internal_field: original_header, ...},
                "unmapped_columns": [original_header, ...],
                "kpi": {"impressions": int, "clicks": int, "spend": float|None, "conversions": int|None},
                "asset_meta": {
                    "campaign_name": str|None, "adset_name": str|None, "ad_name": str|None,
                    "analysis_period": {"start": str|None, "end": str|None},
                },
                "missing_recommended_fields": [internal_field, ...],
                "warnings": [str, ...],
            }

        Raises:
            MetaAdsCsvError: CSVが空/データ行なし/主要指標の列が無い/数値が読めない場合
        """
        if not csv_text or not csv_text.strip():
            raise MetaAdsCsvError(
                "CSVファイルが空です。Meta Ads Managerから正しくエクスポートされているか確認してください。",
                error_code="META_ADS_CSV_EMPTY",
            )

        sample = csv_text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
        except csv.Error:
            dialect = csv.excel

        reader = csv.reader(io.StringIO(csv_text), dialect)
        rows = [row for row in reader if any(cell.strip() for cell in row)]

        if not rows:
            raise MetaAdsCsvError(
                "CSVファイルが空です。Meta Ads Managerから正しくエクスポートされているか確認してください。",
                error_code="META_ADS_CSV_EMPTY",
            )

        header, data_rows = rows[0], rows[1:]
        if not data_rows:
            raise MetaAdsCsvError(
                "CSVにデータ行が含まれていません（ヘッダー行のみ検出されました）。集計期間や絞り込み条件を確認し、"
                "データ行を含む状態で再エクスポートしてください。",
                error_code="META_ADS_CSV_NO_DATA",
            )

        column_index: Dict[str, int] = {}
        column_mapping: Dict[str, str] = {}
        unmapped_columns: List[str] = []
        for idx, col in enumerate(header):
            field = _match_alias(col)
            if field and field not in column_index:
                column_index[field] = idx
                column_mapping[field] = col.strip()
            elif col.strip():
                unmapped_columns.append(col.strip())

        missing_required = [f for f in REQUIRED_FIELDS if f not in column_index]
        if missing_required:
            labels = "、".join(REQUIRED_FIELD_LABELS[f] for f in missing_required)
            raise MetaAdsCsvError(
                f"CSVから主要指標を読み取れませんでした（不足している列: {labels}）。"
                "Meta Ads Manager のエクスポート設定で、これらの指標を含めたうえで再度CSVを書き出し、"
                "そのままアップロードし直してください。",
                error_code="META_ADS_CSV_MISSING_REQUIRED_COLUMNS",
                missing_fields=missing_required,
                details={"unmapped_columns": unmapped_columns},
            )

        def _cell(row: List[str], field: str) -> Optional[str]:
            idx = column_index.get(field)
            if idx is None or idx >= len(row):
                return None
            return row[idx]

        warnings: List[str] = []

        totals = {f: _sum_field(data_rows, f, _cell) for f in ("impressions", "clicks", "spend", "conversions")}

        unreadable = [f for f in REQUIRED_FIELDS if totals[f] is None]
        if unreadable:
            labels = "、".join(REQUIRED_FIELD_LABELS[f] for f in unreadable)
            raise MetaAdsCsvError(
                f"列は見つかりましたが、値を数値として読み取れませんでした（{labels}）。"
                "セルが空欄になっていないか、書式が数値として認識できる形式か確認してください。",
                error_code="META_ADS_CSV_UNREADABLE_VALUES",
                missing_fields=unreadable,
            )

        kpi = {
            "impressions": int(round(totals["impressions"])),
            "clicks": int(round(totals["clicks"])),
            "spend": totals["spend"],
            "conversions": int(round(totals["conversions"])) if totals["conversions"] is not None else None,
        }

        asset_meta: Dict[str, Optional[str]] = {}
        for field in NAME_FIELDS:
            values = [v.strip() for row in data_rows if (v := _cell(row, field)) and v.strip()]
            distinct = sorted(set(values))
            if distinct:
                asset_meta[field] = distinct[0]
                if len(distinct) > 1:
                    warnings.append(
                        f"CSVに複数の{NAME_FIELD_LABELS[field]}が含まれていました（{len(distinct)}件）。"
                        f"先頭の値「{distinct[0]}」を使用しています。"
                    )
            else:
                asset_meta[field] = None

        if asset_meta.get("ad_name"):
            granularity = "ad"
        elif asset_meta.get("adset_name"):
            granularity = "adset"
        elif asset_meta.get("campaign_name"):
            granularity = "campaign"
        else:
            granularity = "unknown"
            warnings.append(
                "キャンペーン名・広告セット名・広告名のいずれの列も見つからなかったため、KPIの粒度を判定できませんでした。"
            )

        asset_meta["analysis_period"] = _extract_analysis_period(data_rows, column_index, _cell, warnings)

        missing_recommended = [f for f in RECOMMENDED_FIELDS if f not in column_index]
        if missing_recommended:
            labels = "、".join(RECOMMENDED_FIELD_LABELS[f] for f in missing_recommended)
            warnings.append(f"任意項目が見つかりませんでした（{labels}）。分析は継続しますが、一部の指標は算出されません。")

        return {
            "granularity": granularity,
            "row_count": len(data_rows),
            "column_mapping": column_mapping,
            "unmapped_columns": unmapped_columns,
            "kpi": kpi,
            "asset_meta": asset_meta,
            "missing_recommended_fields": list(missing_recommended),
            "warnings": warnings,
        }
