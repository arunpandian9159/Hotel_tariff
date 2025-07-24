import base64
import os
from mistralai import Mistral
from datetime import datetime
import pandas as pd
import re
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv()
api_key = os.getenv("MISTRAL_API_KEY")

def extract_text_from_pdf(document_url, client):
    """Extract text from a PDF using Mistral OCR API with a document URL or base64-encoded local file."""
    # If the input is a local file, encode it as base64 with the required prefix
    if not document_url.startswith("http"):
        try:
            with open(document_url, "rb") as f:
                base64_pdf = base64.b64encode(f.read()).decode("utf-8")
            document_url = f"data:application/pdf;base64,{base64_pdf}"
        except Exception as e:
            print(f"Error encoding {document_url} as base64: {e}")
            return ""
    try:
        ocr_response = client.ocr.process(
            model="mistral-ocr-latest",
            document={
                "type": "document_url",
                "document_url": document_url
            },
            include_image_base64=False
        )
        # Debug: Print the full response to inspect its structure
        print("OCR Response:", ocr_response)
        # Extract text from the pages' markdown content
        if hasattr(ocr_response, 'pages') and isinstance(ocr_response.pages, list):
            full_text = "\n".join(page.markdown for page in ocr_response.pages if hasattr(page, 'markdown'))
            return full_text if full_text else ""
        else:
            print("Unable to extract text from OCR response")
            return ""
    except Exception as e:
        print(f"Error processing OCR for {document_url}: {e}")
        return ""

def parse_season_tables(text):
    """Parse all season/date headers and their following tables from the OCR markdown."""
    # Pattern for season/date header
    # e.g. Season Date - (15-APR TO 9-MAY)(1-JUN TO 14-JUN)
    #      Mid Season Date - (15-MAR TO 14-APR)(15-JUNE TO 30-JUN)
    #      Off Season Date : (6-JAN TO 14-MAR)
    #      Black Out Date : (10-MAY TO 31-MAY)
    season_header_pattern = re.compile(r"((?:[A-Za-z ]+Season Date|Black Out Date|Off Season Date)[^\n]*)", re.IGNORECASE)
    # Find all season headers and their positions
    matches = list(season_header_pattern.finditer(text))
    results = []
    for idx, match in enumerate(matches):
        season_header = match.group(1).strip()
        start = match.end()
        end = matches[idx+1].start() if idx+1 < len(matches) else len(text)
        block = text[start:end]
        # Find the first markdown table in this block
        table_matches = re.findall(r'(\|[\s\S]+?)(?:\n\n|$)', block)
        date_ranges = re.findall(r"\(([^\)]+)\)", season_header)
        season_name = season_header.split('-')[0].strip().replace(':','')
        for table in table_matches:
            lines = [l for l in table.split('\n') if l.strip() and l.strip().startswith('|')]
            if not lines or len(lines) < 2:
                continue
            results.append({
                'season_name': season_name,
                'date_ranges': date_ranges,
                'table': table
            })
    return results

def parse_markdown_table(table_text):
    """Parse a markdown table (header + rows) into a list of dicts."""
    lines = [l for l in table_text.split('\n') if l.strip() and l.strip().startswith('|')]
    if not lines or len(lines) < 2:
        return []
    header = [h.strip() for h in lines[0].split('|') if h.strip()]
    data = []
    for row in lines[2:]:  # skip header and separator
        cols = [c.strip() for c in row.split('|') if c.strip()]
        if len(cols) != len(header):
            continue
        data.append(dict(zip(header, cols)))
    return data

def determine_season(text, filename):
    """Determine the season based on text or filename."""
    if re.search(r'off\s*season|low\s*season', text, re.IGNORECASE) or "Off Season" in filename:
        return "offSeason"
    return "onSeason"

def create_output_table(tariff_data, start_date, end_date, season, hotel_name):
    """Create a DataFrame from the extracted tariff data."""
    rows = []
    for meal_plan, prices in tariff_data.items():
        row = {
            "Meal Plan": meal_plan,
            "Start Date": start_date,
            "End Date": end_date,
            "Room Price": prices.get("Room Price", "N/A"),
            "Adult Price": prices.get("Adult Price", "N/A"),
            "Child Price": prices.get("Child Price", "N/A"),
            "Season": season,
            "Hotel": hotel_name
        }
        rows.append(row)
    return pd.DataFrame(rows)

def extract_tariff_data(pdf_path, client):
    """Extract tariff data from a single PDF, supporting multi-table multi-season OCR markdown."""
    text = extract_text_from_pdf(pdf_path, client)
    if not text:
        return pd.DataFrame()

    # Save OCR response to output/ocr_response.txt
    os.makedirs('output', exist_ok=True)
    with open('output/ocr_response.txt', 'w', encoding='utf-8') as f:
        f.write(text)

    hotel_name = os.path.basename(pdf_path).replace(".pdf", "")
    all_rows = []
    # Specifically parse the main tariff table for Hotel Pahalgam View
    # Find the tariff table block
    tariff_table_match = re.search(r'\|\s*Room Category\s*\|[\s\S]+?\|\s*MAP\s*\|\s*\d+\s*\|\s*\d+\s*\|', text)
    if tariff_table_match:
        table_text = tariff_table_match.group(0)
        lines = [l for l in table_text.split('\n') if l.strip() and l.strip().startswith('|')]
        if len(lines) >= 2:
            header = [h.strip() for h in lines[0].split('|') if h.strip()]
            # Identify season columns and extract season name and date range
            season_cols = []
            season_info = []
            for i, h in enumerate(header):
                m = re.match(r'([A-Za-z\- ]+)[\n\r]*\(?([0-9A-Za-z –\-]+)?\)?', h)
                if i >= 3 and m:
                    # Season columns start from index 3
                    season_name = m.group(1).strip()
                    date_range = m.group(2).strip() if m.group(2) else ''
                    season_cols.append(i)
                    season_info.append((season_name, date_range))
            last_room = last_occ = ''
            for row in lines[2:]:
                cols = [c.strip() for c in row.split('|') if c.strip()]
                if len(cols) < 3:
                    continue
                # Track last non-empty Room Category and Occupancy
                if cols[0]:
                    last_room = cols[0]
                if cols[1]:
                    last_occ = cols[1]
                meal_plan = cols[2]
                for idx, (season_name, date_range) in zip(season_cols, season_info):
                    if idx >= len(cols):
                        continue
                    price = cols[idx]
                    row_out = {
                        'Hotel': hotel_name,
                        'Room Category': last_room,
                        'Occupancy': last_occ,
                        'Meal Plan': meal_plan,
                        'Season': season_name,
                        'Start Date': date_range.split('–')[0].strip() if '–' in date_range else date_range,
                        'End Date': date_range.split('–')[1].strip() if '–' in date_range else date_range,
                        'Price': price
                    }
                    all_rows.append(row_out)
        if all_rows:
            return pd.DataFrame(all_rows)
        else:
            print(f"No tariff data extracted from {pdf_path}")
            return pd.DataFrame()
    # Fallback: Try to extract any markdown table if specific pattern not found
    generic_table_match = re.search(r'(\|[\s\S]+?)(?:\n\n|$)', text)
    if generic_table_match:
        table_text = generic_table_match.group(1)
        parsed = parse_markdown_table(table_text)
        if parsed:
            df = pd.DataFrame(parsed)
            df['Hotel'] = hotel_name
            return df
    print(f"No tariff data extracted from {pdf_path}")
    return pd.DataFrame()

def analyze_tariff_text_with_llm(text, client):
    """
    Use Mistral LLM to analyze the extracted OCR text and return a structured tariff table in the required format.
    """
    prompt = (
        "You are an expert at extracting hotel tariff tables from text. "
        "Given the following text extracted from a hotel tariff PDF, extract the room category (e.g., Deluxe Room) and output a markdown table with columns: "
        "room category"
        "| Plan | Start Date | End Date | Room Price | Adult Price | Child Price | Season |. "
        "If there are multiple plans or date ranges, include all rows. "
        "If possible, infer the season name (e.g., peakSeason, offSeason) from the text. "
        "exclude rack price and Published rates. "
        "Output only the markdown table, nothing else.\n\n"
        f"Text: {text}\n"
    )
    try:
        chat_response = client.chat.complete(
            model="mistral-large-latest",  # or another available LLM model
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        # Extract the markdown table from the response
        content = chat_response.choices[0].message.content if hasattr(chat_response.choices[0], 'message') else chat_response.choices[0].content
        return content
    except Exception as e:
        print(f"Error calling Mistral LLM: {e}")
        return None

def extract_tariff_from_pdf(pdf_path, output_csv_path=None, use_llm=True):
    """
    Wrapper for Flask: Given a PDF path, returns a list of dicts with keys:
    Meal Plan, Start Date, End Date, Room Price, Adult Price, Child Price, Season, Hotel
    Optionally saves the extracted data to a specified CSV path.
    If use_llm is True, uses the LLM to extract the table from OCR text.
    """
    client = Mistral(api_key=api_key)
    text = extract_text_from_pdf(pdf_path, client)
    if not text:
        return []
    if use_llm:
        llm_table = analyze_tariff_text_with_llm(text, client)
        if llm_table:
            # Optionally save the markdown table to a file
            os.makedirs('output', exist_ok=True)
            base = os.path.splitext(os.path.basename(pdf_path))[0]
            with open(f'output/{base}_llm_table.md', 'w', encoding='utf-8') as f:
                f.write(llm_table)
            # Optionally, parse the markdown table into a list of dicts for JSON API
            rows = parse_markdown_table(llm_table)
            return rows

if __name__ == "__main__":
    # Initialize Mistral client
    client = Mistral(api_key=api_key)

    # Specify the path to the single PDF you want to process
    pdf_path = "./pdf_folder/Rufina Pinasa Residency - Gangtok-June-2025.pdf"  # Replace with the actual PDF path
    result_df = extract_tariff_data(pdf_path, client)
    if not result_df.empty:
        print(result_df)
        result_df.to_csv("output/hotel_tariff.csv", index=False)
    else:
        print("No data extracted from the PDF")