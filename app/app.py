from fastapi import FastAPI, HTTPException, Query, Depends, status
from sqlalchemy.orm import Session
from hashlib import sha256
from datetime import datetime
from app import models, schemas, database
from typing import Optional
import re
import hashlib

app = FastAPI(title="String Analyzer API")

# Ensure your models and database setup are ready
models.Base.metadata.create_all(bind=database.engine)
    
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/")
def read_root():
    return {"message": "String Analyzer API is running!"}         

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

@app.get("/strings/filter-by-natural-language")
def filter_by_natural_language(
    q: list[str] = Query(..., description="Natural language query, e.g. 'palindrome', 'longest', 'shortest', 'unique'"),
    db: Session = Depends(get_db)
):
    """
    Filters the stored strings based on natural language queries 
    like 'palindrome', 'longest', 'shortest' or 'most unique'.
    """
    results = []

    for query_term in q:
        q_lower = query_term.lower()
        if "palindrome" in q_lower:
            results.extend(db.query(models.StringModel).filter(models.StringModel.is_palindrome == True).all())
        elif "longest" in q_lower:
            max_length_obj = db.query(models.StringModel).order_by(models.StringModel.length.desc()).first()
            if max_length_obj:
                results.extend(db.query(models.StringModel).filter(models.StringModel.length == max_length_obj.length).all())
        elif "shortest" in q_lower:
            min_length_obj = db.query(models.StringModel).order_by(models.StringModel.length.asc()).first()
            if min_length_obj:
                results.extend(db.query(models.StringModel).filter(models.StringModel.length == min_length_obj.length).all())
        elif "unique" in q_lower:
            max_unique_obj = db.query(models.StringModel).order_by(models.StringModel.unique_characters.desc()).first()
            if max_unique_obj:
                results.extend(db.query(models.StringModel).filter(models.StringModel.unique_characters == max_unique_obj.unique_characters).all())
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported query: {query_term}")

    if not results:
        raise HTTPException(status_code=404, detail="String not found based on the query criteria.")

    # Optional: remove duplicates if multiple queries return the same strings
    results = list({r.id: r for r in results}.values())

    return results

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
