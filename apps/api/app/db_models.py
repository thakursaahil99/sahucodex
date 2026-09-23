"""Imports every ORM model so `Base.metadata` is complete (Alembic and tests rely on this).

Add each new module's models here when it is created.
"""

from app.modules.ai.models import AiConversation, AiMessage, AiUsage  # noqa: F401
from app.modules.audit.models import AuditLog  # noqa: F401
from app.modules.auth.models import OneTimeToken, RefreshToken  # noqa: F401
from app.modules.community.models import (  # noqa: F401
    Discussion,
    DiscussionComment,
    DiscussionVote,
    Notification,
    Report,
)
from app.modules.contests.models import Contest, ContestParticipant, ContestProblem  # noqa: F401
from app.modules.problems.models import (  # noqa: F401
    Problem,
    ProblemExample,
    ProblemStarterCode,
    ProblemTag,
    ProblemTestCase,
    ProgrammingLanguage,
    Tag,
    UserProblemProgress,
)
from app.modules.profiles.models import Achievement, UserAchievement, UserStreak  # noqa: F401
from app.modules.submissions.models import Submission, SubmissionResult, SubmissionTestResult  # noqa: F401
from app.modules.users.models import Role, User, UserProfile, UserRole  # noqa: F401
