import pandas as pd
import os


class ExcelExporter:

    def export_to_excel(self, data: dict, output_path: str) -> str:
        """
        Exports extracted data to Excel files.
        - Keeps existing behavior for transaction files.
        - Fixes spelling: 'Security name'
        - Fixes position filename: 'position.xlsx'
        """

        if not data:
            raise ValueError("No data provided for Excel export.")

        if not os.path.exists(output_path):
            os.makedirs(output_path)

        # -------------------------
        # Position
        # -------------------------
        position_data = data.get("position", [])
        if position_data:
            df_pos = pd.DataFrame(position_data)

            # Rename legacy typo columns if they exist
            if "Secuitity name" in df_pos.columns and "Security name" not in df_pos.columns:
                df_pos = df_pos.rename(columns={"Secuitity name": "Security name"})
            if "Secuitity Name" in df_pos.columns and "Security name" not in df_pos.columns:
                df_pos = df_pos.rename(columns={"Secuitity Name": "Security name"})

            desired_cols = [
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
            cols = [c for c in desired_cols if c in df_pos.columns] + [c for c in df_pos.columns if c not in desired_cols]
            df_pos = df_pos[cols]

            df_pos.to_excel(os.path.join(output_path, "position.xlsx"), index=False)
            print(f"[DEBUG] Position exported to Excel: {output_path}")

        # -------------------------
        # Transaction (unchanged)
        # -------------------------
        transaction_data = data.get("transaction", {})
        for d_type in transaction_data:
            df = pd.DataFrame(transaction_data[d_type])
            df.to_excel(os.path.join(output_path, f"{d_type}.xlsx"), index=False)
            print(f"[DEBUG] Transaction exported to Excel: {output_path}")

        return output_path


excel_exporter = ExcelExporter()
