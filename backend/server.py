from fastapi import FastAPI, APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime, timedelta
import jwt
import bcrypt
import re
from enum import Enum

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# JWT Configuration
JWT_SECRET = "mindvault_secret_key_2025"  # In production, use environment variable
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# Create the main app without a prefix
app = FastAPI(title="MindVault API", description="Secure thought journal and idea incubator")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Security
security = HTTPBearer()

# Enums
class PriorityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class ViewMode(str, Enum):
    TIMELINE = "timeline"
    TAG = "tag"
    GRID = "grid"

# Models
class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str
    username: str
    hashed_password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_active: datetime = Field(default_factory=datetime.utcnow)
    is_admin: bool = False

class UserCreate(BaseModel):
    email: str
    username: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    created_at: datetime
    last_active: datetime
    is_admin: bool

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

class Idea(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    title: str
    content: str
    tags: List[str] = []
    priority: PriorityLevel = PriorityLevel.MEDIUM
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_favorite: bool = False
    category: Optional[str] = None

class IdeaCreate(BaseModel):
    title: str
    content: str
    tags: List[str] = []
    priority: PriorityLevel = PriorityLevel.MEDIUM
    category: Optional[str] = None

class IdeaUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[List[str]] = None
    priority: Optional[PriorityLevel] = None
    is_favorite: Optional[bool] = None
    category: Optional[str] = None

class IdeaCombine(BaseModel):
    idea1_id: str
    idea2_id: str
    new_title: Optional[str] = None

class SmartSuggestion(BaseModel):
    type: str  # "category", "tag", "priority"
    suggestions: List[str]
    confidence: float

# Helper Functions
def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    
    user = await db.users.find_one({"id": user_id})
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    
    # Update last active
    await db.users.update_one({"id": user_id}, {"$set": {"last_active": datetime.utcnow()}})
    
    return User(**user)

def generate_smart_suggestions(content: str, existing_tags: List[str] = []) -> SmartSuggestion:
    """Generate local smart suggestions based on content analysis"""
    words = re.findall(r'\b\w+\b', content.lower())
    word_freq = {}
    for word in words:
        if len(word) > 3:  # Only consider words longer than 3 characters
            word_freq[word] = word_freq.get(word, 0) + 1
    
    # Suggest tags based on frequent words
    suggested_tags = []
    for word, freq in sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:5]:
        if word not in existing_tags and word not in ['idea', 'think', 'maybe', 'could', 'would', 'should']:
            suggested_tags.append(word)
    
    return SmartSuggestion(
        type="tag",
        suggestions=suggested_tags[:3],
        confidence=0.7
    )

def categorize_idea(content: str, title: str) -> str:
    """Categorize idea based on content analysis"""
    combined_text = (title + " " + content).lower()
    
    categories = {
        "invention": ["invent", "create", "build", "make", "device", "tool", "machine", "technology"],
        "story": ["character", "plot", "story", "write", "book", "novel", "chapter", "scene"],
        "product": ["sell", "market", "business", "customer", "profit", "service", "app", "platform"],
        "research": ["study", "analyze", "investigate", "research", "experiment", "test", "data"],
        "creative": ["art", "design", "color", "creative", "artistic", "visual", "music", "paint"],
        "personal": ["life", "goal", "habit", "improve", "learn", "grow", "change", "development"]
    }
    
    scores = {}
    for category, keywords in categories.items():
        score = sum(1 for keyword in keywords if keyword in combined_text)
        if score > 0:
            scores[category] = score
    
    if scores:
        return max(scores, key=scores.get)
    return "general"

# Authentication Routes
@api_router.post("/auth/register", response_model=Token)
async def register(user_data: UserCreate):
    # Check if user already exists
    existing_user = await db.users.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    existing_username = await db.users.find_one({"username": user_data.username})
    if existing_username:
        raise HTTPException(status_code=400, detail="Username already taken")
    
    # Create new user
    hashed_password = hash_password(user_data.password)
    user = User(
        email=user_data.email,
        username=user_data.username,
        hashed_password=hashed_password
    )
    
    await db.users.insert_one(user.dict())
    
    # Create access token
    access_token = create_access_token(data={"sub": user.id})
    
    user_response = UserResponse(**user.dict())
    return Token(access_token=access_token, token_type="bearer", user=user_response)

@api_router.post("/auth/login", response_model=Token)
async def login(user_data: UserLogin):
    user = await db.users.find_one({"email": user_data.email})
    if not user or not verify_password(user_data.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Update last active
    await db.users.update_one({"id": user["id"]}, {"$set": {"last_active": datetime.utcnow()}})
    
    # Create access token
    access_token = create_access_token(data={"sub": user["id"]})
    
    user_obj = User(**user)
    user_response = UserResponse(**user_obj.dict())
    return Token(access_token=access_token, token_type="bearer", user=user_response)

@api_router.get("/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    return UserResponse(**current_user.dict())

# Idea Routes
@api_router.post("/ideas", response_model=Idea)
async def create_idea(idea_data: IdeaCreate, current_user: User = Depends(get_current_user)):
    # Auto-categorize if not provided
    category = idea_data.category or categorize_idea(idea_data.content, idea_data.title)
    
    idea = Idea(
        user_id=current_user.id,
        title=idea_data.title,
        content=idea_data.content,
        tags=idea_data.tags,
        priority=idea_data.priority,
        category=category
    )
    
    await db.ideas.insert_one(idea.dict())
    return idea

@api_router.get("/ideas", response_model=List[Idea])
async def get_ideas(
    current_user: User = Depends(get_current_user),
    tag: Optional[str] = None,
    category: Optional[str] = None,
    priority: Optional[PriorityLevel] = None,
    view_mode: ViewMode = ViewMode.TIMELINE
):
    query = {"user_id": current_user.id}
    
    if tag:
        query["tags"] = {"$in": [tag]}
    if category:
        query["category"] = category
    if priority:
        query["priority"] = priority
    
    # Sort based on view mode
    sort_field = "created_at" if view_mode == ViewMode.TIMELINE else "updated_at"
    ideas = await db.ideas.find(query).sort(sort_field, -1).to_list(1000)
    
    return [Idea(**idea) for idea in ideas]

@api_router.get("/ideas/{idea_id}", response_model=Idea)
async def get_idea(idea_id: str, current_user: User = Depends(get_current_user)):
    idea = await db.ideas.find_one({"id": idea_id, "user_id": current_user.id})
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")
    return Idea(**idea)

@api_router.put("/ideas/{idea_id}", response_model=Idea)
async def update_idea(
    idea_id: str, 
    idea_data: IdeaUpdate, 
    current_user: User = Depends(get_current_user)
):
    existing_idea = await db.ideas.find_one({"id": idea_id, "user_id": current_user.id})
    if not existing_idea:
        raise HTTPException(status_code=404, detail="Idea not found")
    
    update_data = {k: v for k, v in idea_data.dict().items() if v is not None}
    update_data["updated_at"] = datetime.utcnow()
    
    await db.ideas.update_one({"id": idea_id}, {"$set": update_data})
    
    updated_idea = await db.ideas.find_one({"id": idea_id})
    return Idea(**updated_idea)

@api_router.delete("/ideas/{idea_id}")
async def delete_idea(idea_id: str, current_user: User = Depends(get_current_user)):
    result = await db.ideas.delete_one({"id": idea_id, "user_id": current_user.id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Idea not found")
    return {"message": "Idea deleted successfully"}

# Smart Features Routes
@api_router.post("/ideas/{idea_id}/suggestions", response_model=SmartSuggestion)
async def get_smart_suggestions(idea_id: str, current_user: User = Depends(get_current_user)):
    idea = await db.ideas.find_one({"id": idea_id, "user_id": current_user.id})
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")
    
    suggestions = generate_smart_suggestions(idea["content"], idea["tags"])
    return suggestions

@api_router.post("/ideas/combine", response_model=Idea)
async def combine_ideas(combine_data: IdeaCombine, current_user: User = Depends(get_current_user)):
    # Get both ideas
    idea1 = await db.ideas.find_one({"id": combine_data.idea1_id, "user_id": current_user.id})
    idea2 = await db.ideas.find_one({"id": combine_data.idea2_id, "user_id": current_user.id})
    
    if not idea1 or not idea2:
        raise HTTPException(status_code=404, detail="One or both ideas not found")
    
    # Combine ideas
    combined_title = combine_data.new_title or f"{idea1['title']} + {idea2['title']}"
    combined_content = f"**Fusion of Ideas:**\n\n**Idea 1: {idea1['title']}**\n{idea1['content']}\n\n**Idea 2: {idea2['title']}**\n{idea2['content']}\n\n**Combined Insight:**\nThis fusion combines elements from both ideas to create a new perspective."
    combined_tags = list(set(idea1['tags'] + idea2['tags']))
    
    # Determine priority (take highest)
    priority_order = {"low": 0, "medium": 1, "high": 2}
    combined_priority = "high" if max(priority_order[idea1['priority']], priority_order[idea2['priority']]) == 2 else ("medium" if max(priority_order[idea1['priority']], priority_order[idea2['priority']]) == 1 else "low")
    
    combined_idea = Idea(
        user_id=current_user.id,
        title=combined_title,
        content=combined_content,
        tags=combined_tags,
        priority=PriorityLevel(combined_priority),
        category="fusion"
    )
    
    await db.ideas.insert_one(combined_idea.dict())
    return combined_idea

# Analytics Routes
@api_router.get("/analytics/dashboard")
async def get_dashboard_stats(current_user: User = Depends(get_current_user)):
    total_ideas = await db.ideas.count_documents({"user_id": current_user.id})
    
    # Get ideas by priority
    high_priority = await db.ideas.count_documents({"user_id": current_user.id, "priority": "high"})
    medium_priority = await db.ideas.count_documents({"user_id": current_user.id, "priority": "medium"})
    low_priority = await db.ideas.count_documents({"user_id": current_user.id, "priority": "low"})
    
    # Get ideas by category
    categories = await db.ideas.distinct("category", {"user_id": current_user.id})
    category_counts = {}
    for category in categories:
        count = await db.ideas.count_documents({"user_id": current_user.id, "category": category})
        category_counts[category] = count
    
    # Get recent activity (last 7 days)
    week_ago = datetime.utcnow() - timedelta(days=7)
    recent_ideas = await db.ideas.count_documents({
        "user_id": current_user.id, 
        "created_at": {"$gte": week_ago}
    })
    
    return {
        "total_ideas": total_ideas,
        "priority_breakdown": {
            "high": high_priority,
            "medium": medium_priority,
            "low": low_priority
        },
        "category_breakdown": category_counts,
        "recent_activity": recent_ideas,
        "favorite_count": await db.ideas.count_documents({"user_id": current_user.id, "is_favorite": True})
    }

# Admin Routes (if user is admin)
@api_router.get("/admin/users")
async def get_all_users(current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    users = await db.users.find({}, {"hashed_password": 0}).to_list(1000)
    for user in users:
        user["idea_count"] = await db.ideas.count_documents({"user_id": user["id"]})
    
    return users

@api_router.get("/admin/export/{user_id}")
async def export_user_data(user_id: str, current_user: User = Depends(get_current_user)):
    if not current_user.is_admin and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    user = await db.users.find_one({"id": user_id}, {"hashed_password": 0})
    ideas = await db.ideas.find({"user_id": user_id}).to_list(1000)
    
    export_data = {
        "user": user,
        "ideas": ideas,
        "export_date": datetime.utcnow(),
        "total_ideas": len(ideas)
    }
    
    return export_data

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

# Root endpoint for health check
@app.get("/")
async def root():
    return {"message": "MindVault API is running", "version": "1.0.0"}