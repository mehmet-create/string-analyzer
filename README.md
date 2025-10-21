# 🧩 String Analyzer API

A RESTful API built for the **HNG Backend Stage 1 Task**, designed to analyze and store properties of any string — including length, palindrome check, word count, unique characters, and more.

---

## 🚀 Features

- Analyze and store strings  
- Compute properties automatically:
  - `length` → number of characters  
  - `is_palindrome` → true/false  
  - `unique_characters` → count of distinct characters  
  - `word_count` → number of words  
  - `sha256_hash` → unique hash ID  
  - `character_frequency_map` → frequency of each character
- Retrieve all analyzed strings with filtering  
- Fetch a specific string by value  
- Delete a string  
- Natural language filtering  
- JSON-based responses

---

## 🛠️ Tech Stack

- **Language:** Python  
- **Framework:** FastAPI  
- **Database:** SQLite (default)  
- **Deployment:** (e.g., PXXL App / Railway / Heroku)  
- **Hashing:** SHA-256 (for unique string IDs)

---

## ⚙️ Setup Instructions

### 1️⃣ Clone the repository
```bash
git clone https://github.com/mehmet-create/string-analyzer.git
cd string-analyzer
