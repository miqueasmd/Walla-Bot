# Wallapop Automation Bot

A professional, configurable Python bot to automatically search Wallapop for new ads matching your criteria, save results, and (optionally) send notifications by email.

---

## Features
- **Automated Wallapop search** with configurable keywords, price range, and location.
- **Avoids duplicate notifications** using a persistent `seen_ads.txt` file.
- **Saves results to CSV** (dynamic columns, e.g., with or without images).
- **Takes a screenshot** of the search results page for each run.
- **Professional logging** with daily rotation and compression (`logs/`).
- **Multiple search terms** supported in one run.
- **Configurable via `config.json` and `.env`** (no sensitive data in code).
- **Optionally sends email alerts** (can be disabled for testing).
- **Headless or visible browser mode.**
- **Test automation script** for batch testing with different settings.

---

## Prerequisites

- Python **3.9 or higher**
- **Google Chrome** (or Chromium) installed
- ChromeDriver is auto-installed by `webdriver-manager`

## Setup

### 1. Clone the Repository
```bash
git clone https://github.com/<user>/wallapop-automation.git
cd wallapop-automation
```

### 2. (Recommended) Create a Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows, use venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install --upgrade pip wheel
pip install -r requirements.txt
```

### 4. Create .env
```bash
cp .env.sample .env  # or create manually
# then fill the three vars shown below
```

| Variable                   | Description                        |
|----------------------------|------------------------------------|
| WALLABOT_SENDER_EMAIL      | Gmail address to send alerts from  |
| WALLABOT_APP_PASSWORD      | Google App Password for sender     |
| WALLABOT_RECIPIENT_EMAIL   | Email address to receive alerts    |

### 5. Configure Your Search in config.json
Example:
```json
{
    "search_terms": ["mountain bike", "gravel"],
    "min_price": 200,
    "max_price": 750,
    "location": "madrid",
    "radius_km": 50,
    "headless_browser": false,
    "save_images": false,
    "max_results": 100,
    "send_email": false
}
```

| Key              | Type      | Description                                                                 |
|------------------|-----------|-----------------------------------------------------------------------------|
| search_terms     | list      | List of keywords to search                                                  |
| min_price        | int/float | Minimum price (euros)                                                       |
| max_price        | int/float | Maximum price (euros)                                                       |
| location         | string    | City or area (currently supports 'madrid'/'barcelona' for coordinates)      |
| radius_km        | int       | Search radius in kilometers                                                 |
| max_results      | int       | Max ads to load per search                                                  |
| save_images      | bool      | Download images (default: false)                                            |
| headless_browser | bool      | Run Chrome headless (default: true)                                         |
| send_email       | bool      | Send email alerts (default: true)                                           |

---

## Usage

### Run the bot
```bash
python walla-bot.py
```
For periodic runs use cron or Windows Task Scheduler—see examples below.

### Create .env (if not already done)
```bash
cp .env.sample .env
# Edit .env and fill in your credentials
```

### Run automated tests
```bash
python test_wallabot_results.py
```
- This script runs the bot with different `max_results` values and disables email/images for fast testing.

---

## Output
- **CSV files**: Results are saved as `wallapop_results_<timestamp>.csv`.
  - Each row includes:
    - `id`, `title`, `price`, `link`, `extracted_at_date` (timestamp when the ad was scraped)
    - *image_url* (optional): Image URL
    - *image_path* (optional): Local path if image is downloaded
- **Screenshots**: Each run saves a screenshot as `wallapop_search_<keyword>_<timestamp>_screenshot.png`.
- **Logs**: All activity is logged in `logs/wallabot.log.YYYY-MM-DD(.gz)`.
- **seen_ads.txt**: Tracks which ads have already been notified (stores only ad IDs for deduplication and efficiency).

### CSV Result Schema

| Column             | Type    | Description                                 |
|--------------------|---------|---------------------------------------------|
| id                 | string  | Wallapop ad ID                              |
| title              | string  | Ad title                                    |
| price              | float   | Price in euros                              |
| link               | string  | Direct URL to the ad                        |
| extracted_at_date  | string  | ISO 8601 timestamp when ad was scraped      |
| *image_url*        | string  | (optional) Image URL                        |
| *image_path*       | string  | (optional) Local path if image is downloaded|

## Project Structure

- `walla-bot.py`: Main bot script that performs the Wallapop scraping, deduplication, CSV export, and (optionally) email notification.
- `config.json`: Main configuration file for search terms, filters, and bot options.
- `.env`: Stores secret credentials (never commit this file!).
- `data/`: Directory containing all data files:
  - `seen_ads.txt`: Tracks IDs of ads already processed to prevent duplicate notifications.
  - `csv/`: Contains timestamped CSV files with the results of each run.
  - `screenshots/`: Stores screenshots of search results for each run.
- `logs/`: Contains daily rotating log files for monitoring and debugging.
- `product_images/`: Stores downloaded images if `save_images` is enabled.
- `test_wallabot_results.py`: Automated test script to run the bot with different settings (e.g., various `max_results`) for validation and performance testing. Disables email and image downloads for fast, repeatable tests.
- `wallapop_automation.ipynb`: Jupyter notebook for prototyping, step-by-step exploration, and ad-hoc data analysis. Useful for development, debugging, or educational purposes.
- `wallapop_automation_demo.mp4`: Video demonstration of the bot in action, showing the automation process and features.

---

## Scheduling Examples

**Linux/macOS (cron):**
```
*/30 * * * * cd /path/to/your/project && /path/to/venv/bin/python walla-bot.py >> logs/cron.log 2>&1
```

**Windows (Task Scheduler):**
- Use the "Create Basic Task" wizard, point to your Python executable and script, and set the working directory.

---

## Security & Legal
- Never commit your `.env` or any credentials to version control.
- Add `.env`, `logs/`, and all result files to your `.gitignore`.
- **Disclaimer:** This project is for educational purposes. Use responsibly and within Wallapop's Terms of Service.

---

## Common Issues
- **SSL handshake failed**: Usually harmless, can be ignored.
- **Permission denied: logs/**: Run as admin or adjust folder permissions.
- **No new ads found**: Try deleting `seen_ads.txt` to reset.