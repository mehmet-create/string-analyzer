from fastapi import FastAPI, HTTPException, Query, Depends, status
from sqlalchemy.orm import Session
from hashlib import sha256
from datetime import datetime
from . import models, schemas, database
from typing import Optional
import re

app = FastAPI(title="String Analyzer API")

models.Base.metadata.create_all(bind=database.engine)

@app.get("/")
def read_root():
    return {"message": "String Analyzer API is running!"}
    
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

def analyze_string(value: str):
    length = len(value)
    is_palindrome = value.lower() == value.lower()[::-1]
    unique_chars = len(set(value))
    word_count = len(value.split())
    freq_map = {}
    for char in value:
        freq_map[char] = freq_map.get(char, 0) + 1
    hash_id = sha256(value.encode()).hexdigest()

    return {
        "id": hash_id,
        "value": value,
        "length": length,
        "is_palindrome": is_palindrome,
        "unique_characters": unique_chars,
        "word_count": word_count,
        "character_frequency_map": freq_map,
        "created_at": datetime.utcnow(),
    }

@app.post("/strings", response_model=schemas.StringResponse, status_code=status.HTTP_201_CREATED)
def create_string(data: schemas.StringCreate, db: Session = Depends(get_db)):
    value = data.value.strip()
    if not value:
        raise HTTPException(status_code=422, detail="Value cannot be empty")

    hash_id = sha256(value.encode()).hexdigest()
    existing = db.query(models.StringModel).filter(models.StringModel.id == hash_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="String already exists")

    result = analyze_string(value)
    new_entry = models.StringModel(**result)
    db.add(new_entry)
    db.commit()
    db.refresh(new_entry)
    return new_entry

@app.get("/strings/{value}", response_model=schemas.StringResponse)
def get_string(value: str, db: Session = Depends(get_db)):
    hash_id = sha256(value.encode()).hexdigest()
    obj = db.query(models.StringModel).filter(models.StringModel.id == hash_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="String not found")
    return obj

@app.get("/strings")
def get_all_strings(
    is_palindrome: Optional[bool] = Query(None),
    min_length: Optional[int] = Query(None),
    max_length: Optional[int] = Query(None),
    word_count: Optional[int] = Query(None),
    contains_character: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(models.StringModel)

    if is_palindrome is not None:
        query = query.filter(models.StringModel.is_palindrome == is_palindrome)
    if min_length is not None:
        query = query.filter(models.StringModel.length >= min_length)
    if max_length is not None:
        query = query.filter(models.StringModel.length <= max_length)
    if word_count is not None:
        query = query.filter(models.StringModel.word_count == word_count)
    if contains_character:
        query = query.filter(models.StringModel.value.contains(contains_character))

    results = query.all()
    filters_applied = {
        "is_palindrome": is_palindrome,
        "min_length": min_length,
        "max_length": max_length,
        "word_count": word_count,
        "contains_character": contains_character,
    }

    return {
        "data": results,
        "count": len(results),
        "filters_applied": {k: v for k, v in filters_applied.items() if v is not None}
    }

@app.delete("/strings/{value}",status_code=status.HTTP_204_NO_CONTENT)
def delete_string(value: str, db: Session = Depends(get_db)):
    if value.strip() == "":
        raise HTTPException(status_code=422, detail="Value cannot be empty")
    hash_id = sha256(value.encode()).hexdigest()
    obj = db.query(models.StringModel).filter(models.StringModel.id == hash_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="String not found")
    db.delete(obj)
    db.commit()
    return {'message': 'String deleted successfully'}

@app.get("/strings/filter-by-natural-language")
def filter_by_natural_language(query: str, db: Session = Depends(get_db)):
    query = query.lower().strip()
    filters = {}

    if "palindrome" in query or "palindromic" in query:
        filters["is_palindrome"] = True

    if "single word" in query or "one word" in query:
        filters["word_count"] = 1

    if "longer than" in query:
        try:
            num = int(query.split("longer than")[1].split()[0])
            filters["min_length"] = num + 1
        except:
            raise HTTPException(status_code=400, detail="Couldn't parse length")

    if "contain" in query or "containing" in query:
        match = re.findall(r"\b[a-zA-Z]\b", query)
        if match:
            filters["contains_character"] = match[0]

    if not filters:
        raise HTTPException(status_code=400, detail="Unable to parse natural language query")

    # Reuse normal filtering
    q = db.query(models.StringModel)
    if "is_palindrome" in filters:
        q = q.filter(models.StringModel.is_palindrome == filters["is_palindrome"])
    if "word_count" in filters:
        q = q.filter(models.StringModel.word_count == filters["word_count"])
    if "min_length" in filters:
        q = q.filter(models.StringModel.length >= filters["min_length"])
    if "contains_character" in filters:
        q = q.filter(models.StringModel.value.contains(filters["contains_character"]))

    results = q.all()

    return {
        "data": results,
        "count": len(results),
        "interpreted_query": {
            "original": query,
            "parsed_filters": filters
        }
    }
