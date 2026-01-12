import pandas as pd
import os


class ExcelExporter:
    def export_to_excel(self, data: dict, output_path: str) -> str:
        """
        Exports extracted data to 4 Excel files:
          - postion.xlsx
          - trade.xlsx
          - fx_tf.xlsx
          - other.xlsx

        Folder: outputs/<task_id>/
        """
        if data is None:
            raise ValueError("No data provided for Excel export.")

        if not os.path.exists(output_path):
            os.makedirs(output_path, exist_ok=True)

        # 1) POSITION
        postion_data = data.get("position", []) or []
        df_pos = pd.DataFrame(postion_data)
        df_pos.to_excel(os.path.join(output_path, "postion.xlsx"), index=False)
        print(f"[DEBUG] Exported: {os.path.join(output_path, 'postion.xlsx')}")

        # 2) TRANSACTIONS (always export 3 files)
        transaction_data = data.get("transaction", {}) or {}

        for d_type in ["trade", "fx_tf", "other"]:
            rows = transaction_data.get(d_type, []) or []
            df = pd.DataFrame(rows)
            df.to_excel(os.path.join(output_path, f"{d_type}.xlsx"), index=False)
            print(f"[DEBUG] Exported: {os.path.join(output_path, f'{d_type}.xlsx')}")

        return output_path


excel_exporter = ExcelExporter()
