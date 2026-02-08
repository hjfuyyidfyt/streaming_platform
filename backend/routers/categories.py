from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
from ..database import get_session
from ..models import Category, CategoryPublic, CategoryBase
import re

router = APIRouter(
    prefix="/categories",
    tags=["categories"]
)

@router.post("/", response_model=CategoryPublic)
async def create_category(
    category: CategoryBase,
    session: Session = Depends(get_session)
):
    # Normalize slug
    if not category.slug:
        category.slug = re.sub(r'[^a-zA-Z0-9]', '-', category.name.lower())
    
    # Check existing
    existing = session.exec(select(Category).where(Category.slug == category.slug)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Category with this slug already exists")
    
    db_category = Category.from_orm(category)
    session.add(db_category)
    session.commit()
    session.refresh(db_category)
    return db_category

@router.delete("/{category_id}")
async def delete_category(
    category_id: int,
    session: Session = Depends(get_session)
):
    category = session.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
        
    session.delete(category)
    session.commit()
    return {"ok": True}

@router.put("/{category_id}", response_model=CategoryPublic)
async def update_category(
    category_id: int,
    category_update: CategoryBase,
    session: Session = Depends(get_session)
):
    db_category = session.get(Category, category_id)
    if not db_category:
        raise HTTPException(status_code=404, detail="Category not found")
        
    category_data = category_update.dict(exclude_unset=True)
    for key, value in category_data.items():
        setattr(db_category, key, value)
        
    session.add(db_category)
    session.commit()
    session.refresh(db_category)
    return db_category
