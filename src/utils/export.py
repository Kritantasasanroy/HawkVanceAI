from fpdf import FPDF
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
import logging

class DocumentExporter:
    def __init__(self, output_dir: str = None):
        if output_dir is None:
            output_dir = r'C:\Users\mithu\OneDrive\Desktop\recogP\HawkVanceAI\exports'

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_to_pdf(self, data: Dict[str, Any], filename: str = None) -> str:
        """Export analysis results to PDF"""
        try:
            pdf = FPDF()
            pdf.set_auto_page_break(auto=True, margin=15)
            
            # Add a title page
            pdf.add_page()
            pdf.set_font("Arial", "B", 16)
            pdf.cell(0, 10, "HawkVanceAI Report", ln=True, align="C")
            pdf.ln(10)
            
            # Include responses from history
            responses_to_include = data.get('response_history', [])
            
            for idx, resp in enumerate(responses_to_include, start=1):
                pdf.set_font("Arial", "B", 12)
                pdf.cell(0, 10, f"Analysis {idx}:", ln=True)
                pdf.set_font("Arial", "", 10)
                
                # Handle multi-line text
                lines = resp.split('\n')
                for line in lines:
                    try:
                        # Handle encoding issues
                        safe_line = line.encode('latin-1', 'replace').decode('latin-1')
                        pdf.multi_cell(0, 5, safe_line)
                    except Exception as e:
                        logging.error(f"Error writing line to PDF: {str(e)}")
                        continue
                pdf.ln(5)

            # Generate filename with timestamp
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"HawkVanceAI_Report_{timestamp}.pdf"

            output_path = self.output_dir / filename
            pdf.output(str(output_path))
            return str(output_path)

        except Exception as e:
            logging.error(f"Error exporting to PDF: {str(e)}")
            raise