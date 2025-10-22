from fastapi import FastAPI, HTTPException, Query, Depends, status
from sqlalchemy.orm import Session
from sqlalchemy import func, select 
from hashlib import sha256
from datetime import datetime
from typing import Optional, List, Dict, Any # Added Dict and Any for structured response
from app import models, schemas, database
import re
import json # Used for JSON.dumps for consistency

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
    """Calculates all required properties for a given string value."""
    length = len(value)
    # Palindrome check is case-insensitive, as required by the task
    is_palindrome = value.lower() == value.lower()[::-1]
    unique_chars = len(set(value))
    word_count = len(value.split())
    freq_map = {}
    for char in value:
        freq_map[char] = freq_map.get(char, 0) + 1
    
    # SHA-256 hash used for both ID and the sha256_hash property
    hash_id = sha256(value.encode()).hexdigest()

    return {
        "id": hash_id,
        "value": value,
        "length": length,
        "is_palindrome": is_palindrome,
        "unique_characters": unique_chars,
        "word_count": word_count,
        "character_frequency_map": freq_map,
        # === FIX: Return native datetime object for SQLAlchemy/SQLite insertion ===
        "created_at": datetime.utcnow(),
    }

def _format_response(db_object: models.StringModel) -> Dict[str, Any]:
    """
    Formats the flat SQLAlchemy model object into the nested structure 
    required by the task (with a 'properties' field).
    """
    # Use id as the sha256_hash value
    hash_id = db_object.id 
    
    # Ensure character_frequency_map is a dictionary (it might be a JSON string from DB)
    freq_map = db_object.character_frequency_map
    if isinstance(freq_map, str):
        try:
            freq_map = json.loads(freq_map)
        except json.JSONDecodeError:
            freq_map = {} # Default to empty if decoding fails

    # The created_at field is retrieved as a datetime object from the DB, 
    # and is converted to an ISO string here for the final JSON response.
    created_at_iso = db_object.created_at.isoformat() if isinstance(db_object.created_at, datetime) else db_object.created_at

    return {
        "id": hash_id,
        "value": db_object.value,
        "properties": {
            "length": db_object.length,
            "is_palindrome": db_object.is_palindrome,
            "unique_characters": db_object.unique_characters,
            "word_count": db_object.word_count,
            "sha256_hash": hash_id, # Required by the spec to be redundant
            "character_frequency_map": freq_map,
        },
        "created_at": created_at_iso
    }

@app.post("/strings", status_code=status.HTTP_201_CREATED)
def create_string(data: schemas.StringCreate, db: Session = Depends(get_db)):
    value = data.value.strip()
    if not value:
        raise HTTPException(status_code=422, detail="Value cannot be empty")

    hash_id = sha256(value.encode()).hexdigest()
    existing = db.query(models.StringModel).filter(models.StringModel.id == hash_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="String already exists")

    result = analyze_string(value)
    
    # Use the generated dict keys to create the model instance
    # created_at is now a native datetime object, satisfying SQLite
    new_entry = models.StringModel(
        id=result['id'],
        value=result['value'],
        length=result['length'],
        is_palindrome=result['is_palindrome'],
        unique_characters=result['unique_characters'],
        word_count=result['word_count'],
        character_frequency_map=result['character_frequency_map'],
        created_at=result['created_at']
    )

    db.add(new_entry)
    db.commit()
    db.refresh(new_entry)
    
    # Format the response to match the nested JSON spec
    return _format_response(new_entry)

# ==============================================================================
# ROUTE PRIORITY FIX: Natural Language Filter MUST be defined before {value}
# ==============================================================================

import re
from fastapi import APIRouter, Query, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from app import models
from app.database import get_db

@app.get("/strings/filter-by-natural-language")
def filter_by_natural_language(
    q: List[str] = Query(..., description="Natural language query terms (can be repeated)"),
    db: Session = Depends(get_db)
):
    """
    Filters strings by parsing natural language queries, supporting combined filters:
    length, word count, palindrome, contains specific letters, and special filters.
    """
    original_query = " ".join(q)
    q_lower = original_query.lower()
    
    query = db.query(models.StringModel)
    parsed_filters = {}

    # --- 1. Extract numbers from query ---
    number_matches = re.findall(r'\b\d+\b', q_lower)
    number = int(number_matches[0]) if number_matches else None

    # --- 2. Length filters ---
    if "longer than" in q_lower and number is not None:
        query = query.filter(models.StringModel.length > number)
        parsed_filters['min_length'] = number + 1
    if "shorter than" in q_lower and number is not None:
        query = query.filter(models.StringModel.length < number)
        parsed_filters['max_length'] = number - 1

    # --- 3. Word count filters ---
    if "single word" in q_lower or "one word" in q_lower:
        query = query.filter(models.StringModel.word_count == 1)
        parsed_filters['word_count'] = 1
    elif "word count" in q_lower and number is not None:
        query = query.filter(models.StringModel.word_count == number)
        parsed_filters['word_count'] = number

    # --- 4. Palindrome filter ---
    if "palindrome" in q_lower or "palindromic" in q_lower:
        query = query.filter(models.StringModel.is_palindrome == True)
        parsed_filters['is_palindrome'] = True

    # --- 5. Contains character filter (letters, first vowel heuristic) ---
    vowels = "aeiou"
    contains_match = re.search(r'contain(?:s|ing)? (?:the letter )?([a-z])', q_lower)
    first_vowel_match = re.search(r'first vowel', q_lower)

    if contains_match:
        char = contains_match.group(1)
        query = query.filter(models.StringModel.value.contains(char))
        parsed_filters['contains_character'] = char
    elif first_vowel_match:
        # Heuristic: assume 'a' is the first vowel
        query = query.filter(models.StringModel.value.op('regexp')('^[^aeiou]*[aeiou]'))
        parsed_filters['contains_character'] = 'a'

    # --- 6. Special filters: longest, shortest, most unique ---
    if any(word in q_lower for word in ["longest", "shortest", "unique"]):
        if "longest" in q_lower:
            max_len = db.query(func.max(models.StringModel.length)).scalar()
            if max_len:
                query = query.filter(models.StringModel.length == max_len)
                parsed_filters['special_filter'] = 'longest'
        elif "shortest" in q_lower:
            min_len = db.query(func.min(models.StringModel.length)).scalar()
            if min_len:
                query = query.filter(models.StringModel.length == min_len)
                parsed_filters['special_filter'] = 'shortest'
        elif "unique" in q_lower:
            max_unique = db.query(func.max(models.StringModel.unique_characters)).scalar()
            if max_unique:
                query = query.filter(models.StringModel.unique_characters == max_unique)
                parsed_filters['special_filter'] = 'most_unique'

    # --- 7. Final validation ---
    if not parsed_filters:
        raise HTTPException(
            status_code=400,
            detail="Unable to parse natural language query. Please use clear keywords like 'palindrome', 'longest', 'word count', 'longer than', or 'contain'."
        )

    results = query.all()
    if not results:
        raise HTTPException(
            status_code=404,
            detail="Query parsed successfully, but no matching strings were found."
        )

    formatted_results = [_format_response(obj) for obj in results]

    return {
        "data": formatted_results,
        "count": len(formatted_results),
        "interpreted_query": {
            "original": original_query,
            "parsed_filters": {k: v for k, v in parsed_filters.items() if k != 'special_filter'}
        }
    }

@app.get("/strings/{value}")
def get_string(value: str, db: Session = Depends(get_db)):
    hash_id = sha256(value.encode()).hexdigest() 
    obj = db.query(models.StringModel).filter(models.StringModel.id == hash_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="String not found")
    
    # Format the response to match the nested JSON spec
    return _format_response(obj)

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
        # Use value.contains for substring search
        query = query.filter(models.StringModel.value.contains(contains_character))

    results = query.all()
    
    # Format results to match the required nested response structure
    formatted_results = [_format_response(obj) for obj in results]

    filters_applied = {
        "is_palindrome": is_palindrome,
        "min_length": min_length,
        "max_length": max_length,
        "word_count": word_count,
        "contains_character": contains_character,
    }

    return {
        "data": formatted_results,
        "count": len(formatted_results),
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
    # FastAPI automatically handles 204 No Content for a successful empty response
    return
