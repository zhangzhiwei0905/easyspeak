"""Import all models so SQLAlchemy relationship strings resolve correctly."""
from app.models.daily import DailyContent
from app.models.phrase import Phrase
from app.models.word import Word
from app.models.user import User, UserProgress, UserAchievement
from app.models.quiz import QuizRecord
from app.models.learn_session import LearnSession
from app.models.review_log import ReviewLog
