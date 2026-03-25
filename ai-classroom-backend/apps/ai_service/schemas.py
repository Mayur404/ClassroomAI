from pydantic import BaseModel, ConfigDict, Field


class StructuredModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ScheduleClassItem(StructuredModel):
    class_number: int
    topic: str
    subtopics: list[str] = Field(default_factory=list)
    learning_objectives: list[str] = Field(default_factory=list)
    duration_minutes: int = 60


class ScheduleResponse(StructuredModel):
    classes: list[ScheduleClassItem] = Field(default_factory=list)


class QuestionRubricEntry(StructuredModel):
    question_number: int
    criteria: list[str] = Field(default_factory=list)


class AssignmentAnswerKeyEntry(StructuredModel):
    correct_option: str = ""
    explanation: str = ""


class AssignmentQuestionItem(StructuredModel):
    question_number: int
    prompt: str
    marks: int
    options: list[str] = Field(default_factory=list)
    rubric: list[str] = Field(default_factory=list)
    topic: str | None = None


class AssignmentResponse(StructuredModel):
    title: str
    description: str = ""
    type: str
    total_marks: int = 0
    questions: list[AssignmentQuestionItem] = Field(default_factory=list)
    rubric: list[QuestionRubricEntry] = Field(default_factory=list)
    answer_key: dict[str, AssignmentAnswerKeyEntry | str] = Field(default_factory=dict)


class GradingBreakdownItem(StructuredModel):
    question_number: int
    score: float
    max_score: float
    feedback: str
    student_answer: str = ""


class GradingResponse(StructuredModel):
    total_score: float = 0
    score_breakdown: list[GradingBreakdownItem] = Field(default_factory=list)
    overall_feedback: str = ""
