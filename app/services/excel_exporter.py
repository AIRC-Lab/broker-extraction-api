import pandas as pd
import os

class ExcelExporter:
    def export_to_excel(self, data: list[dict], output_path: str) -> str:
        """
        Exports a list of dictionaries (extracted data) to an Excel file.
        Each dictionary represents data from a page or a set of extracted fields.
        """
        if not data:
            raise ValueError("No data provided for Excel export.")
        postion_data = data["position"]
        df = pd.DataFrame(postion_data)

        if not os.path.exists(output_path):
            os.makedirs(output_path)

        df.to_excel(os.path.join(output_path,f"postion.xlsx"), index=False)
        print(f"[DEBUG] Data exported to Excel: {output_path}")
        transaction_data = data["transaction"]
        for d_type in transaction_data:
            df = pd.DataFrame(transaction_data[d_type])
            if not os.path.exists(output_path):
                os.makedirs(output_path)

            df.to_excel(os.path.join(output_path, f"{d_type}.xlsx"), index=False)
            print(f"[DEBUG] Data exported to Excel: {output_path}")
        return output_path

excel_exporter = ExcelExporter()

