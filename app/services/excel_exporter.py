import os
import pandas as pd


class ExcelExporter:
    # Schema output cho positions
    POSITION_COLUMNS = [
        "Portfolio No.",
        "Type",
        "Account No",
        "Currency",
        "Quantity/ Amount",
        "Security ID",
        "Security name",
        "Cost price",
        "Market price",
        "Market value",
        "Accrued interest",
        "Valuation date",
    ]

    # Schema output cho trade transactions
    TRADE_COLUMNS = [
        "Client name",
        "Name/ Security",
        "Securities ID",
        "Transaction type",
        "Trade date",
        "Settlement date",
        "Currency",
        "Quantity",
        "Account no.",
        "Foreign Unit Price",
        "Foreign Gross consideration",
        "Foreign Net consideration",
        "Net consideration",
        "Commission fee (Base)",
        "Accrued interest",
        "Foreign Transaction Fee",
    ]

    # Schema output cho FX forward (fx_tf)
    FX_TF_COLUMNS = [
        "Client name",
        "Transaction type",
        "Trade date",
        "Settlement date",
        "Rate",
        "Currency Buy",
        "Amount Buy",
        "Currency Sell",
        "Amount Sell",
        "Account no. Buy",
        "Account no. Sell",
    ]

    # Schema output cho các loại OTHER transactions
    OTHER_COLUMNS = [
        "Client name",
        "Description",
        "Securities ID",
        "Transaction type",
        "Trade date",
        "Settlement date",
        "Currency",
        "Quantity",
        "Foreign Unit Price/ Interest rate",
        "Foreign Gross Amount/Interest",
        "Tax rate (%)",
        "Foreign Net Amount",
        "Payment mode",
        "Account no.",
        "Exrate to GST",
        "Amount (SGD)",
    ]

    def _normalize_rows(self, rows, columns):
        # Nếu None hoặc không phải list -> đưa về list rỗng
        if rows is None:
            rows = []
        if not isinstance(rows, list):
            rows = []

        # Lọc chỉ nhận phần tử là dict; phần tử không phải dict bị bỏ
        safe_rows = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            safe_rows.append(r)

        # Tạo DataFrame từ list dict
        df = pd.DataFrame(safe_rows)

        # Bổ sung các cột bị thiếu trong schema
        for c in columns:
            if c not in df.columns:
                df[c] = ""

        # Chỉ giữ lại các cột trong schema (bỏ key thừa)
        # và sắp xếp theo đúng thứ tự schema
        df = df[columns]

        # NaN -> "" để Excel không hiển thị NaN
        df = df.fillna("")

        return df

    def export_to_excel(self, data: dict, output_path: str) -> str:
        """
        Export dữ liệu extract ra 4 file Excel:

          - position.xlsx
          - trade.xlsx
          - fx_tf.xlsx
          - other.xlsx

        Nằm trong thư mục: outputs/<task_id>/

        data kỳ vọng có cấu trúc:
        {
          "position": [ ... list of dict rows ... ],
          "transaction": {
             "trade": [ ... ],
             "fx_tf": [ ... ],
             "other": [ ... ]
          }
        }
        """
        if data is None:
            raise ValueError("No data provided for Excel export.")

        # Tạo folder output nếu chưa có
        if not os.path.exists(output_path):
            os.makedirs(output_path, exist_ok=True)

        position_data = data.get("position", []) or []
        df_pos = self._normalize_rows(position_data, self.POSITION_COLUMNS)
        pos_path = os.path.join(output_path, "position.xlsx")
        df_pos.to_excel(pos_path, index=False)
        print(f"[DEBUG] Exported: {pos_path}")

        transaction_data = data.get("transaction", {}) or {}

        # trade
        trade_rows = transaction_data.get("trade", []) or []
        df_trade = self._normalize_rows(trade_rows, self.TRADE_COLUMNS)
        trade_path = os.path.join(output_path, "trade.xlsx")
        df_trade.to_excel(trade_path, index=False)
        print(f"[DEBUG] Exported: {trade_path}")

        # fx_tf
        fx_tf_rows = transaction_data.get("fx_tf", []) or []
        df_fx_tf = self._normalize_rows(fx_tf_rows, self.FX_TF_COLUMNS)
        fx_tf_path = os.path.join(output_path, "fx_tf.xlsx")
        df_fx_tf.to_excel(fx_tf_path, index=False)
        print(f"[DEBUG] Exported: {fx_tf_path}")

        # other
        other_rows = transaction_data.get("other", []) or []
        df_other = self._normalize_rows(other_rows, self.OTHER_COLUMNS)
        other_path = os.path.join(output_path, "other.xlsx")
        df_other.to_excel(other_path, index=False)
        print(f"[DEBUG] Exported: {other_path}")

        return output_path


# Tạo instance dùng chung (import ở nơi khác dùng luôn)
excel_exporter = ExcelExporter()
