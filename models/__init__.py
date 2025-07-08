from .user import User
#from .folder import Folder
from .feedback import Feedback
from .workspace import Workspace
from .collaborators import Collaborator
from .developer import Developer
from .feedback_developer import FeedbackDeveloper  
from .otp import OTP_Tbl
# Add other model files here as needed


from sqlalchemy.orm import declarative_base
Base = declarative_base()

