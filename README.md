# PDF Tariff Extractor

A web-based tool to extract tariff details from PDF files. Upload a PDF containing hotel tariff information, and the application will parse and display the extracted data in a user-friendly table.

## Features
- Upload PDF files via a simple web interface
- Extracts meal plan, dates, prices, season, and hotel information
- Displays results in a clean, responsive table
- Error handling and user feedback

## Setup Instructions
1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd Hotel_tariff
   ```
2. **Install dependencies**
   Ensure you have Python 3.x installed. Install required packages:
   ```bash
   pip install -r requirements.txt
   ```
   *(If `requirements.txt` is missing, install Flask and any PDF parsing libraries used in `extract_tariff.py`)*

3. **Run the application**
   ```bash
   python app.py
   ```
   The app will start a local server (usually at http://127.0.0.1:5000/).

4. **Open the frontend**
   Open `index.html` in your browser, or navigate to the server URL if the backend serves the frontend.

## Usage
- Click the "Upload" button and select a PDF file containing tariff details.
- The extracted data will be displayed in a table below the upload form.
- Errors or issues will be shown in red below the form.

## File Structure
- `app.py` - Backend server (Flask or similar)
- `extract_tariff.py` - PDF extraction logic
- `index.html` - Frontend UI
- `uploads/` - Directory for uploaded files
- `output/` - Directory for extracted results (if used)

## License
This project is provided for educational and demonstration purposes.
