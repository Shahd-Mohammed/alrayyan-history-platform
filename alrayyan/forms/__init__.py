from alrayyan.forms.assessment import (
    QuestionForm,
    WorksheetSettingsForm,
)

from alrayyan.forms.auth import (
    AccountSettingsForm,
    LoginForm,
)

from alrayyan.forms.worksheet import (
    EditWorksheetForm,
    UploadWorksheetForm,
)

from alrayyan.forms.site_content import (
    AboutPageForm,
)
from alrayyan.forms.platform import (
    ClassroomForm,
    ConceptMapForm,
    ConceptMapUploadForm,
    CurriculumUploadForm,
    HistoricalCharacterForm,
    InvitationForm,
    InvitationRegistrationForm,
    LearningResourceForm,
    PlatformSettingsForm,
)


__all__ = [
    "LoginForm",
    "AccountSettingsForm",
    "EditWorksheetForm",
    "UploadWorksheetForm",
    "QuestionForm",
    "WorksheetSettingsForm",
    "AboutPageForm",
    "CurriculumUploadForm",
    "ClassroomForm",
    "InvitationForm",
    "InvitationRegistrationForm",
    "PlatformSettingsForm",
    "LearningResourceForm",
    "ConceptMapForm",
    "ConceptMapUploadForm",
    "HistoricalCharacterForm",
]
